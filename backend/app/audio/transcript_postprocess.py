from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.audio.transcribe_faster_whisper import TranscriptSegment


RAW_TRANSCRIPT_FILENAME = "raw_transcript_segments.json"
TRANSCRIPT_POSTPROCESS_SUMMARY_FILENAME = "transcript_postprocess_summary.json"


DEFAULT_TRANSCRIPT_REPLACEMENTS: dict[str, str] = {
    "オープンAI": "OpenAI",
    "オープンエーアイ": "OpenAI",
    "チャットGPT": "ChatGPT",
    "チャットジーピーティー": "ChatGPT",
    "ＧＰＴ": "GPT",
    "ＡＩ": "AI",
    "ＤＸ": "DX",
    "ＮＩＳＡ": "NISA",
    "イーサリアム": "Ethereum",
    "ビットコイン": "Bitcoin",
    "ユーチューブ": "YouTube",
    "ニューズピックス": "NewsPicks",
    "リハック": "ReHacQ",
}


@dataclass(frozen=True)
class TranscriptPostprocessSettings:
    enabled: bool = True
    normalize_unicode: bool = True
    normalize_whitespace: bool = True
    normalize_punctuation: bool = True
    use_default_dictionary: bool = True
    replacements: Mapping[str, str] | None = None


@dataclass(frozen=True)
class TranscriptPostprocessResult:
    segments: list[TranscriptSegment]
    summary: dict[str, Any]


def parse_transcript_postprocess_settings(
    settings: TranscriptPostprocessSettings | Mapping[str, Any] | None,
) -> TranscriptPostprocessSettings:
    if settings is None:
        return TranscriptPostprocessSettings()
    if isinstance(settings, TranscriptPostprocessSettings):
        return settings
    aliases = {
        "enableTranscriptPostProcessing": "enabled",
        "transcriptNormalizeUnicode": "normalize_unicode",
        "transcriptNormalizeWhitespace": "normalize_whitespace",
        "transcriptNormalizePunctuation": "normalize_punctuation",
        "useDefaultTranscriptDictionary": "use_default_dictionary",
        "transcriptReplacements": "replacements",
    }
    normalized = {aliases.get(key, key): value for key, value in settings.items()}
    replacements = _coerce_replacements(normalized.get("replacements"))
    return TranscriptPostprocessSettings(
        enabled=_as_bool(normalized.get("enabled"), True),
        normalize_unicode=_as_bool(normalized.get("normalize_unicode"), True),
        normalize_whitespace=_as_bool(normalized.get("normalize_whitespace"), True),
        normalize_punctuation=_as_bool(normalized.get("normalize_punctuation"), True),
        use_default_dictionary=_as_bool(normalized.get("use_default_dictionary"), True),
        replacements=replacements,
    )


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_replacements(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    replacements: dict[str, str] = {}
    for source, target in value.items():
        source_text = str(source).strip()
        if not source_text:
            continue
        replacements[source_text] = str(target).strip()
    return replacements


def _normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_punctuation(text: str) -> str:
    text = re.sub(r"([。！？!?])\1{1,}", r"\1", text)
    text = re.sub(r"([、,])\1{1,}", r"\1", text)
    text = re.sub(r"\s+([。、！？!?])", r"\1", text)
    text = re.sub(r"([（「『])\s+", r"\1", text)
    text = re.sub(r"\s+([）」』])", r"\1", text)
    return text.strip()


def _apply_replacements(text: str, table: Mapping[str, str]) -> tuple[str, Counter[str]]:
    counts: Counter[str] = Counter()
    updated = text
    for source, target in sorted(table.items(), key=lambda item: len(item[0]), reverse=True):
        if not source:
            continue
        occurrences = updated.count(source)
        if occurrences:
            updated = updated.replace(source, target)
            counts[source] += occurrences
    return updated, counts


def postprocess_transcript_text(
    text: str,
    settings: TranscriptPostprocessSettings | Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    parsed = parse_transcript_postprocess_settings(settings)
    original = str(text)
    if not parsed.enabled:
        return original, {
            "enabled": False,
            "changed": False,
            "replacement_counts": {},
            "normalization_applied": [],
        }

    updated = original
    normalization_applied: list[str] = []
    if parsed.normalize_unicode:
        updated = _normalize_unicode(updated)
        normalization_applied.append("unicode_nfkc")
    if parsed.normalize_whitespace:
        updated = _normalize_whitespace(updated)
        normalization_applied.append("whitespace")
    if parsed.normalize_punctuation:
        updated = _normalize_punctuation(updated)
        normalization_applied.append("punctuation")

    replacement_counts: Counter[str] = Counter()
    if parsed.use_default_dictionary:
        updated, default_counts = _apply_replacements(updated, DEFAULT_TRANSCRIPT_REPLACEMENTS)
        replacement_counts.update(default_counts)
    updated, custom_counts = _apply_replacements(updated, parsed.replacements or {})
    replacement_counts.update(custom_counts)
    return updated, {
        "enabled": True,
        "changed": updated != original,
        "replacement_counts": dict(sorted(replacement_counts.items())),
        "normalization_applied": normalization_applied,
    }


def postprocess_transcript_segments(
    segments: Sequence[TranscriptSegment],
    settings: TranscriptPostprocessSettings | Mapping[str, Any] | None = None,
) -> TranscriptPostprocessResult:
    parsed = parse_transcript_postprocess_settings(settings)
    processed: list[TranscriptSegment] = []
    replacement_counts: Counter[str] = Counter()
    changed_segments: list[dict[str, Any]] = []

    for index, segment in enumerate(segments):
        new_text, text_summary = postprocess_transcript_text(segment.text, parsed)
        replacement_counts.update(text_summary.get("replacement_counts", {}))
        if new_text != segment.text:
            changed_segments.append(
                {
                    "index": index,
                    "start": segment.start,
                    "end": segment.end,
                    "before": segment.text,
                    "after": new_text,
                }
            )
        processed.append(
            TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=new_text,
                confidence=segment.confidence,
            )
        )

    total_chars_before = sum(len(segment.text) for segment in segments)
    total_chars_after = sum(len(segment.text) for segment in processed)
    summary = {
        "enabled": parsed.enabled,
        "segment_count": len(processed),
        "changed_segment_count": len(changed_segments),
        "total_chars_before": total_chars_before,
        "total_chars_after": total_chars_after,
        "replacement_counts": dict(sorted(replacement_counts.items())),
        "normalization": {
            "unicode_nfkc": parsed.normalize_unicode,
            "whitespace": parsed.normalize_whitespace,
            "punctuation": parsed.normalize_punctuation,
        },
        "used_default_dictionary": parsed.use_default_dictionary,
        "custom_replacement_count": len(parsed.replacements or {}),
        "changed_segments": changed_segments[:20],
    }
    return TranscriptPostprocessResult(segments=processed, summary=summary)


def raw_transcript_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / RAW_TRANSCRIPT_FILENAME


def transcript_postprocess_summary_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / TRANSCRIPT_POSTPROCESS_SUMMARY_FILENAME


def write_transcript_postprocess_summary(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
