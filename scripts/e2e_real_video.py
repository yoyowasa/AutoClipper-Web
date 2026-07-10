from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from e2e_summary import print_job_summaries
from e2e_sample_video import _absolute_url, _download, _request_json, _upload_file, _wait_http
from generate_sample_video import _container_storage_path
from smoke_runtime import ROOT, check_services, compose_exec, docker_env


MIN_TRANSCRIPT_CHARS = 20
FIXTURE_TRANSCRIPT_MARKER = "Why automation mistakes matter before launch."
DEFAULT_VALIDATION_PROFILE = "default"
VALIDATION_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "timeout": 1800,
        "normal_count": 1,
        "short_count": 1,
        "mode": "low_cost",
        "normal_min_duration": 90.0,
        "normal_max_duration": 600.0,
        "short_min_duration": 20.0,
        "short_max_duration": 75.0,
        "selection_policy": "fill_requested",
        "openai_candidate_limit": 20,
        "openai_model": "gpt-5.5",
        "openai_fallback_to_rule_score": True,
        "ensure_selected_openai_scored": None,
        "openai_finalist_scoring_limit": None,
    },
    "30min": {
        "timeout": 7200,
        "normal_count": 2,
        "short_count": 3,
        "mode": "low_cost",
        "normal_min_duration": 90.0,
        "normal_max_duration": 600.0,
        "short_min_duration": 20.0,
        "short_max_duration": 75.0,
        "selection_policy": "fill_requested",
        "openai_candidate_limit": 20,
        "openai_model": "gpt-5.5",
        "openai_fallback_to_rule_score": True,
        "ensure_selected_openai_scored": None,
        "openai_finalist_scoring_limit": None,
    },
    "30min_high_quality": {
        "timeout": 7200,
        "normal_count": 2,
        "short_count": 3,
        "mode": "high_quality",
        "normal_min_duration": 90.0,
        "normal_max_duration": 600.0,
        "short_min_duration": 20.0,
        "short_max_duration": 75.0,
        "selection_policy": "fill_requested",
        "use_openai_scoring": True,
        "openai_candidate_limit": 20,
        "openai_model": "gpt-5.5",
        "openai_fallback_to_rule_score": True,
        "ensure_selected_openai_scored": True,
        "openai_finalist_scoring_limit": 7,
    },
}
REQUIRED_RESULT_ARTIFACTS = [
    "selected_clips.json",
    "candidate_summary.json",
    "selected_clips_summary.json",
]


@dataclass(frozen=True)
class ProbeResult:
    width: int
    height: int
    duration: float


@dataclass(frozen=True)
class TimedJobResult:
    final_status: dict[str, Any]
    status_times: dict[str, float]
    poll_started_at: float
    poll_finished_at: float


PHASE_END_STATUSES = {
    "transcribing": ["detecting_scenes", "generating_candidates", "scoring_candidates", "selecting_clips", "failed"],
    "detecting_scenes": ["generating_candidates", "scoring_candidates", "selecting_clips", "failed"],
    "generating_candidates": ["scoring_candidates", "selecting_clips", "rendering_normal_clips", "rendering_shorts", "failed"],
    "scoring_candidates": ["selecting_clips", "rendering_normal_clips", "rendering_shorts", "packaging_zip", "failed"],
    "selecting_clips": ["rendering_normal_clips", "rendering_shorts", "packaging_zip", "completed", "failed"],
    "rendering_normal_clips": ["rendering_shorts", "packaging_zip", "completed", "failed"],
    "rendering_shorts": ["packaging_zip", "completed", "failed"],
    "packaging_zip": ["completed", "failed"],
}


def parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean value, got: {value}")


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def probability_float(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a real spoken-video E2E without fixture transcript.")
    parser.add_argument("--video", type=Path, required=True, help="Path to an MP4 with clear spoken audio.")
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument(
        "--validation-profile",
        default=DEFAULT_VALIDATION_PROFILE,
        choices=sorted(VALIDATION_PROFILES),
        help="Preset E2E defaults. Use 30min for long real-video validation.",
    )
    parser.add_argument("--timeout", type=int, default=None, help="Seconds to wait for job completion.")
    parser.add_argument("--normal-count", type=non_negative_int, default=None)
    parser.add_argument("--short-count", type=non_negative_int, default=None)
    parser.add_argument("--mode", default=None, choices=["low_cost", "fast", "high_quality"])
    parser.add_argument("--profile", default="talk", choices=["auto", "talk", "gameplay", "lecture"])
    parser.add_argument(
        "--whisper-model-size",
        default="base",
        choices=["base", "small", "medium", "large-v3"],
        help="faster-whisper model used by the worker. Default preserves current behavior.",
    )
    parser.add_argument(
        "--transcription-language",
        default="auto",
        choices=["auto", "ja"],
        help="Use auto detection or force Japanese transcription.",
    )
    parser.add_argument("--subtitle-correction-mode", default="off", choices=["off", "openai"])
    parser.add_argument("--subtitle-correction-model", default="gpt-5.5")
    parser.add_argument("--subtitle-correction-min-confidence", type=probability_float, default=0.9)
    parser.add_argument("--subtitle-correction-batch-size", type=positive_int, default=40)
    parser.add_argument("--subtitle-correction-context-segments", type=non_negative_int, default=2)
    parser.add_argument("--subtitle-correction-fallback-enabled", nargs="?", const=True, default=True, type=parse_bool)
    parser.add_argument(
        "--no-subtitle-correction-fallback",
        dest="subtitle_correction_fallback_enabled",
        action="store_false",
    )
    parser.add_argument("--burn-subtitles", nargs="?", const=True, default=True, type=parse_bool)
    parser.add_argument("--no-burn-subtitles", dest="burn_subtitles", action="store_false")
    parser.add_argument("--normal-min-duration", type=positive_float, default=None)
    parser.add_argument("--normal-max-duration", type=positive_float, default=None)
    parser.add_argument("--short-min-duration", type=positive_float, default=None)
    parser.add_argument("--short-max-duration", type=positive_float, default=None)
    parser.add_argument(
        "--short-overlay-title-mode",
        default="auto",
        choices=["auto", "always", "high_quality_only", "never"],
    )
    parser.add_argument("--selection-policy", default=None, choices=["fill_requested", "strict_quality"])
    parser.add_argument("--use-openai-scoring", nargs="?", const=True, default=None, type=parse_bool)
    parser.add_argument("--openai-candidate-limit", type=non_negative_int, default=None)
    parser.add_argument("--openai-model", default=None)
    parser.add_argument("--openai-fallback-to-rule-score", nargs="?", const=True, default=None, type=parse_bool)
    parser.add_argument("--no-openai-fallback-to-rule-score", dest="openai_fallback_to_rule_score", action="store_false")
    parser.add_argument("--ensure-selected-openai-scored", nargs="?", const=True, default=None, type=parse_bool)
    parser.add_argument("--openai-finalist-scoring-limit", type=non_negative_int, default=None)
    parser.add_argument("--max-raw-candidates-per-type", type=non_negative_int, default=None)
    parser.add_argument("--max-kept-candidates-per-type", type=non_negative_int, default=None)
    parser.add_argument("--max-candidates-per-time-bucket", type=non_negative_int, default=None)
    parser.add_argument("--candidate-time-bucket-seconds", type=positive_float, default=None)
    parser.add_argument("--max-candidate-generation-memory-mb", type=non_negative_int, default=None)
    parser.add_argument("--candidate-chunk-seconds", type=positive_float, default=None)
    parser.add_argument("--candidate-chunk-overlap-seconds", type=non_negative_float, default=None)
    parser.add_argument("--enable-transcript-post-processing", nargs="?", const=True, default=None, type=parse_bool)
    parser.add_argument(
        "--disable-transcript-post-processing",
        dest="enable_transcript_post_processing",
        action="store_false",
    )
    parser.add_argument(
        "--transcript-replacements-json",
        type=Path,
        default=None,
        help="Optional JSON object mapping transcript text replacements.",
    )
    return parser


def apply_validation_profile_defaults(args: argparse.Namespace) -> argparse.Namespace:
    defaults = VALIDATION_PROFILES[args.validation_profile]
    for name, value in defaults.items():
        if getattr(args, name) is None:
            setattr(args, name, value)
    return args


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return apply_validation_profile_defaults(build_parser().parse_args(argv))


def resolve_input_video(video_path: Path) -> Path:
    resolved = video_path if video_path.is_absolute() else Path.cwd() / video_path
    resolved = resolved.resolve()
    if not resolved.is_file():
        raise RuntimeError(f"input video not found: {resolved}")
    return resolved


def build_job_settings(args: argparse.Namespace) -> dict[str, Any]:
    if args.normal_max_duration < args.normal_min_duration:
        raise RuntimeError("normal-max-duration must be >= normal-min-duration")
    if args.short_max_duration < args.short_min_duration:
        raise RuntimeError("short-max-duration must be >= short-min-duration")

    use_openai_scoring = args.mode == "high_quality" if args.use_openai_scoring is None else args.use_openai_scoring
    ensure_selected_openai_scored = (
        args.mode == "high_quality"
        if args.ensure_selected_openai_scored is None
        else bool(args.ensure_selected_openai_scored)
    )
    finalist_limit = args.openai_finalist_scoring_limit
    if finalist_limit is None:
        requested_count = int(args.normal_count) + int(args.short_count)
        finalist_limit = requested_count + 2 if requested_count > 0 else 0
    settings = {
        "mode": args.mode,
        "profile": args.profile,
        "whisperModelSize": args.whisper_model_size,
        "transcriptionLanguage": args.transcription_language,
        "subtitleCorrectionMode": args.subtitle_correction_mode,
        "subtitleCorrectionModel": args.subtitle_correction_model,
        "subtitleCorrectionMinConfidence": args.subtitle_correction_min_confidence,
        "subtitleCorrectionBatchSize": args.subtitle_correction_batch_size,
        "subtitleCorrectionContextSegments": args.subtitle_correction_context_segments,
        "subtitleCorrectionFallbackEnabled": args.subtitle_correction_fallback_enabled,
        "normalClipCount": args.normal_count,
        "shortCount": args.short_count,
        "normalMinDuration": args.normal_min_duration,
        "normalMaxDuration": args.normal_max_duration,
        "shortMinDuration": args.short_min_duration,
        "shortMaxDuration": args.short_max_duration,
        "selectionPolicy": args.selection_policy,
        "burnSubtitles": bool(args.burn_subtitles),
        "shortLayout": "auto",
        "shortOverlayTitleMode": args.short_overlay_title_mode,
        "useOpenAIScoring": use_openai_scoring,
        "openaiCandidateLimit": args.openai_candidate_limit,
        "openaiModel": args.openai_model,
        "openaiFallbackToRuleScore": bool(args.openai_fallback_to_rule_score),
        "ensureSelectedOpenAIScored": ensure_selected_openai_scored,
        "openaiFinalistScoringLimit": finalist_limit,
        "normalizeAudio": False,
        "e2eFixtureTranscript": False,
    }
    optional_settings = {
        "maxRawCandidatesPerType": args.max_raw_candidates_per_type,
        "maxKeptCandidatesPerType": args.max_kept_candidates_per_type,
        "maxCandidatesPerTimeBucket": args.max_candidates_per_time_bucket,
        "candidateTimeBucketSeconds": args.candidate_time_bucket_seconds,
        "maxCandidateGenerationMemoryMb": args.max_candidate_generation_memory_mb,
        "candidateChunkSeconds": args.candidate_chunk_seconds,
        "candidateChunkOverlapSeconds": args.candidate_chunk_overlap_seconds,
        "enableTranscriptPostProcessing": args.enable_transcript_post_processing,
    }
    settings.update({key: value for key, value in optional_settings.items() if value is not None})
    if args.transcript_replacements_json is not None:
        replacements_path = args.transcript_replacements_json.resolve()
        replacements = json.loads(replacements_path.read_text(encoding="utf-8"))
        if not isinstance(replacements, dict):
            raise RuntimeError(f"transcript replacements must be a JSON object: {replacements_path}")
        settings["transcriptReplacements"] = {str(key): str(value) for key, value in replacements.items()}
    return settings


def format_seconds(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}s"


def phase_duration(status_times: dict[str, float], start_status: str, end_statuses: Sequence[str]) -> float | None:
    start_time = status_times.get(start_status)
    if start_time is None:
        return None
    candidates = [status_times[status] for status in end_statuses if status in status_times and status_times[status] >= start_time]
    if not candidates:
        return None
    return max(0.0, min(candidates) - start_time)


def render_duration(status_times: dict[str, float]) -> float | None:
    starts = [
        status_times[status]
        for status in ("rendering_normal_clips", "rendering_shorts")
        if status in status_times
    ]
    if not starts:
        return None
    start_time = min(starts)
    candidates = [
        status_times[status]
        for status in ("packaging_zip", "completed", "failed")
        if status in status_times and status_times[status] >= start_time
    ]
    if not candidates:
        return None
    return max(0.0, min(candidates) - start_time)


def poll_job_with_timings(backend_url: str, job_id: str, timeout_seconds: int) -> TimedJobResult:
    deadline = time.monotonic() + timeout_seconds
    status_times: dict[str, float] = {}
    poll_started_at = time.monotonic()
    last_status = ""
    while time.monotonic() < deadline:
        payload = _request_json(f"{backend_url}/api/jobs/{job_id}")
        now = time.monotonic()
        status = str(payload["status"])
        status_times.setdefault(status, now)
        if status != last_status:
            print(f"job {job_id}: {status} {payload.get('progress')}%")
            last_status = status
        if status in {"completed", "failed"}:
            return TimedJobResult(
                final_status=payload,
                status_times=status_times,
                poll_started_at=poll_started_at,
                poll_finished_at=now,
            )
        time.sleep(2)
    raise RuntimeError(f"job did not finish within {timeout_seconds} seconds: {job_id}")


def runtime_metrics(
    *,
    upload_seconds: float,
    job_timing: TimedJobResult,
    total_seconds: float,
) -> dict[str, float | None]:
    return {
        "upload_time": upload_seconds,
        "transcription_time": phase_duration(
            job_timing.status_times,
            "transcribing",
            PHASE_END_STATUSES["transcribing"],
        ),
        "scene_detection_time": phase_duration(
            job_timing.status_times,
            "detecting_scenes",
            PHASE_END_STATUSES["detecting_scenes"],
        ),
        "candidate_generation_time": phase_duration(
            job_timing.status_times,
            "generating_candidates",
            PHASE_END_STATUSES["generating_candidates"],
        ),
        "scoring_time": phase_duration(
            job_timing.status_times,
            "scoring_candidates",
            PHASE_END_STATUSES["scoring_candidates"],
        ),
        "selection_time": phase_duration(
            job_timing.status_times,
            "selecting_clips",
            PHASE_END_STATUSES["selecting_clips"],
        ),
        "normal_render_time": phase_duration(
            job_timing.status_times,
            "rendering_normal_clips",
            PHASE_END_STATUSES["rendering_normal_clips"],
        ),
        "short_render_time": phase_duration(
            job_timing.status_times,
            "rendering_shorts",
            PHASE_END_STATUSES["rendering_shorts"],
        ),
        "zip_packaging_time": phase_duration(
            job_timing.status_times,
            "packaging_zip",
            PHASE_END_STATUSES["packaging_zip"],
        ),
        "render_time": render_duration(job_timing.status_times),
        "total_time": total_seconds,
    }


def print_runtime_metrics(metrics: dict[str, float | None]) -> None:
    print("runtime metrics:")
    print(f"  upload_time={format_seconds(metrics.get('upload_time'))}")
    print(f"  transcription_time={format_seconds(metrics.get('transcription_time'))}")
    print(f"  scene_detection_time={format_seconds(metrics.get('scene_detection_time'))}")
    print(f"  candidate_generation_time={format_seconds(metrics.get('candidate_generation_time'))}")
    print(f"  scoring_time={format_seconds(metrics.get('scoring_time'))}")
    print(f"  selection_time={format_seconds(metrics.get('selection_time'))}")
    print(f"  normal_render_time={format_seconds(metrics.get('normal_render_time'))}")
    print(f"  short_render_time={format_seconds(metrics.get('short_render_time'))}")
    print(f"  zip_packaging_time={format_seconds(metrics.get('zip_packaging_time'))}")
    print(f"  total_time={format_seconds(metrics.get('total_time'))}")


def job_output_dir(job_id: str) -> Path:
    return ROOT / "storage" / "outputs" / job_id


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_summary(output_dir: Path, filename: str) -> dict[str, Any]:
    path = output_dir / filename
    if not path.is_file():
        return {}
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def pipeline_metrics(output_dir: Path) -> dict[str, Any]:
    video_metadata = read_summary(output_dir, "video_metadata.json")
    transcript = read_summary(output_dir, "transcript_summary.json")
    candidates = read_summary(output_dir, "candidate_summary.json")
    candidate_generation = read_summary(output_dir, "candidate_generation_summary.json")
    selected = read_summary(output_dir, "selected_clips_summary.json")
    rejections = read_summary(output_dir, "rejection_summary.json")
    zip_path = output_dir / "download.zip"
    requested_normal = selected.get("requested_normal_count", candidates.get("requested_normal_count"))
    selected_normal = selected.get("selected_normal_count")
    requested_short = selected.get("requested_short_count", candidates.get("requested_short_count"))
    selected_short = selected.get("selected_short_count")
    return {
        "video_duration": video_metadata.get("duration"),
        "transcript_segment_count": transcript.get("segment_count"),
        "total_transcript_text_length": transcript.get("total_text_length"),
        "total_candidates_count": candidates.get("total_candidates"),
        "short_candidates_count": candidates.get("short_candidates"),
        "normal_candidates_count": candidates.get("normal_candidates"),
        "candidate_generation_chunks_processed": candidate_generation.get("chunks_processed"),
        "candidate_generation_raw_considered": candidate_generation.get("raw_candidates_considered"),
        "candidate_generation_kept_by_type": candidate_generation.get("candidates_kept_by_type"),
        "candidate_generation_dropped_due_to_cap": candidate_generation.get("candidates_dropped_due_to_cap"),
        "candidate_generation_dropped_due_to_duplicate": candidate_generation.get("candidates_dropped_due_to_duplicate"),
        "candidate_generation_peak_memory_mb": candidate_generation.get("peak_memory_mb"),
        "candidate_generation_memory_guard_triggered": candidate_generation.get("memory_guard_triggered"),
        "candidate_generation_caps": candidate_generation.get("configured_caps"),
        "hard_gate_passed_count": candidates.get("hard_gate_passed_count"),
        "hard_gate_rejected_count": candidates.get("hard_gate_rejected_count"),
        "requested_normal_count": requested_normal,
        "selected_normal_count": selected_normal,
        "requested_short_count": requested_short,
        "selected_short_count": selected_short,
        "selected_normal_ratio": _ratio(selected_normal, requested_normal),
        "selected_short_ratio": _ratio(selected_short, requested_short),
        "backfilled_count": selected.get(
            "selected_below_threshold_backfill_count",
            candidates.get("selected_below_threshold_backfill_count"),
        ),
        "overlap_relaxed_count": selected.get("overlap_relaxed_count", candidates.get("overlap_relaxed_count")),
        "overlap_relaxation_used": bool(selected.get("overlap_relaxed_count", 0)),
        "high_overlap_rejected_by_type": selected.get(
            "high_overlap_rejected_by_type",
            rejections.get("high_overlap_rejected_by_type", {}),
        ),
        "cross_type_overlap_rejected_count": selected.get(
            "cross_type_overlap_rejected_count",
            rejections.get("cross_type_overlap_rejected_count"),
        ),
        "unfilled_requested_counts": selected.get("unfilled_requested_counts", {}),
        "unfilled_reason_counts": selected.get("unfilled_reason_counts", {}),
        "time_cluster_count": selected.get("time_cluster_count", candidates.get("time_cluster_count", {})),
        "selected_clusters": selected.get("selected_clusters", candidates.get("selected_clusters", {})),
        "render_failures_count": rejections.get("render_failure_count"),
        "zip_size_bytes": zip_path.stat().st_size if zip_path.is_file() else None,
    }


def _ratio(selected: Any, requested: Any) -> str:
    try:
        selected_int = int(selected)
        requested_int = int(requested)
    except (TypeError, ValueError):
        return "n/a"
    if requested_int <= 0:
        return "n/a"
    return f"{selected_int}/{requested_int}"


def print_pipeline_metrics(metrics: dict[str, Any]) -> None:
    print("pipeline metrics:")
    print(f"  video_duration={metrics.get('video_duration')}")
    print(f"  transcript_segment_count={metrics.get('transcript_segment_count')}")
    print(f"  total_transcript_text_length={metrics.get('total_transcript_text_length')}")
    print(f"  total_candidates_count={metrics.get('total_candidates_count')}")
    print(f"  short_candidates_count={metrics.get('short_candidates_count')}")
    print(f"  normal_candidates_count={metrics.get('normal_candidates_count')}")
    print(f"  candidate_generation_chunks_processed={metrics.get('candidate_generation_chunks_processed')}")
    print(f"  candidate_generation_raw_considered={metrics.get('candidate_generation_raw_considered')}")
    print(f"  candidate_generation_kept_by_type={metrics.get('candidate_generation_kept_by_type')}")
    print(f"  candidate_generation_dropped_due_to_cap={metrics.get('candidate_generation_dropped_due_to_cap')}")
    print(f"  candidate_generation_dropped_due_to_duplicate={metrics.get('candidate_generation_dropped_due_to_duplicate')}")
    print(f"  candidate_generation_peak_memory_mb={metrics.get('candidate_generation_peak_memory_mb')}")
    print(f"  candidate_generation_memory_guard_triggered={metrics.get('candidate_generation_memory_guard_triggered')}")
    print(f"  candidate_generation_caps={metrics.get('candidate_generation_caps')}")
    print(f"  hard_gate_passed_count={metrics.get('hard_gate_passed_count')}")
    print(f"  hard_gate_rejected_count={metrics.get('hard_gate_rejected_count')}")
    print(
        "  selected_normal_count="
        f"{metrics.get('selected_normal_count')} "
        f"requested={metrics.get('requested_normal_count')} "
        f"ratio={metrics.get('selected_normal_ratio')}"
    )
    print(
        "  selected_short_count="
        f"{metrics.get('selected_short_count')} "
        f"requested={metrics.get('requested_short_count')} "
        f"ratio={metrics.get('selected_short_ratio')}"
    )
    print(f"  backfilled_count={metrics.get('backfilled_count')}")
    print(f"  overlap_relaxed_count={metrics.get('overlap_relaxed_count')}")
    print(f"  overlap_relaxation_used={metrics.get('overlap_relaxation_used')}")
    print(f"  high_overlap_rejected_by_type={metrics.get('high_overlap_rejected_by_type')}")
    print(f"  cross_type_overlap_rejected_count={metrics.get('cross_type_overlap_rejected_count')}")
    print(f"  time_cluster_count={metrics.get('time_cluster_count')}")
    print(f"  selected_clusters={metrics.get('selected_clusters')}")
    print(f"  unfilled_requested_counts={metrics.get('unfilled_requested_counts')}")
    print(f"  unfilled_reason_counts={metrics.get('unfilled_reason_counts')}")
    print(f"  render_failures_count={metrics.get('render_failures_count')}")
    print(f"  zip_size_bytes={metrics.get('zip_size_bytes')}")


def use_openai_scoring(settings: dict[str, Any]) -> bool:
    return bool(settings.get("useOpenAIScoring"))


def use_openai_subtitle_correction(settings: dict[str, Any]) -> bool:
    return settings.get("subtitleCorrectionMode") == "openai"


def check_openai_api_key_available(env: dict[str, str]) -> None:
    try:
        compose_exec("worker", ["sh", "-lc", 'test -n "${OPENAI_API_KEY:-}"'], env=env)
    except Exception as exc:
        raise RuntimeError(
            "openai_configuration_missing: OPENAI_API_KEY is required for OpenAI scoring or subtitle correction. "
            "Set OPENAI_API_KEY in .env, then run docker compose up -d --build."
        ) from exc


def validate_openai_scoring_summary(output_dir: Path) -> dict[str, Any]:
    summary_path = output_dir / "openai_scoring_summary.json"
    if not summary_path.is_file():
        raise RuntimeError(f"openai_scoring_summary.json not found: {summary_path}")
    payload = read_json(summary_path)
    if not isinstance(payload, dict):
        raise RuntimeError("openai_scoring_summary.json must contain an object")
    candidates_sent = int(payload.get("candidates_sent_to_openai") or 0)
    successful_scores = int(payload.get("successful_scores") or 0)
    final_calls = int(payload.get("total_api_calls") or 0)
    if candidates_sent <= 0:
        raise RuntimeError("OpenAI scoring summary shows zero candidates sent")
    if final_calls <= 0:
        raise RuntimeError("OpenAI scoring summary shows zero API calls")
    if successful_scores <= 0:
        raise RuntimeError("OpenAI scoring summary shows zero successful structured scores")
    print(
        "openai scoring: "
        f"model={payload.get('model')} "
        f"candidate_limit={payload.get('candidate_limit')} "
        f"finalist_limit={payload.get('finalist_scoring_limit')} "
        f"eligible={payload.get('candidates_eligible_for_openai_scoring')} "
        f"selected_for_openai={payload.get('candidates_selected_for_openai')} "
        f"preselection={payload.get('candidates_sent_preselection')} "
        f"finalists={payload.get('candidates_sent_as_finalists')} "
        f"sent={candidates_sent} "
        f"success={successful_scores} "
        f"failed={payload.get('failed_scores')} "
        f"fallback={payload.get('fallback_scores')} "
        f"schema_failures={payload.get('schema_validation_failures')} "
        f"calls={final_calls} "
        f"avg_latency={payload.get('avg_latency_seconds', payload.get('average_latency_seconds'))} "
        f"max_latency={payload.get('max_latency_seconds')} "
        f"total_latency={payload.get('total_latency_seconds')} "
        f"text_size={payload.get('estimated_text_payload_size')}"
    )
    print(
        "openai selected clips: "
        f"ai_score={payload.get('selected_ai_score_count')} "
        f"fallback_score={payload.get('selected_fallback_score_count')} "
        f"not_scored={payload.get('selected_not_scored_count')} "
        f"rule_only_due_to_limit={payload.get('selected_rule_score_only_due_to_limit_count')} "
        f"not_scored_reasons={payload.get('selected_not_scored_reason_counts')}"
    )
    return payload


def validate_transcript_correction_summary(output_dir: Path) -> dict[str, Any]:
    summary_path = output_dir / "transcript_correction_summary.json"
    deterministic_path = output_dir / "deterministic_transcript_segments.json"
    corrected_path = output_dir / "openai_corrected_transcript_segments.json"
    final_path = output_dir / "transcript_segments.json"
    diff_path = output_dir / "transcript_correction_diff.md"
    for path in (summary_path, deterministic_path, corrected_path, final_path, diff_path):
        if not path.is_file():
            raise RuntimeError(f"subtitle correction artifact not found: {path}")
    summary = read_json(summary_path)
    deterministic = read_json(deterministic_path)
    corrected = read_json(corrected_path)
    final = read_json(final_path)
    if not isinstance(summary, dict) or not summary.get("enabled"):
        raise RuntimeError("transcript correction summary does not show enabled correction")
    if not all(isinstance(value, list) for value in (deterministic, corrected, final)):
        raise RuntimeError("transcript correction artifacts must contain segment lists")
    if len(deterministic) != len(corrected) or len(corrected) != len(final):
        raise RuntimeError("subtitle correction changed the segment count")
    for before, after in zip(deterministic, corrected, strict=True):
        if before.get("start") != after.get("start") or before.get("end") != after.get("end"):
            raise RuntimeError("subtitle correction changed segment timestamps")
    if corrected != final:
        raise RuntimeError("final transcript does not match corrected transcript")
    if not summary.get("fallback_used") and int(summary.get("api_call_count") or 0) <= 0:
        raise RuntimeError("subtitle correction summary shows zero API calls")
    print(
        "subtitle correction: "
        f"model={summary.get('model')} "
        f"segments={summary.get('input_segment_count')} "
        f"corrected={summary.get('corrected_segment_count')} "
        f"unchanged={summary.get('unchanged_segment_count')} "
        f"fallback={summary.get('fallback_used')} "
        f"calls={summary.get('api_call_count')} "
        f"seconds={summary.get('processing_seconds')}"
    )
    return summary


def transcript_text_from_segments(segments: Any) -> str:
    if not isinstance(segments, list):
        raise RuntimeError("transcript_segments.json must contain a list")
    texts = [str(segment.get("text", "")).strip() for segment in segments if isinstance(segment, dict)]
    return " ".join(text for text in texts if text).strip()


def validate_transcript_artifact(output_dir: Path, min_chars: int = MIN_TRANSCRIPT_CHARS) -> str:
    transcript_path = output_dir / "transcript_segments.json"
    if not transcript_path.is_file():
        raise RuntimeError(f"transcript_segments.json not found: {transcript_path}")
    segments = read_json(transcript_path)
    text = transcript_text_from_segments(segments)
    if len(text) <= min_chars:
        raise RuntimeError(f"transcript text too short: {len(text)} chars")
    if FIXTURE_TRANSCRIPT_MARKER in text:
        raise RuntimeError("fixture transcript marker was found; e2eFixtureTranscript was not disabled")
    print(f"transcript: {len(segments)} segments, {len(text)} chars")
    print("fixture transcript: disabled and not detected in transcript artifact")
    return text


def _json_list_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    payload = read_json(path)
    return len(payload) if isinstance(payload, list) else None


def _selected_summary(output_dir: Path) -> tuple[int | None, str]:
    path = output_dir / "selected_clips.json"
    if not path.is_file():
        return None, "selected_clips.json missing"
    payload = read_json(path)
    normal = payload.get("normalClips", []) if isinstance(payload, dict) else []
    shorts = payload.get("shorts", []) if isinstance(payload, dict) else []
    rejected = payload.get("rejectedCandidates", []) if isinstance(payload, dict) else []
    reason_counter: Counter[str] = Counter()
    for item in rejected:
        if isinstance(item, dict):
            reason_counter.update(str(reason) for reason in item.get("reasons", []))
    reason_text = ", ".join(f"{reason}={count}" for reason, count in sorted(reason_counter.items()))
    summary = f"selected normal={len(normal)} shorts={len(shorts)} rejected={len(rejected)}"
    if reason_text:
        summary = f"{summary}; rejection reasons: {reason_text}"
    return len(normal) + len(shorts), summary


def _render_failure_summary(output_dir: Path) -> tuple[int | None, str]:
    path = output_dir / "render_failures.json"
    if not path.is_file():
        return None, "render_failures.json missing"
    payload = read_json(path)
    if not isinstance(payload, list):
        return None, "render_failures.json is not a list"
    errors = Counter(str(item.get("error", "unknown")) for item in payload if isinstance(item, dict))
    error_text = ", ".join(f"{error}={count}" for error, count in errors.most_common(3))
    return len(payload), f"render failures={len(payload)}" + (f"; {error_text}" if error_text else "")


def diagnose_no_clips(job_id: str, final_status: dict[str, Any] | None = None) -> str:
    output_dir = job_output_dir(job_id)
    parts: list[str] = []
    error = (final_status or {}).get("error") or {}
    code = str(error.get("code", "")).strip()
    message = str(error.get("message", "")).strip()
    if code:
        parts.append(f"job error={code}: {message}")

    transcript_path = output_dir / "transcript_segments.json"
    if not transcript_path.is_file():
        parts.append("cause=no transcript: transcript_segments.json missing")
        return "; ".join(parts)
    try:
        transcript_text = transcript_text_from_segments(read_json(transcript_path))
    except Exception as exc:
        parts.append(f"cause=no transcript: transcript artifact unreadable: {exc}")
        return "; ".join(parts)
    if len(transcript_text) <= MIN_TRANSCRIPT_CHARS:
        parts.append(f"cause=no transcript: transcript text too short ({len(transcript_text)} chars)")
        return "; ".join(parts)

    candidates_count = _json_list_count(output_dir / "candidates.json")
    if code == "no_candidates_found" or candidates_count == 0:
        parts.append(f"cause=no candidates: candidates={candidates_count}")
        return "; ".join(parts)
    if candidates_count is not None:
        parts.append(f"candidates={candidates_count}")

    selected_count, selected_summary = _selected_summary(output_dir)
    parts.append(selected_summary)
    if selected_count == 0:
        parts.append("cause=quality gate rejection: no selected clips")
        return "; ".join(parts)

    render_failure_count, render_summary = _render_failure_summary(output_dir)
    parts.append(render_summary)
    if code == "no_usable_output" or (render_failure_count and render_failure_count > 0):
        parts.append("cause=render failure: selected clips did not produce usable exports")
        return "; ".join(parts)

    parts.append("cause=unknown: inspect worker logs and job artifacts")
    return "; ".join(parts)


def validate_selected_artifact(output_dir: Path) -> None:
    selected_count, selected_summary = _selected_summary(output_dir)
    if selected_count is None:
        raise RuntimeError(selected_summary)
    if selected_count <= 0:
        raise RuntimeError(f"selected_clips.json has no selected clips: {selected_summary}")
    print(selected_summary)


def validate_required_result_artifacts(output_dir: Path) -> None:
    missing = [filename for filename in REQUIRED_RESULT_ARTIFACTS if not (output_dir / filename).is_file()]
    if missing:
        raise RuntimeError(f"required result artifacts missing: {', '.join(missing)}")
    print("required artifacts: selected_clips.json, candidate_summary.json, selected_clips_summary.json")


def probe_downloaded_mp4(path: Path, env: dict[str, str]) -> ProbeResult:
    container_path = _container_storage_path(path)
    output = compose_exec(
        "worker",
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            container_path,
        ],
        env=env,
    )
    try:
        payload = json.loads(output)
        stream = payload["streams"][0]
        duration = float(payload.get("format", {}).get("duration", 0.0))
        return ProbeResult(width=int(stream["width"]), height=int(stream["height"]), duration=duration)
    except Exception as exc:
        raise RuntimeError(f"could not parse ffprobe output for {path}: {output}") from exc


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_output_probe(export: dict[str, Any], path: Path, probe: ProbeResult) -> None:
    export_type = str(export.get("type", "export"))
    if probe.duration <= 0:
        raise RuntimeError(f"{export_type} output has invalid duration={probe.duration}: {path}")
    if probe.width <= 0 or probe.height <= 0:
        raise RuntimeError(f"{export_type} output has invalid dimensions={probe.width}x{probe.height}: {path}")
    if export_type == "short" and (probe.width, probe.height) != (1080, 1920):
        raise RuntimeError(f"short output must be 1080x1920, got {probe.width}x{probe.height}: {path}")
    if export_type != "normal":
        return
    expected_duration = _optional_float(export.get("duration"))
    if expected_duration is None:
        return
    tolerance = 3.0
    if abs(probe.duration - expected_duration) > tolerance:
        raise RuntimeError(
            f"normal output duration mismatch: expected about {expected_duration:.3f}s, "
            f"got {probe.duration:.3f}s: {path}"
        )


def download_and_probe_outputs(
    *,
    backend_url: str,
    job_id: str,
    results: dict[str, Any],
    env: dict[str, str],
) -> list[tuple[dict[str, Any], Path, ProbeResult]]:
    exports = [*results.get("normalClips", []), *results.get("shorts", [])]
    if not exports:
        raise RuntimeError(f"no output exports returned; {diagnose_no_clips(job_id)}")

    zip_path = ROOT / "storage" / "temp" / f"e2e_real_{job_id}.zip"
    _download(_absolute_url(backend_url, results["zipDownloadUrl"]), zip_path)
    zip_size = zip_path.stat().st_size if zip_path.is_file() else 0
    if zip_size <= 0:
        raise RuntimeError(f"downloaded ZIP is empty or missing: {zip_path}")
    print(f"zip: {zip_path} ({zip_size} bytes)")

    probed: list[tuple[dict[str, Any], Path, ProbeResult]] = []
    for index, export in enumerate(exports, start=1):
        export_type = str(export.get("type", "export"))
        export_id = str(export.get("id", index))
        output_path = ROOT / "storage" / "temp" / f"e2e_real_{job_id}_{index:02d}_{export_type}_{export_id}.mp4"
        _download(_absolute_url(backend_url, export["downloadUrl"]), output_path)
        probe = probe_downloaded_mp4(output_path, env)
        print(f"{export_type} mp4: {output_path} ({probe.width}x{probe.height}, {probe.duration:.3f}s)")
        validate_output_probe(export, output_path, probe)
        probed.append((export, output_path, probe))
    return probed


def run_e2e(args: argparse.Namespace) -> int:
    total_started_at = time.monotonic()
    video_path = resolve_input_video(args.video)
    env = docker_env()
    check_services(env)
    _wait_http(f"{args.backend_url}/health", '"status":"ok"')

    settings = build_job_settings(args)
    if settings.get("e2eFixtureTranscript") is not False:
        raise RuntimeError("e2eFixtureTranscript must be false for real spoken-video E2E")
    print("fixture transcript: explicitly disabled")
    print(
        "transcription: "
        f"model={settings['whisperModelSize']} "
        f"language={settings['transcriptionLanguage']}"
    )
    if use_openai_scoring(settings) or use_openai_subtitle_correction(settings):
        check_openai_api_key_available(env)
    if use_openai_scoring(settings):
        print(
            "openai scoring: enabled "
            f"model={settings['openaiModel']} "
            f"candidate_limit={settings['openaiCandidateLimit']} "
            f"fallback={settings['openaiFallbackToRuleScore']}"
        )
    if use_openai_subtitle_correction(settings):
        print(
            "subtitle correction: enabled "
            f"model={settings['subtitleCorrectionModel']} "
            f"confidence={settings['subtitleCorrectionMinConfidence']} "
            f"batch_size={settings['subtitleCorrectionBatchSize']} "
            f"context={settings['subtitleCorrectionContextSegments']} "
            f"fallback={settings['subtitleCorrectionFallbackEnabled']}"
        )

    upload_started_at = time.monotonic()
    upload = _upload_file(f"{args.backend_url}/api/videos/upload", video_path)
    upload_seconds = time.monotonic() - upload_started_at
    video_id = upload["videoId"]
    print(f"uploaded video: {video_id}")

    job = _request_json(
        f"{args.backend_url}/api/jobs",
        method="POST",
        payload={"videoId": video_id, "settings": settings},
    )
    job_id = job["jobId"]
    print(f"created job: {job_id}")

    job_timing = poll_job_with_timings(args.backend_url, job_id, args.timeout)
    final_status = job_timing.final_status
    if final_status["status"] == "failed":
        print_job_summaries(job_id)
        print_runtime_metrics(
            runtime_metrics(
                upload_seconds=upload_seconds,
                job_timing=job_timing,
                total_seconds=time.monotonic() - total_started_at,
            )
        )
        raise RuntimeError(f"job failed; {diagnose_no_clips(job_id, final_status)}")

    output_dir = job_output_dir(job_id)
    validate_transcript_artifact(output_dir)
    validate_required_result_artifacts(output_dir)
    results = _request_json(f"{args.backend_url}/api/jobs/{job_id}/results")
    exports = [*results.get("normalClips", []), *results.get("shorts", [])]
    if not exports:
        print_job_summaries(job_id)
        print_pipeline_metrics(pipeline_metrics(output_dir))
        print_runtime_metrics(
            runtime_metrics(
                upload_seconds=upload_seconds,
                job_timing=job_timing,
                total_seconds=time.monotonic() - total_started_at,
            )
        )
        raise RuntimeError(f"job completed with no clips; {diagnose_no_clips(job_id, final_status)}")

    validate_selected_artifact(output_dir)
    print_job_summaries(job_id)
    if use_openai_scoring(settings):
        validate_openai_scoring_summary(output_dir)
    if use_openai_subtitle_correction(settings):
        validate_transcript_correction_summary(output_dir)
    print_pipeline_metrics(pipeline_metrics(output_dir))
    download_and_probe_outputs(backend_url=args.backend_url, job_id=job_id, results=results, env=env)
    print_runtime_metrics(
        runtime_metrics(
            upload_seconds=upload_seconds,
            job_timing=job_timing,
            total_seconds=time.monotonic() - total_started_at,
        )
    )
    print(f"job outputs: {output_dir}")
    print("REAL VIDEO E2E PASSED")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    args = parse_args(argv)
    args.backend_url = args.backend_url.rstrip("/")
    try:
        return run_e2e(args)
    except Exception as exc:
        print(f"REAL VIDEO E2E FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
