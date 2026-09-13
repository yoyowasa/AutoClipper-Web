from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Literal


ClipSelectionPreset = Literal[
    "auto",
    "highlights",
    "funny",
    "important",
    "emotional",
    "informative",
]

PRESET_KEYWORDS: dict[str, tuple[str, ...]] = {
    "auto": (),
    "highlights": (
        "実は",
        "初めて",
        "発表",
        "理由",
        "結論",
        "結果",
        "復帰",
        "倒れ",
        "事件",
        "驚",
        "まさか",
        "やば",
    ),
    "funny": (
        "笑",
        "面白",
        "おもしろ",
        "やば",
        "まさか",
        "失敗",
        "間違",
        "勘違",
        "ツッコミ",
    ),
    "important": (
        "重要",
        "大事",
        "発表",
        "お知らせ",
        "決定",
        "理由",
        "今後",
        "予定",
        "復帰",
        "変更",
    ),
    "emotional": (
        "嬉し",
        "悲し",
        "悔し",
        "泣",
        "感動",
        "本音",
        "本当に",
        "大好き",
        "怖",
    ),
    "informative": (
        "理由",
        "なぜ",
        "どうして",
        "方法",
        "解説",
        "説明",
        "つまり",
        "結論",
        "ポイント",
        "仕組み",
    ),
}

INTRO_OUTRO_PATTERNS: tuple[tuple[str, float], ...] = (
    ("ご視聴ありがとうございました", 7.0),
    ("お待たせいたしました", 4.0),
    ("声は聞こえ", 4.0),
    ("聞こえてる", 3.0),
    ("こんばんは", 3.0),
    ("よろしくお願い", 2.0),
    ("本日の配信はこの辺", 8.0),
    ("配信はこの辺", 7.0),
    ("終わりにしよう", 7.0),
    ("お別れいたしましょう", 6.0),
    ("さようなら", 6.0),
    ("バイバイ", 5.0),
    ("次の動画でお会い", 7.0),
)

PROMOTIONAL_PATTERNS: tuple[tuple[str, float], ...] = (
    ("動画アップ", 6.0),
    ("チャンネル登録", 8.0),
    ("高評価", 6.0),
    ("概要欄", 5.0),
    ("ぜひぜひご覧", 5.0),
    ("ご覧になっていただける", 5.0),
)

GENERIC_GUIDANCE_TERMS = {
    "シーン",
    "ところ",
    "場面",
    "切り抜き",
    "動画",
    "内容",
    "優先",
    "除外",
    "ほしい",
    "欲しい",
    "見たい",
    "話している",
    "話した",
    "している",
}

NORMAL_QUESTION_MARKERS = (
    "なぜ",
    "どうして",
    "とは",
    "って何",
    "っていうのは",
    "なんだろう",
    "何が",
    "どんな",
    "どういう",
    "ですか",
)

NORMAL_EXPLANATION_MARKERS = (
    "理由",
    "説明",
    "解説",
    "仕組み",
    "というのは",
    "つまり",
    "要するに",
)

NORMAL_EXAMPLE_MARKERS = (
    "例えば",
    "たとえば",
    "具体的",
    "実際",
    "ケース",
    "例を",
)

NORMAL_CONCLUSION_MARKERS = (
    "結論",
    "だから",
    "なので",
    "ということ",
    "大事",
    "重要",
    "と思います",
    "になります",
)


@dataclass(frozen=True)
class CandidateClipPreference:
    preset: ClipSelectionPreset = "auto"
    guidance: str = ""
    exclude_intro_outro: bool = True
    exclude_promotional_content: bool = False

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def _setting_bool(settings: dict[str, Any], key: str, default: bool) -> bool:
    value = settings.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _setting_text(settings: dict[str, Any], key: str) -> str:
    value = settings.get(key, "")
    return str(value).strip() if value is not None else ""


def _setting_preset(settings: dict[str, Any], key: str) -> ClipSelectionPreset:
    value = _setting_text(settings, key)
    if value in PRESET_KEYWORDS:
        return value  # type: ignore[return-value]
    return "auto"


def build_clip_selection_preferences(
    settings: dict[str, Any] | None,
) -> dict[str, CandidateClipPreference]:
    parsed = settings or {}
    exclude_intro_outro = _setting_bool(parsed, "excludeIntroOutro", True)
    exclude_promotional = _setting_bool(parsed, "excludePromotionalContent", False)
    return {
        "normal": CandidateClipPreference(
            preset=_setting_preset(parsed, "normalClipSelectionPreset"),
            guidance=_setting_text(parsed, "normalClipGuidance"),
            exclude_intro_outro=exclude_intro_outro,
            exclude_promotional_content=exclude_promotional,
        ),
        "short": CandidateClipPreference(
            preset=_setting_preset(parsed, "shortClipSelectionPreset"),
            guidance=_setting_text(parsed, "shortClipGuidance"),
            exclude_intro_outro=exclude_intro_outro,
            exclude_promotional_content=exclude_promotional,
        ),
    }


def normalize_content_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"\s+", "", normalized)


def guidance_terms(guidance: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", guidance)
    chunks = re.split(r"[\s、。,.!?！？:：;；/／\n\r]+", normalized)
    terms: list[str] = []
    for chunk in chunks:
        parts = re.split(
            r"(?:について|している|したい|する|した|優先|除外|場面|ところ|"
            r"から|まで|より|の|を|が|は|に|で|と|へ)",
            chunk,
        )
        for part in parts:
            clean = part.strip("「」『』()（）[]［］ ")
            if len(clean) < 2 or clean in GENERIC_GUIDANCE_TERMS:
                continue
            if clean not in terms:
                terms.append(clean)
    return terms[:20]


def guidance_match_score(text: str, preference: CandidateClipPreference) -> float:
    normalized = normalize_content_text(text)
    preset_hits = sum(
        1 for keyword in PRESET_KEYWORDS.get(preference.preset, ()) if normalize_content_text(keyword) in normalized
    )
    term_hits = sum(
        1 for term in guidance_terms(preference.guidance) if normalize_content_text(term) in normalized
    )
    return min(15.0, preset_hits * 3.0 + term_hits * 5.0)


def _pattern_penalty(text: str, patterns: tuple[tuple[str, float], ...]) -> float:
    normalized = normalize_content_text(text)
    penalty = 0.0
    for pattern, weight in patterns:
        occurrences = normalized.count(normalize_content_text(pattern))
        penalty += min(3, occurrences) * weight
    return penalty


def generic_content_penalty(text: str, preference: CandidateClipPreference) -> float:
    penalty = 0.0
    if preference.exclude_intro_outro:
        penalty += _pattern_penalty(text, INTRO_OUTRO_PATTERNS)
    if preference.exclude_promotional_content:
        penalty += _pattern_penalty(text, PROMOTIONAL_PATTERNS)
    return min(25.0, penalty)


def generic_content_flags(text: str, preference: CandidateClipPreference) -> list[str]:
    flags: list[str] = []
    if preference.exclude_intro_outro and _pattern_penalty(text, INTRO_OUTRO_PATTERNS) > 0:
        flags.append("generic_intro_outro")
    if preference.exclude_promotional_content and _pattern_penalty(text, PROMOTIONAL_PATTERNS) > 0:
        flags.append("promotional_content")
    return flags


def normal_topic_structure_score(text: str) -> float:
    """Score an explanatory topic without rewarding a particular duration."""

    normalized = normalize_content_text(text)
    groups = (
        (NORMAL_QUESTION_MARKERS, 4.0),
        (NORMAL_EXPLANATION_MARKERS, 4.0),
        (NORMAL_EXAMPLE_MARKERS, 3.0),
        (NORMAL_CONCLUSION_MARKERS, 4.0),
    )
    matched_groups = 0
    score = 0.0
    for markers, weight in groups:
        if any(normalize_content_text(marker) in normalized for marker in markers):
            matched_groups += 1
            score += weight
    if matched_groups >= 3:
        score += 2.0
    return min(15.0, score)


def normal_low_value_reading_penalty(text: str) -> float:
    """Penalize normal clips dominated by name/thanks/superchat reading.

    Shorts intentionally do not use this penalty because a short reaction to a
    comment or superchat can still be a complete highlight.
    """

    normalized = normalize_content_text(text)
    thanks_count = normalized.count("ありがとう")
    superchat_count = normalized.count("スーパーチャット") + normalized.count("スパチャ")
    readout_count = normalized.count("読み上げ不要") + normalized.count("読みます")
    name_suffix_count = normalized.count("さん")
    penalty = (
        min(14.0, thanks_count * 2.5)
        + min(8.0, superchat_count * 3.0)
        + min(5.0, readout_count * 2.5)
        + min(6.0, max(0, name_suffix_count - 2) * 1.5)
    )
    structure_score = normal_topic_structure_score(text)
    if structure_score >= 10.0:
        penalty *= 0.35
    elif structure_score >= 4.0:
        penalty *= 0.65
    return min(25.0, penalty)


def selection_content_penalty(
    text: str,
    preference: CandidateClipPreference,
    candidate_type: Literal["normal", "short"],
) -> float:
    penalty = generic_content_penalty(text, preference)
    if candidate_type == "normal":
        penalty += normal_low_value_reading_penalty(text)
    return min(25.0, penalty)


def selection_content_flags(
    text: str,
    preference: CandidateClipPreference,
    candidate_type: Literal["normal", "short"],
) -> list[str]:
    flags = generic_content_flags(text, preference)
    if candidate_type == "normal" and normal_low_value_reading_penalty(text) >= 5.0:
        flags.append("normal_low_value_reading")
    return flags


def is_generic_intro_outro_text(text: str) -> bool:
    preference = CandidateClipPreference()
    return generic_content_penalty(text, preference) >= 3.0
