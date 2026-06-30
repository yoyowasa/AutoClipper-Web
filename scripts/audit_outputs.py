from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DOCKER_BIN_DIR = Path(r"C:\Program Files\Docker\Docker\resources\bin")
SHORT_RECOMMENDED_RANGE = (20.0, 75.0)
NORMAL_RECOMMENDED_RANGE = (90.0, 600.0)
VERY_SHORT_TRANSCRIPT_TEXT = {"normal": 160, "short": 40}
SUBTITLE_READABILITY_LIMITS = {
    "short": {
        "max_lines": 2,
        "max_chars_per_line": 18,
        "max_chars_per_event": 36,
        "max_chars_per_second": 16.0,
    },
    "normal": {
        "max_lines": 2,
        "max_chars_per_line": 30,
        "max_chars_per_event": 60,
        "max_chars_per_second": 18.0,
    },
}
ABRUPT_START_PREFIXES = (
    "だから",
    "それで",
    "で、",
    "でも",
    "あと",
    "そして",
    "つまり",
    "要するに",
    "一方で",
    "ただ",
    "そうですね",
    "はい",
    "うん",
    "and ",
    "but ",
    "so ",
    "because ",
    "then ",
)
ABRUPT_END_SUFFIXES = (
    "ので",
    "から",
    "けど",
    "ですが",
    "けれども",
    "っていう",
    "という",
    "とか",
    " and",
    " but",
    " because",
)
GENERIC_TITLE_PATTERN = re.compile(r"^(Normal clip|Short) \d+$")


@dataclass(frozen=True)
class OutputPaths:
    json_path: Path | None
    markdown_path: Path | None


@dataclass(frozen=True)
class ProbeResult:
    width: int | None
    height: int | None
    duration: float | None
    source: str
    error: str | None = None


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def job_output_dir(job_id: str, *, root: Path = ROOT) -> Path:
    return root / "storage" / "outputs" / job_id


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _bool(value: Any) -> bool:
    return value is True


def _mean(values: Sequence[float | None]) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 6)


def _clip_items(selected_payload: dict[str, Any]) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for key, default_type in (("normalClips", "normal"), ("shorts", "short")):
        for raw in selected_payload.get(key, []):
            if not isinstance(raw, dict):
                continue
            clip = dict(raw)
            clip["id"] = str(raw.get("id", ""))
            clip["type"] = str(raw.get("type") or default_type)
            clip["start"] = _number(raw.get("start"))
            clip["end"] = _number(raw.get("end"))
            clip["duration"] = _number(raw.get("duration"))
            clip["rule_score"] = _number(raw.get("rule_score"))
            clip["ai_score"] = _number(raw.get("ai_score"))
            clip["final_score"] = _number(raw.get("final_score"))
            clip["below_quality_threshold"] = _bool(raw.get("below_quality_threshold"))
            clip["openai_fallback_used"] = _bool(raw.get("openai_fallback_used"))
            clip["used_ai_score"] = _bool(raw.get("used_ai_score"))
            clip["openai_scored"] = _bool(raw.get("openai_scored"))
            clips.append(clip)
    return clips


def _load_export_metadata(output_dir: Path) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for folder_name in ("normal", "shorts"):
        folder = output_dir / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            payload = read_json(path, {})
            if not isinstance(payload, dict):
                continue
            candidate_id = str(payload.get("candidate_id") or "")
            if not candidate_id:
                continue
            enriched = dict(payload)
            enriched["_metadata_path"] = str(path)
            enriched["_folder"] = folder_name
            metadata[candidate_id] = enriched
    return metadata


def _host_path_from_artifact(value: Any, *, root: Path = ROOT) -> Path | None:
    if not value:
        return None
    text = str(value)
    if text.startswith("/app/storage/"):
        relative = text.removeprefix("/app/storage/").replace("/", os.sep)
        return root / "storage" / relative
    path = Path(text)
    if path.is_absolute():
        return path
    return root / path


def _container_path_from_host(path: Path, *, root: Path = ROOT) -> str | None:
    storage_root = (root / "storage").resolve()
    try:
        relative = path.resolve().relative_to(storage_root)
    except ValueError:
        return None
    return f"/app/storage/{relative.as_posix()}"


def _docker_executable() -> str | None:
    docker = shutil.which("docker")
    if docker:
        return docker
    candidate = DOCKER_BIN_DIR / "docker.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def _parse_probe_payload(output: str, *, source: str) -> ProbeResult:
    payload = json.loads(output)
    streams = payload.get("streams") or []
    stream = streams[0] if streams else {}
    duration = _number((payload.get("format") or {}).get("duration"))
    width = stream.get("width")
    height = stream.get("height")
    return ProbeResult(
        width=int(width) if width is not None else None,
        height=int(height) if height is not None else None,
        duration=duration,
        source=source,
    )


def _run_probe(args: list[str], *, cwd: Path | None = None) -> ProbeResult | None:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        return _parse_probe_payload(completed.stdout, source=args[0])
    except Exception:
        return None


def probe_video(
    *,
    host_path: Path | None,
    container_path: str | None,
    root: Path = ROOT,
) -> ProbeResult:
    if host_path is not None and host_path.is_file() and shutil.which("ffprobe"):
        local_result = _run_probe(
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
                str(host_path),
            ]
        )
        if local_result is not None:
            return local_result

    docker = _docker_executable()
    resolved_container_path = container_path
    if resolved_container_path is None and host_path is not None:
        resolved_container_path = _container_path_from_host(host_path, root=root)
    if docker and resolved_container_path:
        docker_result = _run_probe(
            [
                docker,
                "compose",
                "exec",
                "-T",
                "worker",
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                resolved_container_path,
            ],
            cwd=root,
        )
        if docker_result is not None:
            return ProbeResult(
                width=docker_result.width,
                height=docker_result.height,
                duration=docker_result.duration,
                source="docker_worker_ffprobe",
            )

    return ProbeResult(width=None, height=None, duration=None, source="unavailable", error="ffprobe_unavailable")


def _metadata_probe(metadata: dict[str, Any]) -> ProbeResult:
    width = metadata.get("width")
    height = metadata.get("height")
    duration = metadata.get("duration")
    return ProbeResult(
        width=int(width) if width is not None else None,
        height=int(height) if height is not None else None,
        duration=_number(duration),
        source="metadata",
    )


def _resolve_video_path(clip: dict[str, Any], metadata: dict[str, Any], *, root: Path) -> tuple[Path | None, str | None]:
    container_path = metadata.get("video_path") or clip.get("video_path")
    host_path = _host_path_from_artifact(container_path, root=root)
    if host_path is None:
        metadata_path = metadata.get("_metadata_path")
        if metadata_path:
            host_path = Path(str(metadata_path)).with_suffix(".mp4")
    return host_path, str(container_path) if container_path else None


def _resolve_subtitle_path(clip: dict[str, Any], metadata: dict[str, Any], *, root: Path) -> tuple[Path | None, str | None]:
    container_path = metadata.get("subtitle_path") or clip.get("subtitle_path")
    host_path = _host_path_from_artifact(container_path, root=root)
    if host_path is None:
        metadata_path = metadata.get("_metadata_path")
        if metadata_path:
            candidate = Path(str(metadata_path)).with_suffix(".ass")
            if candidate.exists():
                host_path = candidate
    return host_path, str(container_path) if container_path else None


def _segments_for_clip(segments: Sequence[dict[str, Any]], clip: dict[str, Any]) -> list[dict[str, Any]]:
    start = _number(clip.get("start"))
    end = _number(clip.get("end"))
    if start is None or end is None:
        return []
    matched: list[dict[str, Any]] = []
    for segment in segments:
        segment_start = _number(segment.get("start"))
        segment_end = _number(segment.get("end"))
        if segment_start is None or segment_end is None:
            continue
        if segment_end > start and segment_start < end:
            matched.append(segment)
    return matched


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _transcript_excerpt(segments: Sequence[dict[str, Any]], clip: dict[str, Any]) -> dict[str, Any]:
    selected_text = _plain_text(clip.get("transcript_text"))
    matched = _segments_for_clip(segments, clip)
    first_text = _plain_text(matched[0].get("text")) if matched else ""
    last_text = _plain_text(matched[-1].get("text")) if matched else ""
    text_length = int(clip.get("transcript_char_count") or len(selected_text))
    return {
        "transcript_text_length": text_length,
        "first_transcript_text": first_text or selected_text[:160],
        "last_transcript_text": last_text or selected_text[-160:],
        "segments_overlapping_clip": len(matched),
        "first_segment_start": _number(matched[0].get("start")) if matched else None,
        "last_segment_end": _number(matched[-1].get("end")) if matched else None,
    }


def _parse_ass_time(value: str) -> float | None:
    match = re.match(r"(?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})(?:\.(?P<cs>\d{1,2}))?$", value.strip())
    if not match:
        return None
    centiseconds = match.group("cs") or "0"
    return (
        int(match.group("h")) * 3600
        + int(match.group("m")) * 60
        + int(match.group("s"))
        + int(centiseconds.ljust(2, "0")) / 100
    )


def _ass_visible_text(value: str) -> str:
    text = re.sub(r"\{[^}]*\}", "", value)
    text = text.replace(r"\N", "\n")
    return text.strip()


def analyze_ass_subtitles(path: Path | None, *, clip_type: str | None = None) -> dict[str, Any]:
    limits = SUBTITLE_READABILITY_LIMITS.get(clip_type or "", SUBTITLE_READABILITY_LIMITS["normal"])
    if path is None or not path.is_file():
        return {
            "subtitle_exists": False,
            "dialogue_count": 0,
            "max_lines": 0,
            "max_chars_per_dialogue": 0,
            "max_chars_per_line": 0,
            "max_chars_per_second": None,
            "readability_limits": limits,
            "density_reasons": [],
            "worst_density_samples": [],
            "subtitle_too_dense": False,
        }

    max_lines = 0
    max_chars = 0
    max_line_chars = 0
    chars_per_second: list[float] = []
    density_samples: list[dict[str, Any]] = []
    dialogue_count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.removeprefix("Dialogue:").lstrip().split(",", 9)
        if len(parts) < 10:
            continue
        style = parts[3].strip()
        if style != "Subtitle":
            continue
        start = _parse_ass_time(parts[1])
        end = _parse_ass_time(parts[2])
        visible = _ass_visible_text(parts[9])
        lines = visible.splitlines() or [visible]
        char_count = len("".join(lines))
        line_char_count = max((len(subtitle_line) for subtitle_line in lines), default=0)
        duration = (end - start) if start is not None and end is not None else 0.0
        cps = None
        if duration > 0:
            cps = char_count / duration
            chars_per_second.append(cps)
        dialogue_count += 1
        max_lines = max(max_lines, len(lines))
        max_chars = max(max_chars, char_count)
        max_line_chars = max(max_line_chars, line_char_count)
        density_samples.append(
            {
                "start": round(start, 3) if start is not None else None,
                "end": round(end, 3) if end is not None else None,
                "duration": round(duration, 3),
                "line_count": len(lines),
                "char_count": char_count,
                "max_line_chars": line_char_count,
                "chars_per_second": round(cps, 6) if cps is not None else None,
                "text": visible[:160],
            }
        )

    max_cps = max(chars_per_second) if chars_per_second else None
    density_reasons = []
    if max_lines > limits["max_lines"]:
        density_reasons.append("too_many_lines")
    if max_line_chars > limits["max_chars_per_line"]:
        density_reasons.append("line_too_long")
    if max_chars > limits["max_chars_per_event"]:
        density_reasons.append("event_too_long")
    if max_cps is not None and max_cps > limits["max_chars_per_second"]:
        density_reasons.append("too_many_chars_per_second")
    worst_samples = sorted(
        density_samples,
        key=lambda sample: (
            float(sample["chars_per_second"] or 0),
            int(sample["max_line_chars"] or 0),
            int(sample["char_count"] or 0),
        ),
        reverse=True,
    )[:3]
    return {
        "subtitle_exists": True,
        "dialogue_count": dialogue_count,
        "max_lines": max_lines,
        "max_chars_per_dialogue": max_chars,
        "max_chars_per_line": max_line_chars,
        "max_chars_per_second": round(max_cps, 6) if max_cps is not None else None,
        "avg_chars_per_second": round(sum(chars_per_second) / len(chars_per_second), 6)
        if chars_per_second
        else None,
        "readability_limits": limits,
        "density_reasons": density_reasons,
        "worst_density_samples": worst_samples,
        "subtitle_too_dense": bool(density_reasons),
    }


def _has_generic_or_missing_title(selected_title: Any, metadata_title: Any) -> bool:
    selected = _plain_text(selected_title)
    if selected:
        return False
    metadata = _plain_text(metadata_title)
    return not metadata or bool(GENERIC_TITLE_PATTERN.match(metadata))


def _likely_abrupt_start(clip: dict[str, Any], transcript: dict[str, Any]) -> bool:
    start = _number(clip.get("start"))
    first_segment_start = _number(transcript.get("first_segment_start"))
    first_text = _plain_text(transcript.get("first_transcript_text")).lower()
    if start is not None and first_segment_start is not None and first_segment_start < start - 0.3:
        return True
    return first_text.startswith(ABRUPT_START_PREFIXES)


def _likely_abrupt_ending(clip: dict[str, Any], transcript: dict[str, Any]) -> bool:
    end = _number(clip.get("end"))
    last_segment_end = _number(transcript.get("last_segment_end"))
    last_text = _plain_text(transcript.get("last_transcript_text")).lower()
    if end is not None and last_segment_end is not None and last_segment_end > end + 0.3:
        return True
    return last_text.endswith(ABRUPT_END_SUFFIXES)


def _quality_warnings(
    *,
    clip: dict[str, Any],
    metadata: dict[str, Any],
    transcript: dict[str, Any],
    probe: ProbeResult,
    subtitle: dict[str, Any],
    high_quality_mode: bool,
) -> list[str]:
    warnings: list[str] = []
    clip_type = str(clip.get("type"))
    duration = _number(clip.get("duration")) or probe.duration

    if transcript["transcript_text_length"] < VERY_SHORT_TRANSCRIPT_TEXT.get(clip_type, 80):
        warnings.append("very_short_transcript_text")
    if _likely_abrupt_start(clip, transcript):
        warnings.append("likely_abrupt_start")
    if _likely_abrupt_ending(clip, transcript):
        warnings.append("likely_abrupt_ending")
    if subtitle.get("subtitle_too_dense"):
        warnings.append("subtitle_too_dense")
    if not subtitle.get("subtitle_exists"):
        warnings.append("no_subtitle_file")
    if _has_generic_or_missing_title(clip.get("title"), metadata.get("title")):
        warnings.append("missing_title")
    if clip.get("below_quality_threshold"):
        warnings.append("below_quality_threshold")
    if "backfill" in str(clip.get("selection_reason") or ""):
        warnings.append("backfilled_clip")
    if high_quality_mode and not clip.get("used_ai_score") and not clip.get("openai_fallback_used"):
        warnings.append("rule_only_clip_in_high_quality_mode")
    if duration is None or duration <= 0:
        warnings.append("invalid_duration")
    elif clip_type == "short" and not (SHORT_RECOMMENDED_RANGE[0] <= duration <= SHORT_RECOMMENDED_RANGE[1]):
        warnings.append("short_duration_outside_recommended_range")
    elif clip_type == "normal" and not (NORMAL_RECOMMENDED_RANGE[0] <= duration <= NORMAL_RECOMMENDED_RANGE[1]):
        warnings.append("normal_duration_outside_recommended_range")

    if probe.width is None or probe.height is None or probe.width <= 0 or probe.height <= 0:
        warnings.append("missing_or_invalid_resolution")
    elif clip_type == "short" and (probe.width, probe.height) != (1080, 1920):
        warnings.append("short_resolution_not_1080x1920")
    if clip_type == "short" and high_quality_mode and not _plain_text(clip.get("overlay_title") or metadata.get("overlay_title")):
        warnings.append("missing_overlay_title")
    return warnings


def _clip_report(
    *,
    clip: dict[str, Any],
    metadata: dict[str, Any],
    transcript_segments: Sequence[dict[str, Any]],
    high_quality_mode: bool,
    root: Path,
) -> dict[str, Any]:
    host_path, container_video_path = _resolve_video_path(clip, metadata, root=root)
    subtitle_path, container_subtitle_path = _resolve_subtitle_path(clip, metadata, root=root)
    metadata_probe = _metadata_probe(metadata)
    probe = metadata_probe
    if probe.width is None or probe.height is None or probe.duration is None:
        probe = probe_video(host_path=host_path, container_path=container_video_path, root=root)
    transcript = _transcript_excerpt(transcript_segments, clip)
    subtitle = analyze_ass_subtitles(subtitle_path, clip_type=str(clip.get("type") or ""))
    warnings = _quality_warnings(
        clip=clip,
        metadata=metadata,
        transcript=transcript,
        probe=probe,
        subtitle=subtitle,
        high_quality_mode=high_quality_mode,
    )
    title = clip.get("title") or metadata.get("title")
    overlay_title = clip.get("overlay_title") or metadata.get("overlay_title")
    duration = _number(clip.get("duration")) or probe.duration
    return {
        "id": clip.get("id"),
        "type": clip.get("type"),
        "file_path": str(host_path) if host_path is not None else None,
        "container_file_path": container_video_path,
        "duration": duration,
        "resolution": {
            "width": probe.width,
            "height": probe.height,
            "source": probe.source,
            "error": probe.error,
        },
        "selected_start": clip.get("start"),
        "selected_end": clip.get("end"),
        "transcript_text_length": transcript["transcript_text_length"],
        "first_transcript_text": transcript["first_transcript_text"],
        "last_transcript_text": transcript["last_transcript_text"],
        "segments_overlapping_clip": transcript["segments_overlapping_clip"],
        "rule_score": clip.get("rule_score"),
        "ai_score": clip.get("ai_score"),
        "final_score": clip.get("final_score"),
        "selection_reason": clip.get("selection_reason"),
        "below_quality_threshold": clip.get("below_quality_threshold"),
        "quality_warning": clip.get("quality_warning"),
        "openai_score_source": clip.get("openai_score_source"),
        "used_ai_score": clip.get("used_ai_score"),
        "openai_fallback_used": clip.get("openai_fallback_used"),
        "subtitle_file_path": str(subtitle_path) if subtitle_path is not None else None,
        "container_subtitle_file_path": container_subtitle_path,
        "subtitle": subtitle,
        "title": title,
        "overlay_title": overlay_title,
        "metadata_path": metadata.get("_metadata_path"),
        "warnings": warnings,
        "requires_human_visual_inspection": bool(warnings),
    }


def _warnings_by_type(clips: Sequence[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for clip in clips:
        clip_type = str(clip.get("type") or "unknown")
        bucket = counts.setdefault(clip_type, {})
        for warning in clip.get("warnings", []):
            bucket[warning] = bucket.get(warning, 0) + 1
    return counts


def _count_by_type(clips: Sequence[dict[str, Any]], clip_type: str) -> int:
    return sum(1 for clip in clips if clip.get("type") == clip_type)


def build_audit_report(job_id: str, *, root: Path = ROOT) -> dict[str, Any]:
    output_dir = job_output_dir(job_id, root=root)
    selected = read_json(output_dir / "selected_clips.json")
    if not isinstance(selected, dict):
        raise RuntimeError(f"selected_clips.json not found or invalid for {job_id}: {output_dir}")

    selected_summary = read_json(output_dir / "selected_clips_summary.json", {})
    candidate_summary = read_json(output_dir / "candidate_summary.json", {})
    transcript_segments = read_json(output_dir / "transcript_segments.json", [])
    openai_summary = read_json(output_dir / "openai_scoring_summary.json", None)
    if not isinstance(transcript_segments, list):
        transcript_segments = []
    transcript_segments = [segment for segment in transcript_segments if isinstance(segment, dict)]
    export_metadata = _load_export_metadata(output_dir)
    high_quality_mode = isinstance(openai_summary, dict)

    clip_reports = [
        _clip_report(
            clip=clip,
            metadata=export_metadata.get(str(clip.get("id")), {}),
            transcript_segments=transcript_segments,
            high_quality_mode=high_quality_mode,
            root=root,
        )
        for clip in _clip_items(selected)
    ]
    average_duration = _mean([_number(clip.get("duration")) for clip in clip_reports])
    average_final_score = _mean([_number(clip.get("final_score")) for clip in clip_reports])
    inspection_clips = [
        {
            "id": clip.get("id"),
            "type": clip.get("type"),
            "file_path": clip.get("file_path"),
            "warnings": clip.get("warnings"),
        }
        for clip in clip_reports
        if clip.get("requires_human_visual_inspection")
    ]
    return {
        "audit": {
            "job_id": job_id,
            "output_dir": str(output_dir),
            "high_quality_mode": high_quality_mode,
        },
        "aggregate_summary": {
            "generated_normal_count": _count_by_type(clip_reports, "normal"),
            "generated_short_count": _count_by_type(clip_reports, "short"),
            "average_duration": average_duration,
            "average_final_score": average_final_score,
            "warnings_by_type": _warnings_by_type(clip_reports),
            "clips_requiring_human_visual_inspection_count": len(inspection_clips),
            "clips_requiring_human_visual_inspection": inspection_clips,
        },
        "clips": clip_reports,
        "source_artifacts": {
            "selected_clips_summary": selected_summary if isinstance(selected_summary, dict) else {},
            "candidate_summary": candidate_summary if isinstance(candidate_summary, dict) else {},
            "openai_scoring_summary": openai_summary if isinstance(openai_summary, dict) else None,
        },
    }


def _markdown_value(value: Any, *, limit: int = 100) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value)
    else:
        text = str(value)
    text = text.replace("\n", " ").replace("|", "\\|")
    if len(text) > limit:
        return f"{text[: limit - 3]}..."
    return text


def render_markdown(report: dict[str, Any]) -> str:
    audit = report["audit"]
    summary = report["aggregate_summary"]
    lines = [
        "# AutoClipper Output Quality Audit",
        "",
        f"- job: `{audit['job_id']}`",
        f"- output dir: `{audit['output_dir']}`",
        f"- high quality mode: `{audit['high_quality_mode']}`",
        "",
        "## Aggregate Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| generated_normal_count | {summary['generated_normal_count']} |",
        f"| generated_short_count | {summary['generated_short_count']} |",
        f"| average_duration | {_markdown_value(summary['average_duration'])} |",
        f"| average_final_score | {_markdown_value(summary['average_final_score'])} |",
        "| clips_requiring_human_visual_inspection | "
        f"{summary['clips_requiring_human_visual_inspection_count']} |",
        "",
        "## Warnings By Type",
        "",
        "| Type | Warning | Count |",
        "| --- | --- | ---: |",
    ]
    warning_rows = False
    for clip_type, warning_counts in sorted(summary["warnings_by_type"].items()):
        for warning, count in sorted(warning_counts.items()):
            warning_rows = True
            lines.append(f"| {clip_type} | `{warning}` | {count} |")
    if not warning_rows:
        lines.append("| none | none | 0 |")

    lines.extend(
        [
            "",
            "## Generated Clips",
            "",
            "| Type | Clip | Range | Duration | Resolution | Final | Selection | Warnings | Title | Overlay |",
            "| --- | --- | --- | ---: | --- | ---: | --- | --- | --- | --- |",
        ]
    )
    for clip in report["clips"]:
        resolution = clip.get("resolution") or {}
        width = resolution.get("width")
        height = resolution.get("height")
        resolution_text = f"{width}x{height}" if width and height else "unknown"
        lines.append(
            "| "
            f"{_markdown_value(clip.get('type'))} | "
            f"`{_markdown_value(clip.get('id'), limit=48)}` | "
            f"{_markdown_value(clip.get('selected_start'))}-"
            f"{_markdown_value(clip.get('selected_end'))} | "
            f"{_markdown_value(clip.get('duration'))} | "
            f"{resolution_text} | "
            f"{_markdown_value(clip.get('final_score'))} | "
            f"{_markdown_value(clip.get('selection_reason'))} | "
            f"{_markdown_value(clip.get('warnings'), limit=160)} | "
            f"{_markdown_value(clip.get('title'))} | "
            f"{_markdown_value(clip.get('overlay_title'))} |"
        )

    dense_clips = [
        clip
        for clip in report["clips"]
        if clip.get("subtitle", {}).get("subtitle_too_dense")
        and clip.get("subtitle", {}).get("worst_density_samples")
    ]
    if dense_clips:
        lines.extend(["", "## Subtitle Density Samples", ""])
        for clip in dense_clips:
            subtitle = clip.get("subtitle", {})
            lines.append(
                f"- `{clip.get('id')}` ({clip.get('type')}): "
                f"{_markdown_value(subtitle.get('density_reasons'), limit=160)}"
            )
            for sample in subtitle.get("worst_density_samples", [])[:2]:
                lines.append(
                    f"  - {sample.get('start')}s-{sample.get('end')}s, "
                    f"{sample.get('chars_per_second')} cps, "
                    f"{sample.get('max_line_chars')} chars/line: "
                    f"{_markdown_value(sample.get('text'), limit=120)}"
                )

    lines.extend(
        [
            "",
            "## Inspection Notes",
            "",
        ]
    )
    for clip in summary["clips_requiring_human_visual_inspection"]:
        lines.append(
            f"- `{clip['id']}` ({clip['type']}): "
            f"{_markdown_value(clip.get('warnings'), limit=180)}"
        )
    if not summary["clips_requiring_human_visual_inspection"]:
        lines.append("- No heuristic warnings.")
    lines.append("")
    return "\n".join(lines)


def output_paths(
    *,
    job_id: str,
    output: Path | None,
    output_format: str,
    root: Path = ROOT,
) -> OutputPaths:
    json_enabled = output_format in {"json", "both"}
    markdown_enabled = output_format in {"markdown", "both"}
    if output is None:
        output_dir = job_output_dir(job_id, root=root) / "audit"
        return OutputPaths(
            json_path=output_dir / "output_audit_report.json" if json_enabled else None,
            markdown_path=output_dir / "output_audit_report.md" if markdown_enabled else None,
        )
    if output.suffix:
        if output_format == "json":
            return OutputPaths(json_path=output, markdown_path=None)
        if output_format == "markdown":
            return OutputPaths(json_path=None, markdown_path=output)
        return OutputPaths(json_path=output.with_suffix(".json"), markdown_path=output.with_suffix(".md"))
    return OutputPaths(
        json_path=output / "output_audit_report.json" if json_enabled else None,
        markdown_path=output / "output_audit_report.md" if markdown_enabled else None,
    )


def write_report(report: dict[str, Any], paths: OutputPaths) -> list[Path]:
    written: list[Path] = []
    if paths.json_path is not None:
        paths.json_path.parent.mkdir(parents=True, exist_ok=True)
        paths.json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(paths.json_path)
    if paths.markdown_path is not None:
        paths.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        paths.markdown_path.write_text(render_markdown(report), encoding="utf-8")
        written.append(paths.markdown_path)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit generated AutoClipper output artifacts for likely quality issues.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="both")
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run(args: argparse.Namespace) -> int:
    report = build_audit_report(args.job_id)
    paths = output_paths(job_id=args.job_id, output=args.output, output_format=args.format)
    written = write_report(report, paths)
    summary = report["aggregate_summary"]
    print(
        "audit summary: "
        f"normal={summary['generated_normal_count']} "
        f"short={summary['generated_short_count']} "
        f"inspection={summary['clips_requiring_human_visual_inspection_count']}"
    )
    for path in written:
        print(f"report: {path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        return run(parse_args(argv))
    except Exception as exc:
        print(f"OUTPUT AUDIT FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
