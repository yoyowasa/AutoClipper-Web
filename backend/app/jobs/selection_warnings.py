"""Only explicit subtitle/fact review flags can be deferred to human subtitle review."""
from typing import Literal

from pydantic import BaseModel, ConfigDict

# Do not infer safety from substrings. New/selection risk flags remain blocking.
SUBTITLE_REVIEW_RISKS = {
    "historical_claims_require_review": "歴史上の事実・年代について、音声と字幕の内容を確認してください。",
    "proper_noun_caption_review": "人名・地名・作品名などの固有名詞が、音声どおりの表記か確認してください。",
    "factual_claims_require_review": "事実・数値について、音声と字幕の内容を確認してください。",
    "transcript_accuracy_review": "音声の聞き取りと字幕の内容が一致しているか確認してください。",
    "subtitle_accuracy_review": "音声の聞き取りと字幕の内容が一致しているか確認してください。",
}


class SelectionReviewWarning(BaseModel):
    code: str
    message: str
    scope: Literal["clip"] = "clip"
    start: float
    end: float

    model_config = ConfigDict(extra="forbid")


def subtitle_review_warnings(flags: list[str], start: float, end: float) -> list[SelectionReviewWarning]:
    # The selection response has clip-level flags, not per-flag subtitle evidence.
    return [SelectionReviewWarning(code=code, message=SUBTITLE_REVIEW_RISKS[code], start=start, end=end)
            for code in dict.fromkeys(flags) if code in SUBTITLE_REVIEW_RISKS]
