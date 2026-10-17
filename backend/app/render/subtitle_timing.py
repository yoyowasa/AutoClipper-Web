"""Speech-aligned caption chunks. Keep the TypeScript port covered by shared fixtures."""
import math
import re
from collections.abc import Sequence

from app.audio.transcribe_faster_whisper import TranscriptWord

MIN_SUBTITLE_FRAGMENT_CHARACTERS = 6
LONG_EDITED_SUBTITLE_SECONDS = 6.0
BREAKS = ("。、！？!?", "、，, ", "でにはをがともやへ")


def normalize(text: str) -> str:
    return " ".join(text.split())


def round_milliseconds(value: float) -> float:
    # JavaScript Math.round, including exact half milliseconds.
    return math.floor(value * 1000 + 0.5) / 1000


def usable_words(text: str, words: Sequence[TranscriptWord] | None) -> bool:
    if not words or re.sub(r"\s", "", text) != re.sub(r"\s", "", "".join(w.word for w in words)):
        return False
    previous = -math.inf
    for word in words:
        if not math.isfinite(word.start) or not math.isfinite(word.end) or word.start < previous or word.end < word.start:
            return False
        previous = word.end
    return any(word.end > word.start for word in words)


def chunk_units(units: Sequence[str], limit: int) -> list[tuple[int, int]]:
    """Prefer punctuation/particles, keeping whole units and at least six characters."""
    chunks = []
    start = 0
    while start < len(units):
        remaining = normalize("".join(units[start:]))
        if len(remaining) <= limit:
            chunks.append((start, len(units)))
            break
        fitting = []
        overflow = None
        for index in range(start + 1, len(units)):
            length = len(normalize("".join(units[start:index])))
            if length < MIN_SUBTITLE_FRAGMENT_CHARACTERS:
                continue
            if len(normalize("".join(units[index:]))) < MIN_SUBTITLE_FRAGMENT_CHARACTERS:
                break
            if length > limit:
                overflow = index
                break
            fitting.append(index)
        if fitting:
            end = fitting[-1]
            for breaks in BREAKS:
                preferred = [index for index in fitting if "".join(units[start:index])[-1] in breaks]
                if preferred:
                    end = preferred[-1]
                    break
        elif overflow is not None:
            # An ASR token can exceed the width; never cut it in the middle.
            end = overflow
        else:
            end = len(units)
        chunks.append((start, end))
        start = end
    return chunks


def speech_chunks(words: Sequence[TranscriptWord], limit: int) -> list[tuple[float, float, str]]:
    return [(words[a].start, words[b - 1].end, normalize("".join(w.word for w in words[a:b])))
            for a, b in chunk_units([w.word for w in words], limit)]


def text_chunks(text: str, limit: int) -> list[str]:
    text = normalize(text)
    return [text[a:b].strip() for a, b in chunk_units(list(text), limit)]
