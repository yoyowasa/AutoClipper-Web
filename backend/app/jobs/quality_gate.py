from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
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


QualityGateStage = Literal["selection", "content", "post_render"]
QualityGateMode = Literal["shadow", "guarded"]
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
        if self.enforced is not (self.mode == "guarded"):
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
    if stage == "content":
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
        enforced=mode == "guarded",
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
        settings=ShortDiversitySettings(
            enforce_heatmap_segment_uniqueness=bool(
                settings.get("heatmapIntervalMode", False)
            )
        ),
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


def evaluate_content_quality_gate(
    *,
    job_id: str,
    document: SubtitleReviewDocument,
    settings: Mapping[str, Any],
    mode: QualityGateMode = "guarded",
) -> QualityGateDecision:
    checks = [
        _content_structure_check(document),
        _preview_check(document),
        _check(
            "content.title_hook_semantics",
            "unknown",
            reason_code="title_hook_semantic_quality_not_connected",
            evidence={"provider": "not_connected"},
        ),
        _check(
            "content.subtitle_accuracy",
            "unknown",
            reason_code="subtitle_accuracy_check_not_connected",
            evidence={"provider": "not_connected"},
        ),
        _check(
            "content.actual_framing",
            "unknown" if any(clip.type == "short" for clip in document.clips) else "pass",
            reason_code=(
                "actual_framing_check_not_connected"
                if any(clip.type == "short" for clip in document.clips)
                else None
            ),
            evidence={
                "provider": "not_connected",
                "applicable": any(clip.type == "short" for clip in document.clips),
            },
        ),
    ]
    return _decision(
        job_id=job_id,
        stage="content",
        payload={"document": document, "settings": dict(settings)},
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
        }
    return {
        "id": payload.get("id"),
        "candidateId": payload.get("candidateId", payload.get("candidate_id")),
        "type": payload.get("type"),
        "videoPath": payload.get("videoPath", payload.get("video_path")),
    }


def evaluate_post_render_quality_gate(
    *,
    job_id: str,
    expected_export_count: int,
    exports: Sequence[Any] | None,
    render_failures: Sequence[Any] | None,
    mode: QualityGateMode = "guarded",
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
    return _decision(
        job_id=job_id,
        stage="post_render",
        payload={
            "expectedExportCount": expected_export_count,
            "exports": export_payload,
            "renderFailures": failure_payload,
        },
        checks=checks,
        mode=mode,
    )
