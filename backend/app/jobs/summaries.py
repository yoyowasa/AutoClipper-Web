from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.volume_features import AudioFeatures
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.models import ExportItem
from app.render.render_normal import NormalRenderBatchResult
from app.render.render_short import ShortRenderBatchResult


TRANSCRIPT_SUMMARY_FILENAME = "transcript_summary.json"
AUDIO_FEATURE_SUMMARY_FILENAME = "audio_feature_summary.json"
CANDIDATE_SUMMARY_FILENAME = "candidate_summary.json"
CANDIDATE_GENERATION_SUMMARY_FILENAME = "candidate_generation_summary.json"
OPENAI_SCORING_SUMMARY_FILENAME = "openai_scoring_summary.json"
REJECTION_SUMMARY_FILENAME = "rejection_summary.json"
SELECTED_CLIPS_SUMMARY_FILENAME = "selected_clips_summary.json"

SUMMARY_FILENAMES = [
    TRANSCRIPT_SUMMARY_FILENAME,
    AUDIO_FEATURE_SUMMARY_FILENAME,
    CANDIDATE_SUMMARY_FILENAME,
    CANDIDATE_GENERATION_SUMMARY_FILENAME,
    OPENAI_SCORING_SUMMARY_FILENAME,
    REJECTION_SUMMARY_FILENAME,
    SELECTED_CLIPS_SUMMARY_FILENAME,
]


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _stats(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "max": None, "avg": None}
    return {
        "min": _round(min(values)),
        "max": _round(max(values)),
        "avg": _round(sum(values) / len(values)),
    }


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return _round(ordered[0])
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return _round(ordered[lower])
    weight = position - lower
    return _round((ordered[lower] * (1 - weight)) + (ordered[upper] * weight))


def _score(candidate: Candidate) -> float | None:
    for value in (candidate.final_score, candidate.ai_score, candidate.rule_score):
        if value is not None:
            return float(value)
    return None


def _candidate_summary_item(candidate: Candidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "type": candidate.type,
        "title": candidate.title,
        "overlay_title": candidate.overlay_title,
        "title_source": candidate.title_source,
        "duration": _round(candidate.duration),
        "original_start": _round(candidate.original_start),
        "original_end": _round(candidate.original_end),
        "refined_start": _round(candidate.refined_start),
        "refined_end": _round(candidate.refined_end),
        "boundary_refined": candidate.boundary_refined,
        "boundary_refinement_reason": candidate.boundary_refinement_reason,
        "boundary_expansion_seconds": _round(candidate.boundary_expansion_seconds),
        "rule_score": _round(candidate.rule_score),
        "final_score": _round(_score(candidate)),
        "hard_gate_passed": candidate.hard_gate_passed,
        "below_quality_threshold": candidate.below_quality_threshold,
        "quality_warning": candidate.quality_warning,
        "selection_reason": candidate.selection_reason,
        "overlap_relaxed": candidate.overlap_relaxed,
        "overlap_ratio_used": _round(candidate.overlap_ratio_used),
        "time_cluster": candidate.time_cluster,
        "used_ai_score": candidate.used_ai_score,
        "openai_scored": candidate.openai_scored,
        "openai_fallback_used": candidate.openai_fallback_used,
        "openai_score_source": candidate.openai_score_source,
        "openai_not_scored_reason": candidate.openai_not_scored_reason,
    }


def _transcript_text(segments: Sequence[TranscriptSegment]) -> str:
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()


def _transcript_speech_duration(segments: Sequence[TranscriptSegment]) -> float:
    return sum(max(0.0, segment.end - segment.start) for segment in segments if segment.text.strip())


def _average_confidence(segments: Sequence[TranscriptSegment]) -> float | None:
    values = [segment.confidence for segment in segments if segment.confidence is not None]
    if not values:
        return None
    return sum(values) / len(values)


def build_transcript_summary(
    transcript_segments: Sequence[TranscriptSegment] | None,
    *,
    transcription_engine: str,
    used_fixture_transcript: bool,
    transcription_model: str | None = None,
    transcription_language: str | None = None,
) -> dict[str, Any]:
    segments = list(transcript_segments or [])
    return {
        "segment_count": len(segments),
        "total_text_length": len(_transcript_text(segments)),
        "total_speech_duration": _round(_transcript_speech_duration(segments)),
        "average_confidence": _round(_average_confidence(segments)),
        "first_segments": [
            {
                "start": _round(segment.start),
                "end": _round(segment.end),
                "text": segment.text,
                "confidence": _round(segment.confidence),
            }
            for segment in segments[:3]
        ],
        "transcription_engine": transcription_engine,
        "transcription_model": transcription_model,
        "transcription_language": transcription_language,
        "used_fixture_transcript": used_fixture_transcript,
    }


def build_audio_feature_summary(audio_features: AudioFeatures | None) -> dict[str, Any]:
    if audio_features is None:
        return {
            "has_audio_features": False,
            "duration": None,
            "silence_ratio": None,
            "speech_density": None,
            "volume_peak": None,
            "silent_seconds": None,
            "speech_seconds": None,
        }
    payload = audio_features.model_dump()
    return {
        "has_audio_features": True,
        **{key: _round(float(value)) for key, value in payload.items()},
    }


def build_candidate_summary(
    normal_candidates: Sequence[Candidate] | None,
    short_candidates: Sequence[Candidate] | None,
    scored_candidates: Sequence[Candidate] | None,
    selection: CandidateSelection | None = None,
) -> dict[str, Any]:
    generated = [*(normal_candidates or []), *(short_candidates or [])]
    candidates = list(scored_candidates or generated)
    selected = [*(selection.normal_clips if selection is not None else []), *(selection.shorts if selection is not None else [])]
    duration_stats = _stats([float(candidate.duration) for candidate in candidates])
    rule_score_stats = _stats(
        [float(candidate.rule_score) for candidate in candidates if candidate.rule_score is not None]
    )
    final_scores = [float(score) for candidate in candidates if (score := _score(candidate)) is not None]
    final_score_stats = _stats(final_scores)
    rejection_counter: Counter[str] = Counter()
    rejected_ids_by_reason: dict[str, list[str]] = {}
    if selection is not None:
        for rejection in selection.rejected_candidates:
            for reason in rejection.reasons:
                rejection_counter[reason] += 1
                rejected_ids_by_reason.setdefault(reason, []).append(rejection.candidate_id)
    return {
        "total_candidates": len(candidates),
        "short_candidates": sum(1 for candidate in candidates if candidate.type == "short"),
        "normal_candidates": sum(1 for candidate in candidates if candidate.type == "normal"),
        "candidates_with_transcript_text": sum(1 for candidate in candidates if candidate.transcript_text.strip()),
        "hard_gate_passed_count": selection.hard_gate_passed_count if selection is not None else 0,
        "hard_gate_rejected_count": selection.hard_gate_rejected_count if selection is not None else 0,
        "requested_normal_count": selection.requested_normal_count if selection is not None else 0,
        "selected_normal_count": len(selection.normal_clips) if selection is not None else 0,
        "requested_short_count": selection.requested_short_count if selection is not None else 0,
        "selected_short_count": len(selection.shorts) if selection is not None else 0,
        "normal_hard_gate_passed_count": selection.normal_hard_gate_passed_count if selection is not None else 0,
        "short_hard_gate_passed_count": selection.short_hard_gate_passed_count if selection is not None else 0,
        "selected_above_threshold_count": selection.selected_above_threshold_count if selection is not None else 0,
        "selected_below_threshold_backfill_count": (
            selection.selected_below_threshold_backfill_count if selection is not None else 0
        ),
        "overlap_relaxed_count": selection.overlap_relaxed_count if selection is not None else 0,
        "high_overlap_rejected_by_type": selection.high_overlap_rejected_by_type if selection is not None else {},
        "cross_type_overlap_rejected_count": selection.cross_type_overlap_rejected_count if selection is not None else 0,
        "time_cluster_count": selection.time_cluster_count if selection is not None else {},
        "selected_clusters": selection.selected_clusters if selection is not None else {},
        "unfilled_requested_counts": selection.unfilled_requested_counts if selection is not None else {},
        "unfilled_reason_counts": selection.unfilled_reason_counts if selection is not None else {},
        "min_duration": duration_stats["min"],
        "max_duration": duration_stats["max"],
        "avg_duration": duration_stats["avg"],
        "min_rule_score": rule_score_stats["min"],
        "max_rule_score": rule_score_stats["max"],
        "avg_rule_score": rule_score_stats["avg"],
        "min_final_score": final_score_stats["min"],
        "max_final_score": final_score_stats["max"],
        "avg_final_score": final_score_stats["avg"],
        "p50_final_score": _percentile(final_scores, 0.50),
        "p75_final_score": _percentile(final_scores, 0.75),
        "p90_final_score": _percentile(final_scores, 0.90),
        "p95_final_score": _percentile(final_scores, 0.95),
        "top_selected_candidates": [
            _candidate_summary_item(candidate)
            for candidate in sorted(selected, key=lambda item: _score(item) or 0.0, reverse=True)[:10]
        ],
        "top_rejected_candidates_by_reason": [
            {
                "reason": reason,
                "count": count,
                "candidate_ids": rejected_ids_by_reason.get(reason, [])[:10],
            }
            for reason, count in rejection_counter.most_common(10)
        ],
    }


def _render_failures(
    normal_result: NormalRenderBatchResult | None,
    short_result: ShortRenderBatchResult | None,
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if normal_result is not None:
        failures.extend(
            {"type": "normal", "candidate_id": failure.candidate_id, "error": failure.error}
            for failure in normal_result.failures
        )
    if short_result is not None:
        failures.extend(
            {"type": "short", "candidate_id": failure.candidate_id, "error": failure.error}
            for failure in short_result.failures
        )
    return failures


def build_rejection_summary(
    selection: CandidateSelection | None,
    normal_result: NormalRenderBatchResult | None,
    short_result: ShortRenderBatchResult | None,
) -> dict[str, Any]:
    rejections = list(selection.rejected_candidates if selection is not None else [])
    rejection_reasons: Counter[str] = Counter()
    rejected_by_type: Counter[str] = Counter()
    high_overlap_by_type: Counter[str] = Counter()
    cross_type_overlap_rejected_count = 0
    for rejection in rejections:
        rejected_by_type[str(rejection.type)] += 1
        rejection_reasons.update(rejection.reasons)
        if "high_overlap" in rejection.reasons:
            high_overlap_by_type[str(rejection.type)] += 1
        if "cross_type_high_overlap" in rejection.reasons:
            cross_type_overlap_rejected_count += 1

    render_failures = _render_failures(normal_result, short_result)
    render_failures_by_type = Counter(failure["type"] for failure in render_failures)
    render_failure_errors = Counter(failure["error"] for failure in render_failures)

    return {
        "total_rejected": len(rejections),
        "rejected_by_type": dict(sorted(rejected_by_type.items())),
        "rejected_by_reason": dict(sorted(rejection_reasons.items())),
        "high_overlap_rejected_by_type": dict(sorted(high_overlap_by_type.items())),
        "cross_type_overlap_rejected_count": cross_type_overlap_rejected_count,
        "rejected_candidate_ids": [rejection.candidate_id for rejection in rejections],
        "candidate_rejections": [
            {
                "candidate_id": rejection.candidate_id,
                "type": rejection.type,
                "reasons": rejection.reasons,
                "details": rejection.details,
            }
            for rejection in rejections
        ],
        "render_failure_count": len(render_failures),
        "render_failures_by_type": dict(sorted(render_failures_by_type.items())),
        "render_failure_errors": dict(render_failure_errors.most_common(10)),
        "render_failures": render_failures,
    }


def _export_paths_by_candidate(exports: Sequence[ExportItem] | None) -> dict[str, dict[str, str | None]]:
    paths: dict[str, dict[str, str | None]] = {}
    for export in exports or []:
        if not export.candidate_id:
            continue
        paths[export.candidate_id] = {
            "video_path": export.video_path,
            "subtitle_path": export.subtitle_path,
            "metadata_path": export.metadata_path,
        }
    return paths


def _selected_item(candidate: Candidate, output_paths: dict[str, dict[str, str | None]]) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "type": candidate.type,
        "title": candidate.title,
        "overlay_title": candidate.overlay_title,
        "title_source": candidate.title_source,
        "duration": _round(candidate.duration),
        "original_start": _round(candidate.original_start),
        "original_end": _round(candidate.original_end),
        "refined_start": _round(candidate.refined_start),
        "refined_end": _round(candidate.refined_end),
        "boundary_refined": candidate.boundary_refined,
        "boundary_refinement_reason": candidate.boundary_refinement_reason,
        "boundary_expansion_seconds": _round(candidate.boundary_expansion_seconds),
        "score": _round(_score(candidate)),
        "rule_score": _round(candidate.rule_score),
        "final_score": _round(_score(candidate)),
        "hard_gate_passed": candidate.hard_gate_passed,
        "below_quality_threshold": candidate.below_quality_threshold,
        "quality_warning": candidate.quality_warning,
        "selection_reason": candidate.selection_reason,
        "overlap_relaxed": candidate.overlap_relaxed,
        "overlap_ratio_used": _round(candidate.overlap_ratio_used),
        "time_cluster": candidate.time_cluster,
        "used_ai_score": candidate.used_ai_score,
        "ai_score": _round(candidate.ai_score),
        "openai_scored": candidate.openai_scored,
        "openai_fallback_used": candidate.openai_fallback_used,
        "openai_score_source": candidate.openai_score_source,
        "openai_not_scored_reason": candidate.openai_not_scored_reason,
        "output_paths": output_paths.get(candidate.id, {}),
    }


def build_selected_clips_summary(
    selection: CandidateSelection | None,
    exports: Sequence[ExportItem] | None,
) -> dict[str, Any]:
    normal = list(selection.normal_clips if selection is not None else [])
    shorts = list(selection.shorts if selection is not None else [])
    selected = [*normal, *shorts]
    output_paths = _export_paths_by_candidate(exports)
    return {
        "selected_normal_count": len(normal),
        "selected_short_count": len(shorts),
        "requested_normal_count": selection.requested_normal_count if selection is not None else 0,
        "requested_short_count": selection.requested_short_count if selection is not None else 0,
        "normal_hard_gate_passed_count": selection.normal_hard_gate_passed_count if selection is not None else 0,
        "short_hard_gate_passed_count": selection.short_hard_gate_passed_count if selection is not None else 0,
        "selected_above_threshold_count": selection.selected_above_threshold_count if selection is not None else 0,
        "selected_below_threshold_backfill_count": (
            selection.selected_below_threshold_backfill_count if selection is not None else 0
        ),
        "overlap_relaxed_count": selection.overlap_relaxed_count if selection is not None else 0,
        "high_overlap_rejected_by_type": selection.high_overlap_rejected_by_type if selection is not None else {},
        "cross_type_overlap_dedupe": selection.cross_type_overlap_dedupe if selection is not None else False,
        "cross_type_overlap_rejected_count": selection.cross_type_overlap_rejected_count if selection is not None else 0,
        "time_cluster_count": selection.time_cluster_count if selection is not None else {},
        "selected_clusters": selection.selected_clusters if selection is not None else {},
        "unfilled_requested_counts": selection.unfilled_requested_counts if selection is not None else {},
        "unfilled_reason_counts": selection.unfilled_reason_counts if selection is not None else {},
        "selected_ids": [candidate.id for candidate in selected],
        "selected_durations": {candidate.id: _round(candidate.duration) for candidate in selected},
        "selected_scores": {candidate.id: _round(_score(candidate)) for candidate in selected},
        "selection_reasons": {candidate.id: candidate.selection_reason for candidate in selected},
        "output_paths": output_paths,
        "normal": [_selected_item(candidate, output_paths) for candidate in normal],
        "shorts": [_selected_item(candidate, output_paths) for candidate in shorts],
    }


def _selected_score_source_item(candidate: Candidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "type": candidate.type,
        "final_score": _round(_score(candidate)),
        "ai_score": _round(candidate.ai_score),
        "rule_score": _round(candidate.rule_score),
        "used_ai_score": candidate.used_ai_score,
        "openai_scored": candidate.openai_scored,
        "openai_fallback_used": candidate.openai_fallback_used,
        "openai_score_source": candidate.openai_score_source,
        "openai_not_scored_reason": candidate.openai_not_scored_reason,
        "risk_flags": candidate.risk_flags,
    }


def build_openai_scoring_summary(
    summary: dict[str, Any],
    selection: CandidateSelection | None,
) -> dict[str, Any]:
    selected = []
    if selection is not None:
        selected = [*selection.normal_clips, *selection.shorts]

    ai_scored = [
        candidate
        for candidate in selected
        if candidate.ai_score is not None and "openai_fallback_rule_score" not in candidate.risk_flags
    ]
    fallback_scored = [
        candidate for candidate in selected if "openai_fallback_rule_score" in candidate.risk_flags
    ]
    rule_only_due_to_limit = [
        candidate for candidate in selected if "openai_not_scored_candidate_limit" in candidate.risk_flags
    ]
    not_scored = [
        candidate
        for candidate in selected
        if candidate.openai_scored is not True and candidate.openai_fallback_used is not True
    ]
    not_scored_reasons = Counter(candidate.openai_not_scored_reason or "unknown" for candidate in not_scored)

    payload = dict(summary)
    candidates_considered = payload.get("candidates_considered")
    candidates_sent = payload.get("candidates_sent_to_openai")
    payload.setdefault("candidates_eligible_for_openai_scoring", candidates_considered)
    payload.setdefault("candidates_selected_for_openai", candidates_sent)
    payload.setdefault("candidates_actually_sent", candidates_sent)
    payload.setdefault("successful_structured_scores", payload.get("successful_scores"))
    payload.setdefault("failed_structured_scores", payload.get("failed_scores"))
    payload.setdefault("avg_latency_seconds", payload.get("average_latency_seconds"))
    payload.setdefault("estimated_text_payload_size", None)
    payload.setdefault("schema_validation_failures", 0)
    payload["selected_ai_score_count"] = len(ai_scored)
    payload["selected_fallback_score_count"] = len(fallback_scored)
    payload["selected_rule_score_only_due_to_limit_count"] = len(rule_only_due_to_limit)
    payload["selected_not_scored_count"] = len(not_scored)
    payload["selected_not_scored_reason_counts"] = dict(sorted(not_scored_reasons.items()))
    payload["final_selected_clips_using_ai_score"] = [
        _selected_score_source_item(candidate) for candidate in ai_scored
    ]
    payload["final_selected_clips_using_fallback_score"] = [
        _selected_score_source_item(candidate) for candidate in fallback_scored
    ]
    payload["final_selected_clips_rule_score_only_due_to_limit"] = [
        _selected_score_source_item(candidate) for candidate in rule_only_due_to_limit
    ]
    payload["final_selected_clips_not_scored"] = [
        _selected_score_source_item(candidate) for candidate in not_scored
    ]
    return payload


def write_generation_summaries(
    output_dir: str | Path,
    *,
    transcript_segments: Sequence[TranscriptSegment] | None = None,
    audio_features: AudioFeatures | None = None,
    normal_candidates: Sequence[Candidate] | None = None,
    short_candidates: Sequence[Candidate] | None = None,
    candidate_generation_summary: dict[str, Any] | None = None,
    scored_candidates: Sequence[Candidate] | None = None,
    selection: CandidateSelection | None = None,
    openai_scoring_summary: dict[str, Any] | None = None,
    normal_result: NormalRenderBatchResult | None = None,
    short_result: ShortRenderBatchResult | None = None,
    exports: Sequence[ExportItem] | None = None,
    transcription_engine: str = "not_run",
    used_fixture_transcript: bool = False,
    transcription_model: str | None = None,
    transcription_language: str | None = None,
) -> list[Path]:
    root = Path(output_dir)
    payloads = {
        TRANSCRIPT_SUMMARY_FILENAME: build_transcript_summary(
            transcript_segments,
            transcription_engine=transcription_engine,
            used_fixture_transcript=used_fixture_transcript,
            transcription_model=transcription_model,
            transcription_language=transcription_language,
        ),
        AUDIO_FEATURE_SUMMARY_FILENAME: build_audio_feature_summary(audio_features),
        CANDIDATE_SUMMARY_FILENAME: build_candidate_summary(
            normal_candidates,
            short_candidates,
            scored_candidates,
            selection=selection,
        ),
        CANDIDATE_GENERATION_SUMMARY_FILENAME: candidate_generation_summary or {},
        REJECTION_SUMMARY_FILENAME: build_rejection_summary(selection, normal_result, short_result),
        SELECTED_CLIPS_SUMMARY_FILENAME: build_selected_clips_summary(selection, exports),
    }
    if openai_scoring_summary is not None:
        payloads[OPENAI_SCORING_SUMMARY_FILENAME] = build_openai_scoring_summary(
            openai_scoring_summary,
            selection,
        )
    return [_write_json(root / filename, payload) for filename, payload in payloads.items()]
