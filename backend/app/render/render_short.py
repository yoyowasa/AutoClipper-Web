from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.title_fallback import candidate_with_title, resolve_candidate_title
from app.ids import make_id
from app.short_banners import resolve_banner_path
from app.models import ExportItem, Job
from app.render.crop_strategy import (
    CropLayout,
    CropPlan,
    CropStrategy,
    SHORT_HEIGHT,
    SHORT_WIDTH,
    build_center_crop_filter as _build_center_crop_filter,
    build_crop_filter,
    plan_short_crop,
    resolve_tracking_crop_evidence_geometry,
    resolve_tracking_crop_geometry,
    tracking_safe_margins,
)
from app.render.filters import ass_filter, loudnorm_filter
from app.render.subtitles_ass import SubtitleLayout, SubtitleRenderSettings, write_ass_for_candidate
from app.render.title_policy import (
    normalize_short_overlay_title_mode,
    short_overlay_title_expected,
)
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.face_detect import FaceDetection, best_face_center, detect_faces_for_clip
from app.video.person_detect import PersonDetection, detect_person_for_clip
from app.video.probe import VideoMetadata, probe_metadata
from app.video.speaker_detect import DialogueWindow, SpeakerDetection, detect_speaker_for_clip, dialogue_windows_for_clip
from app.video.subject_detect import SubjectDetection, detect_subject_for_clip

SHORT_BANNER_ASSET_DIR = Path(__file__).resolve().parent / "assets"
DEFAULT_SHORT_TOP_BANNER_PATH = SHORT_BANNER_ASSET_DIR / "short_top_banner.png"
DEFAULT_SHORT_BOTTOM_BANNER_PATH = SHORT_BANNER_ASSET_DIR / "short_bottom_banner.png"
SHORT_BANNER_HEIGHT = SHORT_WIDTH // 3


@dataclass(frozen=True)
class ShortRenderResult:
    path: Path
    strategy: CropStrategy
    crop_signal_source: str | None = None
    crop_confidence: float | None = None
    crop_fallback_reason: str | None = None
    crop_x: int | None = None
    crop_y: int | None = None
    crop_detection_count: int | None = None
    crop_sampled_frames: int | None = None
    crop_subject_x: float | None = None
    crop_stability_score: float | None = None
    person_detection_count: int | None = None
    person_detection_confidence: float | None = None
    person_box: tuple[float, float, float, float] | None = None
    face_box: tuple[float, float, float, float] | None = None
    speaker_window_count: int | None = None
    speaker_region_confidence: float | None = None
    speaker_region_box: tuple[float, float, float, float] | None = None
    tracking_evidence: dict[str, Any] | None = None
    crop_attempted_strategies: tuple[CropStrategy, ...] = ()


@dataclass(frozen=True)
class ShortRenderFailure:
    candidate_id: str
    error: str


@dataclass(frozen=True)
class ShortRenderBatchResult:
    exports: list[ExportItem]
    failures: list[ShortRenderFailure]


def build_center_crop_filter(subtitle_path: str | Path | None = None) -> str:
    return _build_center_crop_filter(subtitle_path)


ShortCommandRunner = Callable[[list[str]], None]
ShortClipRenderer = Callable[..., Path | ShortRenderResult]
FaceDetector = Callable[[str | Path, float, float], list[FaceDetection]]
SpeakerDetector = Callable[..., SpeakerDetection | None]
PersonDetector = Callable[[str | Path, float, float], PersonDetection | None]
SubjectDetector = Callable[[str | Path, float, float], SubjectDetection | None]
MetadataProbe = Callable[[str | Path], VideoMetadata]


def _effective_tracking_crop_coordinates(
    strategy: CropStrategy,
    *,
    source_width: int,
    source_height: int,
    target_height: int,
    face_center: tuple[float, float] | None,
    speaker_center: tuple[float, float] | None,
    person_center: tuple[float, float] | None,
    subject_center: tuple[float, float] | None,
    framing_offset_x: float,
    framing_offset_y: float,
    framing_zoom: float,
) -> tuple[int | None, int | None]:
    centers = {
        "face_tracking_crop": face_center,
        "speaker_tracking_crop": speaker_center,
        "person_tracking_crop": person_center,
        "subject_tracking_crop": subject_center,
    }
    center = centers.get(strategy)
    if center is None:
        return None, None
    _, _, crop_x, crop_y = resolve_tracking_crop_geometry(
        source_width,
        source_height,
        center,
        target_width=SHORT_WIDTH,
        target_height=target_height,
        framing_offset_x=framing_offset_x,
        framing_offset_y=framing_offset_y,
        framing_zoom=framing_zoom,
    )
    return crop_x, crop_y


def _tracking_evidence_for_render(
    strategy: CropStrategy,
    *,
    crop_plan: CropPlan,
    detections: Sequence[FaceDetection],
    start: float,
    end: float,
    source_width: int,
    source_height: int,
    target_height: int,
    framing_offset_x: float,
    framing_offset_y: float,
    framing_zoom: float,
) -> dict[str, Any] | None:
    centers = {
        "face_tracking_crop": crop_plan.face_center or best_face_center(detections),
        "speaker_tracking_crop": crop_plan.speaker_center,
        "person_tracking_crop": crop_plan.person_center,
        "subject_tracking_crop": crop_plan.subject_center,
    }
    center = centers.get(strategy)
    margins = tracking_safe_margins(strategy)
    if center is None or margins is None:
        return None
    scaled_width, scaled_height, crop_x, crop_y = resolve_tracking_crop_evidence_geometry(
        source_width,
        source_height,
        center,
        target_width=SHORT_WIDTH,
        target_height=target_height,
        framing_offset_x=framing_offset_x,
        framing_offset_y=framing_offset_y,
        framing_zoom=framing_zoom,
    )
    margin_left, margin_top, margin_right, margin_bottom = margins
    safe_width = SHORT_WIDTH - margin_left - margin_right
    safe_height = target_height - margin_top - margin_bottom
    if safe_width <= 0 or safe_height <= 0:
        return None

    samples: list[dict[str, Any]] = []
    if strategy == "face_tracking_crop":
        samples = [
            {
                "start": detection.start,
                "end": detection.end,
                "box": [
                    detection.center_x - detection.width / 2,
                    detection.center_y - detection.height / 2,
                    detection.center_x + detection.width / 2,
                    detection.center_y + detection.height / 2,
                ],
                "confidence": detection.confidence,
                "source": "face_detection",
            }
            for detection in detections
        ]
    elif strategy == "speaker_tracking_crop" and crop_plan.speaker_region_box is not None:
        samples = [
            {
                "start": start,
                "end": end,
                "box": list(crop_plan.speaker_region_box),
                "confidence": crop_plan.speaker_region_confidence,
                "source": crop_plan.signal_source,
            }
        ]
    elif strategy == "person_tracking_crop" and crop_plan.person_box is not None:
        samples = [
            {
                "start": start,
                "end": end,
                "box": list(crop_plan.person_box),
                "confidence": crop_plan.person_detection_confidence,
                "source": crop_plan.signal_source,
            }
        ]

    return {
        "schema_version": 1,
        "strategy": strategy,
        "source": {"width": source_width, "height": source_height},
        "scaled": {"width": scaled_width, "height": scaled_height},
        "crop": {
            "x": crop_x,
            "y": crop_y,
            "width": SHORT_WIDTH,
            "height": target_height,
        },
        "safe_area": {
            "x": crop_x + margin_left,
            "y": crop_y + margin_top,
            "width": safe_width,
            "height": safe_height,
        },
        "samples": samples,
    }


def _duration(start: float, end: float) -> float:
    duration = end - start
    if duration <= 0:
        raise ValueError("end must be greater than start")
    return duration


def _run_ffmpeg_command(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _hook_scene_range(
    start: float | None,
    end: float | None,
) -> tuple[float, float, float] | None:
    if (start is None) != (end is None):
        raise ValueError("hook scene requires both start and end")
    if start is None or end is None:
        return None
    duration = end - start
    if not 0.5 <= duration <= 3:
        raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
    return start, end, duration


def _labeled_crop_filter(
    input_label: str,
    output_label: str,
    namespace: str,
    *,
    layout: CropStrategy,
    source_width: int | None,
    source_height: int | None,
    face_center: tuple[float, float] | None,
    speaker_center: tuple[float, float] | None,
    person_center: tuple[float, float] | None,
    subject_center: tuple[float, float] | None,
    content_height: int = SHORT_HEIGHT,
    content_y: int = 0,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> str:
    if content_height <= 0 or content_y < 0 or content_y + content_height > SHORT_HEIGHT:
        raise ValueError("short content viewport must stay within 1080x1920")
    pad_filter = (
        ""
        if content_height == SHORT_HEIGHT and content_y == 0
        else f",pad={SHORT_WIDTH}:{SHORT_HEIGHT}:0:{content_y}:color=black"
    )
    if layout == "blur_background":
        foreground_width = round(SHORT_WIDTH * framing_zoom)
        foreground_height = round(content_height * framing_zoom)
        foreground_width += foreground_width % 2
        foreground_height += foreground_height % 2
        overlay_x = f"(W-w)/2-(w-W)*{framing_offset_x / 200:.4f}"
        overlay_y = f"(H-h)/2-(h-H)*{framing_offset_y / 200:.4f}"
        return (
            f"[{input_label}]setpts=PTS-STARTPTS,"
            f"split=2[{namespace}_bgsrc][{namespace}_fgsrc];"
            f"[{namespace}_bgsrc]"
            f"scale={SHORT_WIDTH}:{content_height}:force_original_aspect_ratio=increase,"
            f"crop={SHORT_WIDTH}:{content_height},gblur=sigma=24[{namespace}_bg];"
            f"[{namespace}_fgsrc]"
            f"scale={foreground_width}:{foreground_height}:force_original_aspect_ratio=decrease"
            f"[{namespace}_fg];"
            f"[{namespace}_bg][{namespace}_fg]"
            f"overlay={overlay_x}:{overlay_y}{pad_filter}[{output_label}]"
        )
    crop_filter = build_crop_filter(
        layout,
        source_width=source_width,
        source_height=source_height,
        face_center=face_center,
        speaker_center=speaker_center,
        person_center=person_center,
        subject_center=subject_center,
        target_width=SHORT_WIDTH,
        target_height=content_height,
        framing_offset_x=framing_offset_x,
        framing_offset_y=framing_offset_y,
        framing_zoom=framing_zoom,
    )
    return (
        f"[{input_label}]setpts=PTS-STARTPTS,{crop_filter}{pad_filter}[{output_label}]"
    )


def _content_viewport(
    *,
    top_banner_enabled: bool,
    bottom_banner_enabled: bool,
) -> tuple[int, int]:
    content_y = SHORT_BANNER_HEIGHT if top_banner_enabled else 0
    reserved_height = content_y
    if bottom_banner_enabled:
        reserved_height += SHORT_BANNER_HEIGHT
    return SHORT_HEIGHT - reserved_height, content_y


def _banner_input_args(
    *,
    top_banner_path: str | Path | None,
    bottom_banner_path: str | Path | None,
    first_input_index: int,
) -> tuple[list[str], int | None, int | None]:
    args: list[str] = []
    next_input_index = first_input_index
    top_input_index: int | None = None
    bottom_input_index: int | None = None

    if top_banner_path is not None:
        top_input_index = next_input_index
        next_input_index += 1
        args.extend(["-loop", "1", "-i", str(top_banner_path)])
    if bottom_banner_path is not None:
        bottom_input_index = next_input_index
        args.extend(["-loop", "1", "-i", str(bottom_banner_path)])

    return args, top_input_index, bottom_input_index


def _append_banner_and_subtitle_filters(
    filters: list[str],
    video_label: str,
    *,
    subtitle_path: str | Path | None,
    top_banner_input_index: int | None,
    bottom_banner_input_index: int | None,
) -> str:
    current_label = video_label
    has_banner = top_banner_input_index is not None or bottom_banner_input_index is not None

    if top_banner_input_index is not None:
        filters.append(
            f"[{top_banner_input_index}:v:0]"
            f"scale={SHORT_WIDTH}:-2,setpts=PTS-STARTPTS,format=rgba[top_banner]"
        )
        filters.append(
            f"[{current_label}][top_banner]"
            "overlay=0:0:shortest=1:format=auto[top_banded]"
        )
        current_label = "top_banded"

    if bottom_banner_input_index is not None:
        filters.append(
            f"[{bottom_banner_input_index}:v:0]"
            f"scale={SHORT_WIDTH}:-2,setpts=PTS-STARTPTS,format=rgba[bottom_banner]"
        )
        filters.append(
            f"[{current_label}][bottom_banner]"
            "overlay=0:H-h:shortest=1:format=auto[bottom_banded]"
        )
        current_label = "bottom_banded"

    if subtitle_path is not None:
        subtitle_output_label = "subtitled_v" if has_banner else "video_out"
        filters.append(f"[{current_label}]{ass_filter(subtitle_path)}[{subtitle_output_label}]")
        current_label = subtitle_output_label

    if has_banner:
        filters.append(f"[{current_label}]format=yuv420p,setsar=1[video_out]")
        current_label = "video_out"

    return current_label


def _build_hook_prepend_filter(
    *,
    layout: CropStrategy,
    subtitle_path: str | Path | None,
    normalize_audio: bool,
    source_width: int | None,
    source_height: int | None,
    face_center: tuple[float, float] | None,
    speaker_center: tuple[float, float] | None,
    person_center: tuple[float, float] | None,
    subject_center: tuple[float, float] | None,
    top_banner_input_index: int | None = None,
    bottom_banner_input_index: int | None = None,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> tuple[str, str, str]:
    content_height, content_y = _content_viewport(
        top_banner_enabled=top_banner_input_index is not None,
        bottom_banner_enabled=bottom_banner_input_index is not None,
    )
    filters = [
        _labeled_crop_filter(
            "0:v:0",
            "hook_v",
            "hook",
            layout=layout,
            source_width=source_width,
            source_height=source_height,
            face_center=face_center,
            speaker_center=speaker_center,
            person_center=person_center,
            subject_center=subject_center,
            content_height=content_height,
            content_y=content_y,
            framing_offset_x=framing_offset_x,
            framing_offset_y=framing_offset_y,
            framing_zoom=framing_zoom,
        ),
        _labeled_crop_filter(
            "1:v:0",
            "main_v",
            "main",
            layout=layout,
            source_width=source_width,
            source_height=source_height,
            face_center=face_center,
            speaker_center=speaker_center,
            person_center=person_center,
            subject_center=subject_center,
            content_height=content_height,
            content_y=content_y,
            framing_offset_x=framing_offset_x,
            framing_offset_y=framing_offset_y,
            framing_zoom=framing_zoom,
        ),
        "[0:a:0]aresample=48000,asetpts=PTS-STARTPTS[hook_a]",
        "[1:a:0]aresample=48000,asetpts=PTS-STARTPTS[main_a]",
        (
            "[hook_v][hook_a][main_v][main_a]"
            "concat=n=2:v=1:a=1[concat_v][concat_a]"
        ),
    ]
    video_label = _append_banner_and_subtitle_filters(
        filters,
        "concat_v",
        subtitle_path=subtitle_path,
        top_banner_input_index=top_banner_input_index,
        bottom_banner_input_index=bottom_banner_input_index,
    )
    audio_label = "concat_a"
    if normalize_audio:
        filters.append(f"[concat_a]{loudnorm_filter()}[audio_out]")
        audio_label = "audio_out"
    return ";".join(filters), video_label, audio_label


def build_render_short_command(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
    layout: CropStrategy = "center_crop",
    source_width: int | None = None,
    source_height: int | None = None,
    face_center: tuple[float, float] | None = None,
    speaker_center: tuple[float, float] | None = None,
    person_center: tuple[float, float] | None = None,
    subject_center: tuple[float, float] | None = None,
    hook_scene_start: float | None = None,
    hook_scene_end: float | None = None,
    top_banner_path: str | Path | None = None,
    bottom_banner_path: str | Path | None = None,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
) -> list[str]:
    hook_scene = _hook_scene_range(hook_scene_start, hook_scene_end)
    if hook_scene is not None:
        hook_start, _hook_end, hook_duration = hook_scene
        banner_args, top_banner_input_index, bottom_banner_input_index = _banner_input_args(
            top_banner_path=top_banner_path,
            bottom_banner_path=bottom_banner_path,
            first_input_index=2,
        )
        filter_graph, video_label, audio_label = _build_hook_prepend_filter(
            layout=layout,
            subtitle_path=subtitle_path,
            normalize_audio=normalize_audio,
            source_width=source_width,
            source_height=source_height,
            face_center=face_center,
            speaker_center=speaker_center,
            person_center=person_center,
            subject_center=subject_center,
            top_banner_input_index=top_banner_input_index,
            bottom_banner_input_index=bottom_banner_input_index,
            framing_offset_x=framing_offset_x,
            framing_offset_y=framing_offset_y,
            framing_zoom=framing_zoom,
        )
        return [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{hook_start:.3f}",
            "-t",
            f"{hook_duration:.3f}",
            "-i",
            str(input_path),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{_duration(start, end):.3f}",
            "-i",
            str(input_path),
            *banner_args,
            "-filter_complex",
            filter_graph,
            "-map",
            f"[{video_label}]",
            "-map",
            f"[{audio_label}]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    banner_args, top_banner_input_index, bottom_banner_input_index = _banner_input_args(
        top_banner_path=top_banner_path,
        bottom_banner_path=bottom_banner_path,
        first_input_index=1,
    )
    if banner_args:
        content_height, content_y = _content_viewport(
            top_banner_enabled=top_banner_input_index is not None,
            bottom_banner_enabled=bottom_banner_input_index is not None,
        )
        filters = [
            _labeled_crop_filter(
                "0:v:0",
                "main_v",
                "main",
                layout=layout,
                source_width=source_width,
                source_height=source_height,
                face_center=face_center,
                speaker_center=speaker_center,
                person_center=person_center,
                subject_center=subject_center,
                content_height=content_height,
                content_y=content_y,
                framing_offset_x=framing_offset_x,
                framing_offset_y=framing_offset_y,
                framing_zoom=framing_zoom,
            )
        ]
        video_label = _append_banner_and_subtitle_filters(
            filters,
            "main_v",
            subtitle_path=subtitle_path,
            top_banner_input_index=top_banner_input_index,
            bottom_banner_input_index=bottom_banner_input_index,
        )
        command = [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(input_path),
            *banner_args,
            "-t",
            f"{_duration(start, end):.3f}",
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{video_label}]",
            "-map",
            "0:a?",
        ]
    else:
        command = [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(input_path),
            "-t",
            f"{_duration(start, end):.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-vf",
            build_crop_filter(
                layout,
                subtitle_path=subtitle_path,
                source_width=source_width,
                source_height=source_height,
                face_center=face_center,
                speaker_center=speaker_center,
                person_center=person_center,
                subject_center=subject_center,
                framing_offset_x=framing_offset_x,
                framing_offset_y=framing_offset_y,
                framing_zoom=framing_zoom,
            ),
        ]

    if normalize_audio:
        command.extend(["-af", loudnorm_filter()])

    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def render_short_center_crop(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    command = build_render_short_command(
        input_path,
        output_path,
        start,
        end,
        subtitle_path=subtitle_path,
        normalize_audio=normalize_audio,
        ffmpeg_bin=ffmpeg_bin,
    )
    _run_ffmpeg_command(command)
    return Path(output_path)


def _source_dimensions(
    input_path: str | Path,
    source_width: int | None,
    source_height: int | None,
    metadata_probe: MetadataProbe,
) -> tuple[int | None, int | None]:
    if source_width is not None and source_height is not None:
        return source_width, source_height
    try:
        metadata = metadata_probe(input_path)
    except Exception:
        return source_width, source_height
    return source_width or metadata.width, source_height or metadata.height


def _detect_faces_for_layout(
    layout: CropLayout,
    input_path: str | Path,
    start: float,
    end: float,
    face_detector: FaceDetector,
) -> list[FaceDetection]:
    if layout not in ("auto", "face_tracking_crop"):
        return []
    try:
        return face_detector(input_path, start, end)
    except Exception:
        return []


def _detect_subject_for_layout(
    layout: CropLayout,
    input_path: str | Path,
    start: float,
    end: float,
    subject_detector: SubjectDetector,
) -> SubjectDetection | None:
    if layout != "auto":
        return None
    try:
        return subject_detector(input_path, start, end)
    except Exception:
        return None


def _detect_person_for_layout(
    layout: CropLayout,
    input_path: str | Path,
    start: float,
    end: float,
    person_detector: PersonDetector,
) -> PersonDetection | None:
    if layout != "auto":
        return None
    try:
        return person_detector(input_path, start, end)
    except Exception:
        return None


def _detect_speaker_for_layout(
    layout: CropLayout,
    input_path: str | Path,
    start: float,
    end: float,
    dialogue_windows: Sequence[DialogueWindow] | None,
    speaker_detector: SpeakerDetector,
    face_detector: FaceDetector,
    person_detector: PersonDetector,
) -> SpeakerDetection | None:
    if layout != "auto" or not dialogue_windows:
        return None
    try:
        return speaker_detector(
            input_path,
            start,
            end,
            dialogue_windows,
            face_detector=face_detector,
            person_detector=person_detector,
        )
    except Exception:
        return None


def _needs_secondary_crop_signals(layout: CropLayout, crop_plan: Any) -> bool:
    return layout == "auto" and crop_plan.fallback_reason in {
        "no_face_detections",
        "weak_face_signal",
        "no_face_center",
        "face_group_too_wide_for_9x16_crop",
    }


def resolve_short_crop_plan(
    input_path: str | Path, start: float, end: float, *,
    layout: CropLayout, width: int, height: int, target_height: int,
    dialogue_windows: Sequence[DialogueWindow] | None = None,
    face_detector: FaceDetector = detect_faces_for_clip,
    speaker_detector: SpeakerDetector = detect_speaker_for_clip,
    person_detector: PersonDetector = detect_person_for_clip,
    subject_detector: SubjectDetector = detect_subject_for_clip,
) -> tuple[CropPlan, Sequence[FaceDetection]]:
    """Resolve the same composition for rendering and the interactive crop guide."""
    detections = _detect_faces_for_layout(
        layout,
        input_path=input_path,
        start=start,
        end=end,
        face_detector=face_detector,
    )
    crop_plan = plan_short_crop(
        layout,
        detections=detections,
        source_width=width,
        source_height=height,
        target_width=SHORT_WIDTH,
        target_height=target_height,
    )
    if _needs_secondary_crop_signals(layout, crop_plan):
        speaker_signal = _detect_speaker_for_layout(
            layout,
            input_path=input_path,
            start=start,
            end=end,
            dialogue_windows=dialogue_windows,
            speaker_detector=speaker_detector,
            face_detector=face_detector,
            person_detector=person_detector,
        )
        person_signal = _detect_person_for_layout(
            layout,
            input_path=input_path,
            start=start,
            end=end,
            person_detector=person_detector,
        )
        subject_signal = _detect_subject_for_layout(
            layout,
            input_path=input_path,
            start=start,
            end=end,
            subject_detector=subject_detector,
        )
        crop_plan = plan_short_crop(
            layout,
            detections=detections,
            source_width=width,
            source_height=height,
            speaker_signal=speaker_signal,
            person_signal=person_signal,
            subject_signal=subject_signal,
            target_width=SHORT_WIDTH,
            target_height=target_height,
        )
    return crop_plan, detections


def render_short_clip(
    input_path: str | Path,
    output_path: str | Path,
    start: float,
    end: float,
    subtitle_path: str | Path | None = None,
    normalize_audio: bool = False,
    ffmpeg_bin: str = "ffmpeg",
    layout: CropLayout = "auto",
    source_width: int | None = None,
    source_height: int | None = None,
    face_detector: FaceDetector = detect_faces_for_clip,
    speaker_detector: SpeakerDetector = detect_speaker_for_clip,
    person_detector: PersonDetector = detect_person_for_clip,
    subject_detector: SubjectDetector = detect_subject_for_clip,
    metadata_probe: MetadataProbe = probe_metadata,
    command_runner: ShortCommandRunner = _run_ffmpeg_command,
    dialogue_windows: Sequence[DialogueWindow] | None = None,
    hook_scene_start: float | None = None,
    hook_scene_end: float | None = None,
    top_banner_path: str | Path | None = None,
    bottom_banner_path: str | Path | None = None,
    framing_offset_x: float = 0.0,
    framing_offset_y: float = 0.0,
    framing_zoom: float = 1.0,
    live_output_path: str | Path | None = None,
) -> ShortRenderResult:
    for label, banner_path in (
        ("top", top_banner_path),
        ("bottom", bottom_banner_path),
    ):
        if banner_path is not None and not Path(banner_path).is_file():
            raise FileNotFoundError(f"short {label} banner asset not found: {banner_path}")

    width, height = _source_dimensions(
        input_path,
        source_width=source_width,
        source_height=source_height,
        metadata_probe=metadata_probe,
    )
    content_height, _content_y = _content_viewport(
        top_banner_enabled=top_banner_path is not None,
        bottom_banner_enabled=bottom_banner_path is not None,
    )
    crop_plan, detections = resolve_short_crop_plan(
        input_path, start, end, layout=layout, width=width, height=height,
        target_height=content_height, dialogue_windows=dialogue_windows,
        face_detector=face_detector, speaker_detector=speaker_detector,
        person_detector=person_detector, subject_detector=subject_detector,
    )
    face_center = crop_plan.face_center or best_face_center(detections)
    speaker_center = crop_plan.speaker_center
    person_center = crop_plan.person_center
    subject_center = crop_plan.subject_center
    last_error: Exception | None = None
    attempted: list[CropStrategy] = []

    for strategy in crop_plan.strategy_order:
        attempted.append(strategy)
        try:
            command = build_render_short_command(
                input_path,
                output_path,
                start=start,
                end=end,
                subtitle_path=subtitle_path if live_output_path is None else None,
                normalize_audio=normalize_audio,
                ffmpeg_bin=ffmpeg_bin,
                layout=strategy,
                source_width=width,
                source_height=height,
                face_center=face_center if strategy == "face_tracking_crop" else None,
                speaker_center=speaker_center if strategy == "speaker_tracking_crop" else None,
                person_center=person_center if strategy == "person_tracking_crop" else None,
                subject_center=subject_center if strategy == "subject_tracking_crop" else None,
                hook_scene_start=hook_scene_start,
                hook_scene_end=hook_scene_end,
                top_banner_path=top_banner_path,
                bottom_banner_path=bottom_banner_path,
                framing_offset_x=framing_offset_x,
                framing_offset_y=framing_offset_y,
                framing_zoom=framing_zoom,
            )
            if live_output_path is not None:
                from app.render.paired_preview import paired_preview_command

                command = paired_preview_command(
                    command, live_output_path=live_output_path,
                    subtitle_path=subtitle_path,
                )
            command_runner(command)
            fallback_reason = crop_plan.fallback_reason
            if len(attempted) > 1 and fallback_reason is None:
                fallback_reason = f"render_strategy_failed:{attempted[0]}"
            crop_x, crop_y = _effective_tracking_crop_coordinates(
                strategy,
                source_width=width,
                source_height=height,
                target_height=content_height,
                face_center=face_center,
                speaker_center=speaker_center,
                person_center=person_center,
                subject_center=subject_center,
                framing_offset_x=framing_offset_x,
                framing_offset_y=framing_offset_y,
                framing_zoom=framing_zoom,
            )
            tracking_evidence = _tracking_evidence_for_render(
                strategy,
                crop_plan=crop_plan,
                detections=detections,
                start=start,
                end=end,
                source_width=width,
                source_height=height,
                target_height=content_height,
                framing_offset_x=framing_offset_x,
                framing_offset_y=framing_offset_y,
                framing_zoom=framing_zoom,
            )
            return ShortRenderResult(
                path=Path(output_path),
                strategy=strategy,
                crop_signal_source=crop_plan.signal_source,
                crop_confidence=crop_plan.confidence,
                crop_fallback_reason=fallback_reason,
                crop_x=crop_x,
                crop_y=crop_y,
                crop_detection_count=crop_plan.detection_count,
                crop_sampled_frames=crop_plan.sampled_frame_count,
                crop_subject_x=crop_plan.subject_x,
                crop_stability_score=crop_plan.stability_score,
                person_detection_count=crop_plan.person_detection_count,
                person_detection_confidence=crop_plan.person_detection_confidence,
                person_box=crop_plan.person_box,
                face_box=crop_plan.face_box,
                speaker_window_count=crop_plan.speaker_window_count,
                speaker_region_confidence=crop_plan.speaker_region_confidence,
                speaker_region_box=crop_plan.speaker_region_box,
                tracking_evidence=tracking_evidence,
                crop_attempted_strategies=tuple(attempted),
            )
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"short render failed: {last_error}") from last_error


def shorts_output_dir(paths: StoragePaths, job_id: str) -> Path:
    output_dir = paths.job_outputs(job_id) / "shorts"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def shorts_subtitle_dir(paths: StoragePaths, job_id: str) -> Path:
    return paths.job_subtitles(job_id, "short")


def _remove_autoload_sidecar(output_path: Path, subtitle_path: Path | None) -> None:
    sidecar_path = output_path.with_suffix(".ass")
    if subtitle_path is not None and sidecar_path.resolve() == subtitle_path.resolve():
        return
    if sidecar_path.is_file():
        sidecar_path.unlink()


def _candidate_score(candidate: Candidate) -> float:
    for score in (candidate.final_score, candidate.ai_score, candidate.rule_score):
        if score is not None:
            return float(score)
    return 0.0


def _candidate_title(candidate: Candidate, index: int) -> str:
    return resolve_candidate_title(candidate, index=index).title


def _setting_text(settings: SubtitleRenderSettings | dict[str, Any] | None, key: str) -> str | None:
    if isinstance(settings, dict):
        value = settings.get(key)
        if value is not None:
            return str(value)
    return None


def _render_mode(settings: SubtitleRenderSettings | dict[str, Any] | None, explicit_mode: str | None) -> str:
    return (explicit_mode or _setting_text(settings, "mode") or "high_quality").strip()


def _overlay_title_for_burn(candidate: Candidate, *, expected: bool, fallback_title: str) -> str:
    if not expected:
        return ""
    return (
        candidate.overlay_title
        if candidate.overlay_title is not None
        else fallback_title
    ).strip()


def _candidate_hook_scene_duration(candidate: Candidate) -> float:
    hook_scene = _hook_scene_range(
        candidate.hook_scene_start,
        candidate.hook_scene_end,
    )
    return 0.0 if hook_scene is None else hook_scene[2]


def _write_export_metadata(
    path: Path,
    export_id: str,
    candidate: Candidate,
    title: str,
    video_path: Path,
    subtitle_path: Path | None,
    strategy: str | None,
    crop_signal_source: str | None,
    crop_confidence: float | None,
    crop_fallback_reason: str | None,
    crop_x: int | None,
    crop_y: int | None,
    crop_detection_count: int | None,
    crop_sampled_frames: int | None,
    crop_subject_x: float | None,
    crop_stability_score: float | None,
    person_detection_count: int | None,
    person_detection_confidence: float | None,
    person_box: tuple[float, float, float, float] | None,
    face_box: tuple[float, float, float, float] | None,
    speaker_window_count: int | None,
    speaker_region_confidence: float | None,
    speaker_region_box: tuple[float, float, float, float] | None,
    tracking_evidence: Mapping[str, Any] | None,
    crop_attempted_strategies: Sequence[str],
    overlay_title_expected: bool,
    overlay_title_rendered: bool,
    overlay_title_mode: str,
    hook_rendered: bool,
    hook_scene_rendered: bool,
    top_banner_rendered: bool,
    bottom_banner_rendered: bool,
    output_duration: float,
    source_width: int | None,
    source_height: int | None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "id": export_id,
                "type": "short",
                "candidate_id": candidate.id,
                "title": title,
                "overlay_title": candidate.overlay_title,
                "overlay_title_expected": overlay_title_expected,
                "overlay_title_rendered": overlay_title_rendered,
                "overlay_title_mode": overlay_title_mode,
                "title_source": candidate.title_source,
                "title_candidates": [
                    item.model_dump(by_alias=True, mode="json")
                    for item in candidate.title_candidates
                ],
                "recommended_title_id": candidate.recommended_title_id,
                "selected_title_id": candidate.selected_title_id,
                "youtube_description": candidate.youtube_description,
                "youtube_hashtags": candidate.youtube_hashtags,
                "youtube_tags": candidate.youtube_tags,
                "description_evidence_segment_ids": candidate.description_evidence_segment_ids,
                "post_metadata_source": candidate.post_metadata_source,
                "post_metadata_revision_hash": candidate.post_metadata_revision_hash,
                "hook_text": candidate.hook_text,
                "hook_duration_seconds": candidate.hook_duration_seconds,
                "hook_rendered": hook_rendered,
                "hook_scene_start": candidate.hook_scene_start,
                "hook_scene_end": candidate.hook_scene_end,
                "thumbnail_kicker": candidate.thumbnail_kicker,
                "thumbnail_line1": candidate.thumbnail_line1,
                "thumbnail_line2": candidate.thumbnail_line2,
                "thumbnail_frame_seconds": candidate.thumbnail_frame_seconds,
                "hook_scene_duration": _candidate_hook_scene_duration(candidate),
                "hook_scene_rendered": hook_scene_rendered,
                "top_banner_rendered": top_banner_rendered,
                "bottom_banner_rendered": bottom_banner_rendered,
                "title_style": (
                    candidate.title_style.model_dump(by_alias=True)
                    if candidate.title_style
                    else None
                ),
                "hook_style": (
                    candidate.hook_style.model_dump(by_alias=True)
                    if candidate.hook_style
                    else None
                ),
                "subtitle_style": (
                    candidate.subtitle_style.model_dump(by_alias=True)
                    if candidate.subtitle_style
                    else None
                ),
                "start": candidate.start,
                "end": candidate.end,
                "duration": output_duration,
                "body_duration": candidate.duration,
                "original_start": candidate.original_start,
                "original_end": candidate.original_end,
                "refined_start": candidate.refined_start,
                "refined_end": candidate.refined_end,
                "boundary_refined": candidate.boundary_refined,
                "boundary_refinement_reason": candidate.boundary_refinement_reason,
                "boundary_expansion_seconds": candidate.boundary_expansion_seconds,
                "score": _candidate_score(candidate),
                "strategy": strategy,
                "crop_strategy": strategy,
                "crop_signal_source": crop_signal_source,
                "crop_confidence": crop_confidence,
                "crop_fallback_reason": crop_fallback_reason,
                "crop_x": crop_x,
                "crop_y": crop_y,
                "crop_detection_count": crop_detection_count,
                "crop_sampled_frames": crop_sampled_frames,
                "crop_subject_x": crop_subject_x,
                "crop_stability_score": crop_stability_score,
                "framing_offset_x": candidate.framing_offset_x,
                "framing_offset_y": candidate.framing_offset_y,
                "framing_zoom": candidate.framing_zoom,
                "source_width": source_width,
                "source_height": source_height,
                "person_detection_count": person_detection_count,
                "person_detection_confidence": person_detection_confidence,
                "person_box": list(person_box) if person_box is not None else None,
                "face_box": list(face_box) if face_box is not None else None,
                "speaker_window_count": speaker_window_count,
                "speaker_region_confidence": speaker_region_confidence,
                "speaker_region_box": list(speaker_region_box) if speaker_region_box is not None else None,
                "tracking_evidence": dict(tracking_evidence) if tracking_evidence is not None else None,
                "crop_attempted_strategies": list(crop_attempted_strategies),
                "video_path": str(video_path),
                "subtitle_path": str(subtitle_path) if subtitle_path is not None else None,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _subtitle_segments_for_candidate(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment] | None,
) -> list[TranscriptSegment]:
    if transcript_segments is not None:
        return list(transcript_segments)
    if not candidate.transcript_text.strip():
        return []
    return [
        TranscriptSegment(
            start=candidate.start,
            end=candidate.end,
            text=candidate.transcript_text,
        )
    ]


def _rendered_path(result: Path | ShortRenderResult) -> Path:
    if isinstance(result, ShortRenderResult):
        return result.path
    return Path(result)


def render_selected_short_candidates(
    db: Session,
    job: Job,
    input_path: str | Path,
    selected_candidates: Sequence[Candidate],
    transcript_segments: Sequence[TranscriptSegment] | None = None,
    burn_subtitles: bool = True,
    normalize_audio: bool = False,
    layout: CropLayout = "auto",
    paths: StoragePaths | None = None,
    renderer: ShortClipRenderer = render_short_clip,
    ffmpeg_bin: str = "ffmpeg",
    source_width: int | None = None,
    source_height: int | None = None,
    subtitle_settings: SubtitleRenderSettings | dict[str, Any] | None = None,
    mode: str | None = None,
    short_overlay_title_mode: str | None = None,
    short_top_banner_enabled: bool = False,
    short_bottom_banner_enabled: bool = False,
    banner_paths: StoragePaths | None = None,
) -> ShortRenderBatchResult:
    storage_paths = paths or get_storage_paths()
    banner_storage_paths = banner_paths or storage_paths
    output_dir = shorts_output_dir(storage_paths, job.id)
    subtitle_dir = shorts_subtitle_dir(storage_paths, job.id)
    exports: list[ExportItem] = []
    failures: list[ShortRenderFailure] = []
    resolved_mode = _render_mode(subtitle_settings, mode)
    stored_overlay_title_mode = normalize_short_overlay_title_mode(
        short_overlay_title_mode or _setting_text(subtitle_settings, "shortOverlayTitleMode")
    )
    overlay_title_mode = (
        "always" if short_top_banner_enabled else stored_overlay_title_mode
    )

    short_candidates = [candidate for candidate in selected_candidates if candidate.type == "short"]
    for index, candidate in enumerate(short_candidates, start=1):
        candidate = candidate_with_title(candidate, index=index, transcript_segments=transcript_segments)
        hook_scene_duration = _candidate_hook_scene_duration(candidate)
        output_duration = candidate.duration + hook_scene_duration
        hook_scene_rendered = hook_scene_duration > 0
        overlay_expected = bool(
            candidate.overlay_title
            if candidate.overlay_title is not None
            else candidate.title
        ) and short_overlay_title_expected(
            render_mode=resolved_mode,
            stored_mode=stored_overlay_title_mode,
            top_banner_enabled=short_top_banner_enabled,
            title_manually_reviewed=candidate.title_source == "manual_review",
        )
        export_id = make_id("exp")
        output_path = output_dir / f"short_{index:02d}.mp4"
        metadata_path = output_dir / f"short_{index:02d}.json"
        subtitle_path: Path | None = None

        try:
            title = _candidate_title(candidate, index)
            top_title = _overlay_title_for_burn(candidate, expected=overlay_expected, fallback_title=title)
            hook_rendered = bool(burn_subtitles and candidate.hook_text)
            overlay_rendered = bool(
                top_title
                and (
                    not hook_rendered
                    or (candidate.hook_duration_seconds or 3.0) < output_duration
                )
            )
            if burn_subtitles or short_top_banner_enabled or top_title:
                subtitle_path = subtitle_dir / f"short_{index:02d}.ass"
                ass_candidate = (
                    candidate
                    if burn_subtitles
                    else candidate.model_copy(update={"hook_text": None})
                )
                write_ass_for_candidate(
                    ass_candidate,
                    (
                        _subtitle_segments_for_candidate(candidate, transcript_segments)
                        if burn_subtitles
                        else []
                    ),
                    subtitle_path,
                    layout=SubtitleLayout.short(settings=subtitle_settings),
                    top_title=top_title,
                    subtitle_settings=subtitle_settings,
                )

            render_kwargs: dict[str, Any] = {
                "start": candidate.start,
                "end": candidate.end,
                "subtitle_path": subtitle_path,
                "normalize_audio": normalize_audio,
                "ffmpeg_bin": ffmpeg_bin,
                "layout": candidate.short_layout or layout,
                "source_width": source_width,
                "source_height": source_height,
                "framing_offset_x": candidate.framing_offset_x,
                "framing_offset_y": candidate.framing_offset_y,
                "framing_zoom": candidate.framing_zoom,
                "dialogue_windows": dialogue_windows_for_clip(
                    candidate.start,
                    candidate.end,
                    transcript_segments,
                ),
            }
            if short_top_banner_enabled:
                render_kwargs["top_banner_path"] = resolve_banner_path(
                    job.settings_json, "top", DEFAULT_SHORT_TOP_BANNER_PATH, banner_storage_paths
                )
            if short_bottom_banner_enabled:
                render_kwargs["bottom_banner_path"] = resolve_banner_path(
                    job.settings_json, "bottom", DEFAULT_SHORT_BOTTOM_BANNER_PATH, banner_storage_paths
                )
            if hook_scene_rendered:
                render_kwargs["hook_scene_start"] = candidate.hook_scene_start
                render_kwargs["hook_scene_end"] = candidate.hook_scene_end
            render_result = renderer(
                input_path,
                output_path,
                **render_kwargs,
            )
            rendered_path = _rendered_path(render_result)
            _remove_autoload_sidecar(output_path, subtitle_path)
            _write_export_metadata(
                metadata_path,
                export_id=export_id,
                candidate=candidate,
                title=title,
                video_path=rendered_path,
                subtitle_path=subtitle_path,
                strategy=render_result.strategy if isinstance(render_result, ShortRenderResult) else None,
                crop_signal_source=render_result.crop_signal_source if isinstance(render_result, ShortRenderResult) else None,
                crop_confidence=render_result.crop_confidence if isinstance(render_result, ShortRenderResult) else None,
                crop_fallback_reason=render_result.crop_fallback_reason if isinstance(render_result, ShortRenderResult) else None,
                crop_x=render_result.crop_x if isinstance(render_result, ShortRenderResult) else None,
                crop_y=render_result.crop_y if isinstance(render_result, ShortRenderResult) else None,
                crop_detection_count=render_result.crop_detection_count if isinstance(render_result, ShortRenderResult) else None,
                crop_sampled_frames=render_result.crop_sampled_frames
                if isinstance(render_result, ShortRenderResult)
                else None,
                crop_subject_x=render_result.crop_subject_x if isinstance(render_result, ShortRenderResult) else None,
                crop_stability_score=render_result.crop_stability_score
                if isinstance(render_result, ShortRenderResult)
                else None,
                person_detection_count=render_result.person_detection_count
                if isinstance(render_result, ShortRenderResult)
                else None,
                person_detection_confidence=render_result.person_detection_confidence
                if isinstance(render_result, ShortRenderResult)
                else None,
                person_box=render_result.person_box if isinstance(render_result, ShortRenderResult) else None,
                face_box=render_result.face_box if isinstance(render_result, ShortRenderResult) else None,
                speaker_window_count=render_result.speaker_window_count
                if isinstance(render_result, ShortRenderResult)
                else None,
                speaker_region_confidence=render_result.speaker_region_confidence
                if isinstance(render_result, ShortRenderResult)
                else None,
                speaker_region_box=render_result.speaker_region_box if isinstance(render_result, ShortRenderResult) else None,
                tracking_evidence=render_result.tracking_evidence
                if isinstance(render_result, ShortRenderResult)
                else None,
                crop_attempted_strategies=render_result.crop_attempted_strategies
                if isinstance(render_result, ShortRenderResult)
                else (),
                overlay_title_expected=overlay_expected,
                overlay_title_rendered=overlay_rendered,
                overlay_title_mode=overlay_title_mode,
                hook_rendered=hook_rendered,
                hook_scene_rendered=hook_scene_rendered,
                top_banner_rendered=short_top_banner_enabled,
                bottom_banner_rendered=short_bottom_banner_enabled,
                output_duration=output_duration,
                source_width=source_width,
                source_height=source_height,
            )

            export = ExportItem(
                id=export_id,
                job_id=job.id,
                video_id=job.video_id,
                candidate_id=candidate.id,
                type="short",
                title=title,
                duration=output_duration,
                score=_candidate_score(candidate),
                video_path=str(rendered_path),
                subtitle_path=str(subtitle_path) if subtitle_path is not None else None,
                metadata_path=str(metadata_path),
            )
            db.add(export)
            db.commit()
            db.refresh(export)
            exports.append(export)
        except Exception as exc:
            db.rollback()
            failures.append(ShortRenderFailure(candidate_id=candidate.id, error=str(exc)))

    return ShortRenderBatchResult(exports=exports, failures=failures)
