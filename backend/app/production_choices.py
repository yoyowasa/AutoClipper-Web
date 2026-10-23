"""Small, allowlisted decision evidence shared by existing working artifacts.

This is a record format, not a selection policy. Unknown provenance stays unknown.
"""

from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


ChoiceSource = Literal["automatic", "manual", "preset", "default", "fallback", "unrecorded"]
ChoiceKind = Literal["range", "title_hook", "thumbnail", "framing", "text_style", "effects", "post_copy", "publication"]
VALUE_KEYS = frozenset({
    "type", "start", "end", "title", "publicationTitle", "overlayTitle", "hookText", "hookDurationSeconds",
    "hookSceneStart", "hookSceneEnd", "thumbnailKicker", "thumbnailLine1", "thumbnailLine2", "thumbnailFrameSeconds",
    "intent", "score", "openingScore", "topicKey", "longformReason", "framingOffsetX", "framingOffsetY", "framingZoom",
    "shortLayout", "titleStyle", "hookStyle", "subtitleStyle", "resolvedTitleStyle", "resolvedHookStyle",
    "resolvedSubtitleStyle", "postMetadataSource", "descriptionHash", "tagsHash", "hashtagsHash", "source",
    "assetId", "emotion", "cropMode", "templateVersion", "templateDesign", "subjectPlacement", "textStyles", "frameCandidateId",
    "second", "closeAvailable", "scale", "offsetX", "offsetY", "selectedTitleId", "recommendedTitleId",
    "bodyDurationSeconds", "completedDurationSeconds", "characterPresetName",
    "resolvedLayout", "settingSource", "cropX", "cropY", "cropSignalSource", "cropFallbackReason",
    "cropAttemptedStrategies", "renderedTextStyles", "additionalEffects",
    "outputSize", "contentViewport",
})
NESTED_KEYS = frozenset({
    "fontPreset", "fontName", "fontSize", "primaryColor", "outlineColor", "outlineWidth", "outerOutlineColor",
    "outerOutlineWidth", "shadow", "bold", "alignment", "marginX", "marginV", "xPercent", "yPercent", "positionMode",
    "positionOverride", "scale", "offsetX", "offsetY", "offset_x", "offset_y", "heading", "upper", "lower",
    "role", "source", "effectiveFontSize", "maxWidthPx", "fits", "overflowReason", "lineCount", "eventCount",
    "width", "height", "y",
})


def _project(value, keys):
    if isinstance(value, dict):
        return {key: _project(item, NESTED_KEYS) for key, item in value.items() if key in keys}
    if isinstance(value, list):
        return [_project(item, NESTED_KEYS) for item in value]
    return value


def choice_values(payload: dict) -> dict:
    """Never copy arbitrary metadata, paths, subtitle text or settings into a record."""
    return _project(payload, VALUE_KEYS)


def value_hash(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


class ChoiceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str
    values: dict[str, JsonValue] = Field(default_factory=dict)
    outcome: Literal["proposed", "selected", "not_selected", "rejected"] = "proposed"
    reason: str | None = None

    @field_validator("values")
    @classmethod
    def allowlisted_values(cls, value):
        if choice_values(value) != value:
            raise ValueError("Unexpected choice value field")
        return value


class ProductionChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(default_factory=lambda: uuid4().hex)
    kind: ChoiceKind
    scope: Literal["clip", "job"] = "clip"
    clipId: str | None = None
    stage: Literal["proposed", "applied", "removed", "published", "observed"]
    source: ChoiceSource = "unrecorded"
    recordedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))
    appliedAt: datetime | None = None
    inputRevision: str | None = None
    policyVersion: str | None = None
    timeBasis: Literal["source", "clip"] | None = None
    reason: str | None = None  # null explicitly means the reason was not recorded.
    candidates: list[ChoiceCandidate] = Field(default_factory=list)
    selectedIds: list[str] = Field(default_factory=list)
    recommendedId: str | None = None
    values: dict[str, JsonValue] = Field(default_factory=dict)

    _allowlisted_values = field_validator("values")(ChoiceCandidate.allowlisted_values.__func__)


def merge_history(*histories) -> list[ProductionChoice]:
    unique = {}
    for history in histories:
        for item in history:
            choice = item if isinstance(item, ProductionChoice) else ProductionChoice.model_validate(item)
            unique.setdefault(choice.id, choice)
    return sorted(unique.values(), key=lambda item: (item.recordedAt, item.id))


def append_choice(history: list[ProductionChoice], **kwargs) -> None:
    choice = ProductionChoice(**kwargs)
    previous = next((item for item in reversed(history) if (item.kind, item.scope, item.clipId) ==
                     (choice.kind, choice.scope, choice.clipId)), None)
    ignored = {"id", "recordedAt", "appliedAt"}
    if previous and previous.model_dump(exclude=ignored) == choice.model_dump(exclude=ignored):
        return
    if choice.stage in {"applied", "published"}:
        choice.appliedAt = choice.recordedAt
    history.append(choice)


def dump_history(history) -> list[dict]:
    return [item.model_dump(mode="json", exclude_none=True) for item in history]
