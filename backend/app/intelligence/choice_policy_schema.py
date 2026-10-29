"""Executable allowlist. No text, paths, code or validation thresholds are policy data."""
import math
from pydantic import BaseModel, ConfigDict, Field, field_validator

FRAMING_OPTIONS = ("center_crop", "face_tracking_crop", "subject_tracking_crop", "speaker_tracking_crop", "blur_background")
INTENTS = ("factual", "engagement", "concise")
DEFAULT_WEIGHTS = {**{"ranking.opening": 1.0},
    **{f"title_hook.{v}": 1.0 for v in INTENTS},
    **{f"framing.{v}": 1.0 for v in FRAMING_OPTIONS},
    **{f"text_style.{role}.{v}": 1.0 for role in ("title", "hook", "subtitle") for v in ("bold", "regular")},
    **{f"effects.{v}": 1.0 for v in ("topic", "number", "reaction")},
    **{f"allocation.{v}": 1.0 for v in ("normal", "short")}}
MAX_CHANGE = .1
IMPROVEMENT = 1.2
REGRESSION = .8


class ChoicePolicyValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    @field_validator("weights")
    @classmethod
    def allowlist(cls, value):
        if set(value) != set(DEFAULT_WEIGHTS) or any(not math.isfinite(v) or not .5 <= v <= 2 for v in value.values()):
            raise ValueError("POLICY_VALUE_NOT_ALLOWED")
        return dict(value)


def changed_values(before, key, value):
    old = ChoicePolicyValues.model_validate(before).weights
    if key not in old or value == old[key] or abs(value - old[key]) > old[key] * MAX_CHANGE + 1e-9:
        raise ValueError("POLICY_STEP_NOT_ALLOWED")
    return ChoicePolicyValues(weights={**old, key: value}).model_dump()
