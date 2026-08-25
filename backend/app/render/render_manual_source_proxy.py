from collections.abc import Callable
from pathlib import Path

from app.render.render_review_preview import render_review_preview


MANUAL_SOURCE_PROXY_FILENAME = "manual_source_preview.mp4"


def manual_source_proxy_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / MANUAL_SOURCE_PROXY_FILENAME


def manual_source_proxy_url(job_id: str) -> str:
    return f"/api/jobs/{job_id}/editor-video"


def render_manual_source_proxy(
    input_path: str | Path,
    output_path: str | Path,
    *,
    duration: float,
    has_audio: bool,
    preview_renderer: Callable[..., Path] = render_review_preview,
) -> Path:
    if duration <= 0:
        raise ValueError("manual source preview requires a positive duration")
    return preview_renderer(
        input_path,
        output_path,
        start=0.0,
        duration=duration,
        include_audio=has_audio,
    )
