from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SCORE_SCHEMA_NAME = "clip_candidate_score"


class ClipCandidateScore(BaseModel):
    should_use: bool
    final_score: int = Field(ge=0, le=100)
    hook_score: int = Field(ge=0, le=100)
    completeness_score: int = Field(ge=0, le=100)
    context_independence_score: int = Field(ge=0, le=100)
    information_density_score: int = Field(ge=0, le=100)
    title: str
    overlay_title: str
    reason: str
    risk_flags: list[str]

    model_config = ConfigDict(extra="forbid")


def clip_candidate_score_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "should_use",
            "final_score",
            "hook_score",
            "completeness_score",
            "context_independence_score",
            "information_density_score",
            "title",
            "overlay_title",
            "reason",
            "risk_flags",
        ],
        "properties": {
            "should_use": {"type": "boolean"},
            "final_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "hook_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "completeness_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "context_independence_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "information_density_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "title": {"type": "string"},
            "overlay_title": {"type": "string"},
            "reason": {"type": "string"},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
        },
    }


def response_format_json_schema() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": SCORE_SCHEMA_NAME,
        "strict": True,
        "schema": clip_candidate_score_json_schema(),
    }
