import subprocess
from pathlib import Path


class AudioExtractionError(RuntimeError):
    pass


def _audio_extraction_error_message(stderr: str) -> str:
    normalized = stderr.lower()
    corruption_markers = (
        "invalid data found when processing input",
        "error submitting packet to decoder",
        "input buffer exhausted",
        "reserved bit set",
        "failed to configure output pad",
    )
    if any(marker in normalized for marker in corruption_markers):
        return (
            "音声データを読み取れません。動画ファイルが破損または不完全な可能性があります。"
            "元動画を再ダウンロードして、再アップロードしてください。"
        )
    return (
        "動画から音声を抽出できませんでした。"
        "元動画を再ダウンロードするか、MP4へ再変換してから再アップロードしてください。"
    )


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
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError as exc:
        Path(output_path).unlink(missing_ok=True)
        raise AudioExtractionError(_audio_extraction_error_message(exc.stderr or "")) from exc
    return Path(output_path)
