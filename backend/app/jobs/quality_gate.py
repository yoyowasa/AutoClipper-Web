from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.candidates.short_diversity import (
    ShortDiversitySettings,
    select_diverse_shorts,
)
from app.jobs.subtitle_review import SubtitleReviewDocument
from app.jobs.title_hook_suggestions import TitleHookSuggestionsDocument
from app.overlay_text import fit_overlay_text
from app.posting_metadata import (
    build_post_metadata_revision_hash,
    ensure_publication_title_suffix,
)
from app.render.render_short import SHORT_BANNER_HEIGHT
from app.render.subtitles_ass import (
    SubtitleEvent,
    SubtitleLayout,
    split_subtitle_lines,
    subtitle_events_for_candidate_output,
)
from app.video.probe import VideoMetadata, probe_metadata


QualityGateStage = Literal["selection", "content", "post_render"]
QualityGateMode = Literal["shadow", "guarded", "auto"]
QualityGateOutcome = Literal["pass", "fail", "unknown"]
QualityGateRoute = Literal[
    "observe",
    "continue",
    "clip_review",
    "subtitle_review",
    "failed",
]

QUALITY_GATE_SCHEMA_VERSION = 1
QUALITY_GATE_PRODUCER_VERSION = "guarded_quality_gate_v1"
QUALITY_GATE_DIRNAME = "quality_gate"


class QualityGateCheck(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    version: Literal[1] = 1
    hard: Literal[True] = True
    outcome: QualityGateOutcome
    reason_code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        alias="reasonCode",
    )
    evidence: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def validate_reason(self) -> "QualityGateCheck":
        if self.outcome == "pass" and self.reason_code is not None:
            raise ValueError("passing checks must not have reasonCode")
        if self.outcome != "pass" and self.reason_code is None:
            raise ValueError("non-passing checks require reasonCode")
        return self


class QualityGateDecision(BaseModel):
    schema_version: Literal[1] = Field(
        default=QUALITY_GATE_SCHEMA_VERSION,
        alias="schemaVersion",
    )
    producer_version: Literal[QUALITY_GATE_PRODUCER_VERSION] = Field(
        default=QUALITY_GATE_PRODUCER_VERSION,
        alias="producerVersion",
    )
    job_id: str = Field(min_length=1, max_length=128, alias="jobId")
    mode: QualityGateMode = "guarded"
    enforced: bool = True
    stage: QualityGateStage
    input_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        alias="inputHash",
    )
    outcome: QualityGateOutcome
    route: QualityGateRoute
    checks: list[QualityGateCheck] = Field(min_length=1)
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def validate_aggregate(self) -> "QualityGateDecision":
        if self.enforced is not (self.mode in {"guarded", "auto"}):
            raise ValueError("enforced must match the automation mode")
        expected_outcome = aggregate_quality_gate_outcomes(
            [check.outcome for check in self.checks]
        )
        if self.outcome != expected_outcome:
            raise ValueError("outcome must match the hard-check aggregate")
        expected_route = quality_gate_route(self.stage, self.outcome, mode=self.mode)
        if self.route != expected_route:
            raise ValueError("route must match stage and outcome")
        return self


def aggregate_quality_gate_outcomes(
    outcomes: Sequence[QualityGateOutcome],
) -> QualityGateOutcome:
    if not outcomes:
        raise ValueError("at least one hard-check outcome is required")
    if "fail" in outcomes:
        return "fail"
    if "unknown" in outcomes:
        return "unknown"
    return "pass"


def quality_gate_route(
    stage: QualityGateStage,
    outcome: QualityGateOutcome,
    *,
    mode: QualityGateMode = "guarded",
) -> QualityGateRoute:
    if mode == "shadow":
        return "observe"
    if outcome == "pass":
        return "continue"
    if stage == "selection":
        return "clip_review"
    if stage == "content" or (stage == "post_render" and mode == "auto"):
        return "subtitle_review"
    return "failed"


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(by_alias=True, mode="json"))
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_canonical_value(item) for item in value]
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("quality-gate hash input must contain finite numbers")
        return value
    raise TypeError(
        f"unsupported quality-gate hash input type: {type(value).__name__}"
    )


def quality_gate_input_hash(
    stage: QualityGateStage,
    payload: Any,
) -> str:
    encoded = json.dumps(
        {
            "schemaVersion": QUALITY_GATE_SCHEMA_VERSION,
            "stage": stage,
            "input": _canonical_value(payload),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def quality_gate_decision_path(
    output_dir: str | Path,
    stage: QualityGateStage,
) -> Path:
    return Path(output_dir) / QUALITY_GATE_DIRNAME / f"{stage}.json"


def invalidate_quality_gate_decisions(
    output_dir: str | Path,
    stages: Sequence[QualityGateStage],
) -> bool:
    removed_all = True
    for stage in stages:
        try:
            quality_gate_decision_path(output_dir, stage).unlink(missing_ok=True)
        except OSError:
            removed_all = False
    return removed_all


def write_quality_gate_decision(
    document: QualityGateDecision,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(
                document.model_dump(by_alias=True, mode="json"),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def load_quality_gate_decision(
    input_path: str | Path,
) -> QualityGateDecision:
    return QualityGateDecision.model_validate_json(
        Path(input_path).read_text(encoding="utf-8")
    )


def _check(
    code: str,
    outcome: QualityGateOutcome,
    *,
    reason_code: str | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> QualityGateCheck:
    return QualityGateCheck(
        code=code,
        outcome=outcome,
        reasonCode=reason_code,
        evidence=dict(evidence or {}),
    )


def _decision(
    *,
    job_id: str,
    stage: QualityGateStage,
    payload: Any,
    checks: Sequence[QualityGateCheck],
    mode: QualityGateMode = "guarded",
) -> QualityGateDecision:
    outcomes = [check.outcome for check in checks]
    outcome = aggregate_quality_gate_outcomes(outcomes)
    return QualityGateDecision(
        jobId=job_id,
        mode=mode,
        enforced=mode in {"guarded", "auto"},
        stage=stage,
        inputHash=quality_gate_input_hash(stage, payload),
        outcome=outcome,
        route=quality_gate_route(stage, outcome, mode=mode),
        checks=list(checks),
        createdAt=datetime.now(UTC),
    )


def unknown_quality_gate_decision(
    *,
    job_id: str,
    stage: QualityGateStage,
    reason_code: str,
    evidence: Mapping[str, Any] | None = None,
    mode: QualityGateMode = "guarded",
) -> QualityGateDecision:
    """Record an evaluator failure without allowing guarded automation to continue."""
    return _decision(
        job_id=job_id,
        stage=stage,
        payload={
            "reasonCode": reason_code,
            "evidence": dict(evidence or {}),
        },
        checks=[
            _check(
                f"{stage}.evaluation_available",
                "unknown",
                reason_code=reason_code,
                evidence=evidence,
            )
        ],
        mode=mode,
    )


def _requested_count(settings: Mapping[str, Any], key: str, fallback: int) -> int:
    value = settings.get(key, fallback)
    if isinstance(value, bool):
        return fallback
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def _duration_bounds(
    settings: Mapping[str, Any],
    candidate: Candidate,
) -> tuple[float, float]:
    if candidate.type == "short":
        return (
            float(settings.get("shortMinDuration", 20.0)),
            float(settings.get("shortMaxDuration", 75.0)),
        )
    return (
        float(settings.get("normalMinDuration", 90.0)),
        float(settings.get("normalMaxDuration", 600.0)),
    )


def _segment_overlaps_candidate(
    segment: TranscriptSegment,
    candidate: Candidate,
) -> bool:
    if segment.clip_id is not None and segment.clip_id != candidate.id:
        return False
    return segment.end > candidate.start and segment.start < candidate.end


def evaluate_selection_quality_gate(
    *,
    job_id: str,
    selection: CandidateSelection,
    transcript_segments: Sequence[TranscriptSegment],
    settings: Mapping[str, Any],
    source_duration: float,
    mode: QualityGateMode = "guarded",
) -> QualityGateDecision:
    clips = [*selection.normal_clips, *selection.shorts]
    relevant_settings = {
        key: settings.get(key)
        for key in (
            "normalClipCount",
            "shortCount",
            "normalMinDuration",
            "normalMaxDuration",
            "shortMinDuration",
            "shortMaxDuration",
            "heatmapIntervalMode",
        )
    }
    payload = {
        "selection": selection,
        "transcript": list(transcript_segments),
        "settings": relevant_settings,
        "sourceDuration": source_duration,
    }
    checks: list[QualityGateCheck] = []

    invalid_ranges: list[str] = []
    for candidate in clips:
        try:
            minimum, maximum = _duration_bounds(settings, candidate)
        except (TypeError, ValueError):
            invalid_ranges.append(candidate.id)
            continue
        if (
            candidate.start < 0
            or candidate.end <= candidate.start
            or candidate.end > source_duration + 0.001
            or abs(candidate.duration - (candidate.end - candidate.start)) > 0.001
            or candidate.duration < minimum - 0.001
            or candidate.duration > maximum + 0.001
        ):
            invalid_ranges.append(candidate.id)
    checks.append(
        _check(
            "selection.range_duration",
            "fail" if invalid_ranges else "pass",
            reason_code=("invalid_clip_range_or_duration" if invalid_ranges else None),
            evidence={"invalidClipIds": invalid_ranges, "sourceDuration": source_duration},
        )
    )

    missing_titles = [candidate.id for candidate in clips if not (candidate.title or "").strip()]
    checks.append(
        _check(
            "selection.title_present",
            "fail" if missing_titles else "pass",
            reason_code="missing_title" if missing_titles else None,
            evidence={"missingClipIds": missing_titles},
        )
    )

    uncovered: list[str] = []
    for candidate in clips:
        overlapping = [
            segment
            for segment in transcript_segments
            if _segment_overlaps_candidate(segment, candidate)
            and segment.text.strip()
        ]
        if not candidate.transcript_text.strip() or not overlapping:
            uncovered.append(candidate.id)
    checks.append(
        _check(
            "selection.transcript_coverage",
            "fail" if uncovered else "pass",
            reason_code="missing_transcript_coverage" if uncovered else None,
            evidence={"uncoveredClipIds": uncovered},
        )
    )

    requested_normal = _requested_count(
        settings,
        "normalClipCount",
        selection.requested_normal_count,
    )
    requested_short = _requested_count(
        settings,
        "shortCount",
        selection.requested_short_count,
    )
    shortfall = {
        "normal": max(0, requested_normal - len(selection.normal_clips)),
        "short": max(0, requested_short - len(selection.shorts)),
    }
    has_shortfall = any(shortfall.values())
    checks.append(
        _check(
            "selection.requested_counts",
            "fail" if has_shortfall else "pass",
            reason_code="requested_clip_shortfall" if has_shortfall else None,
            evidence={
                "requested": {"normal": requested_normal, "short": requested_short},
                "selected": {
                    "normal": len(selection.normal_clips),
                    "short": len(selection.shorts),
                },
                "shortfall": shortfall,
            },
        )
    )

    rejected_hard_gate = [
        candidate.id for candidate in clips if candidate.hard_gate_passed is False
    ]
    unknown_hard_gate = [
        candidate.id for candidate in clips if candidate.hard_gate_passed is None
    ]
    hard_gate_outcome: QualityGateOutcome = (
        "fail"
        if rejected_hard_gate
        else "unknown"
        if unknown_hard_gate
        else "pass"
    )
    checks.append(
        _check(
            "selection.candidate_hard_gate",
            hard_gate_outcome,
            reason_code=(
                "candidate_hard_gate_failed"
                if rejected_hard_gate
                else "candidate_hard_gate_not_recorded"
                if unknown_hard_gate
                else None
            ),
            evidence={
                "failedClipIds": rejected_hard_gate,
                "unknownClipIds": unknown_hard_gate,
            },
        )
    )

    risk_flags = {
        candidate.id: list(candidate.risk_flags)
        for candidate in clips
        if candidate.risk_flags
    }
    checks.append(
        _check(
            "selection.risk_flags",
            "unknown" if risk_flags else "pass",
            reason_code="unresolved_candidate_risk_flags" if risk_flags else None,
            evidence={"flagsByClipId": risk_flags},
        )
    )

    diversity = select_diverse_shorts(
        selection.shorts,
        requested_count=len(selection.shorts),
        settings=ShortDiversitySettings(enforce_heatmap_segment_uniqueness=False),
    )
    duplicate_evidence = [
        {
            "clipId": rejection.candidate_id,
            "duplicateOf": rejection.duplicate_of,
            "reasons": list(rejection.reasons),
        }
        for rejection in diversity.rejected
    ]
    checks.append(
        _check(
            "selection.short_diversity",
            "fail" if duplicate_evidence else "pass",
            reason_code="duplicate_short_moment" if duplicate_evidence else None,
            evidence={"duplicates": duplicate_evidence},
        )
    )

    return _decision(
        job_id=job_id,
        stage="selection",
        payload=payload,
        checks=checks,
        mode=mode,
    )


def _content_structure_check(
    document: SubtitleReviewDocument,
) -> QualityGateCheck:
    segment_by_id = {segment.id: segment for segment in document.segments}
    problems: list[dict[str, str]] = []
    if not document.clips:
        problems.append({"clipId": "", "reason": "no_clips"})
    if len(segment_by_id) != len(document.segments):
        problems.append({"clipId": "", "reason": "duplicate_segment_id"})

    for clip in document.clips:
        if clip.end <= clip.start or abs(clip.duration - (clip.end - clip.start)) > 0.001:
            problems.append({"clipId": clip.id, "reason": "invalid_clip_range"})
        if not clip.segment_ids:
            problems.append({"clipId": clip.id, "reason": "no_subtitle_segments"})
        previous_start: float | None = None
        for segment_id in clip.segment_ids:
            segment = segment_by_id.get(segment_id)
            if segment is None:
                problems.append({"clipId": clip.id, "reason": "missing_segment"})
                continue
            if segment.end <= segment.start:
                problems.append({"clipId": clip.id, "reason": "invalid_segment_range"})
            if not segment.text.strip():
                problems.append({"clipId": clip.id, "reason": "empty_subtitle_text"})
            if previous_start is not None and segment.start < previous_start:
                problems.append({"clipId": clip.id, "reason": "unordered_segments"})
            previous_start = segment.start
            if segment.end <= clip.start or segment.start >= clip.end:
                problems.append({"clipId": clip.id, "reason": "segment_outside_clip"})
            if clip.id not in segment.affected_clip_ids:
                problems.append({"clipId": clip.id, "reason": "segment_clip_link_missing"})

    return _check(
        "content.subtitle_structure",
        "fail" if problems else "pass",
        reason_code="invalid_subtitle_structure" if problems else None,
        evidence={"problems": problems},
    )


def _preview_check(document: SubtitleReviewDocument) -> QualityGateCheck:
    failed = [clip.id for clip in document.clips if clip.preview_state == "failed"]
    incomplete = [
        clip.id
        for clip in document.clips
        if clip.preview_state != "ready"
        or not clip.preview_spec_hash
        or not clip.preview_video_url
        or not clip.live_preview_spec_hash
        or not clip.live_preview_video_url
    ]
    if failed:
        outcome: QualityGateOutcome = "fail"
        reason_code = "preview_render_failed"
    elif incomplete:
        outcome = "unknown"
        reason_code = "preview_not_ready_or_unverifiable"
    else:
        outcome = "pass"
        reason_code = None
    return _check(
        "content.preview_ready",
        outcome,
        reason_code=reason_code,
        evidence={"failedClipIds": failed, "incompleteClipIds": incomplete},
    )


def _human_review_confirmation(
    clips: Sequence[Any],
    *,
    scope: str,
    applicable: bool = True,
) -> tuple[bool, dict[str, Any]]:
    scoped_clips = list(clips)
    current_preview_ready_clip_ids = [
        clip.id
        for clip in scoped_clips
        if clip.preview_state == "ready"
        and clip.preview_spec_hash
        and clip.preview_video_url
    ]
    confirmed_clip_ids = [clip.id for clip in scoped_clips if clip.confirmed]
    accepted_ready_clip_ids = [
        clip.id
        for clip in scoped_clips
        if clip.confirmed
        and clip.preview_state == "ready"
        and clip.preview_spec_hash
        and clip.preview_video_url
    ]
    accepted = bool(scoped_clips) and len(accepted_ready_clip_ids) == len(scoped_clips)
    evidence = {
        "provider": "human_review_confirmation",
        "scope": scope,
        "applicable": applicable,
        "clipCount": len(scoped_clips),
        "currentPreviewReadyClipIds": current_preview_ready_clip_ids,
        "confirmedClipIds": confirmed_clip_ids,
        "acceptedReadyClipIds": accepted_ready_clip_ids,
        "previewSpecHashes": {
            clip.id: clip.preview_spec_hash for clip in scoped_clips
        },
        "incompleteClipIds": [
            clip.id for clip in scoped_clips if clip.id not in accepted_ready_clip_ids
        ],
    }
    return accepted, evidence


ASR_MIN_CONFIDENCE_MEAN = 0.68
ASR_MIN_CONFIDENCE_P10 = 0.50
ASR_MAX_REPEATED_TEXT_RATIO = 0.60


def _clip_segments(document: SubtitleReviewDocument, clip: Any) -> list[Any]:
    segment_by_id = {segment.id: segment for segment in document.segments}
    return [
        segment_by_id[segment_id]
        for segment_id in clip.segment_ids
        if segment_id in segment_by_id
    ]


def _current_post_metadata_revision(
    document: SubtitleReviewDocument,
    clip: Any,
) -> str:
    segments = sorted(_clip_segments(document, clip), key=lambda item: item.index)
    return build_post_metadata_revision_hash(
        clip_id=clip.id,
        clip_type=clip.type,
        start=clip.start,
        end=clip.end,
        segments=[
            {
                "segmentId": segment.id,
                "start": round(min(clip.duration, max(0.0, segment.start - clip.start)), 3),
                "end": round(min(clip.duration, max(0.0, segment.end - clip.start)), 3),
                "text": segment.text,
            }
            for segment in segments
        ],
    )


def _automated_title_hook_check(
    document: SubtitleReviewDocument,
    artifacts: Mapping[str, TitleHookSuggestionsDocument] | None,
    *,
    human_accepted_clip_ids: set[str],
    human_evidence: Mapping[str, Any],
) -> QualityGateCheck:
    missing: list[str] = []
    stale: list[str] = []
    inconsistent: list[dict[str, str]] = []
    evidence_by_clip: dict[str, Any] = {}
    artifact_map = dict(artifacts or {})
    for clip in document.clips:
        if clip.id in human_accepted_clip_ids:
            evidence_by_clip[clip.id] = {
                "provider": "human_review_confirmation",
                "previewSpecHash": clip.preview_spec_hash,
            }
            continue
        artifact = artifact_map.get(clip.id)
        if artifact is None or artifact.state != "ready":
            missing.append(clip.id)
            continue
        current_revision = _current_post_metadata_revision(document, clip)
        recommended = next(
            (
                item
                for item in artifact.suggestions
                if item.id == artifact.recommended_suggestion_id
            ),
            None,
        )
        if (
            not artifact.revision_hash
            or artifact.revision_hash != current_revision
            or clip.post_metadata_revision_hash != current_revision
        ):
            stale.append(clip.id)
            continue
        if recommended is None:
            inconsistent.append(
                {"clipId": clip.id, "reason": "recommended_suggestion_missing"}
            )
            continue
        allowed_ids = set(clip.segment_ids)
        evidence_ids = set(recommended.evidence_segment_ids)
        description_ids = set(artifact.description_evidence_segment_ids)
        if not evidence_ids or not evidence_ids.issubset(allowed_ids):
            inconsistent.append(
                {"clipId": clip.id, "reason": "title_hook_evidence_invalid"}
            )
            continue
        if artifact.youtube_description and (
            not description_ids or not description_ids.issubset(allowed_ids)
        ):
            inconsistent.append(
                {"clipId": clip.id, "reason": "description_evidence_invalid"}
            )
            continue
        expected_scene_start = (
            None
            if recommended.hook_scene_start is None
            else round(clip.start + recommended.hook_scene_start, 3)
        )
        expected_scene_end = (
            None
            if recommended.hook_scene_end is None
            else round(clip.start + recommended.hook_scene_end, 3)
        )
        if (
            clip.post_metadata_source != "codex"
            or clip.recommended_title_id != recommended.id
            or clip.selected_title_id != recommended.id
            or clip.title != recommended.overlay_title
            or clip.publication_title
            != ensure_publication_title_suffix(
                recommended.publication_title,
                clip_type=clip.type,
                suffix=clip.normal_title_suffix,
            )
            or clip.hook_text != recommended.hook_text
            or clip.hook_scene_start != expected_scene_start
            or clip.hook_scene_end != expected_scene_end
        ):
            inconsistent.append(
                {"clipId": clip.id, "reason": "applied_suggestion_mismatch"}
            )
            continue
        evidence_by_clip[clip.id] = {
            "provider": "codex_host_bridge",
            "artifactInputHash": artifact.input_hash,
            "revisionHash": current_revision,
            "recommendedSuggestionId": recommended.id,
            "evidenceSegmentIds": sorted(evidence_ids),
        }

    if inconsistent:
        outcome: QualityGateOutcome = "fail"
        reason = "title_hook_evidence_inconsistent"
    elif missing or stale:
        outcome = "unknown"
        reason = "title_hook_evidence_unavailable_or_stale"
    else:
        outcome = "pass"
        reason = None
    return _check(
        "content.title_hook_semantics",
        outcome,
        reason_code=reason,
        evidence={
            "provider": "codex_revision_evidence_with_clip_overrides_v1",
            "clips": evidence_by_clip,
            "humanAcceptedClipIds": sorted(human_accepted_clip_ids),
            "humanReview": dict(human_evidence),
            "missingClipIds": missing,
            "staleClipIds": stale,
            "inconsistent": inconsistent,
            "limitation": "segment provenance does not independently prove semantic entailment",
        },
    )


def _automated_subtitle_alignment_check(
    document: SubtitleReviewDocument,
    *,
    human_accepted_clip_ids: set[str],
    human_evidence: Mapping[str, Any],
) -> QualityGateCheck:
    unknown: list[dict[str, Any]] = []
    metrics_by_clip: dict[str, Any] = {}
    for clip in document.clips:
        if clip.id in human_accepted_clip_ids:
            metrics_by_clip[clip.id] = {
                "acceptedByHuman": True,
                "previewSpecHash": clip.preview_spec_hash,
            }
            continue
        segments = _clip_segments(document, clip)
        confidences = [
            float(segment.confidence)
            for segment in segments
            if segment.confidence is not None
        ]
        coverage = len(confidences) / max(len(segments), 1)
        edited_ids = [segment.id for segment in segments if segment.edited]
        normalized_texts = [
            "".join(segment.text.split())
            for segment in segments
            if "".join(segment.text.split())
        ]
        repeated_ratio = (
            max(normalized_texts.count(text) for text in set(normalized_texts))
            / len(normalized_texts)
            if normalized_texts
            else 1.0
        )
        mean_confidence = (
            sum(confidences) / len(confidences) if confidences else None
        )
        sorted_confidences = sorted(confidences)
        p10_confidence = (
            sorted_confidences[math.floor((len(sorted_confidences) - 1) * 0.10)]
            if sorted_confidences
            else None
        )
        metrics_by_clip[clip.id] = {
            "segmentCount": len(segments),
            "confidenceCoverage": round(coverage, 4),
            "meanConfidence": (
                round(mean_confidence, 4) if mean_confidence is not None else None
            ),
            "p10Confidence": (
                round(p10_confidence, 4) if p10_confidence is not None else None
            ),
            "repeatedTextRatio": round(repeated_ratio, 4),
            "editedSegmentIds": edited_ids,
        }
        reasons: list[str] = []
        if not segments or coverage < 1.0:
            reasons.append("confidence_provenance_incomplete")
        if mean_confidence is None or mean_confidence < ASR_MIN_CONFIDENCE_MEAN:
            reasons.append("mean_confidence_below_threshold")
        if p10_confidence is None or p10_confidence < ASR_MIN_CONFIDENCE_P10:
            reasons.append("p10_confidence_below_threshold")
        if edited_ids:
            reasons.append("edited_text_not_acoustically_rechecked")
        if len(normalized_texts) >= 4 and repeated_ratio >= ASR_MAX_REPEATED_TEXT_RATIO:
            reasons.append("abnormal_repeated_transcript")
        if reasons:
            unknown.append({"clipId": clip.id, "reasons": reasons})

    return _check(
        "content.subtitle_accuracy",
        "unknown" if unknown else "pass",
        reason_code=("asr_alignment_evidence_insufficient" if unknown else None),
        evidence={
            "provider": "whisper_timing_confidence_with_clip_overrides_v1",
            "humanAcceptedClipIds": sorted(human_accepted_clip_ids),
            "humanReview": dict(human_evidence),
            "thresholds": {
                "confidenceCoverage": 1.0,
                "meanConfidence": ASR_MIN_CONFIDENCE_MEAN,
                "p10Confidence": ASR_MIN_CONFIDENCE_P10,
                "maxRepeatedTextRatio": ASR_MAX_REPEATED_TEXT_RATIO,
            },
            "clips": metrics_by_clip,
            "unknown": unknown,
            "limitation": "ASR confidence and timestamps are indirect audio-alignment evidence",
        },
    )


def _text_vertical_bounds(
    *,
    y_percent: float,
    alignment: int,
    line_count: int,
    font_size: int,
    outline_width: int,
    shadow: int,
    output_height: int,
) -> tuple[float, float]:
    visual_height = max(1, line_count) * font_size * 1.20 + 2 * (
        outline_width + shadow
    )
    anchor_y = output_height * min(100.0, max(0.0, y_percent)) / 100.0
    row = (min(9, max(1, alignment)) - 1) // 3
    if row == 0:
        return anchor_y - visual_height, anchor_y
    if row == 2:
        return anchor_y, anchor_y + visual_height
    return anchor_y - visual_height / 2, anchor_y + visual_height / 2


def _subtitle_events_for_review_clip(
    document: SubtitleReviewDocument,
    clip: Any,
    *,
    width: int,
    height: int,
) -> tuple[list[SubtitleEvent], SubtitleLayout]:
    segments = _clip_segments(document, clip)
    base_layout = (
        SubtitleLayout.short()
        if clip.type == "short"
        else SubtitleLayout.normal(width=width, height=height)
    )
    layout = replace(
        base_layout,
        width=width,
        height=height,
        max_chars_per_line=(
            clip.subtitle_max_chars_per_line
            if clip.subtitle_max_chars_per_line is not None
            else base_layout.max_chars_per_line
        ),
        max_lines=(
            clip.subtitle_max_lines
            if clip.subtitle_max_lines is not None
            else base_layout.max_lines
        ),
        min_subtitle_duration=(
            clip.subtitle_min_duration_seconds
            if clip.subtitle_min_duration_seconds is not None
            else base_layout.min_subtitle_duration
        ),
        max_subtitle_duration=(
            clip.subtitle_max_duration_seconds
            if clip.subtitle_max_duration_seconds is not None
            else base_layout.max_subtitle_duration
        ),
        min_gap_between_subtitles=(
            clip.subtitle_min_gap_seconds
            if clip.subtitle_min_gap_seconds is not None
            else base_layout.min_gap_between_subtitles
        ),
    )
    candidate = Candidate(
        id=clip.id,
        type=clip.type,
        start=clip.start,
        end=clip.end,
        duration=clip.duration,
        transcript_text=" ".join(segment.text for segment in segments),
        hook_text=clip.hook_text or None,
        hook_duration_seconds=clip.hook_duration_seconds,
        hook_scene_start=clip.hook_scene_start,
        hook_scene_end=clip.hook_scene_end,
    )
    transcript_segments = [
        TranscriptSegment(
            start=segment.start,
            end=segment.end,
            text=segment.text,
            confidence=segment.confidence,
            clipId=clip.id,
        )
        for segment in segments
    ]
    events, _ = subtitle_events_for_candidate_output(
        transcript_segments,
        candidate,
        layout,
    )
    return events, layout


def _automated_overlay_layout_check(
    document: SubtitleReviewDocument,
    *,
    human_accepted_clip_ids: set[str],
    human_evidence: Mapping[str, Any],
) -> QualityGateCheck:
    failures: list[dict[str, Any]] = []
    unknown: list[dict[str, str]] = []
    inspected: list[dict[str, Any]] = []

    for clip in document.clips:
        if clip.id in human_accepted_clip_ids:
            continue
        width = clip.preview_width
        height = clip.preview_height
        if width is None or height is None:
            unknown.append({"clipId": clip.id, "reason": "preview_dimensions_missing"})
            continue
        top_content = (
            SHORT_BANNER_HEIGHT
            if clip.type == "short" and document.short_top_banner_enabled
            else 0
        )
        bottom_content = height - (
            SHORT_BANNER_HEIGHT
            if clip.type == "short" and document.short_bottom_banner_enabled
            else 0
        )
        role_items: list[tuple[str, str, Any, int, int]] = []
        if clip.overlay_title_expected and clip.title:
            role_items.append(
                (
                    "title",
                    clip.title,
                    clip.resolved_title_style,
                    0,
                    SHORT_BANNER_HEIGHT
                    if clip.type == "short" and document.short_top_banner_enabled
                    else height,
                )
            )
        if clip.hook_text:
            role_items.append(
                (
                    "hook",
                    clip.hook_text,
                    clip.resolved_hook_style,
                    # The default hook anchor sits exactly on the lower edge of
                    # the top banner. Its centered ASS box intentionally spans
                    # that boundary, while subtitles must stay in the body.
                    0,
                    bottom_content,
                )
            )
        subtitle_events, subtitle_layout = _subtitle_events_for_review_clip(
            document,
            clip,
            width=width,
            height=height,
        )
        for event_index, event in enumerate(subtitle_events, start=1):
            max_lines = min(2, subtitle_layout.max_lines)
            role_items.append(
                (
                    f"subtitle:event_{event_index:05d}",
                    split_subtitle_lines(
                        event.text,
                        max_chars_per_line=subtitle_layout.max_chars_per_line,
                        max_lines=max_lines,
                    ),
                    clip.resolved_subtitle_style,
                    top_content,
                    bottom_content,
                )
            )

        for role, text, style, safe_top, safe_bottom in role_items:
            if style is None:
                unknown.append(
                    {"clipId": clip.id, "reason": f"{role}_resolved_style_missing"}
                )
                continue
            fit = fit_overlay_text(
                text,
                output_width=width,
                font_name=style.font_name,
                font_size=style.font_size,
                margin_x=style.margin_x,
                outline_width=style.outline_width,
                shadow=style.shadow,
                alignment=style.alignment,
                x_percent=style.x_percent,
                max_lines=2,
            )
            vertical_top, vertical_bottom = _text_vertical_bounds(
                y_percent=style.y_percent,
                alignment=style.alignment,
                line_count=len(fit.lines),
                font_size=fit.effective_font_size,
                outline_width=style.outline_width,
                shadow=style.shadow,
                output_height=height,
            )
            item = {
                "clipId": clip.id,
                "role": role,
                "fitsWidth": fit.fits,
                "effectiveFontSize": fit.effective_font_size,
                "lineCount": len(fit.lines),
                "verticalBounds": [round(vertical_top, 2), round(vertical_bottom, 2)],
                "safeBounds": [safe_top, safe_bottom],
            }
            inspected.append(item)
            if not fit.fits:
                failures.append({**item, "reason": "horizontal_text_overflow"})
            elif vertical_top < safe_top or vertical_bottom > safe_bottom:
                failures.append({**item, "reason": "text_outside_safe_vertical_area"})

    if failures:
        outcome: QualityGateOutcome = "fail"
        reason = "overlay_layout_outside_safe_area"
    elif unknown:
        outcome = "unknown"
        reason = "overlay_layout_evidence_incomplete"
    else:
        outcome = "pass"
        reason = None
    return _check(
        "content.overlay_layout",
        outcome,
        reason_code=reason,
        evidence={
            "provider": "resolved_text_geometry_with_clip_overrides_v1",
            "humanAcceptedClipIds": sorted(human_accepted_clip_ids),
            "humanReview": dict(human_evidence),
            "inspected": inspected,
            "failures": failures,
            "unknown": unknown,
        },
    )


def evaluate_content_quality_gate(
    *,
    job_id: str,
    document: SubtitleReviewDocument,
    settings: Mapping[str, Any],
    mode: QualityGateMode = "guarded",
    title_hook_evidence: Mapping[str, TitleHookSuggestionsDocument] | None = None,
) -> QualityGateDecision:
    all_clips_accepted, all_clips_evidence = _human_review_confirmation(
        document.clips,
        scope="all_clips",
    )
    human_accepted_clip_ids = set(
        all_clips_evidence["acceptedReadyClipIds"]
    )
    short_clips = [clip for clip in document.clips if clip.type == "short"]
    all_shorts_accepted, short_evidence = _human_review_confirmation(
        short_clips,
        scope="short_clips",
        applicable=bool(short_clips),
    )
    framing_deferred = bool(short_clips and mode == "auto" and not all_shorts_accepted)
    framing_outcome: QualityGateOutcome = (
        "pass"
        if not short_clips or all_shorts_accepted or framing_deferred
        else "unknown"
    )
    checks = [_content_structure_check(document), _preview_check(document)]
    if mode == "auto":
        checks.extend(
            [
                _automated_title_hook_check(
                    document,
                    title_hook_evidence,
                    human_accepted_clip_ids=human_accepted_clip_ids,
                    human_evidence=all_clips_evidence,
                ),
                _automated_subtitle_alignment_check(
                    document,
                    human_accepted_clip_ids=human_accepted_clip_ids,
                    human_evidence=all_clips_evidence,
                ),
                _automated_overlay_layout_check(
                    document,
                    human_accepted_clip_ids=human_accepted_clip_ids,
                    human_evidence=all_clips_evidence,
                ),
            ]
        )
    else:
        checks.extend(
            [
                _check(
                    "content.title_hook_semantics",
                    "pass" if all_clips_accepted else "unknown",
                    reason_code=(
                        None
                        if all_clips_accepted
                        else "human_review_or_current_preview_incomplete"
                    ),
                    evidence=all_clips_evidence,
                ),
                _check(
                    "content.subtitle_accuracy",
                    "pass" if all_clips_accepted else "unknown",
                    reason_code=(
                        None
                        if all_clips_accepted
                        else "human_review_or_current_preview_incomplete"
                    ),
                    evidence=all_clips_evidence,
                ),
            ]
        )
    checks.append(
        _check(
            "content.actual_framing",
            framing_outcome,
            reason_code=(
                "human_review_or_current_preview_incomplete"
                if framing_outcome == "unknown"
                else None
            ),
            evidence=(
                {
                    "provider": "post_render_crop_metadata_v1",
                    "deferredToPostRender": True,
                    "clipIds": [clip.id for clip in short_clips],
                }
                if framing_deferred
                else short_evidence
            ),
        )
    )
    return _decision(
        job_id=job_id,
        stage="content",
        payload={
            "document": document,
            "settings": dict(settings),
            "titleHookEvidence": dict(title_hook_evidence or {}),
        },
        checks=checks,
        mode=mode,
    )


def _export_identity(export: Any) -> dict[str, Any]:
    if isinstance(export, BaseModel):
        payload = export.model_dump(by_alias=True, mode="json")
    elif isinstance(export, Mapping):
        payload = dict(export)
    else:
        payload = {
            "id": getattr(export, "id", None),
            "candidateId": getattr(export, "candidate_id", None),
            "type": getattr(export, "type", None),
            "videoPath": getattr(export, "video_path", None),
            "subtitlePath": getattr(export, "subtitle_path", None),
            "metadataPath": getattr(export, "metadata_path", None),
        }
    return {
        "id": payload.get("id"),
        "candidateId": payload.get("candidateId", payload.get("candidate_id")),
        "type": payload.get("type"),
        "videoPath": payload.get("videoPath", payload.get("video_path")),
        "subtitlePath": payload.get("subtitlePath", payload.get("subtitle_path")),
        "metadataPath": payload.get("metadataPath", payload.get("metadata_path")),
    }


def _export_inspection_path(export: Any, field_name: str) -> Any:
    inspection_names = {
        "videoPath": ("inspectionVideoPath", "inspection_video_path"),
        "subtitlePath": ("inspectionSubtitlePath", "inspection_subtitle_path"),
        "metadataPath": ("inspectionMetadataPath", "inspection_metadata_path"),
    }
    if isinstance(export, BaseModel):
        payload = export.model_dump(by_alias=True, mode="json")
    elif isinstance(export, Mapping):
        payload = dict(export)
    else:
        payload = {}
    for name in inspection_names[field_name]:
        value = payload.get(name)
        if value:
            return value
    return _export_identity(export).get(field_name)


def _load_export_metadata(export: Any) -> tuple[dict[str, Any] | None, str | None]:
    metadata_value = _export_inspection_path(export, "metadataPath")
    if not metadata_value:
        return None, "metadata_path_missing"
    path = Path(str(metadata_value))
    if not path.is_file():
        return None, "metadata_file_missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None, "metadata_file_unreadable"
    if not isinstance(payload, dict):
        return None, "metadata_payload_invalid"
    return payload, None


def _post_render_export_identity_check(
    exports: Sequence[Any] | None,
    document: SubtitleReviewDocument | None,
) -> QualityGateCheck:
    if exports is None or document is None:
        return _check(
            "post_render.export_identity",
            "unknown",
            reason_code="export_identity_not_inspected",
        )

    expected = [(clip.id, clip.type) for clip in document.clips]
    actual: list[tuple[str, str]] = []
    invalid: list[dict[str, Any]] = []
    for export in exports:
        identity = _export_identity(export)
        candidate_id = str(identity.get("candidateId") or "")
        export_type = str(identity.get("type") or "")
        if not candidate_id or export_type not in {"normal", "short"}:
            invalid.append(
                {
                    "exportId": identity.get("id"),
                    "candidateId": candidate_id or None,
                    "type": export_type or None,
                }
            )
            continue
        actual.append((candidate_id, export_type))

    expected_set = set(expected)
    actual_set = set(actual)
    missing = [
        {"candidateId": candidate_id, "type": clip_type}
        for candidate_id, clip_type in sorted(expected_set - actual_set)
    ]
    unexpected = [
        {"candidateId": candidate_id, "type": clip_type}
        for candidate_id, clip_type in sorted(actual_set - expected_set)
    ]
    duplicates = [
        {"candidateId": candidate_id, "type": clip_type, "count": actual.count(item)}
        for item in sorted(actual_set)
        if actual.count(item) > 1
        for candidate_id, clip_type in [item]
    ]
    expected_types = {candidate_id: clip_type for candidate_id, clip_type in expected}
    type_mismatches = [
        {
            "candidateId": candidate_id,
            "expectedType": expected_types[candidate_id],
            "actualType": clip_type,
        }
        for candidate_id, clip_type in sorted(actual_set)
        if candidate_id in expected_types and expected_types[candidate_id] != clip_type
    ]
    mismatched = bool(missing or unexpected or duplicates or type_mismatches or invalid)
    return _check(
        "post_render.export_identity",
        "fail" if mismatched else "pass",
        reason_code="rendered_export_identity_mismatch" if mismatched else None,
        evidence={
            "expected": [
                {"candidateId": candidate_id, "type": clip_type}
                for candidate_id, clip_type in expected
            ],
            "missing": missing,
            "unexpected": unexpected,
            "duplicates": duplicates,
            "typeMismatches": type_mismatches,
            "invalid": invalid,
        },
    )


def _hook_scene_contract_matches(
    metadata: Mapping[str, Any],
    *,
    clip: Any,
) -> bool:
    expected = clip.hook_scene_start is not None and clip.hook_scene_end is not None
    rendered = bool(metadata.get("hook_scene_rendered"))
    try:
        metadata_start = (
            float(metadata["hook_scene_start"])
            if metadata.get("hook_scene_start") is not None
            else None
        )
        metadata_end = (
            float(metadata["hook_scene_end"])
            if metadata.get("hook_scene_end") is not None
            else None
        )
    except (TypeError, ValueError):
        return False
    if not expected:
        return not rendered and metadata_start is None and metadata_end is None
    return bool(
        rendered
        and metadata_start is not None
        and metadata_end is not None
        and math.isclose(metadata_start, float(clip.hook_scene_start), abs_tol=1e-6)
        and math.isclose(metadata_end, float(clip.hook_scene_end), abs_tol=1e-6)
    )


def _post_render_content_contract_check(
    exports: Sequence[Any] | None,
    document: SubtitleReviewDocument | None,
) -> QualityGateCheck:
    if exports is None or document is None:
        return _check(
            "post_render.content_contract",
            "unknown",
            reason_code="rendered_content_contract_not_inspected",
        )
    clip_by_id = {clip.id: clip for clip in document.clips}
    failures: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    inspected: list[dict[str, Any]] = []
    for export in exports:
        identity = _export_identity(export)
        clip_id = str(identity.get("candidateId") or "")
        clip = clip_by_id.get(clip_id)
        metadata, metadata_error = _load_export_metadata(export)
        if clip is None or metadata is None:
            unknown.append(
                {
                    "clipId": clip_id,
                    "reason": metadata_error or "review_clip_missing",
                }
            )
            continue

        expected_publication_title = clip.publication_title or clip.title
        mismatches: list[str] = []
        if str(metadata.get("candidate_id") or "") != clip.id:
            mismatches.append("candidate_id")
        if str(metadata.get("type") or "") != clip.type:
            mismatches.append("type")
        if str(metadata.get("title") or "") != expected_publication_title:
            mismatches.append("title")
        if str(metadata.get("overlay_title") or "") != clip.title:
            mismatches.append("overlay_title")
        if bool(metadata.get("overlay_title_expected")) != clip.overlay_title_expected:
            mismatches.append("overlay_title_expected")
        if bool(metadata.get("overlay_title_rendered")) != clip.overlay_title_expected:
            mismatches.append("overlay_title_rendered")
        if clip.type == "normal" and not bool(metadata.get("title_rendered")):
            mismatches.append("title_rendered")
        if str(metadata.get("hook_text") or "") != clip.hook_text:
            mismatches.append("hook_text")
        if bool(metadata.get("hook_rendered")) != bool(clip.hook_text):
            mismatches.append("hook_rendered")
        if not _hook_scene_contract_matches(metadata, clip=clip):
            mismatches.append("hook_scene")
        if metadata.get("post_metadata_revision_hash") != clip.post_metadata_revision_hash:
            mismatches.append("post_metadata_revision_hash")
        item = {"clipId": clip_id, "type": clip.type, "mismatches": mismatches}
        inspected.append(item)
        if mismatches:
            failures.append(item)

    if failures:
        outcome: QualityGateOutcome = "fail"
        reason = "rendered_content_contract_mismatch"
    elif unknown:
        outcome = "unknown"
        reason = "rendered_content_contract_unavailable"
    else:
        outcome = "pass"
        reason = None
    return _check(
        "post_render.content_contract",
        outcome,
        reason_code=reason,
        evidence={"inspected": inspected, "failures": failures, "unknown": unknown},
    )


def _expected_export_dimensions(
    identity: Mapping[str, Any],
    document: SubtitleReviewDocument | None,
) -> tuple[int, int] | None:
    candidate_id = str(identity.get("candidateId") or "")
    if document is not None:
        clip = next((item for item in document.clips if item.id == candidate_id), None)
        if clip is not None and clip.preview_width and clip.preview_height:
            return clip.preview_width, clip.preview_height
    if identity.get("type") == "short":
        return 1080, 1920
    return None


def _expected_export_duration(
    identity: Mapping[str, Any],
    document: SubtitleReviewDocument | None,
) -> float | None:
    if document is None:
        return None
    candidate_id = str(identity.get("candidateId") or "")
    clip = next((item for item in document.clips if item.id == candidate_id), None)
    if clip is None:
        return None
    hook_scene_duration = (
        clip.hook_scene_end - clip.hook_scene_start
        if clip.hook_scene_start is not None and clip.hook_scene_end is not None
        else 0.0
    )
    return clip.duration + hook_scene_duration


def _post_render_media_artifact_check(
    exports: Sequence[Any] | None,
    document: SubtitleReviewDocument | None,
) -> QualityGateCheck:
    if exports is None:
        return _check(
            "post_render.media_artifacts",
            "unknown",
            reason_code="exports_not_inspected",
        )
    failures: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    inspected: list[dict[str, Any]] = []
    for export in exports:
        identity = _export_identity(export)
        video_value = _export_inspection_path(export, "videoPath")
        subtitle_value = _export_inspection_path(export, "subtitlePath")
        video_path = Path(str(video_value)) if video_value else None
        subtitle_path = Path(str(subtitle_value)) if subtitle_value else None
        video_ready = bool(
            video_path is not None
            and video_path.is_file()
            and video_path.stat().st_size > 0
        )
        subtitle_ready = bool(
            subtitle_path is not None
            and subtitle_path.is_file()
            and subtitle_path.stat().st_size > 0
        )
        item: dict[str, Any] = {
            "exportId": identity.get("id"),
            "candidateId": identity.get("candidateId"),
            "videoReady": video_ready,
            "subtitleReady": subtitle_ready,
            "videoSize": (
                video_path.stat().st_size if video_ready and video_path is not None else None
            ),
        }
        if not video_ready or not subtitle_ready:
            failures.append({**item, "reason": "rendered_media_artifact_missing"})
            inspected.append(item)
            continue
        try:
            metadata: VideoMetadata = probe_metadata(video_path)
        except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            unknown.append(
                {
                    **item,
                    "reason": "rendered_media_probe_failed",
                    "errorType": exc.__class__.__name__,
                }
            )
            inspected.append(item)
            continue

        expected_dimensions = _expected_export_dimensions(identity, document)
        expected_duration = _expected_export_duration(identity, document)
        duration_tolerance = (
            max(0.35, min(0.5, expected_duration * 0.01))
            if expected_duration is not None
            else None
        )
        export_metadata, _metadata_error = _load_export_metadata(export)
        metadata_duration_value = (
            export_metadata.get("output_duration", export_metadata.get("duration"))
            if export_metadata is not None
            else None
        )
        try:
            metadata_duration = (
                float(metadata_duration_value)
                if metadata_duration_value is not None
                else None
            )
        except (TypeError, ValueError):
            metadata_duration = None
        dimensions_match = bool(
            expected_dimensions is None
            or (metadata.width, metadata.height) == expected_dimensions
        )
        duration_ready = bool(metadata.duration is not None and metadata.duration > 0)
        stream_ready = bool(metadata.width and metadata.height and metadata.has_audio)
        expected_duration_match = bool(
            expected_duration is None
            or (
                metadata.duration is not None
                and duration_tolerance is not None
                and abs(metadata.duration - expected_duration) <= duration_tolerance
            )
        )
        metadata_duration_match = bool(
            expected_duration is None
            or (
                metadata_duration is not None
                and duration_tolerance is not None
                and abs(metadata_duration - expected_duration) <= duration_tolerance
            )
        )
        stream_durations_reported = bool(
            metadata.video_stream_duration is not None
            and metadata.audio_stream_duration is not None
        )
        streams_synchronized = bool(
            stream_durations_reported
            and duration_tolerance is not None
            and abs(
                float(metadata.video_stream_duration)
                - float(metadata.audio_stream_duration)
            )
            <= duration_tolerance
        )
        item.update(
            {
                "duration": metadata.duration,
                "metadataDuration": metadata_duration,
                "videoStreamDuration": metadata.video_stream_duration,
                "audioStreamDuration": metadata.audio_stream_duration,
                "expectedDuration": expected_duration,
                "durationTolerance": duration_tolerance,
                "expectedDurationMatch": expected_duration_match,
                "metadataDurationMatch": metadata_duration_match,
                "streamsSynchronized": streams_synchronized,
                "width": metadata.width,
                "height": metadata.height,
                "hasAudio": metadata.has_audio,
                "expectedDimensions": (
                    list(expected_dimensions) if expected_dimensions is not None else None
                ),
                "dimensionsMatch": dimensions_match,
            }
        )
        inspected.append(item)
        if not stream_durations_reported:
            unknown.append({**item, "reason": "rendered_stream_duration_unavailable"})
        elif (
            not stream_ready
            or not duration_ready
            or not dimensions_match
            or not expected_duration_match
            or not metadata_duration_match
            or not streams_synchronized
        ):
            failures.append({**item, "reason": "rendered_media_stream_contract_failed"})

    if failures:
        outcome: QualityGateOutcome = "fail"
        reason = "rendered_media_artifact_invalid"
    elif unknown:
        outcome = "unknown"
        reason = "rendered_media_probe_unavailable"
    else:
        outcome = "pass"
        reason = None
    return _check(
        "post_render.media_artifacts",
        outcome,
        reason_code=reason,
        evidence={"inspected": inspected, "failures": failures, "unknown": unknown},
    )


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _geometry_values(
    value: Any,
    *,
    keys: Sequence[str],
) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    resolved = {key: _finite_float(value.get(key)) for key in keys}
    if any(item is None for item in resolved.values()):
        return None
    return {key: float(item) for key, item in resolved.items() if item is not None}


def _tracking_crop_containment(
    metadata: Mapping[str, Any],
    *,
    strategy: str,
    top_banner_enabled: bool,
    bottom_banner_enabled: bool,
) -> tuple[bool | None, dict[str, Any]]:
    evidence = metadata.get("tracking_evidence")
    summary: dict[str, Any] = {
        "provider": "render_tracking_geometry_v1",
        "strategy": strategy,
    }
    if not isinstance(evidence, Mapping):
        return None, {**summary, "reason": "tracking_evidence_missing"}
    if evidence.get("schema_version") != 1 or evidence.get("strategy") != strategy:
        return None, {**summary, "reason": "tracking_evidence_identity_mismatch"}

    source = _geometry_values(evidence.get("source"), keys=("width", "height"))
    scaled = _geometry_values(evidence.get("scaled"), keys=("width", "height"))
    crop = _geometry_values(evidence.get("crop"), keys=("x", "y", "width", "height"))
    safe_area = _geometry_values(
        evidence.get("safe_area"),
        keys=("x", "y", "width", "height"),
    )
    if source is None or scaled is None or crop is None or safe_area is None:
        return None, {**summary, "reason": "tracking_geometry_missing_or_invalid"}
    if any(
        geometry[dimension] <= 0
        for geometry in (source, scaled, crop, safe_area)
        for dimension in ("width", "height")
    ):
        return None, {**summary, "reason": "tracking_geometry_non_positive"}

    tolerance = 2.0
    crop_right = crop["x"] + crop["width"]
    crop_bottom = crop["y"] + crop["height"]
    safe_right = safe_area["x"] + safe_area["width"]
    safe_bottom = safe_area["y"] + safe_area["height"]
    expected_crop_height = (
        1920
        - SHORT_BANNER_HEIGHT * int(top_banner_enabled)
        - SHORT_BANNER_HEIGHT * int(bottom_banner_enabled)
    )
    crop_geometry_matches_render = bool(
        abs(crop["width"] - 1080) <= tolerance
        and abs(crop["height"] - expected_crop_height) <= tolerance
        and crop["x"] >= -tolerance
        and crop["y"] >= -tolerance
        and crop_right <= scaled["width"] + tolerance
        and crop_bottom <= scaled["height"] + tolerance
    )
    safe_area_inside_crop = bool(
        safe_area["x"] >= crop["x"] - tolerance
        and safe_area["y"] >= crop["y"] - tolerance
        and safe_right <= crop_right + tolerance
        and safe_bottom <= crop_bottom + tolerance
    )
    if not crop_geometry_matches_render or not safe_area_inside_crop:
        return None, {
            **summary,
            "reason": "tracking_geometry_inconsistent_with_render",
            "crop": crop,
            "safeArea": safe_area,
        }

    for metadata_key, evidence_key in (
        ("source_width", "width"),
        ("source_height", "height"),
        ("crop_x", "x"),
        ("crop_y", "y"),
    ):
        metadata_value = _finite_float(metadata.get(metadata_key))
        if metadata_value is not None:
            expected_value = source[evidence_key] if metadata_key.startswith("source_") else crop[evidence_key]
            if abs(metadata_value - expected_value) > tolerance:
                return None, {
                    **summary,
                    "reason": "tracking_geometry_metadata_mismatch",
                    "field": metadata_key,
                }

    samples = evidence.get("samples")
    if not isinstance(samples, list) or not samples:
        return None, {**summary, "reason": "tracking_samples_missing"}
    outside_sample_indexes: list[int] = []
    sample_timestamps: set[float] = set()
    for index, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            return None, {**summary, "reason": "tracking_sample_invalid", "sampleIndex": index}
        box = sample.get("box")
        if not isinstance(box, list | tuple) or len(box) != 4:
            return None, {**summary, "reason": "tracking_sample_box_invalid", "sampleIndex": index}
        ratios = [_finite_float(value) for value in box]
        if any(value is None for value in ratios):
            return None, {**summary, "reason": "tracking_sample_box_invalid", "sampleIndex": index}
        left_ratio, top_ratio, right_ratio, bottom_ratio = [
            float(value) for value in ratios if value is not None
        ]
        confidence = _finite_float(sample.get("confidence"))
        sample_start = _finite_float(sample.get("start"))
        sample_end = _finite_float(sample.get("end"))
        if not (
            0.0 <= left_ratio < right_ratio <= 1.0
            and 0.0 <= top_ratio < bottom_ratio <= 1.0
            and confidence is not None
            and 0.0 <= confidence <= 1.0
            and sample_start is not None
            and sample_end is not None
            and sample_end >= sample_start
        ):
            return None, {**summary, "reason": "tracking_sample_box_invalid", "sampleIndex": index}
        sample_timestamps.add(round(sample_start, 3))
        left = left_ratio * scaled["width"]
        top = top_ratio * scaled["height"]
        right = right_ratio * scaled["width"]
        bottom = bottom_ratio * scaled["height"]
        if not (
            left >= safe_area["x"] - tolerance
            and top >= safe_area["y"] - tolerance
            and right <= safe_right + tolerance
            and bottom <= safe_bottom + tolerance
        ):
            outside_sample_indexes.append(index)

    summary.update(
        {
            "sampleCount": len(samples),
            "distinctSampleTimestamps": len(sample_timestamps),
            "outsideSampleIndexes": outside_sample_indexes,
            "crop": crop,
            "safeArea": safe_area,
        }
    )
    if outside_sample_indexes:
        return False, {**summary, "reason": "tracking_subject_outside_safe_area"}

    if strategy == "face_tracking_crop":
        if len(sample_timestamps) < 3:
            return None, {**summary, "reason": "face_tracking_time_coverage_insufficient"}
    elif strategy == "speaker_tracking_crop":
        speaker_confidence = _finite_float(metadata.get("speaker_region_confidence"))
        stability = _finite_float(metadata.get("crop_stability_score"))
        window_count = _finite_float(metadata.get("speaker_window_count"))
        summary.update(
            {
                "speakerRegionConfidence": speaker_confidence,
                "cropStabilityScore": stability,
                "speakerWindowCount": window_count,
            }
        )
        if (
            speaker_confidence is None
            or speaker_confidence < 0.72
            or stability is None
            or stability < 0.68
            or window_count is None
            or window_count < 2
        ):
            return None, {**summary, "reason": "speaker_tracking_signal_below_threshold"}
    elif strategy == "person_tracking_crop":
        person_confidence = _finite_float(
            metadata.get("person_detection_confidence", metadata.get("crop_confidence"))
        )
        stability = _finite_float(metadata.get("crop_stability_score"))
        sampled_frames = _finite_float(metadata.get("crop_sampled_frames"))
        summary.update(
            {
                "personDetectionConfidence": person_confidence,
                "cropStabilityScore": stability,
                "sampledFrames": sampled_frames,
            }
        )
        if (
            person_confidence is None
            or person_confidence < 0.68
            or stability is None
            or stability < 0.58
            or sampled_frames is None
            or sampled_frames < 2
        ):
            return None, {**summary, "reason": "person_tracking_signal_below_threshold"}
    return True, summary


def _post_render_visual_check(
    exports: Sequence[Any] | None,
    document: SubtitleReviewDocument | None,
) -> QualityGateCheck:
    if exports is None or document is None:
        return _check(
            "post_render.visual_framing_layout",
            "unknown",
            reason_code="visual_evidence_not_inspected",
        )
    clip_by_id = {clip.id: clip for clip in document.clips}
    short_clips = [clip for clip in document.clips if clip.type == "short"]
    _all_shorts_accepted, human_visual_evidence = _human_review_confirmation(
        short_clips,
        scope="short_clips",
        applicable=bool(short_clips),
    )
    human_accepted_ids = set(human_visual_evidence["acceptedReadyClipIds"])
    failures: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    inspected: list[dict[str, Any]] = []
    for export in exports:
        identity = _export_identity(export)
        if identity.get("type") != "short":
            continue
        clip_id = str(identity.get("candidateId") or "")
        clip = clip_by_id.get(clip_id)
        metadata, metadata_error = _load_export_metadata(export)
        if clip is None or metadata is None:
            unknown.append(
                {
                    "clipId": clip_id,
                    "reason": metadata_error or "review_clip_missing",
                }
            )
            continue
        top_expected = document.short_top_banner_enabled
        bottom_expected = document.short_bottom_banner_enabled
        banner_mismatch = (
            bool(metadata.get("top_banner_rendered")) != top_expected
            or bool(metadata.get("bottom_banner_rendered")) != bottom_expected
        )
        strategy = str(metadata.get("crop_strategy") or metadata.get("strategy") or "")
        confidence_value = metadata.get("crop_confidence")
        try:
            confidence = (
                float(confidence_value) if confidence_value is not None else None
            )
        except (TypeError, ValueError):
            confidence = None
        tracking_status: bool | None = None
        tracking_summary: dict[str, Any] | None = None
        if strategy in {
            "face_tracking_crop",
            "speaker_tracking_crop",
            "person_tracking_crop",
            "subject_tracking_crop",
        }:
            tracking_status, tracking_summary = _tracking_crop_containment(
                metadata,
                strategy=strategy,
                top_banner_enabled=top_expected,
                bottom_banner_enabled=bottom_expected,
            )
        item = {
            "clipId": clip_id,
            "strategy": strategy,
            "cropConfidence": confidence,
            "cropFallbackReason": metadata.get("crop_fallback_reason"),
            "trackingContainment": tracking_status,
            "trackingEvidence": tracking_summary,
            "topBannerExpected": top_expected,
            "bottomBannerExpected": bottom_expected,
            "humanPreviewAccepted": clip_id in human_accepted_ids,
        }
        inspected.append(item)
        if banner_mismatch:
            failures.append({**item, "reason": "rendered_overlay_contract_mismatch"})
            continue
        if tracking_status is False:
            failures.append({**item, "reason": "tracking_subject_outside_safe_area"})
            continue
        if clip_id in human_accepted_ids:
            continue
        if strategy == "blur_background":
            continue
        if strategy in {
            "face_tracking_crop",
            "speaker_tracking_crop",
            "person_tracking_crop",
            "subject_tracking_crop",
        }:
            if tracking_status is None:
                unknown.append(
                    {
                        **item,
                        "reason": (
                            tracking_summary.get("reason")
                            if tracking_summary is not None
                            else "tracking_crop_containment_unverified"
                        ),
                    }
                )
            continue
        unknown.append({**item, "reason": "destructive_crop_not_visually_verified"})

    if failures:
        outcome: QualityGateOutcome = "fail"
        reason = "post_render_visual_contract_failed"
    elif unknown:
        outcome = "unknown"
        reason = "post_render_visual_evidence_insufficient"
    else:
        outcome = "pass"
        reason = None
    return _check(
        "post_render.visual_framing_layout",
        outcome,
        reason_code=reason,
        evidence={
            "provider": "render_metadata_geometry_v1",
            "inspected": inspected,
            "failures": failures,
            "unknown": unknown,
        },
    )


def evaluate_post_render_quality_gate(
    *,
    job_id: str,
    expected_export_count: int,
    exports: Sequence[Any] | None,
    render_failures: Sequence[Any] | None,
    mode: QualityGateMode = "guarded",
    document: SubtitleReviewDocument | None = None,
) -> QualityGateDecision:
    if expected_export_count < 0:
        raise ValueError("expected_export_count must be non-negative")
    export_payload = (
        sorted(
            (_export_identity(export) for export in exports),
            key=lambda item: (
                str(item.get("type") or ""),
                str(item.get("candidateId") or ""),
                str(item.get("id") or ""),
            ),
        )
        if exports is not None
        else None
    )
    failure_payload = (
        [_canonical_value(failure) for failure in render_failures]
        if render_failures is not None
        else None
    )

    if exports is None:
        count_outcome: QualityGateOutcome = "unknown"
        count_reason = "exports_not_inspected"
        actual_count = None
    else:
        actual_count = len(exports)
        count_outcome = "pass" if actual_count == expected_export_count else "fail"
        count_reason = None if count_outcome == "pass" else "export_count_mismatch"

    if render_failures is None:
        failures_outcome: QualityGateOutcome = "unknown"
        failures_reason = "render_failures_not_inspected"
    else:
        failures_outcome = "pass" if not render_failures else "fail"
        failures_reason = (
            None if failures_outcome == "pass" else "render_failures_present"
        )

    checks = [
        _check(
            "post_render.export_count",
            count_outcome,
            reason_code=count_reason,
            evidence={"expected": expected_export_count, "actual": actual_count},
        ),
        _check(
            "post_render.render_failures",
            failures_outcome,
            reason_code=failures_reason,
            evidence={
                "failureCount": (
                    len(render_failures) if render_failures is not None else None
                )
            },
        ),
    ]
    if mode == "auto":
        checks.extend(
            [
                _post_render_export_identity_check(exports, document),
                _post_render_content_contract_check(exports, document),
                _post_render_media_artifact_check(exports, document),
                _post_render_visual_check(exports, document),
            ]
        )
    return _decision(
        job_id=job_id,
        stage="post_render",
        payload={
            "expectedExportCount": expected_export_count,
            "exports": export_payload,
            "renderFailures": failure_payload,
            "reviewDocument": document,
        },
        checks=checks,
        mode=mode,
    )
