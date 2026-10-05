"""Interval operations and conservative merging shared by offline D and production repair."""
from collections import defaultdict
from collections.abc import Sequence
from typing import Any
import unicodedata

Range = tuple[float, float]
Segment = dict[str, Any]


def normalize_for_cer(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return "".join(c for c in normalized if not c.isspace() and not unicodedata.category(c).startswith("P"))


def merge_ranges(ranges: Sequence[Range]) -> list[Range]:
    merged: list[Range] = []
    for start, end in sorted(ranges):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract_ranges(ranges: Sequence[Range], exclusions: Sequence[Range]) -> list[Range]:
    result: list[Range] = []
    excluded = merge_ranges(exclusions)
    for start, end in merge_ranges(ranges):
        cursor = start
        for excluded_start, excluded_end in excluded:
            if excluded_end <= cursor:
                continue
            if excluded_start >= end:
                break
            if excluded_start > cursor:
                result.append((cursor, min(end, excluded_start)))
            cursor = max(cursor, excluded_end)
            if cursor >= end:
                break
        if cursor < end:
            result.append((cursor, end))
    return result


def subtitle_gaps(segments: Sequence[Segment], duration: float) -> list[Range]:
    covered = [
        (max(0.0, float(segment["start"])), min(duration, float(segment["end"])))
        for segment in segments if str(segment.get("text", "")).strip()
    ]
    return subtract_ranges([(0.0, duration)], covered)


def nonsilent_gaps(segments: Sequence[Segment], duration: float, silence: Sequence[Range], minimum: float) -> list[Range]:
    return [item for item in subtract_ranges(subtitle_gaps(segments, duration), silence) if item[1] - item[0] >= minimum]


def merge_repair(
    original: Sequence[Segment], reread: Sequence[Segment], *, window: Range, gaps: Sequence[Range], preserve_existing: bool = False,
) -> tuple[list[Segment], dict[str, Any]]:
    """Keep original coverage unless a matched sentence is retimed or a gap receives new speech."""
    result = [dict(segment) for segment in original]
    available: dict[str, list[int]] = defaultdict(list)
    for index, segment in enumerate(result):
        if float(segment["end"]) > window[0] and float(segment["start"]) < window[1]:
            available[normalize_for_cer(str(segment.get("text", "")))].append(index)
    following = set()
    if preserve_existing:
        for start, end in gaps:
            candidates = [i for i, item in enumerate(result) if float(item["start"]) >= start
                          and float(item["end"]) >= end and str(item.get("text", "")).strip()]
            if candidates:
                following.add(min(candidates, key=lambda i: float(result[i]["start"])))
    replaced: set[int] = set()
    corrections: list[dict[str, Any]] = []
    skipped_retimes: list[dict[str, Any]] = []
    unmatched: list[Segment] = []
    added = 0
    # Resolve exact matches first so additions cannot block a safe timestamp correction.
    for segment in reread:
        normalized = normalize_for_cer(str(segment.get("text", "")))
        if not normalized:
            continue
        matches = [index for index in available.get(normalized, [])
                   if index not in replaced and (not preserve_existing or index in following)]
        if matches:
            index = min(matches, key=lambda item: abs(float(result[item]["start"]) - float(segment["start"])))
            replaced.add(index)
            if preserve_existing and not (window[0] <= float(segment["start"]) < float(segment["end"]) <= window[1]):
                skipped_retimes.append({"text": segment["text"], "reason": "outside_reread_window"})
                continue
            if any(
                other_index != index and str(other.get("text", "")).strip()
                and float(other["end"]) > float(segment["start"]) + 1e-9
                and float(other["start"]) < float(segment["end"]) - 1e-9
                for other_index, other in enumerate(result)
            ):
                skipped_retimes.append({
                    "text": segment["text"], "old_start": result[index]["start"], "new_start": segment["start"],
                    "reason": "would_overlap_existing_caption",
                })
                continue
            if preserve_existing and all(abs(float(result[index][key]) - float(segment[key])) < 0.001 for key in ("start", "end")):
                continue
            corrections.append({
                "text": segment["text"], "old_start": result[index]["start"], "new_start": segment["start"],
                "old_end": result[index]["end"], "new_end": segment["end"],
            })
            result[index] = ({**result[index], "start": segment["start"], "end": segment["end"],
                              "words": segment.get("words"), "repaired": True,
                              "repair_windows": [*(result[index].get("repair_windows") or []),
                                                 {"start": window[0], "end": window[1]}]}
                             if preserve_existing else dict(segment))
        else:
            unmatched.append(segment)
    open_gaps = subtract_ranges(
        [(max(start, window[0]), min(end, window[1])) for start, end in gaps],
        [(float(segment["start"]), float(segment["end"])) for segment in result if str(segment.get("text", "")).strip()],
    )
    skipped_partial_segments: list[dict[str, Any]] = []
    for segment in unmatched:
        words = segment.get("words")
        additions: list[Segment] = []
        if words:
            for gap_start, gap_end in open_gaps:
                accepted_words = []
                previous_end = gap_start
                for word in sorted(words, key=lambda item: (float(item["start"]), float(item["end"]))):
                    midpoint = (float(word["start"]) + float(word["end"])) / 2
                    if not str(word.get("word", "")).strip() or not gap_start <= midpoint < gap_end:
                        continue
                    word_start = max(gap_start, float(word["start"]), previous_end)
                    word_end = min(gap_end, float(word["end"]))
                    if word_end <= word_start:
                        continue
                    accepted_words.append({**word, "start": word_start, "end": word_end})
                    previous_end = word_end
                if accepted_words:
                    additions.append({
                        **segment, "start": accepted_words[0]["start"], "end": accepted_words[-1]["end"],
                        "text": "".join(str(word["word"]) for word in accepted_words).strip(), "words": accepted_words,
                    })
        elif any(
            float(segment["start"]) >= start and float(segment["end"]) <= end
            and float(segment["end"]) > float(segment["start"])
            for start, end in open_gaps
        ):
            additions.append(dict(segment))
        elif any(float(segment["end"]) > start and float(segment["start"]) < end for start, end in open_gaps):
            skipped_partial_segments.append({
                "start": segment["start"], "end": segment["end"], "text": segment["text"],
                "reason": "words_unavailable_partial_overlap",
            })
        if preserve_existing:
            additions = [{**item, "repaired": True, "repair_windows": [{"start": window[0], "end": window[1]}]}
                         for item in additions]
        result.extend(additions)
        added += len(additions)
        open_gaps = subtract_ranges(open_gaps, [(float(item["start"]), float(item["end"])) for item in additions])
    ordered = sorted(result, key=lambda item: (float(item["start"]), float(item["end"])))
    deduplicated: list[Segment] = []
    for segment in ordered:
        duplicate = any(
            normalize_for_cer(str(previous["text"])) == normalize_for_cer(str(segment["text"]))
            and float(previous["end"]) > float(segment["start"])
            and float(previous["start"]) < float(segment["end"])
            for previous in reversed(deduplicated[-20:])
        )
        if not duplicate:
            deduplicated.append(segment)
    return ordered if preserve_existing else deduplicated, {
        "added_segments": added, "retimed_segments": len(corrections), "corrections": corrections,
        "skipped_retimes": skipped_retimes, "skipped_partial_segments": skipped_partial_segments,
    }


