import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AutomationMode = Literal["manual", "shadow", "guarded", "auto"]
EffectiveAutomationMode = Literal["manual", "shadow"]
AUTOMATION_MANIFEST_FILENAME = "automation_manifest.json"


class AutomationRoleAssignments(BaseModel):
    initial_selection: Literal["legacy", "codex"] = Field(alias="initialSelection")
    title_hook: Literal["manual_request"] = Field(
        default="manual_request",
        alias="titleHook",
    )
    clip_review: Literal["manual", "skipped"] = Field(alias="clipReview")
    subtitle_review: Literal["manual", "skipped"] = Field(alias="subtitleReview")
    final_quality_gate: Literal["not_connected"] = Field(
        default="not_connected",
        alias="finalQualityGate",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class AutomationManifest(BaseModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    job_id: str = Field(alias="jobId")
    video_id: str = Field(alias="videoId")
    decision_input_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        alias="decisionInputHash",
    )
    requested_mode: AutomationMode = Field(alias="requestedMode")
    effective_mode: EffectiveAutomationMode = Field(alias="effectiveMode")
    fallback_reason: str | None = Field(default=None, alias="fallbackReason")
    state: Literal["configured"] = "configured"
    roles: AutomationRoleAssignments
    limitations: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


def automation_manifest_path(output_dir: Path) -> Path:
    return output_dir / AUTOMATION_MANIFEST_FILENAME


def automation_decision_input_hash(
    *,
    video_id: str,
    stored_path: str,
    settings: dict[str, Any],
) -> str:
    canonical_payload = json.dumps(
        {
            "videoId": video_id,
            "storedPath": stored_path,
            "settings": settings,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()


def build_automation_manifest(
    *,
    job_id: str,
    video_id: str,
    stored_path: str,
    settings: dict[str, Any],
) -> AutomationManifest:
    raw_mode = str(settings.get("automationMode") or "manual").strip()
    requested_mode: AutomationMode = (
        raw_mode if raw_mode in {"manual", "shadow", "guarded", "auto"} else "manual"
    )
    burn_subtitles = bool(settings.get("burnSubtitles", True))
    clip_review = bool(settings.get("requireClipPlanReview", False))
    subtitle_review = burn_subtitles and bool(
        settings.get("requireSubtitleReview", False)
    )

    fallback_reason: str | None = None
    if requested_mode == "shadow" and burn_subtitles and clip_review and subtitle_review:
        effective_mode: EffectiveAutomationMode = "shadow"
    else:
        effective_mode = "manual"
        if requested_mode in {"guarded", "auto"}:
            fallback_reason = "quality_gate_not_connected"
        elif requested_mode == "shadow":
            fallback_reason = "shadow_review_stops_incomplete"
        elif raw_mode != requested_mode:
            fallback_reason = "unknown_mode"

    initial_selection = str(
        settings.get("initialSelectionProvider") or "legacy"
    ).strip()
    return AutomationManifest(
        jobId=job_id,
        videoId=video_id,
        decisionInputHash=automation_decision_input_hash(
            video_id=video_id,
            stored_path=stored_path,
            settings=settings,
        ),
        requestedMode=requested_mode,
        effectiveMode=effective_mode,
        fallbackReason=fallback_reason,
        roles=AutomationRoleAssignments(
            initialSelection=(
                "codex" if initial_selection == "codex" else "legacy"
            ),
            clipReview="manual" if clip_review else "skipped",
            subtitleReview="manual" if subtitle_review else "skipped",
        ),
        limitations=[
            "automated_title_hook_not_connected",
            "automated_final_quality_gate_not_connected",
        ],
    )


def write_automation_manifest(
    document: AutomationManifest,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(
                document.model_dump(by_alias=True, mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


def load_automation_manifest(input_path: Path) -> AutomationManifest:
    return AutomationManifest.model_validate_json(input_path.read_text(encoding="utf-8"))
