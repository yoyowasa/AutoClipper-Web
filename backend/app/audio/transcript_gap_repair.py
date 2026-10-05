"""One best-effort, word-timestamp based repair pass before transcript postprocessing."""
from collections.abc import Callable, Sequence
import logging
from pathlib import Path
import tempfile
import time
from typing import Any
import wave

from app.audio.transcribe_faster_whisper import TranscriptSegment, _write_pcm_wav_chunk, segment_from_faster_whisper
from app.audio.transcript_repair_merge import merge_ranges, merge_repair, nonsilent_gaps

logger = logging.getLogger(__name__)


def repair_transcript_gaps(
    audio_path: Path, load_model: Callable[[], Any], baseline: Sequence[TranscriptSegment], *,
    duration: float, silence: Sequence[tuple[float, float]], language: str | None = None, beam_size: int = 5,
) -> tuple[list[TranscriptSegment], dict[str, Any]]:
    started = time.monotonic()
    original = list(baseline)
    summary: dict[str, Any] = {
        "status": "completed", "repaired_segment_count": 0, "added_segment_count": 0,
        "retimed_segment_count": 0, "added_characters": 0, "reread_interval_count": 0,
        "planned_interval_count": 0, "reread_seconds": 0.0, "elapsed_seconds": 0.0, "windows": [],
    }
    try:
        missing_words = [item for item in original if item.text.strip() and not item.words]
        summary["segments_without_word_timestamps"] = len(missing_words)
        if missing_words and not any(item.words for item in original if item.text.strip()):
            summary.update(status="skipped", reason="word_timestamps_unavailable")
            return original, summary
        coverage = [{"start": word.start, "end": word.end, "text": word.word}
                    for item in original for word in (item.words or [])]
        # A segment without words protects its own envelope; it must not disable
        # repair of unrelated word-timed gaps or be mistaken for missing speech.
        coverage.extend({"start": item.start, "end": item.end, "text": item.text} for item in missing_words)
        gaps = nonsilent_gaps(coverage, duration, silence, 3.0)
        windows = merge_ranges([(max(0.0, start - 2.0), min(duration, end + 2.0)) for start, end in gaps])
        summary["planned_interval_count"] = len(windows)
        if not windows:
            return original, summary
        # Reuse the model which produced the selected transcription, without another model load.
        model = load_model()
        current = [item.model_dump() for item in original]
        changes = []
        with wave.open(str(audio_path), "rb") as reader, tempfile.TemporaryDirectory(prefix="autoclipper-repair-") as directory:
            rate = reader.getframerate()
            if reader.getnchannels() != 1 or reader.getsampwidth() != 2 or rate != 16000:
                raise ValueError("Repair requires mono 16 kHz PCM signed 16-bit WAV")
            for start, end in windows:
                path = Path(directory) / "repair.wav"
                start_frame = int(start * rate)
                end_frame = min(reader.getnframes(), int(end * rate))
                _write_pcm_wav_chunk(reader, path, start_frame=start_frame, frame_count=end_frame - start_frame)
                summary["reread_interval_count"] += 1
                summary["reread_seconds"] += (end_frame - start_frame) / rate
                offset = start_frame / rate
                segments, _ = model.transcribe(str(path), language=language, beam_size=beam_size,
                                               word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
                reread = []
                for segment in segments:
                    item = segment_from_faster_whisper(segment)
                    shifted = item.model_dump()
                    shifted.update(start=item.start + offset, end=item.end + offset)
                    shifted["words"] = [{**word.model_dump(), "start": word.start + offset, "end": word.end + offset}
                                        for word in (item.words or [])] or None
                    reread.append(shifted)
                current, detail = merge_repair(current, reread, window=(start, end), gaps=gaps, preserve_existing=True)
                changes.append(detail)
                summary["windows"].append({"start": start, "end": end, **detail})
        result = [TranscriptSegment.model_validate(item) for item in current]
        summary.update(
            added_segment_count=sum(item["added_segments"] for item in changes),
            retimed_segment_count=sum(item["retimed_segments"] for item in changes),
            added_characters=sum(len(item.text) for item in result) - sum(len(item.text) for item in original),
        )
        summary["repaired_segment_count"] = summary["added_segment_count"] + summary["retimed_segment_count"]
        return result, summary
    except Exception as exc:
        # Do not publish a partially repaired transcript if any reread or validation fails.
        logger.warning("Transcript gap repair failed; keeping original transcription (%s)", type(exc).__name__)
        summary.update(status="failed", error_type=type(exc).__name__)
        return original, summary
    finally:
        summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
        summary["reread_seconds"] = round(summary["reread_seconds"], 3)
