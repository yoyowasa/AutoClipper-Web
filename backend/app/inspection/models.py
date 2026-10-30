"""Evidence from decoded final files, separate from the renderer's claims."""

from datetime import UTC, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

INSPECTION_VERSION = "final-output-inspection-v1"
MAX_REPAIRS = 2
SEMANTIC_TIMEOUT_SECONDS = 120
Outcome = Literal["pass", "fail", "unknown"]


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    outcome: Outcome
    evidence: dict = Field(default_factory=dict)
    second: float | None = None


class Attempt(BaseModel):
    index: int
    output_sha256: str | None = None
    checks: list[Check]
    repair: str | None = None
    repair_result: str | None = None


class InspectionRecord(BaseModel):
    version: Literal["final-output-inspection-v1"] = INSPECTION_VERSION
    job_id: str
    clip_id: str
    label: str
    input_revision: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    max_repairs: int = MAX_REPAIRS
    outcome: Literal["inspecting", "pass", "incomplete"] = "inspecting"
    attempts: list[Attempt] = Field(default_factory=list)


REASONS = {
    "MEDIA_UNREADABLE": "完成MP4を読み取れません。",
    "STREAM_MISSING": "映像または音声がありません。",
    "DURATION_MISMATCH": "完成MP4の尺が確定した範囲と一致しません。",
    "AV_DURATION_MISMATCH": "映像と音声の長さが一致しません。",
    "DIMENSIONS_INVALID": "解像度・縦横比が形式の条件に一致しません。",
    "BLACK_INTERVAL": "元映像にない黒画面が続いています。",
    "FREEZE_INTERVAL": "元映像にない静止が続いています。",
    "SILENCE_INTERVAL": "元音声にない無音が続いています。",
    "SOURCE_SCAN_UNAVAILABLE": "元動画との比較を完了できません。",
    "SUBTITLE_PIXELS_MISMATCH": "確定字幕と完成映像の表示時刻・文字・位置が一致しません。",
    "SUBTITLE_LINGERS": "字幕が確定した終了時刻を超えて残っています。",
    "SUBTITLE_OUT_OF_FRAME": "字幕が画面の外にはみ出しています。",
    "SUBTITLE_BANNER_COLLISION": "字幕が帯と重なっています。",
    "SUBTITLE_OVERLAP": "字幕同士の表示時刻が重なっています。",
    "SUBTITLE_REFERENCE_EMPTY": "確定字幕の表示を検証できません。",
    "SUBTITLE_SAMPLE_UNAVAILABLE": "短い字幕の表示を検証できません。",
    "SUBTITLE_DECODE_FAILED": "完成映像の字幕検査を完了できません。",
    "OPENING_MISMATCH": "冒頭・フックの音声が確定した場面と一致しません。",
    "OPENING_UNVERIFIED": "冒頭・フックの一致を検証できません。",
    "CONTENT_MISMATCH": "タイトル・投稿文とこの動画の内容が一致しません。",
    "THUMBNAIL_MISMATCH": "サムネとこの動画の内容が一致しません。",
    "SEMANTIC_UNVERIFIED": "Codexによる内容検査を完了できません。",
    "REPAIR_FAILED": "局所修復を完了できません。",
}


def failures(record: InspectionRecord) -> list[Check]:
    return [c for c in record.attempts[-1].checks if c.outcome != "pass"] if record.attempts else []


def stop_message(record: InspectionRecord) -> str:
    problems = failures(record)
    return (
        record.label
        + "："
        + " ".join(
            dict.fromkeys(
                REASONS.get(c.code, "完成検査を完了できません。") + (f"（完成動画 {c.second:.1f}秒）" if c.second is not None else "")
                for c in problems
            )
        )
    )
