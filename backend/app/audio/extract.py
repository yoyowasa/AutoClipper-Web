import subprocess
from pathlib import Path


def build_extract_audio_command(
    input_path: str | Path,
    output_path: str | Path,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    return [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]


def extract_mono_wav(
    input_path: str | Path,
    output_path: str | Path,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    command = build_extract_audio_command(input_path, output_path, ffmpeg_bin=ffmpeg_bin)
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return Path(output_path)
