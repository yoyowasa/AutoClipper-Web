"""Apply explicit human decisions independently of the general reselection switch."""

import json
from collections import Counter
from typing import Any

from app.candidates.used_ranges import PREVIOUS_PROPOSALS_SETTING, near_duplicate_of_previous

REJECTED_RANGES_SETTING = "_rejectedRanges"
REASON_LABELS = {
    "no_content": "内容がない",
    "missing_context": "文脈不足",
    "weak_highlight": "見どころが弱い",
    "other": "その他",
    "unspecified": "理由未指定",
}


def _same_range(start: float, end: float, row: dict[str, Any]) -> bool:
    return abs(start - row["start"]) <= 0.001 and abs(end - row["end"]) <= 0.001


def missing_context_count(row: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    return sum(
        item["reason"] == "missing_context"
        and item["type"] == row["type"]
        and near_duplicate_of_previous(
            row["start"],
            row["end"],
            {
                PREVIOUS_PROPOSALS_SETTING: [(item["start"], item["end"])],
            },
        )
        for item in rows
    )


def _expanded(start: float, end: float, row: dict[str, Any]) -> bool:
    return start <= row["start"] and end >= row["end"] and (start < row["start"] - 0.001 or end > row["end"] + 0.001)


def user_rejection_reason(start: float, end: float, clip_type: str, settings: dict[str, Any]) -> str | None:
    rows = settings.get(REJECTED_RANGES_SETTING, [])
    for row in sorted(rows, key=lambda item: {"no_content": 0, "weak_highlight": 1, "missing_context": 2}.get(item["reason"], 3)):
        old_duration = row["end"] - row["start"]
        if old_duration <= 0 or (row["reason"] != "no_content" and row["type"] != clip_type):
            continue
        overlap = max(0.0, min(end, row["end"]) - max(start, row["start"]))
        covers_half = overlap + 1e-9 >= old_duration * 0.5
        reason = row["reason"]
        if reason in {"no_content", "weak_highlight"} and covers_half:
            return f"rejected_by_user_{reason}"
        near = near_duplicate_of_previous(start, end, {PREVIOUS_PROPOSALS_SETTING: [(row["start"], row["end"])]})
        if reason == "missing_context":
            if missing_context_count(row, rows) >= 2 and covers_half:
                return "rejected_by_user_missing_context_repeated"
            if near and not _expanded(start, end, row):
                return "rejected_by_user_missing_context"
        elif reason in {"other", "unspecified"} and near:
            return f"rejected_by_user_{reason}"
    return None


def near_previous_except_context_expansion(start: float, end: float, clip_type: str, settings: dict[str, Any]) -> bool:
    rows = settings.get(REJECTED_RANGES_SETTING, [])
    other_kept = settings.get("_allocationKeptRanges", {}).get("short" if clip_type == "normal" else "normal", [])
    previous = [
        old
        for old in settings.get(PREVIOUS_PROPOSALS_SETTING, [])
        if tuple(old) not in {tuple(item) for item in other_kept} and not any(
            row["reason"] == "missing_context"
            and row["type"] == clip_type
            and _same_range(*old, row)
            and missing_context_count(row, rows) == 1
            and _expanded(start, end, row)
            for row in rows
        )
    ]
    return near_duplicate_of_previous(start, end, {PREVIOUS_PROPOSALS_SETTING: previous})


def rejection_context_guidance(clip_type: str, settings: dict[str, Any], *, max_length: int) -> str:
    rows = [row for row in settings.get(REJECTED_RANGES_SETTING, []) if row["type"] == clip_type or row["reason"] == "no_content"]
    if not rows:
        return ""
    rules = (
        "ユーザーの不採用判断: 内容なしは形式を問わず元区間の50%以上を含む候補を避ける。"
        "見どころが弱い場合は同じ形式の元区間50%以上を避け、より見どころの強い別の場面を探す。"
        "文脈不足は元区間を含め前後へ広げた尺ルール内の候補を優先して検討し、成立しなければ別の場面でよい。通常は10分を超えて最長30分まで拡張できるが、longformReasonに内容上必要な理由を書く。"
        "同区間で2回目の文脈不足は同じ形式の元区間50%以上を避ける。その他・未指定はほぼ同じ場面を避ける。"
    )
    counts = Counter(REASON_LABELS[row["reason"]] for row in rows)
    summary = f"不採用区間{len(rows)}件（" + "、".join(f"{label}{count}件" for label, count in counts.items()) + "）。"
    for count in range(min(15, len(rows)), -1, -1):
        details = "\n".join(
            f"{row['start']:g}-{row['end']:g}秒 {REASON_LABELS[row['reason']]}"
            + ("（文脈不足2回以上）" if row["reason"] == "missing_context" and missing_context_count(row, rows) >= 2 else "")
            + (f" ユーザー補足: {json.dumps(row['note'], ensure_ascii=False)}" if row.get("note") else "")
            for row in list(reversed(rows))[:count]
        )
        omitted = len(rows) - count
        text = rules + "\n" + summary + details + (f"\nほか{omitted}件（区間・補足を省略）" if omitted else "")
        if len(text) <= max_length:
            return text
    brief = summary + f"ユーザー補足{sum(bool(row.get('note')) for row in rows)}件（詳細省略）。"
    return brief if len(brief) <= max_length else ""
