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
REJECTION_SUMMARY_FILENAME = "rejection_summary.json"
SELECTED_CLIPS_SUMMARY_FILENAME = "selected_clips_summary.json"

SUMMARY_FILENAMES = [
    TRANSCRIPT_SUMMARY_FILENAME,
    AUDIO_FEATURE_SUMMARY_FILENAME,
    CANDIDATE_SUMMARY_FILENAME,
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
        "duration": _round(candidate.duration),
        "rule_score": _round(candidate.rule_score),
        "final_score": _round(_score(candidate)),
        "hard_gate_passed": candidate.hard_gate_passed,
        "below_quality_threshold": candidate.below_quality_threshold,
        "quality_warning": candidate.quality_warning,
        "selection_reason": candidate.selection_reason,
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
        "selected_above_threshold_count": selection.selected_above_threshold_count if selection is not None else 0,
        "selected_below_threshold_backfill_count": (
            selection.selected_below_threshold_backfill_count if selection is not None else 0
        ),
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
    for rejection in rejections:
        rejected_by_type[str(rejection.type)] += 1
        rejection_reasons.update(rejection.reasons)

    render_failures = _render_failures(normal_result, short_result)
    render_failures_by_type = Counter(failure["type"] for failure in render_failures)
    render_failure_errors = Counter(failure["error"] for failure in render_failures)

    return {
        "total_rejected": len(rejections),
        "rejected_by_type": dict(sorted(rejected_by_type.items())),
        "rejected_by_reason": dict(sorted(rejection_reasons.items())),
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
        "duration": _round(candidate.duration),
        "score": _round(_score(candidate)),
        "rule_score": _round(candidate.rule_score),
        "final_score": _round(_score(candidate)),
        "hard_gate_passed": candidate.hard_gate_passed,
        "below_quality_threshold": candidate.below_quality_threshold,
        "quality_warning": candidate.quality_warning,
        "selection_reason": candidate.selection_reason,
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
        "selected_above_threshold_count": selection.selected_above_threshold_count if selection is not None else 0,
        "selected_below_threshold_backfill_count": (
            selection.selected_below_threshold_backfill_count if selection is not None else 0
        ),
        "selected_ids": [candidate.id for candidate in selected],
        "selected_durations": {candidate.id: _round(candidate.duration) for candidate in selected},
        "selected_scores": {candidate.id: _round(_score(candidate)) for candidate in selected},
        "selection_reasons": {candidate.id: candidate.selection_reason for candidate in selected},
        "output_paths": output_paths,
        "normal": [_selected_item(candidate, output_paths) for candidate in normal],
        "shorts": [_selected_item(candidate, output_paths) for candidate in shorts],
    }


def write_generation_summaries(
    output_dir: str | Path,
    *,
    transcript_segments: Sequence[TranscriptSegment] | None = None,
    audio_features: AudioFeatures | None = None,
    normal_candidates: Sequence[Candidate] | None = None,
    short_candidates: Sequence[Candidate] | None = None,
    scored_candidates: Sequence[Candidate] | None = None,
    selection: CandidateSelection | None = None,
    normal_result: NormalRenderBatchResult | None = None,
    short_result: ShortRenderBatchResult | None = None,
    exports: Sequence[ExportItem] | None = None,
    transcription_engine: str = "not_run",
    used_fixture_transcript: bool = False,
) -> list[Path]:
    root = Path(output_dir)
    payloads = {
        TRANSCRIPT_SUMMARY_FILENAME: build_transcript_summary(
            transcript_segments,
            transcription_engine=transcription_engine,
            used_fixture_transcript=used_fixture_transcript,
        ),
        AUDIO_FEATURE_SUMMARY_FILENAME: build_audio_feature_summary(audio_features),
        CANDIDATE_SUMMARY_FILENAME: build_candidate_summary(
            normal_candidates,
            short_candidates,
            scored_candidates,
            selection=selection,
        ),
        REJECTION_SUMMARY_FILENAME: build_rejection_summary(selection, normal_result, short_result),
        SELECTED_CLIPS_SUMMARY_FILENAME: build_selected_clips_summary(selection, exports),
    }
    return [_write_json(root / filename, payload) for filename, payload in payloads.items()]
