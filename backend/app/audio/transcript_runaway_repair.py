"""Pure detection and conservative replacement of runaway word/character runs."""
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby
from typing import Any

from app.audio.transcript_repair_merge import Range, Segment, normalize_for_cer

RUNAWAY_WORD_MIN_SECONDS = 3.0
RUNAWAY_TEXT_MIN_SECONDS = 5.0
RUNAWAY_TEXT_MIN_CHARACTERS = 10
RUNAWAY_WINDOW_PADDING_SECONDS = 2.0
RUNAWAY_TEXT_PREFIX_LENGTH = 80


@dataclass(frozen=True)
class RunawaySegment:
    index: int
    start: float
    end: float
    trigger: str


def detect_runaway_segments(segments: Sequence[Segment]) -> list[RunawaySegment]:
    detected = []
    for index, segment in enumerate(segments):
        start, end = float(segment["start"]), float(segment["end"])
        words = segment.get("words")
        if not words:
            normalized = normalize_for_cer(str(segment.get("text", "")))
            repeated = any(sum(1 for _ in run) >= RUNAWAY_TEXT_MIN_CHARACTERS for _, run in groupby(normalized))
            if end - start >= RUNAWAY_TEXT_MIN_SECONDS and repeated:
                detected.append(RunawaySegment(index, start, end, "text_repetition_without_words"))
            continue
        runs: list[Range] = []
        key, run_start, run_end, count = "", start, start, 0

        def record_run() -> None:
            if count >= 2 and run_end - run_start >= RUNAWAY_WORD_MIN_SECONDS:
                runs.append((run_start, run_end))

        for word in words:
            normalized = normalize_for_cer(str(word.get("word", "")))
            word_start, word_end = max(start, float(word["start"])), min(end, float(word["end"]))
            if not normalized or word_end < word_start:
                continue
            # A token containing only repetitions of one character joins that
            # character's run even when ASR splits it into differently sized words.
            token = normalized[0] if len(set(normalized)) == 1 else normalized
            repeats_in_token = len(normalized) if len(set(normalized)) == 1 else 1
            if token != key:
                record_run()
                key, run_start, run_end, count = token, word_start, word_end, repeats_in_token
            else:
                run_end = max(run_end, word_end)
                count += repeats_in_token
        record_run()
        if runs:
            detected.append(RunawaySegment(index, min(item[0] for item in runs), max(item[1] for item in runs), "word_repetition"))
    return detected


def replace_runaway_segment(
    original: Segment, reread: Sequence[Segment], *, runaway: RunawaySegment, window: Range,
    other_segments: Sequence[Segment] = (),
) -> tuple[list[Segment], dict[str, Any]]:
    """Replace the whole segment only with better, non-runaway words inside its run."""
    detail: dict[str, Any] = {
        "kind": "runaway", "start": window[0], "end": window[1],
        "original_start": original["start"], "original_end": original["end"],
        "original_text_prefix": str(original.get("text", ""))[:RUNAWAY_TEXT_PREFIX_LENGTH],
        "runaway_start": runaway.start, "runaway_end": runaway.end, "trigger": runaway.trigger,
        "replaced": False,
    }

    def skip(reason: str) -> tuple[list[Segment], dict[str, Any]]:
        return [dict(original)], {**detail, "reason": reason}

    if detect_runaway_segments(reread):
        return skip("reread_contains_runaway")
    replacements = []
    previous_end = runaway.start
    for segment in sorted(reread, key=lambda item: (float(item["start"]), float(item["end"]))):
        accepted = []
        for word in sorted(segment.get("words") or [], key=lambda item: (float(item["start"]), float(item["end"]))):
            midpoint = (float(word["start"]) + float(word["end"])) / 2
            if not str(word.get("word", "")).strip() or not runaway.start <= midpoint < runaway.end:
                continue
            start, end = max(runaway.start, float(word["start"]), previous_end), min(runaway.end, float(word["end"]))
            if end > start:
                accepted.append({**word, "start": start, "end": end})
                previous_end = end
        if accepted:
            replacements.append({
                **original, "start": accepted[0]["start"], "end": accepted[-1]["end"],
                "text": "".join(str(word["word"]) for word in accepted).strip(), "words": accepted,
                "confidence": segment.get("confidence"), "repaired": True,
                "repair_windows": [*(original.get("repair_windows") or []), {"start": window[0], "end": window[1]}],
            })
    if not replacements:
        return skip("no_words_in_runaway_range")
    if detect_runaway_segments(replacements):
        return skip("replacement_contains_runaway")
    old_characters = len(set(normalize_for_cer(str(original.get("text", "")))))
    new_characters = len(set(normalize_for_cer("".join(item["text"] for item in replacements))))
    detail.update(original_distinct_characters=old_characters, replacement_distinct_characters=new_characters)
    if new_characters <= old_characters:
        return skip("insufficient_character_diversity")
    if any(float(other["end"]) > float(item["start"]) + 1e-9 and float(other["start"]) < float(item["end"]) - 1e-9
           for item in replacements for other in other_segments if str(other.get("text", "")).strip()):
        return skip("would_overlap_existing_caption")
    return replacements, {**detail, "replaced": True, "reason": "replaced", "replacement_segment_count": len(replacements)}
