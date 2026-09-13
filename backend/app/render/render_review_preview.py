import subprocess
from pathlib import Path


def build_review_preview_command(
    input_path: str | Path,
    output_path: str | Path,
    *,
    start: float,
    duration: float,
    hook_start: float | None = None,
    hook_duration: float | None = None,
    include_audio: bool = True,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    if (hook_start is None) != (hook_duration is None):
        raise ValueError("hook preview requires both start and duration")
    if hook_start is not None and hook_duration is not None:
        if hook_duration < 0.5 or hook_duration > 3:
            raise ValueError("hook preview duration must be between 0.5 and 3 seconds")
        video_filter = (
            "[0:v:0]fps=30,scale=960:540:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2,"
            "setsar=1,setpts=PTS-STARTPTS[hook_v];"
            "[1:v:0]fps=30,scale=960:540:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2,"
            "setsar=1,setpts=PTS-STARTPTS[main_v];"
            "[0:a:0]aresample=48000,asetpts=PTS-STARTPTS[hook_a];"
            "[1:a:0]aresample=48000,asetpts=PTS-STARTPTS[main_a];"
            "[hook_v][hook_a][main_v][main_a]"
            "concat=n=2:v=1:a=1[video][audio]"
        )
        return [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{max(0.0, hook_start):.6f}",
            "-t",
            f"{hook_duration:.6f}",
            "-i",
            str(input_path),
            "-ss",
            f"{max(0.0, start):.6f}",
            "-t",
            f"{max(0.05, duration):.6f}",
            "-i",
            str(input_path),
            "-filter_complex",
            video_filter,
            "-map",
            "[video]",
            "-map",
            "[audio]",
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
    command = [
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
        "fps=30,scale=960:540:force_original_aspect_ratio=decrease:force_divisible_by=2,"
        "setsar=1",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
    ]
    if include_audio:
        command.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-ac",
                "2",
            ]
        )
    else:
        command.append("-an")
    command.extend(["-movflags", "+faststart", str(output_path)])
    return command


def render_review_preview(
    input_path: str | Path,
    output_path: str | Path,
    *,
    start: float,
    duration: float,
    hook_start: float | None = None,
    hook_duration: float | None = None,
    include_audio: bool = True,
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
        hook_start=hook_start,
        hook_duration=hook_duration,
        include_audio=include_audio,
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
