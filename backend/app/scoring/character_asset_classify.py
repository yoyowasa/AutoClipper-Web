"""Visual classification via the existing ChatGPT-login Codex bridge."""

from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw, ImageOps
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.scoring.codex_title_hook_suggestions import CodexTitleHookSuggestionGenerator


EMOTIONS = ["joy", "anger", "sorrow", "fun", "neutral"]
ISSUES = ["blur", "eyes_closed", "occluded", "other_character", "cut_off"]
CLASSIFY_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "properties": {"candidates": {
        "type": "array", "minItems": 1, "maxItems": 8,
        "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "candidateId": {"type": "integer", "minimum": 0, "maximum": 7},
                "emotion": {"type": "string", "enum": EMOTIONS},
                "usable": {"type": "boolean"},
                "issues": {"type": "array", "items": {"type": "string", "enum": ISSUES}},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "same_character": {"type": ["boolean", "null"]},
            },
            "required": ["candidateId", "emotion", "usable", "issues", "score", "same_character"],
        },
    }},
    "required": ["candidates"],
}
CLASSIFY_PROMPT = """キャラのサムネイル素材を判定してください。最初の画像は最大8枚の一覧です。
番号は左から右、上から下。入力のcandidateCount枚だけを、各番号1回ずつ返してください。
喜=joy、怒=anger、哀=sorrow、楽=fun、判別できない/平静=neutral。
顔と胸から上が見え、サムネ素材として使えるかをusableで判定し、問題をissuesで列挙してください。
scoreは素材としての品質0〜1。見えない表情や人物は推測しないでください。
hasReference=trueなら2枚目は採用済みのキャラ参照です。同一人物かをsame_characterに真偽値で返す。
参照がなければsame_characterはnull。返答は指定JSONだけ。promptVersion=character-assets-v1。"""


class ClassifiedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)
    candidate_id: int = Field(alias="candidateId", ge=0, le=7, strict=True)
    emotion: Literal["joy", "anger", "sorrow", "fun", "neutral"]
    usable: StrictBool
    issues: list[Literal["blur", "eyes_closed", "occluded", "other_character", "cut_off"]]
    score: float = Field(ge=0, le=1, strict=True)
    same_character: StrictBool | None


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[ClassifiedCandidate] = Field(min_length=1, max_length=8)


def validate_classification(payload: Any, *, count: int, has_reference: bool) -> Classification:
    result = Classification.model_validate(payload)
    if len(result.candidates) != count or {item.candidate_id for item in result.candidates} != set(range(count)):
        raise ValueError("素材判定の番号に重複・欠落があります。")
    if any((item.same_character is None) == has_reference for item in result.candidates):
        raise ValueError("参照画像の有無とsame_characterが一致しません。")
    return result


def contact_sheet(frames: list[Path], output: Path) -> Path:
    if not 1 <= len(frames) <= 8:
        raise ValueError("素材の一覧画像は1〜8枚です。")
    sheet = Image.new("RGB", (1280, 880), "#242424")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(frames):
        x, y = (index % 4) * 320, (index // 4) * 440
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "#888888")
            background.alpha_composite(rgba)
            tile = ImageOps.contain(background.convert("RGB"), (310, 410))
        sheet.paste(tile, (x + (320 - tile.width) // 2, y + 25))
        draw.text((x + 10, y + 6), f"CANDIDATE {index}", fill="white")
    sheet.save(output, "JPEG", quality=88)
    return output


class CodexCharacterAssetClassifier(CodexTitleHookSuggestionGenerator):
    task = "character_asset_classify"
    system_prompt = CLASSIFY_PROMPT
    response_schema = CLASSIFY_SCHEMA

    def parse_output(self, output: dict[str, Any]) -> Classification:
        return Classification.model_validate(output)

    def classify(self, sheet: Path, *, count: int, reference: Path | None) -> Classification:
        if not 1 <= count <= 8:
            raise ValueError("素材判定は1〜8枚です。")
        result = self.generate(
            {"candidateCount": count, "hasReference": reference is not None},
            [sheet] + ([reference] if reference else []),
        )
        return validate_classification(result, count=count, has_reference=reference is not None)
