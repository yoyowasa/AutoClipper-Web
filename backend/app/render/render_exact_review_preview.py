from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.title_fallback import candidate_with_title, resolve_candidate_title
from app.render.render_normal import render_normal_clip
from app.render.render_short import (
    DEFAULT_SHORT_BOTTOM_BANNER_PATH,
    DEFAULT_SHORT_TOP_BANNER_PATH,
    render_short_clip,
)
from app.render.subtitles_ass import (
    SubtitleLayout,
    parse_subtitle_settings,
    write_ass_for_candidate,
)
from app.render.title_policy import (
    normalize_short_overlay_title_mode,
    short_overlay_title_expected,
)
from app.video.speaker_detect import dialogue_windows_for_clip


EXACT_SUBTITLE_REVIEW_RENDERER_VERSION = "exact-subtitle-review-v3"
LIVE_SUBTITLE_REVIEW_RENDERER_VERSION = "live-subtitle-review-v3"
SUBTITLE_REVIEW_PREVIEW_DIRNAME = "subtitle_review_previews"
# The API keeps the full SHA-256. The 128-bit filesystem key avoids MAX_PATH
# failures under long Windows storage/test roots while remaining content addressed.
FILESYSTEM_SPEC_HASH_LENGTH = 32

NormalPreviewRenderer = Callable[..., Any]
ShortPreviewRenderer = Callable[..., Any]


@dataclass(frozen=True)
class ExactPreviewPaths:
    video_path: Path
    subtitle_path: Path
    spec_path: Path

    @property
    def video(self) -> Path:
        return self.video_path

    @property
    def subtitle(self) -> Path:
        return self.subtitle_path

    @property
    def spec(self) -> Path:
        return self.spec_path


@dataclass(frozen=True)
class ExactPreviewResult:
    path: Path
    subtitle_path: Path
    spec_path: Path
    spec_hash: str
    live_path: Path
    live_spec_path: Path
    live_spec_hash: str


@dataclass(frozen=True)
class LivePreviewPaths:
    video_path: Path
    spec_path: Path


def _normalize_for_spec(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _normalize_for_spec(
            value.model_dump(mode="json", by_alias=False, exclude_none=False)
        )
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_for_spec(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_for_spec(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("preview spec does not allow non-finite numbers")
        normalized = round(value, 6)
        return 0.0 if normalized == 0 else normalized
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported preview spec value: {type(value).__name__}")


def _canonical_spec_json(spec: Mapping[str, Any]) -> str:
    normalized = _normalize_for_spec(spec)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _relevant_segments(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
) -> list[TranscriptSegment]:
    return [
        segment
        for segment in transcript_segments
        if segment.end > candidate.start and segment.start < candidate.end
    ]


@lru_cache(maxsize=8)
def _file_sha256(path_value: str, size: int, mtime_ns: int) -> str:
    del size, mtime_ns
    digest = sha256()
    with Path(path_value).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _banner_asset_fingerprint(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
        digest = _file_sha256(str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    except OSError:
        return {"name": path.name, "state": "unavailable"}
    return {
        "name": path.name,
        "size": stat.st_size,
        "sha256": digest,
    }


def _canonical_render_settings(
    settings: Mapping[str, Any] | None,
    *,
    candidate: Candidate,
    source_width: int | None,
    source_height: int | None,
) -> dict[str, Any]:
    raw = dict(settings or {})
    subtitle_settings = asdict(parse_subtitle_settings(raw))
    layout = (
        SubtitleLayout.short(settings=subtitle_settings)
        if candidate.type == "short"
        else SubtitleLayout.normal(
            width=source_width or 1920,
            height=source_height or 1080,
            settings=subtitle_settings,
        )
    )
    render_settings: dict[str, Any] = {
        "layout": asdict(layout),
        "burnSubtitles": bool(raw.get("burnSubtitles", True)),
        "normalizeAudio": bool(raw.get("normalizeAudio", False)),
    }
    if candidate.type == "short":
        mode_value = raw.get("mode")
        mode = str(mode_value).strip() if mode_value is not None else "high_quality"
        short_layout_value = raw.get("shortLayout", raw.get("layout"))
        short_layout = (
            str(short_layout_value).strip()
            if short_layout_value is not None
            else "auto"
        )
        render_settings.update(
            {
                "shortLayout": short_layout or "auto",
                "mode": mode or "high_quality",
                "shortOverlayTitleMode": normalize_short_overlay_title_mode(
                    str(raw.get("shortOverlayTitleMode", "auto"))
                ),
                "shortTopBannerEnabled": bool(
                    raw.get("shortTopBannerEnabled", False)
                ),
                "shortBottomBannerEnabled": bool(
                    raw.get("shortBottomBannerEnabled", False)
                ),
            }
        )
        if render_settings["shortTopBannerEnabled"]:
            render_settings["shortTopBannerAsset"] = _banner_asset_fingerprint(
                DEFAULT_SHORT_TOP_BANNER_PATH
            )
        if render_settings["shortBottomBannerEnabled"]:
            render_settings["shortBottomBannerAsset"] = _banner_asset_fingerprint(
                DEFAULT_SHORT_BOTTOM_BANNER_PATH
            )
    return render_settings


def _overlay_title_expected(
    candidate: Candidate,
    render_settings: Mapping[str, Any],
    explicit_value: bool | None,
) -> bool:
    if candidate.type == "normal":
        return True
    if explicit_value is not None:
        return explicit_value
    return short_overlay_title_expected(
        render_mode=str(render_settings["mode"]),
        stored_mode=str(render_settings["shortOverlayTitleMode"]),
        top_banner_enabled=bool(render_settings["shortTopBannerEnabled"]),
        title_manually_reviewed=candidate.title_source == "manual_review",
    )


def build_subtitle_review_preview_spec(
    *,
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
    settings: Mapping[str, Any] | None,
    source_fingerprint: str,
    source_width: int | None,
    source_height: int | None,
    candidate_index: int = 1,
    overlay_title_expected: bool | None = None,
    renderer_version: str = EXACT_SUBTITLE_REVIEW_RENDERER_VERSION,
) -> dict[str, Any]:
    if not source_fingerprint.strip():
        raise ValueError("source_fingerprint must not be empty")
    if candidate_index < 1:
        raise ValueError("candidate_index must be at least 1")
    if not renderer_version.strip():
        raise ValueError("renderer_version must not be empty")

    relevant_segments = _relevant_segments(candidate, transcript_segments)
    resolved_candidate = candidate_with_title(
        candidate,
        index=candidate_index,
        transcript_segments=relevant_segments,
    )
    render_settings = _canonical_render_settings(
        settings,
        candidate=resolved_candidate,
        source_width=source_width,
        source_height=source_height,
    )
    title_expected = _overlay_title_expected(
        resolved_candidate,
        render_settings,
        overlay_title_expected,
    )
    resolved_title = resolve_candidate_title(
        resolved_candidate,
        index=candidate_index,
        transcript_segments=relevant_segments,
    ).title
    top_title = ""
    if title_expected:
        top_title = (
            resolved_title
            if resolved_candidate.type == "normal"
            else (resolved_candidate.overlay_title or resolved_title)
        ).strip()
    return _normalize_for_spec(
        {
            "rendererVersion": renderer_version.strip(),
            "source": {
                "fingerprint": source_fingerprint.strip(),
                "width": source_width,
                "height": source_height,
            },
            "candidateIndex": candidate_index,
            "clip": resolved_candidate,
            "segments": relevant_segments,
            "settings": render_settings,
            "overlayTitleExpected": title_expected,
            "topTitle": top_title,
        }
    )


def subtitle_review_preview_spec_hash(spec: Mapping[str, Any]) -> str:
    return sha256(_canonical_spec_json(spec).encode("utf-8")).hexdigest()


def build_live_subtitle_review_preview_spec(
    exact_spec: Mapping[str, Any],
    *,
    renderer_version: str = LIVE_SUBTITLE_REVIEW_RENDERER_VERSION,
) -> dict[str, Any]:
    """Return the visual-only contract used behind the browser text overlay."""
    clip = dict(exact_spec["clip"])
    settings = dict(exact_spec["settings"])
    source = dict(exact_spec["source"])
    visual_settings: dict[str, Any] = {
        "normalizeAudio": bool(settings.get("normalizeAudio", False)),
    }
    if clip.get("type") == "short":
        for key in (
            "shortLayout",
            "shortTopBannerEnabled",
            "shortBottomBannerEnabled",
            "shortTopBannerAsset",
            "shortBottomBannerAsset",
        ):
            if key in settings:
                visual_settings[key] = settings[key]
    visual_segments = [
        {
            "start": segment["start"],
            "end": segment["end"],
        }
        for segment in exact_spec.get("segments", [])
        if isinstance(segment, Mapping)
    ]
    return _normalize_for_spec(
        {
            "rendererVersion": renderer_version,
            "source": source,
            "clip": {
                "id": clip.get("id"),
                "type": clip.get("type"),
                "start": clip.get("start"),
                "end": clip.get("end"),
                "hookSceneStart": clip.get("hook_scene_start"),
                "hookSceneEnd": clip.get("hook_scene_end"),
            },
            "segments": visual_segments,
            "settings": visual_settings,
        }
    )


def exact_subtitle_review_preview_paths(
    output_dir: str | Path,
    clip_id: str,
    spec_hash: str,
) -> ExactPreviewPaths:
    normalized_hash = spec_hash.strip().lower()
    if len(normalized_hash) != 64 or any(
        character not in "0123456789abcdef" for character in normalized_hash
    ):
        raise ValueError("spec_hash must be a 64-character SHA-256 hex digest")
    artifact_key = normalized_hash[:FILESYSTEM_SPEC_HASH_LENGTH]
    clip_digest = sha256(clip_id.encode("utf-8")).hexdigest()[:16]
    preview_dir = (
        Path(output_dir)
        / SUBTITLE_REVIEW_PREVIEW_DIRNAME
        / clip_digest
    )
    return ExactPreviewPaths(
        video_path=preview_dir / f"{artifact_key}.mp4",
        subtitle_path=preview_dir / f"{artifact_key}.ass",
        spec_path=preview_dir / f"{artifact_key}.json",
    )


def live_subtitle_review_preview_paths(
    output_dir: str | Path,
    clip_id: str,
    spec_hash: str,
) -> LivePreviewPaths:
    normalized_hash = spec_hash.strip().lower()
    if len(normalized_hash) != 64 or any(
        character not in "0123456789abcdef" for character in normalized_hash
    ):
        raise ValueError("spec_hash must be a 64-character SHA-256 hex digest")
    artifact_key = normalized_hash[:FILESYSTEM_SPEC_HASH_LENGTH]
    clip_digest = sha256(clip_id.encode("utf-8")).hexdigest()[:16]
    preview_dir = (
        Path(output_dir)
        / SUBTITLE_REVIEW_PREVIEW_DIRNAME
        / clip_digest
        / "live"
    )
    return LivePreviewPaths(
        video_path=preview_dir / f"{artifact_key}.mp4",
        spec_path=preview_dir / f"{artifact_key}.json",
    )


def _temporary_artifact(path: Path, token: str) -> Path:
    return path.with_name(f".render-{token[:12]}.tmp{path.suffix}")


def _write_spec(path: Path, spec: Mapping[str, Any]) -> None:
    path.write_text(_canonical_spec_json(spec) + "\n", encoding="utf-8")


def _cached_artifacts_match(
    paths: ExactPreviewPaths,
    spec: Mapping[str, Any],
) -> bool:
    try:
        return (
            paths.video_path.is_file()
            and paths.video_path.stat().st_size > 0
            and paths.subtitle_path.is_file()
            and paths.subtitle_path.stat().st_size > 0
            and paths.spec_path.read_text(encoding="utf-8")
            == _canonical_spec_json(spec) + "\n"
        )
    except (OSError, UnicodeError):
        return False


def _cached_live_artifacts_match(
    paths: LivePreviewPaths,
    spec: Mapping[str, Any],
) -> bool:
    try:
        return (
            paths.video_path.is_file()
            and paths.video_path.stat().st_size > 0
            and paths.spec_path.read_text(encoding="utf-8")
            == _canonical_spec_json(spec) + "\n"
        )
    except (OSError, UnicodeError):
        return False


def render_exact_subtitle_review_preview(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
    settings: Mapping[str, Any] | None,
    source_fingerprint: str,
    source_width: int | None,
    source_height: int | None,
    candidate_index: int = 1,
    overlay_title_expected: bool | None = None,
    renderer_version: str = EXACT_SUBTITLE_REVIEW_RENDERER_VERSION,
    ffmpeg_bin: str = "ffmpeg",
    normal_renderer: NormalPreviewRenderer = render_normal_clip,
    short_renderer: ShortPreviewRenderer = render_short_clip,
) -> ExactPreviewResult:
    spec = build_subtitle_review_preview_spec(
        candidate=candidate,
        transcript_segments=transcript_segments,
        settings=settings,
        source_fingerprint=source_fingerprint,
        source_width=source_width,
        source_height=source_height,
        candidate_index=candidate_index,
        overlay_title_expected=overlay_title_expected,
        renderer_version=renderer_version,
    )
    spec_hash = subtitle_review_preview_spec_hash(spec)
    live_spec = build_live_subtitle_review_preview_spec(spec)
    live_spec_hash = subtitle_review_preview_spec_hash(live_spec)
    paths = exact_subtitle_review_preview_paths(
        output_dir,
        candidate.id,
        spec_hash,
    )
    live_paths = live_subtitle_review_preview_paths(
        output_dir,
        candidate.id,
        live_spec_hash,
    )
    exact_cached = _cached_artifacts_match(paths, spec)
    live_cached = _cached_live_artifacts_match(live_paths, live_spec)
    if exact_cached and live_cached:
        return ExactPreviewResult(
            path=paths.video_path,
            subtitle_path=paths.subtitle_path,
            spec_path=paths.spec_path,
            spec_hash=spec_hash,
            live_path=live_paths.video_path,
            live_spec_path=live_paths.spec_path,
            live_spec_hash=live_spec_hash,
        )

    paths.video_path.parent.mkdir(parents=True, exist_ok=True)
    live_paths.video_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    temporary_video = _temporary_artifact(paths.video_path, token)
    temporary_subtitle = _temporary_artifact(paths.subtitle_path, token)
    temporary_spec = _temporary_artifact(paths.spec_path, token)
    temporary_live_video = _temporary_artifact(live_paths.video_path, token)
    temporary_live_spec = _temporary_artifact(live_paths.spec_path, token)
    temporary_paths = (
        temporary_video,
        temporary_subtitle,
        temporary_spec,
        temporary_live_video,
        temporary_live_spec,
    )

    resolved_candidate = Candidate.model_validate(spec["clip"])
    resolved_segments = [
        TranscriptSegment.model_validate(segment)
        for segment in spec["segments"]
    ]
    render_settings = dict(spec["settings"])
    burn_subtitles = bool(render_settings["burnSubtitles"])
    normalize_audio = bool(render_settings["normalizeAudio"])
    top_title = str(spec["topTitle"])

    try:
        if not exact_cached:
            layout = SubtitleLayout(**dict(render_settings["layout"]))
            ass_candidate = (
                resolved_candidate
                if burn_subtitles
                else resolved_candidate.model_copy(update={"hook_text": None})
            )
            write_ass_for_candidate(
                ass_candidate,
                resolved_segments if burn_subtitles else [],
                temporary_subtitle,
                layout=layout,
                top_title=top_title,
            )

        if resolved_candidate.type == "normal":
            normal_use_ass = burn_subtitles or bool(top_title)
            normal_kwargs: dict[str, Any] = {
                "start": resolved_candidate.start,
                "end": resolved_candidate.end,
                "normalize_audio": normalize_audio,
                "ffmpeg_bin": ffmpeg_bin,
            }
            if (
                resolved_candidate.hook_scene_start is not None
                and resolved_candidate.hook_scene_end is not None
            ):
                normal_kwargs["hook_scene_start"] = resolved_candidate.hook_scene_start
                normal_kwargs["hook_scene_end"] = resolved_candidate.hook_scene_end
            if not exact_cached:
                normal_renderer(
                    input_path,
                    temporary_video,
                    subtitle_path=temporary_subtitle if normal_use_ass else None,
                    **normal_kwargs,
                )
            if not live_cached:
                normal_renderer(
                    input_path,
                    temporary_live_video,
                    subtitle_path=None,
                    **normal_kwargs,
                )
        else:
            top_banner_enabled = bool(render_settings["shortTopBannerEnabled"])
            bottom_banner_enabled = bool(render_settings["shortBottomBannerEnabled"])
            use_ass = burn_subtitles or top_banner_enabled or bool(top_title)
            short_kwargs: dict[str, Any] = {
                "start": resolved_candidate.start,
                "end": resolved_candidate.end,
                "subtitle_path": temporary_subtitle if use_ass else None,
                "normalize_audio": normalize_audio,
                "ffmpeg_bin": ffmpeg_bin,
                "layout": str(render_settings["shortLayout"]),
                "source_width": source_width,
                "source_height": source_height,
                "dialogue_windows": dialogue_windows_for_clip(
                    resolved_candidate.start,
                    resolved_candidate.end,
                    resolved_segments,
                ),
            }
            if top_banner_enabled:
                short_kwargs["top_banner_path"] = DEFAULT_SHORT_TOP_BANNER_PATH
            if bottom_banner_enabled:
                short_kwargs["bottom_banner_path"] = DEFAULT_SHORT_BOTTOM_BANNER_PATH
            if (
                resolved_candidate.hook_scene_start is not None
                and resolved_candidate.hook_scene_end is not None
            ):
                short_kwargs["hook_scene_start"] = resolved_candidate.hook_scene_start
                short_kwargs["hook_scene_end"] = resolved_candidate.hook_scene_end
            if not exact_cached:
                short_renderer(
                    input_path,
                    temporary_video,
                    **short_kwargs,
                )
            if not live_cached:
                live_kwargs = {**short_kwargs, "subtitle_path": None}
                short_renderer(
                    input_path,
                    temporary_live_video,
                    **live_kwargs,
                )

        if not exact_cached:
            if not temporary_video.is_file() or temporary_video.stat().st_size <= 0:
                raise RuntimeError("exact subtitle review preview was not created")
            if not temporary_subtitle.is_file():
                raise RuntimeError("exact subtitle review ASS was not created")
            _write_spec(temporary_spec, spec)
            temporary_subtitle.replace(paths.subtitle_path)
            temporary_spec.replace(paths.spec_path)
            temporary_video.replace(paths.video_path)
        if not live_cached:
            if (
                not temporary_live_video.is_file()
                or temporary_live_video.stat().st_size <= 0
            ):
                raise RuntimeError("live subtitle review preview was not created")
            _write_spec(temporary_live_spec, live_spec)
            temporary_live_spec.replace(live_paths.spec_path)
            temporary_live_video.replace(live_paths.video_path)
    finally:
        for temporary_path in temporary_paths:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    return ExactPreviewResult(
        path=paths.video_path,
        subtitle_path=paths.subtitle_path,
        spec_path=paths.spec_path,
        spec_hash=spec_hash,
        live_path=live_paths.video_path,
        live_spec_path=live_paths.spec_path,
        live_spec_hash=live_spec_hash,
    )
