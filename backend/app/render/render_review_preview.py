import subprocess
from pathlib import Path


def build_review_preview_command(
    input_path: str | Path,
    output_path: str | Path,
    *,
    start: float,
    duration: float,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{max(0.0, start):.6f}",
        "-i",
        str(input_path),
        "-t",
        f"{max(0.05, duration):.6f}",
        "-vf",
        "fps=30,scale=960:540:force_original_aspect_ratio=decrease",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def render_review_preview(
    input_path: str | Path,
    output_path: str | Path,
    *,
    start: float,
    duration: float,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.stem}.tmp{target.suffix}")
    command = build_review_preview_command(
        input_path,
        temporary,
        start=start,
        duration=duration,
        ffmpeg_bin=ffmpeg_bin,
    )
    try:
        subprocess.run(command, check=True)
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError("subtitle review preview was not created")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
