"""Text-only emotion selection through the ChatGPT-login Codex bridge."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.character_asset_rules import CharacterEmotion
from app.scoring.codex_title_hook_suggestions import CodexTitleHookSuggestionGenerator


EMOTION_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "emotion": {"type": "string", "enum": ["joy", "anger", "sorrow", "fun"]},
        "reason": {"type": "string", "minLength": 1, "maxLength": 500},
    },
    "required": ["emotion", "reason"],
}


class ThumbnailEmotion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    emotion: CharacterEmotion
    reason: str = Field(min_length=1, max_length=500)


class CodexThumbnailEmotionSelector(CodexTitleHookSuggestionGenerator):
    task = "thumbnail_emotion_select"
    response_schema = EMOTION_SCHEMA
    system_prompt = """サムネ文言・動画タイトル・近くの字幕から、人物素材の表情を1つ選んでください。
availableEmotionsにある表情だけから選ぶ。喜=joy、怒=anger、哀=sorrow、楽=fun。
字幕やタイトルにない感情を捏造しない。reasonに選んだ理由を簡潔に記載する。
返答は指定JSONだけ。promptVersion=thumbnail-emotion-v1。"""

    def parse_output(self, output: dict[str, Any]) -> ThumbnailEmotion:
        return ThumbnailEmotion.model_validate(output)
