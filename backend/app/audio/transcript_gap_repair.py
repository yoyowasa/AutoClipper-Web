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
from app.audio.transcript_runaway_repair import (
    RUNAWAY_WINDOW_PADDING_SECONDS, detect_runaway_segments, replace_runaway_segment,
)

logger = logging.getLogger(__name__)


def repair_transcript_gaps(
    audio_path: Path, load_model: Callable[[], Any], baseline: Sequence[TranscriptSegment], *,
    duration: float, silence: Sequence[tuple[float, float]], language: str | None = None, beam_size: int = 5,
) -> tuple[list[TranscriptSegment], dict[str, Any]]:
    """Run unchanged gap repair, then independently repair runaway segments."""
    started = time.monotonic()
    model = None

    def reused_model() -> Any:
        nonlocal model
        if model is None:
            model = load_model()
        return model

    original = [item.model_dump() for item in baseline]
    detected = detect_runaway_segments(original)
    result, summary = _repair_transcript_gaps(
        audio_path, reused_model, baseline, duration=duration, silence=silence, language=language, beam_size=beam_size,
    )
    current = [item.model_dump() for item in result]
    # Only baseline runaway segments are eligible. Gap rereads, their timestamps,
    # and even any artifacts they add remain identical when the baseline is normal.
    targets = []
    for runaway in detected:
        source = original[runaway.index]
        matches = [item for item in current if item["text"] == source["text"]
                   and item["start"] < source["end"] and item["end"] > source["start"]]
        target = min(matches, key=lambda item: abs(item["start"] - source["start"])) if matches else source
        targets.append((target, runaway))
    summary.update(runaway_segment_count=len(targets), runaway_replaced_count=0, runaway_skipped=[])
    if not targets:
        return result, summary
    for target, runaway in targets:
        start = max(0.0, runaway.start - RUNAWAY_WINDOW_PADDING_SECONDS)
        end = min(duration, runaway.end + RUNAWAY_WINDOW_PADDING_SECONDS)
        summary["planned_interval_count"] += 1
        try:
            if not any(item is target for item in current) or end <= start:
                replacements, detail = replace_runaway_segment(target, [], runaway=runaway, window=(start, end))
                detail["reason"] = "segment_changed_by_gap_repair" if end > start else "outside_audio_range"
            elif summary["status"] == "failed":
                replacements, detail = replace_runaway_segment(target, [], runaway=runaway, window=(start, end))
                detail["reason"] = "gap_repair_failed"
            else:
                reread = _reread_runaway_window(
                    audio_path, reused_model, start=start, end=end, summary=summary, language=language, beam_size=beam_size,
                )
                replacements, detail = replace_runaway_segment(
                    target, reread, runaway=runaway, window=(start, end), other_segments=[item for item in current if item is not target],
                )
                # Validate before publishing any replacements from this window.
                for item in replacements:
                    TranscriptSegment.model_validate(item)
        except Exception as exc:
            replacements, detail = replace_runaway_segment(target, [], runaway=runaway, window=(start, end))
            detail.update(reason="reread_failed", error_type=type(exc).__name__)
            logger.warning("Runaway transcript repair failed; keeping segment (%s)", type(exc).__name__)
        summary["windows"].append(detail)
        if detail["replaced"]:
            index = next(index for index, item in enumerate(current) if item is target)
            current[index:index + 1] = replacements
            summary["runaway_replaced_count"] += 1
            summary["repaired_segment_count"] += len(replacements)
            summary["added_characters"] += sum(len(item["text"]) for item in replacements)
        else:
            summary["runaway_skipped"].append(detail)
    if summary["status"] == "skipped" and summary.get("reason") == "word_timestamps_unavailable":
        summary.update(status="completed")
        summary.pop("reason")
    summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
    summary["reread_seconds"] = round(summary["reread_seconds"], 3)
    return [TranscriptSegment.model_validate(item) for item in sorted(current, key=lambda item: (item["start"], item["end"]))], summary


def _reread_runaway_window(
    audio_path: Path, load_model: Callable[[], Any], *, start: float, end: float, summary: dict[str, Any],
    language: str | None, beam_size: int,
) -> list[dict[str, Any]]:
    with wave.open(str(audio_path), "rb") as reader, tempfile.TemporaryDirectory(prefix="autoclipper-runaway-") as directory:
        rate = reader.getframerate()
        if reader.getnchannels() != 1 or reader.getsampwidth() != 2 or rate != 16000:
            raise ValueError("Repair requires mono 16 kHz PCM signed 16-bit WAV")
        path = Path(directory) / "repair.wav"
        start_frame, end_frame = int(start * rate), min(reader.getnframes(), int(end * rate))
        _write_pcm_wav_chunk(reader, path, start_frame=start_frame, frame_count=end_frame - start_frame)
        summary["reread_interval_count"] += 1
        summary["reread_seconds"] += (end_frame - start_frame) / rate
        offset = start_frame / rate
        segments, _ = load_model().transcribe(
            str(path), language=language, beam_size=beam_size, word_timestamps=True, vad_filter=False, condition_on_previous_text=False,
        )
        reread = []
        for segment in segments:
            item = segment_from_faster_whisper(segment)
            reread.append({**item.model_dump(), "start": item.start + offset, "end": item.end + offset,
                           "words": [{**word.model_dump(), "start": word.start + offset, "end": word.end + offset}
                                     for word in (item.words or [])] or None})
        return reread


def _repair_transcript_gaps(
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
