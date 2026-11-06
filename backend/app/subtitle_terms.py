"""Per-character learning of exact subtitle terms the human corrected repeatedly.

Only whole-string replacements the human actually made are learned: no context, meaning or
timing inference. A rule needs the same correction at least three times, in two jobs or five times in
one, and is dropped when the human leaves the source term alone or changes the result back.
"""
import difflib
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from app.audio.transcribe_faster_whisper import TranscriptSegment, TranscriptWord
from app.render.subtitle_timing import usable_words
from app.storage.json_io import write_json_atomic
from app.storage.locking import storage_mutation_lock

MIN_OCCURRENCES = 3
MIN_JOBS = 2
SINGLE_JOB_OCCURRENCES = 5
MIN_SHARE = .8
MIN_SOURCE_CHARS = 2
MAX_SOURCE_CHARS = 20
MAX_REVERSALS = 2
MAX_JOBS = 300
SEPARATOR = "\t"
_LETTER = re.compile(r"[0-9A-Za-z぀-ヿ㐀-鿿]")


def character_id(character: str) -> str:
    return hashlib.sha256(character.encode("utf-8")).hexdigest()[:32]


def store_path(root: Path, character: str) -> Path:
    return root / "subtitle_terms" / f"{character_id(character)}.json"


def read_store(root: Path, character: str) -> dict:
    try:
        data = json.loads(store_path(root, character).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"schemaVersion": 1, "character": character, "jobs": data.get("jobs", {}), "disabled": data.get("disabled", [])}


def extract_pairs(original: str, final: str) -> list[tuple[str, str]]:
    """Replaced strings only; insertions, deletions and one-character fragments are not terms."""
    matcher = difflib.SequenceMatcher(None, original, final, autojunk=False)
    pairs = []
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag != "replace":
            continue
        source, target = original[a1:a2], final[b1:b2]
        if (MIN_SOURCE_CHARS <= len(source) <= MAX_SOURCE_CHARS and 0 < len(target) <= MAX_SOURCE_CHARS
                and not re.search(r"\s", source + target) and _LETTER.search(source)):
            pairs.append((source, target))
    return pairs


def job_evidence(document) -> dict:
    pairs: dict[str, int] = defaultdict(int)
    for segment in document.segments:
        if segment.edited and segment.original_text != segment.text:
            for source, target in extract_pairs(segment.original_text, segment.text):
                pairs[source + SEPARATOR + target] += 1
    sources = {key.split(SEPARATOR)[0] for key in pairs}
    kept = {source: sum(segment.text.count(source) for segment in document.segments) for source in sources}
    return {"pairs": dict(pairs), "kept": kept}


def learn_from_document(document, root: Path) -> bool:
    """Replace this job's evidence with what its saved subtitles show now (idempotent)."""
    character = getattr(document, "character_preset_name", None)
    if not character:
        return False
    evidence = job_evidence(document)
    with storage_mutation_lock(root / "subtitle_terms"):
        store = read_store(root, character)
        known = store["jobs"].get(document.job_id)
        if known == evidence or (known is None and not evidence["pairs"]):
            return False
        store["jobs"].pop(document.job_id, None)
        if evidence["pairs"]:
            store["jobs"][document.job_id] = evidence
        while len(store["jobs"]) > MAX_JOBS:
            store["jobs"].pop(next(iter(store["jobs"])))
        write_json_atomic(store_path(root, character), store)
    return True


def derive_rules(store: dict) -> list[dict]:
    """Every candidate with the numbers behind it; `active` marks the ones that meet all thresholds."""
    counts: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"count": 0, "jobs": 0}))
    kept: dict[str, int] = defaultdict(int)
    for evidence in store["jobs"].values():
        for key, count in evidence["pairs"].items():
            source, target = key.split(SEPARATOR)
            counts[source][target]["count"] += count
            counts[source][target]["jobs"] += 1
        for source, count in evidence["kept"].items():
            kept[source] += count
    disabled = {tuple(item) for item in store["disabled"]}
    rules = []
    for source, targets in counts.items():
        total = sum(item["count"] for item in targets.values())
        target, best = max(targets.items(), key=lambda entry: (entry[1]["count"], entry[0]))
        reversed_count = counts[target][source]["count"] if target in counts and source in counts[target] else 0
        corrected, remaining = best["count"], kept[source]
        rules.append({
            "src": source, "dst": target, "count": corrected, "jobs": best["jobs"], "kept": remaining,
            "share": corrected / total, "reversed": reversed_count,
            "disabled": (source, target) in disabled,
            "active": (corrected >= MIN_OCCURRENCES and (best["jobs"] >= MIN_JOBS or corrected >= SINGLE_JOB_OCCURRENCES)
                       and corrected / total >= MIN_SHARE
                       and corrected / (corrected + remaining) >= MIN_SHARE and reversed_count < MAX_REVERSALS
                       and (source, target) not in disabled),
        })
    return sorted(rules, key=lambda rule: (-rule["count"], rule["src"]))


def active_rules(root: Path, character: str | None) -> list[dict]:
    return [rule for rule in derive_rules(read_store(root, character)) if rule["active"]] if character else []


def set_disabled(root: Path, character: str, source: str, target: str, disabled: bool) -> None:
    with storage_mutation_lock(root / "subtitle_terms"):
        store = read_store(root, character)
        pair = [source, target]
        store["disabled"] = [item for item in store["disabled"] if item != pair]
        if disabled:
            store["disabled"].append(pair)
        write_json_atomic(store_path(root, character), store)


def _replace_words(words: list[TranscriptWord], pattern, mapping) -> list[TranscriptWord]:
    """Same replacement on word-level timing; the term keeps the first overlapped word's start."""
    owners: list[int] = []
    stripped = []
    for index, word in enumerate(words):
        chars = re.sub(r"\s", "", word.word)
        owners += [index] * len(chars)
        stripped.append(chars)
    whole = "".join(stripped)
    pieces: list[list[str]] = [[] for _ in words]
    ends = [word.end for word in words]
    overlapped: list[tuple[int, set[int]]] = []
    position = 0
    for match in pattern.finditer(whole):
        start, end = match.span()
        for p in range(position, start):
            pieces[owners[p]].append(whole[p])
        pieces[owners[start]].append(mapping[match.group()])
        overlapped.append((owners[start], {owners[p] for p in range(start, end)}))
        position = end
    for p in range(position, len(whole)):
        pieces[owners[p]].append(whole[p])
    for owner, covered in overlapped:
        for index in covered - {owner}:
            if not pieces[index]:
                ends[owner] = max(ends[owner], words[index].end)
    result = []
    for index, word in enumerate(words):
        if not stripped[index]:
            result.append(word)
        elif pieces[index]:
            lead = word.word[:len(word.word) - len(word.word.lstrip())]
            result.append(word.model_copy(update={"word": lead + "".join(pieces[index]), "end": ends[index]}))
    return result


def apply_rules(segments: list[TranscriptSegment], rules: list[dict]) -> tuple[list[TranscriptSegment], list[dict]]:
    """Single pass, longest source first, so one replacement never feeds another."""
    if not rules:
        return segments, []
    mapping = {rule["src"]: rule["dst"] for rule in rules}
    pattern = re.compile("|".join(re.escape(source) for source in sorted(mapping, key=lambda s: (-len(s), s))))
    result, applied = [], []
    for index, segment in enumerate(segments):
        found = [match.group() for match in pattern.finditer(segment.text)]
        if not found:
            result.append(segment)
            continue
        update = {"text": pattern.sub(lambda match: mapping[match.group()], segment.text)}
        if segment.words and usable_words(segment.text, segment.words):
            words = _replace_words(segment.words, pattern, mapping)
            update["words"] = words if words and usable_words(update["text"], words) else None
        result.append(segment.model_copy(update=update))
        applied += [{"segmentIndex": index, "start": segment.start, "src": source, "dst": mapping[source]} for source in found]
    return result, applied
