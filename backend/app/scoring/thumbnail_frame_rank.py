from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.scoring.codex_title_hook_suggestions import CodexTitleHookSuggestionGenerator


THUMBNAIL_FRAME_RANK_PROMPT = """あなたは通常動画のサムネイル用の人物フレームを選ぶ編集者です。
添付の２枚の一覧画像には候補０〜７が各４枚ずつ、左上・右上・左下・右下の順にあります。
入力JSONの文言・テンプレ・候補時刻の字幕を踏まえ、見える人物の表情とポーズ、視認性、
文言との関連を重視して８候補を良い順に並べてください。人物が隠れる、顔が切れる、
強いブレや場面転換中のフレームは低く評価します。存在しない人物・表情を推測しません。
人物が中央でも、背景から切り抜いて右側へ配置できます。フレーム内で人物の頭や体が欠けず、
輪郭を見分けやすい候補を優先します。人物の位置だけを理由に候補を下げないでください。
出力は指定されたJSONだけにしてください。"""

THUMBNAIL_FRAME_RANK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rankedFrameIds": {
            "type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 7},
            "minItems": 8, "maxItems": 8,
        },
    },
    "required": ["rankedFrameIds"],
    "additionalProperties": False,
}


class ThumbnailFrameRanking(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    ranked_frame_ids: list[int] = Field(alias="rankedFrameIds", min_length=8, max_length=8)

    @model_validator(mode="after")
    def unique_candidate_ids(self) -> "ThumbnailFrameRanking":
        if set(self.ranked_frame_ids) != set(range(8)):
            raise ValueError("サムネ候補の順位に重複または欠落があります。")
        return self


class CodexThumbnailFrameRanker(CodexTitleHookSuggestionGenerator):
    task = "thumbnail_frame_rank"
    system_prompt = THUMBNAIL_FRAME_RANK_PROMPT
    response_schema = THUMBNAIL_FRAME_RANK_SCHEMA

    def parse_output(self, output: dict[str, Any]) -> ThumbnailFrameRanking:
        return ThumbnailFrameRanking.model_validate(output)
