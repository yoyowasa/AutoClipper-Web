"""Fit the complete prompt, preserving channel trends and recording all omissions."""

from app.intelligence.analysis_prompt import MAX_ANALYSIS_PROMPT_CHARS, render_analysis_prompt

ANALYSIS_PROMPT_BUDGET_CHARS = MAX_ANALYSIS_PROMPT_CHARS - 20_000


def fit_analysis_budget(payload: dict, *, budget: int = ANALYSIS_PROMPT_BUDGET_CHARS) -> None:
    omissions = {"budget_chars": budget, "removed_video_ids": [], "removed_videos": 0,
                 "removal_order": "oldest_publication_first", "removed_reports": 0}
    payload["budget_omissions"] = omissions
    payload["input_scope"]["included_videos"] = len(payload["videos"])
    for video in sorted(payload["videos"], key=lambda video: (video["published_at"] or "", video["id"])):
        if len(render_analysis_prompt(payload)) <= budget:
            break
        payload["videos"].remove(video)
        payload["format_videos"][video["format"]].remove(video["id"])
        omissions["removed_video_ids"].append(video["id"])
        omissions["removed_videos"] += 1
        omissions["removed_reports"] += len(video["reports"]) + int("production" in video)
        payload["input_scope"]["included_videos"] = len(payload["videos"])


def compression_limitation(payload: dict) -> str:
    scope, budget = payload["input_scope"], payload["budget_omissions"]
    return (f"入力は新しい公開動画と形式別の累計再生数上位・下位を対象とし、対象外{scope['excluded_videos']}本、"
            f"文字数の都合で古い動画からさらに{budget['removed_videos']}本を省略、"
            f"{scope['eligible_videos']}本中{len(payload['videos'])}本を分析。"
            "動画別の日次行は返却日分の加算可能指標の期間合計・公式の初期7日と直近28日・ピーク日に要約。"
            "未返却日を0とせず、平均値・割合を再平均していない。チャンネル全体の日次推移は保持。")
