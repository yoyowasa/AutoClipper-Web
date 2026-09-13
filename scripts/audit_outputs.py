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
GENERIC_TITLE_PATTERN = re.compile(r"^(Normal\s+[Cc]lip|Short)\s+\d+$")
EXPECTED_ASS_FONT = "Noto Sans CJK JP"
JAPANESE_ASS_FONTS = frozenset(
    {
        "Noto Sans CJK JP",
        "Noto Sans JP Black",
        "Noto Serif CJK JP",
        "Noto Sans Mono CJK JP",
        "Source Han Sans JP Heavy",
        "M PLUS 1 ExtraBold",
        "Rounded Mplus 1c ExtraBold",
        "851CHIKARA-DZUYOKU-KANA-A",
        "Dela Gothic One",
        "Corporate-Logo-Bold-ver3",
    }
)
AUTOLOAD_SUBTITLE_SUFFIXES = (".ass", ".srt", ".vtt")


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
            effective_start = _number(raw.get("refined_start"))
            if effective_start is None:
                effective_start = _number(raw.get("start"))
            effective_end = _number(raw.get("refined_end"))
            if effective_end is None:
                effective_end = _number(raw.get("end"))
            clip["id"] = str(raw.get("id", ""))
            clip["type"] = str(raw.get("type") or default_type)
            clip["start"] = effective_start
            clip["end"] = effective_end
            clip["duration"] = _number(raw.get("duration"))
            clip["original_start"] = _number(raw.get("original_start"))
            clip["original_end"] = _number(raw.get("original_end"))
            clip["refined_start"] = _number(raw.get("refined_start"))
            clip["refined_end"] = _number(raw.get("refined_end"))
            clip["boundary_refined"] = _bool(raw.get("boundary_refined"))
            clip["boundary_expansion_seconds"] = _number(raw.get("boundary_expansion_seconds"))
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


def same_basename_subtitle_sidecars(video_path: Path | None) -> list[Path]:
    if video_path is None or video_path.suffix.lower() != ".mp4":
        return []
    return [
        candidate
        for suffix in AUTOLOAD_SUBTITLE_SUFFIXES
        if (candidate := video_path.with_suffix(suffix)).is_file()
    ]


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


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _number(value)
        if parsed is not None:
            return parsed
    return None


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


def _parse_ass_style(line: str) -> dict[str, Any] | None:
    if not line.startswith("Style:"):
        return None
    parts = line.removeprefix("Style:").strip().split(",")
    if len(parts) < 23:
        return None
    try:
        return {
            "name": parts[0],
            "font_name": parts[1],
            "font_size": int(float(parts[2])),
            "outline": int(float(parts[16])),
            "alignment": int(parts[18]),
            "margin_v": int(parts[21]),
        }
    except ValueError:
        return None


def analyze_ass_subtitles(path: Path | None, *, clip_type: str | None = None) -> dict[str, Any]:
    limits = SUBTITLE_READABILITY_LIMITS.get(clip_type or "", SUBTITLE_READABILITY_LIMITS["normal"])
    if path is None or not path.is_file():
        return {
            "subtitle_exists": False,
            "dialogue_count": 0,
            "title_dialogue_count": 0,
            "max_lines": 0,
            "max_chars_per_dialogue": 0,
            "max_chars_per_line": 0,
            "max_chars_per_second": None,
            "subtitle_style": None,
            "title_style": None,
            "expected_font": EXPECTED_ASS_FONT,
            "font_supports_japanese": False,
            "title_subtitle_vertical_gap": None,
            "title_subtitle_vertical_overlap": False,
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
    title_dialogue_count = 0
    play_res_y: int | None = None
    styles: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("PlayResY:"):
            try:
                play_res_y = int(float(line.split(":", 1)[1].strip()))
            except ValueError:
                play_res_y = None
            continue
        parsed_style = _parse_ass_style(line)
        if parsed_style:
            styles[str(parsed_style["name"])] = parsed_style
            continue
        if not line.startswith("Dialogue:"):
            continue
        parts = line.removeprefix("Dialogue:").lstrip().split(",", 9)
        if len(parts) < 10:
            continue
        style = parts[3].strip()
        if style == "Title":
            title_dialogue_count += 1
            continue
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
    subtitle_style = styles.get("Subtitle")
    title_style = styles.get("Title")
    hook_style = styles.get("Hook")
    font_supports_japanese = bool(
        subtitle_style
        and subtitle_style.get("font_name") in JAPANESE_ASS_FONTS
        and (
            not title_style
            or title_style.get("font_name") in JAPANESE_ASS_FONTS
        )
        and (
            not hook_style
            or hook_style.get("font_name") in JAPANESE_ASS_FONTS
        )
    )
    vertical_gap = None
    vertical_overlap = False
    if play_res_y is not None and subtitle_style and title_style:
        layout_lines = int(limits.get("max_lines") or 2)
        title_bottom = (
            int(title_style["margin_v"])
            + int(title_style["font_size"]) * layout_lines
            + int(title_style.get("outline") or 0) * 2
        )
        subtitle_top = (
            play_res_y
            - int(subtitle_style["margin_v"])
            - int(subtitle_style["font_size"]) * layout_lines
            - int(subtitle_style.get("outline") or 0) * 2
        )
        vertical_gap = subtitle_top - title_bottom
        vertical_overlap = vertical_gap <= 0
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
        "title_dialogue_count": title_dialogue_count,
        "max_lines": max_lines,
        "max_chars_per_dialogue": max_chars,
        "max_chars_per_line": max_line_chars,
        "max_chars_per_second": round(max_cps, 6) if max_cps is not None else None,
        "avg_chars_per_second": round(sum(chars_per_second) / len(chars_per_second), 6)
        if chars_per_second
        else None,
        "subtitle_style": subtitle_style,
        "title_style": title_style,
        "expected_font": EXPECTED_ASS_FONT,
        "font_supports_japanese": font_supports_japanese,
        "title_subtitle_vertical_gap": vertical_gap,
        "title_subtitle_vertical_overlap": vertical_overlap,
        "readability_limits": limits,
        "density_reasons": density_reasons,
        "worst_density_samples": worst_samples,
        "subtitle_too_dense": bool(density_reasons),
    }


def _resolved_title(clip: dict[str, Any], metadata: dict[str, Any]) -> str:
    return _plain_text(clip.get("title") or metadata.get("title"))


def _resolved_title_source(clip: dict[str, Any], metadata: dict[str, Any]) -> str:
    return _plain_text(clip.get("title_source") or metadata.get("title_source"))


def _missing_title(clip: dict[str, Any], metadata: dict[str, Any]) -> bool:
    return not _resolved_title(clip, metadata)


def _has_generic_title(clip: dict[str, Any], metadata: dict[str, Any]) -> bool:
    title = _resolved_title(clip, metadata)
    if not title:
        return False
    if _resolved_title_source(clip, metadata) == "deterministic_fallback":
        return True
    return bool(GENERIC_TITLE_PATTERN.match(title))


def _metadata_bool(clip: dict[str, Any], metadata: dict[str, Any], key: str) -> bool | None:
    for source in (clip, metadata):
        if key not in source:
            continue
        value = source.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
    return None


def _overlay_title_mode(clip: dict[str, Any], metadata: dict[str, Any]) -> str:
    value = clip.get("overlay_title_mode") or metadata.get("overlay_title_mode") or "auto"
    mode = str(value).strip()
    return mode if mode in {"auto", "always", "high_quality_only", "never"} else "auto"


def _overlay_title_expected(
    clip: dict[str, Any],
    metadata: dict[str, Any],
    *,
    high_quality_mode: bool,
) -> bool:
    explicit = _metadata_bool(clip, metadata, "overlay_title_expected")
    if explicit is not None:
        return explicit
    mode = _overlay_title_mode(clip, metadata)
    if mode == "always":
        return True
    if mode == "never":
        return False
    return high_quality_mode


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


def _configured_duration_range_for_type(
    candidate_generation_summary: dict[str, Any],
    clip_type: str,
) -> dict[str, Any] | None:
    ranges = candidate_generation_summary.get("configured_duration_ranges")
    if isinstance(ranges, dict) and isinstance(ranges.get(clip_type), dict):
        return ranges[clip_type]
    by_type = candidate_generation_summary.get("by_type")
    if isinstance(by_type, dict):
        type_summary = by_type.get(clip_type)
        if isinstance(type_summary, dict) and isinstance(type_summary.get("configured_duration_range"), dict):
            return type_summary["configured_duration_range"]
    return None


def _duration_policy(
    *,
    clip_type: str,
    candidate_generation_summary: dict[str, Any],
) -> dict[str, Any]:
    default_min, default_max = (
        SHORT_RECOMMENDED_RANGE if clip_type == "short" else NORMAL_RECOMMENDED_RANGE
    )
    configured = _configured_duration_range_for_type(candidate_generation_summary, clip_type)
    if configured is not None:
        configured_min = _number(configured.get("min_duration"))
        configured_max = _number(configured.get("max_duration"))
        if configured_min is not None and configured_max is not None:
            return {
                "min_duration": configured_min,
                "max_duration": configured_max,
                "source": "candidate_generation_summary",
                "label": "configured_duration_range",
            }
    return {
        "min_duration": default_min,
        "max_duration": default_max,
        "source": "default_recommended_range",
        "label": "default_recommended_range",
    }


def _selection_summary_context(selected_summary: dict[str, Any], clip_type: str) -> dict[str, Any]:
    requested_key = "requested_short_count" if clip_type == "short" else "requested_normal_count"
    selected_key = "selected_short_count" if clip_type == "short" else "selected_normal_count"
    hard_gate_key = "short_hard_gate_passed_count" if clip_type == "short" else "normal_hard_gate_passed_count"
    unfilled_counts = selected_summary.get("unfilled_requested_counts")
    unfilled_count = None
    if isinstance(unfilled_counts, dict):
        unfilled_count = unfilled_counts.get(clip_type)
    return {
        "requested_count": selected_summary.get(requested_key),
        "selected_count": selected_summary.get(selected_key),
        "hard_gate_passed_count": selected_summary.get(hard_gate_key),
        "selected_above_threshold_count": selected_summary.get("selected_above_threshold_count"),
        "selected_below_threshold_backfill_count": selected_summary.get("selected_below_threshold_backfill_count"),
        "unfilled_requested_count": unfilled_count,
    }


def _quality_warnings(
    *,
    clip: dict[str, Any],
    metadata: dict[str, Any],
    transcript: dict[str, Any],
    probe: ProbeResult,
    subtitle: dict[str, Any],
    duration_policy: dict[str, Any],
    external_subtitle_autoload_risks: Sequence[Path],
    high_quality_mode: bool,
) -> list[str]:
    warnings: list[str] = []
    clip_type = str(clip.get("type"))
    duration = _number(clip.get("duration")) or probe.duration
    duration_min = _number(duration_policy.get("min_duration"))
    duration_max = _number(duration_policy.get("max_duration"))

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
    if _missing_title(clip, metadata):
        warnings.append("missing_title")
    elif _has_generic_title(clip, metadata):
        warnings.append("generic_fallback_title")
    if clip.get("below_quality_threshold"):
        warnings.append("below_quality_threshold")
    if "backfill" in str(clip.get("selection_reason") or ""):
        warnings.append("backfilled_clip")
    if high_quality_mode and not clip.get("used_ai_score") and not clip.get("openai_fallback_used"):
        warnings.append("rule_only_clip_in_high_quality_mode")
    if duration is None or duration <= 0:
        warnings.append("invalid_duration")
    elif (
        clip_type == "short"
        and duration_min is not None
        and duration_max is not None
        and not (duration_min <= duration <= duration_max)
    ):
        warnings.append("short_duration_outside_recommended_range")
    elif (
        clip_type == "normal"
        and duration_min is not None
        and duration_max is not None
        and not (duration_min <= duration <= duration_max)
    ):
        warnings.append("normal_duration_outside_recommended_range")

    if probe.width is None or probe.height is None or probe.width <= 0 or probe.height <= 0:
        warnings.append("missing_or_invalid_resolution")
    elif clip_type == "short" and (probe.width, probe.height) != (1080, 1920):
        warnings.append("short_resolution_not_1080x1920")
    overlay_title = _plain_text(clip.get("overlay_title") or metadata.get("overlay_title"))
    overlay_expected = _overlay_title_expected(clip, metadata, high_quality_mode=high_quality_mode)
    title_dialogue_count = int(subtitle.get("title_dialogue_count", 0) or 0)
    if clip_type == "short" and overlay_expected and not overlay_title:
        warnings.append("missing_overlay_title")
    if clip_type == "short" and overlay_expected and overlay_title and title_dialogue_count <= 0:
        warnings.append("missing_ass_title_event")
    if clip_type == "short" and title_dialogue_count > 0 and subtitle.get("title_subtitle_vertical_overlap"):
        warnings.append("title_subtitle_vertical_overlap")
    if subtitle.get("subtitle_exists") and not subtitle.get("font_supports_japanese"):
        warnings.append("subtitle_font_missing_japanese_support")
    if external_subtitle_autoload_risks:
        warnings.append("external_subtitle_autoload_risk")
    return warnings


def _warning_details(
    *,
    warnings: Sequence[str],
    clip: dict[str, Any],
    transcript: dict[str, Any],
    probe: ProbeResult,
    subtitle: dict[str, Any],
    duration_policy: dict[str, Any],
    selected_summary: dict[str, Any],
    external_subtitle_autoload_risks: Sequence[Path],
) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    duration = _number(clip.get("duration")) or probe.duration
    boundary_context = {
        "boundary_refined": clip.get("boundary_refined"),
        "boundary_refinement_reason": clip.get("boundary_refinement_reason"),
        "boundary_expansion_seconds": clip.get("boundary_expansion_seconds"),
        "original_start": clip.get("original_start"),
        "original_end": clip.get("original_end"),
        "refined_start": clip.get("refined_start"),
        "refined_end": clip.get("refined_end"),
    }
    if "likely_abrupt_start" in warnings:
        details["likely_abrupt_start"] = {
            **boundary_context,
            "selected_start": clip.get("start"),
            "first_segment_start": transcript.get("first_segment_start"),
            "first_transcript_text": transcript.get("first_transcript_text"),
            "reason": "clip may start after the first overlapping transcript segment or with a continuation marker",
        }
    if "likely_abrupt_ending" in warnings:
        details["likely_abrupt_ending"] = {
            **boundary_context,
            "selected_end": clip.get("end"),
            "last_segment_end": transcript.get("last_segment_end"),
            "last_transcript_text": transcript.get("last_transcript_text"),
            "reason": "clip may end before the last overlapping transcript segment or on an incomplete phrase",
        }
    if "below_quality_threshold" in warnings:
        details["below_quality_threshold"] = {
            "final_score": clip.get("final_score"),
            "rule_score": clip.get("rule_score"),
            "ai_score": clip.get("ai_score"),
            "quality_warning": clip.get("quality_warning"),
            "selection_reason": clip.get("selection_reason"),
            "reason": "selected clip is below min final score",
            "selection_summary": _selection_summary_context(selected_summary, str(clip.get("type") or "")),
        }
        if "backfill" in str(clip.get("selection_reason") or ""):
            details["below_quality_threshold"]["selection_context"] = (
                "fill_requested backfilled this clip because the requested count was not filled by higher-scoring candidates"
            )
    if "backfilled_clip" in warnings:
        details["backfilled_clip"] = {
            "selection_reason": clip.get("selection_reason"),
            "quality_warning": clip.get("quality_warning"),
            "below_quality_threshold": clip.get("below_quality_threshold"),
            "overlap_relaxed": clip.get("overlap_relaxed"),
            "overlap_ratio_used": clip.get("overlap_ratio_used"),
        }
    for warning in ("short_duration_outside_recommended_range", "normal_duration_outside_recommended_range"):
        if warning in warnings:
            details[warning] = {
                "duration": duration,
                "min_duration": duration_policy.get("min_duration"),
                "max_duration": duration_policy.get("max_duration"),
                "duration_policy_source": duration_policy.get("source"),
                "duration_policy_label": duration_policy.get("label"),
                "reason": "clip duration is outside the active audit duration policy",
            }
    if "subtitle_too_dense" in warnings:
        details["subtitle_too_dense"] = {
            "density_reasons": subtitle.get("density_reasons"),
            "worst_density_samples": subtitle.get("worst_density_samples"),
        }
    if "external_subtitle_autoload_risk" in warnings:
        details["external_subtitle_autoload_risk"] = {
            "sidecar_files": [str(path) for path in external_subtitle_autoload_risks],
        }
    return details


def _clip_report(
    *,
    clip: dict[str, Any],
    metadata: dict[str, Any],
    transcript_segments: Sequence[dict[str, Any]],
    candidate_generation_summary: dict[str, Any],
    selected_summary: dict[str, Any],
    high_quality_mode: bool,
    root: Path,
) -> dict[str, Any]:
    host_path, container_video_path = _resolve_video_path(clip, metadata, root=root)
    subtitle_path, container_subtitle_path = _resolve_subtitle_path(clip, metadata, root=root)
    external_subtitle_autoload_risks = same_basename_subtitle_sidecars(host_path)
    metadata_probe = _metadata_probe(metadata)
    probe = metadata_probe
    if probe.width is None or probe.height is None or probe.duration is None:
        probe = probe_video(host_path=host_path, container_path=container_video_path, root=root)
    transcript = _transcript_excerpt(transcript_segments, clip)
    subtitle = analyze_ass_subtitles(subtitle_path, clip_type=str(clip.get("type") or ""))
    duration_policy = _duration_policy(
        clip_type=str(clip.get("type") or ""),
        candidate_generation_summary=candidate_generation_summary,
    )
    warnings = _quality_warnings(
        clip=clip,
        metadata=metadata,
        transcript=transcript,
        probe=probe,
        subtitle=subtitle,
        duration_policy=duration_policy,
        external_subtitle_autoload_risks=external_subtitle_autoload_risks,
        high_quality_mode=high_quality_mode,
    )
    warning_details = _warning_details(
        warnings=warnings,
        clip=clip,
        transcript=transcript,
        probe=probe,
        subtitle=subtitle,
        duration_policy=duration_policy,
        selected_summary=selected_summary,
        external_subtitle_autoload_risks=external_subtitle_autoload_risks,
    )
    title = clip.get("title") or metadata.get("title")
    title_source = clip.get("title_source") or metadata.get("title_source")
    overlay_title = clip.get("overlay_title") or metadata.get("overlay_title")
    overlay_title_mode = _overlay_title_mode(clip, metadata)
    overlay_title_expected = _overlay_title_expected(clip, metadata, high_quality_mode=high_quality_mode)
    overlay_title_rendered = _metadata_bool(clip, metadata, "overlay_title_rendered")
    if overlay_title_rendered is None:
        overlay_title_rendered = bool(subtitle.get("title_dialogue_count", 0))
    overlay_title_not_rendered = bool(overlay_title and not overlay_title_rendered)
    duration = _number(clip.get("duration")) or probe.duration
    original_start = _first_number(clip.get("original_start"), metadata.get("original_start"))
    original_end = _first_number(clip.get("original_end"), metadata.get("original_end"))
    refined_start = _first_number(clip.get("refined_start"), metadata.get("refined_start"))
    refined_end = _first_number(clip.get("refined_end"), metadata.get("refined_end"))
    return {
        "id": clip.get("id"),
        "type": clip.get("type"),
        "file_path": str(host_path) if host_path is not None else None,
        "container_file_path": container_video_path,
        "duration": duration,
        "duration_policy": duration_policy,
        "resolution": {
            "width": probe.width,
            "height": probe.height,
            "source": probe.source,
            "error": probe.error,
        },
        "selected_start": clip.get("start"),
        "selected_end": clip.get("end"),
        "original_start": original_start,
        "original_end": original_end,
        "refined_start": refined_start,
        "refined_end": refined_end,
        "boundary_refined": clip.get("boundary_refined") or _bool(metadata.get("boundary_refined")),
        "boundary_refinement_reason": (
            clip.get("boundary_refinement_reason") or metadata.get("boundary_refinement_reason")
        ),
        "boundary_expansion_seconds": _first_number(
            clip.get("boundary_expansion_seconds"),
            metadata.get("boundary_expansion_seconds"),
        ),
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
        "external_subtitle_autoload_risk_files": [str(path) for path in external_subtitle_autoload_risks],
        "subtitle": subtitle,
        "title": title,
        "overlay_title": overlay_title,
        "overlay_title_expected": overlay_title_expected,
        "overlay_title_rendered": overlay_title_rendered,
        "overlay_title_mode": overlay_title_mode,
        "overlay_title_not_rendered": overlay_title_not_rendered,
        "title_source": title_source,
        "metadata_path": metadata.get("_metadata_path"),
        "warnings": warnings,
        "warning_details": warning_details,
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
    candidate_generation_summary = read_json(output_dir / "candidate_generation_summary.json", {})
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
            candidate_generation_summary=(
                candidate_generation_summary if isinstance(candidate_generation_summary, dict) else {}
            ),
            selected_summary=selected_summary if isinstance(selected_summary, dict) else {},
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
            "warning_details": clip.get("warning_details"),
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
            "candidate_generation_summary": (
                candidate_generation_summary if isinstance(candidate_generation_summary, dict) else {}
            ),
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
            "| Type | Clip | Range | Original Range | Duration | Resolution | Final | "
            "Selection | Boundary | Warnings | Title | Title Source | Overlay |",
            "| --- | --- | --- | --- | ---: | --- | ---: | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for clip in report["clips"]:
        resolution = clip.get("resolution") or {}
        width = resolution.get("width")
        height = resolution.get("height")
        resolution_text = f"{width}x{height}" if width and height else "unknown"
        original_range = ""
        if clip.get("original_start") is not None and clip.get("original_end") is not None:
            original_range = f"{_markdown_value(clip.get('original_start'))}-{_markdown_value(clip.get('original_end'))}"
        lines.append(
            "| "
            f"{_markdown_value(clip.get('type'))} | "
            f"`{_markdown_value(clip.get('id'), limit=48)}` | "
            f"{_markdown_value(clip.get('selected_start'))}-"
            f"{_markdown_value(clip.get('selected_end'))} | "
            f"{_markdown_value(original_range)} | "
            f"{_markdown_value(clip.get('duration'))} | "
            f"{resolution_text} | "
            f"{_markdown_value(clip.get('final_score'))} | "
            f"{_markdown_value(clip.get('selection_reason'))} | "
            f"{_markdown_value(clip.get('boundary_refinement_reason'))} | "
            f"{_markdown_value(clip.get('warnings'), limit=160)} | "
            f"{_markdown_value(clip.get('title'))} | "
            f"{_markdown_value(clip.get('title_source'))} | "
            f"{_markdown_value(clip.get('overlay_title'))} |"
        )

    detail_clips = [
        clip
        for clip in report["clips"]
        if isinstance(clip.get("warning_details"), dict) and clip.get("warning_details")
    ]
    if detail_clips:
        lines.extend(
            [
                "",
                "## Warning Details",
                "",
                "| Type | Clip | Warning | Details |",
                "| --- | --- | --- | --- |",
            ]
        )
        for clip in detail_clips:
            warning_details = clip.get("warning_details") or {}
            for warning, details in sorted(warning_details.items()):
                lines.append(
                    "| "
                    f"{_markdown_value(clip.get('type'))} | "
                    f"`{_markdown_value(clip.get('id'), limit=48)}` | "
                    f"`{_markdown_value(warning)}` | "
                    f"{_markdown_value(details, limit=220)} |"
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
