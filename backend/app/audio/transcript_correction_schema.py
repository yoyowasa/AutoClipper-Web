from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CorrectionReason = Literal[
    "unchanged",
    "proper_noun",
    "homophone",
    "punctuation",
    "numeric_expression",
    "asr_error",
]
ChangedCorrectionReason = Literal[
    "proper_noun",
    "homophone",
    "punctuation",
    "numeric_expression",
    "asr_error",
]


class CorrectedTranscriptSegment(BaseModel):
    index: int = Field(ge=0)
    original_text: str
    corrected_text: str
    changed: bool
    reason: CorrectionReason
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class TranscriptCorrectionBatch(BaseModel):
    segments: list[CorrectedTranscriptSegment]

    model_config = ConfigDict(extra="forbid")


class CompactTranscriptCorrection(BaseModel):
    index: int = Field(ge=0)
    corrected_text: str = Field(min_length=1)
    reason: ChangedCorrectionReason
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")


class CompactTranscriptCorrectionBatch(BaseModel):
    target_count: int = Field(ge=0)
    changes: list[CompactTranscriptCorrection]

    model_config = ConfigDict(extra="forbid")


def transcript_correction_json_schema(expected_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["segments"],
        "properties": {
            "segments": {
                "type": "array",
                "minItems": expected_count,
                "maxItems": expected_count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "index",
                        "original_text",
                        "corrected_text",
                        "changed",
                        "reason",
                        "confidence",
                    ],
                    "properties": {
                        "index": {"type": "integer", "minimum": 0},
                        "original_text": {"type": "string"},
                        "corrected_text": {"type": "string"},
                        "changed": {"type": "boolean"},
                        "reason": {
                            "type": "string",
                            "enum": [
                                "unchanged",
                                "proper_noun",
                                "homophone",
                                "punctuation",
                                "numeric_expression",
                                "asr_error",
                            ],
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            }
        },
    }


def transcript_correction_response_format(expected_count: int) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "subtitle_correction_batch",
        "strict": True,
        "schema": transcript_correction_json_schema(expected_count),
    }


def compact_transcript_correction_json_schema(expected_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_count", "changes"],
        "properties": {
            "target_count": {
                "type": "integer",
                "enum": [expected_count],
            },
            "changes": {
                "type": "array",
                "minItems": 0,
                "maxItems": expected_count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "index",
                        "corrected_text",
                        "reason",
                        "confidence",
                    ],
                    "properties": {
                        "index": {"type": "integer", "minimum": 0},
                        "corrected_text": {"type": "string", "minLength": 1},
                        "reason": {
                            "type": "string",
                            "enum": [
                                "proper_noun",
                                "homophone",
                                "punctuation",
                                "numeric_expression",
                                "asr_error",
                            ],
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
        },
    }


def compact_transcript_correction_response_format(expected_count: int) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "subtitle_correction_changes_only_batch",
        "strict": True,
        "schema": compact_transcript_correction_json_schema(expected_count),
    }
