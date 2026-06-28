from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smoke_runtime import ROOT


SUMMARY_FILENAMES = [
    "transcript_summary.json",
    "audio_feature_summary.json",
    "candidate_summary.json",
    "rejection_summary.json",
    "selected_clips_summary.json",
]


def _value(payload: dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    return "null" if value is None else value


def summary_line(filename: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return f"type={type(payload).__name__}"

    if filename == "transcript_summary.json":
        return (
            f"segments={_value(payload, 'segment_count')} "
            f"chars={_value(payload, 'total_text_length')} "
            f"speech={_value(payload, 'total_speech_duration')} "
            f"confidence={_value(payload, 'average_confidence')} "
            f"engine={_value(payload, 'transcription_engine')} "
            f"fixture={_value(payload, 'used_fixture_transcript')}"
        )
    if filename == "audio_feature_summary.json":
        return (
            f"duration={_value(payload, 'duration')} "
            f"silence_ratio={_value(payload, 'silence_ratio')} "
            f"speech_density={_value(payload, 'speech_density')} "
            f"volume_peak={_value(payload, 'volume_peak')}"
        )
    if filename == "candidate_summary.json":
        return (
            f"total={_value(payload, 'total_candidates')} "
            f"normal={_value(payload, 'normal_candidates')} "
            f"short={_value(payload, 'short_candidates')} "
            f"with_text={_value(payload, 'candidates_with_transcript_text')} "
            f"hard_passed={_value(payload, 'hard_gate_passed_count')} "
            f"backfill={_value(payload, 'selected_below_threshold_backfill_count')} "
            f"avg_duration={_value(payload, 'avg_duration')} "
            f"avg_final_score={_value(payload, 'avg_final_score')}"
        )
    if filename == "rejection_summary.json":
        return (
            f"rejected={_value(payload, 'total_rejected')} "
            f"by_reason={_value(payload, 'rejected_by_reason')} "
            f"render_failures={_value(payload, 'render_failure_count')}"
        )
    if filename == "selected_clips_summary.json":
        selected_ids = payload.get("selected_ids", [])
        if isinstance(selected_ids, list) and len(selected_ids) > 5:
            selected_ids = [*selected_ids[:5], "..."]
        return (
            f"normal={_value(payload, 'selected_normal_count')} "
            f"short={_value(payload, 'selected_short_count')} "
            f"backfill={_value(payload, 'selected_below_threshold_backfill_count')} "
            f"ids={selected_ids}"
        )
    return ", ".join(f"{key}={value}" for key, value in sorted(payload.items())[:6])


def print_job_summaries(job_id: str, *, root: Path = ROOT) -> None:
    output_dir = root / "storage" / "outputs" / job_id
    print(f"diagnostic summaries: {output_dir}")
    for filename in SUMMARY_FILENAMES:
        path = output_dir / filename
        if not path.is_file():
            print(f"{filename}: missing")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"{filename}: unreadable: {exc}")
            continue
        print(f"{filename}: {summary_line(filename, payload)}")
