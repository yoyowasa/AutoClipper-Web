from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.scoring.title_hook_suggestions import (
    SYSTEM_PROMPT,
    TITLE_HOOK_GENERATION_SCHEMA,
    GeneratedTitleHookSuggestionResult,
    TitleHookSuggestionResult,
)


BRIDGE_DIRNAME = "codex_bridge"
BRIDGE_REQUESTS_DIRNAME = "requests"
BRIDGE_RESPONSES_DIRNAME = "responses"
BRIDGE_STATUS_FILENAME = "status.json"
BRIDGE_REQUEST_CLAIM_GRACE_SECONDS = 10.0
BRIDGE_STATUS_STALE_SECONDS = 15.0
BRIDGE_UNAVAILABLE_CONFIRMATION_SECONDS = 2.0
BRIDGE_STATUS_FUTURE_TOLERANCE_SECONDS = 30.0
MAX_BRIDGE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_BRIDGE_STATUS_BYTES = 64 * 1024
DEFAULT_CODEX_RESPONSE_TIMEOUT_SECONDS = 240.0
DEFAULT_CODEX_RESPONSE_POLL_SECONDS = 0.25


class CodexTitleHookSuggestionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _BridgeEnvelope(BaseModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    task: Literal["title_hook_suggestions", "thumbnail_copy_suggestions"] = "title_hook_suggestions"
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    prompt: str = Field(min_length=1)
    response_schema: dict[str, Any] = Field(alias="responseSchema")
    images: list[str] = Field(default_factory=list, max_length=4)
    model: str | None = Field(default=None, min_length=1, max_length=64)
    thread_id: str | None = Field(default=None, alias="threadId")
    thread_scope: str = Field(min_length=1, max_length=128, alias="threadScope")

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class _BridgeError(BaseModel):
    code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9_]+$",
    )
    message: str = Field(min_length=1, max_length=300)

    model_config = ConfigDict(extra="ignore")


class _BridgeHostResponse(BaseModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    state: Literal["queued", "running", "ready", "completed", "failed"]
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        alias="threadId",
    )
    output: dict[str, Any] | None = None
    error: _BridgeError | None = None

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def validate_state_payload(self) -> "_BridgeHostResponse":
        if self.state in {"ready", "completed"} and self.output is None:
            raise ValueError("ready host response requires output")
        if self.state == "failed" and self.error is None:
            raise ValueError("failed host response requires error")
        return self


class _BridgeStatus(BaseModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    state: Literal["ready", "error", "stopped"]
    updated_at: datetime = Field(alias="updatedAt")
    request_id: str | None = Field(default=None, max_length=100, alias="requestId")
    request_state: Literal["idle", "processing"] | None = Field(
        default=None,
        alias="requestState",
    )

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @model_validator(mode="after")
    def validate_status(self) -> "_BridgeStatus":
        if self.updated_at.tzinfo is None:
            raise ValueError("updatedAt must include a timezone")
        if self.request_state == "processing" and not self.request_id:
            raise ValueError("processing bridge status requires requestId")
        return self


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)
    return path


class CodexTitleHookSuggestionGenerator:
    task = "title_hook_suggestions"
    system_prompt = SYSTEM_PROMPT
    response_schema = TITLE_HOOK_GENERATION_SCHEMA

    def parse_output(self, output: dict[str, Any]) -> Any:
        return GeneratedTitleHookSuggestionResult.model_validate(output).to_compatible()

    def __init__(
        self,
        *,
        storage_root: str | Path,
        job_id: str,
        clip_id: str,
        model: str | None = None,
        thread_id: str | None = None,
        timeout_seconds: float = DEFAULT_CODEX_RESPONSE_TIMEOUT_SECONDS,
        poll_seconds: float = DEFAULT_CODEX_RESPONSE_POLL_SECONDS,
        sleep_func: Callable[[float], None] = time.sleep,
        monotonic_func: Callable[[], float] = time.monotonic,
        wall_time_func: Callable[[], float] = time.time,
    ) -> None:
        self.storage_root = Path(storage_root).resolve()
        self.job_id = job_id
        self.clip_id = clip_id
        normalized_model = model.strip() if isinstance(model, str) else ""
        self.model = (
            normalized_model
            if normalized_model
            and normalized_model not in {"auto", "codex-default", "default"}
            else None
        )
        self.thread_id = thread_id
        self.last_thread_id = thread_id
        self.timeout_seconds = max(0.01, float(timeout_seconds))
        self.poll_seconds = min(max(0.01, float(poll_seconds)), 5.0)
        self.sleep_func = sleep_func
        self.monotonic_func = monotonic_func
        self.wall_time_func = wall_time_func

    @property
    def bridge_root(self) -> Path:
        return self.storage_root / BRIDGE_DIRNAME

    def request_path(self, request_id: str) -> Path:
        return self.bridge_root / BRIDGE_REQUESTS_DIRNAME / f"{request_id}.json"

    def response_path(self, request_id: str) -> Path:
        return self.bridge_root / BRIDGE_RESPONSES_DIRNAME / f"{request_id}.json"

    @property
    def status_path(self) -> Path:
        return self.bridge_root / BRIDGE_STATUS_FILENAME

    def _relative_image_paths(self, frame_paths: Sequence[Path]) -> list[str]:
        relative_paths: list[str] = []
        for raw_path in frame_paths[:4]:
            path = Path(raw_path).resolve()
            try:
                relative = path.relative_to(self.storage_root)
            except ValueError as exc:
                raise CodexTitleHookSuggestionError(
                    "codex_title_hook_image_outside_storage",
                    "representative frame is outside storage",
                ) from exc
            relative_paths.append(relative.as_posix())
        return relative_paths

    def _read_status(self) -> _BridgeStatus | None:
        try:
            if not self.status_path.is_file():
                return None
            if self.status_path.stat().st_size > MAX_BRIDGE_STATUS_BYTES:
                return None
            return _BridgeStatus.model_validate_json(
                self.status_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError):
            return None

    def _bridge_unavailable_reason(
        self,
        *,
        request_id: str,
        request_created_at: float,
        elapsed_seconds: float,
    ) -> str | None:
        status = self._read_status()
        if status is None:
            return (
                "status_missing"
                if elapsed_seconds >= BRIDGE_REQUEST_CLAIM_GRACE_SECONDS
                else None
            )
        status_updated_at = status.updated_at.astimezone(UTC).timestamp()
        wall_time = self.wall_time_func()
        if status_updated_at > wall_time + BRIDGE_STATUS_FUTURE_TOLERANCE_SECONDS:
            return (
                "status_clock_invalid"
                if elapsed_seconds >= BRIDGE_REQUEST_CLAIM_GRACE_SECONDS
                else None
            )
        if status.state in {"error", "stopped"}:
            return f"status_{status.state}"
        if status.request_state == "processing":
            if wall_time - status_updated_at > BRIDGE_STATUS_STALE_SECONDS:
                return "status_stale"
            return None
        idle_reference = max(request_created_at, status_updated_at)
        if wall_time - idle_reference >= BRIDGE_REQUEST_CLAIM_GRACE_SECONDS:
            return f"request_unclaimed:{request_id}"
        return None

    def _read_response(self, request_id: str) -> TitleHookSuggestionResult | None:
        path = self.response_path(request_id)
        try:
            if path.stat().st_size > MAX_BRIDGE_RESPONSE_BYTES:
                raise CodexTitleHookSuggestionError(
                    "codex_title_hook_response_too_large",
                    "Codex title/hook response is too large",
                )
            host_response = _BridgeHostResponse.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except CodexTitleHookSuggestionError:
            raise
        except (OSError, ValidationError, ValueError) as exc:
            raise CodexTitleHookSuggestionError(
                "codex_title_hook_response_invalid",
                "Codex title/hook response is invalid",
            ) from exc
        if host_response.request_id != request_id:
            raise CodexTitleHookSuggestionError(
                "codex_title_hook_request_mismatch",
                "Codex title/hook response request does not match",
            )
        if host_response.state in {"queued", "running"}:
            return None
        if host_response.state == "failed":
            code = host_response.error.code if host_response.error is not None else "host_failed"
            raise CodexTitleHookSuggestionError(
                f"codex_title_hook_{code}",
                "Codex title/hook generation failed",
            )
        self.last_thread_id = host_response.thread_id or self.thread_id
        try:
            return self.parse_output(host_response.output)
        except ValidationError as exc:
            raise CodexTitleHookSuggestionError(
                "codex_title_hook_output_invalid",
                "Codex title/hook output does not match the contract",
            ) from exc

    def generate(
        self,
        payload: dict[str, Any],
        frame_paths: Sequence[Path],
    ) -> TitleHookSuggestionResult:
        request_id = uuid4().hex
        request_created_at = self.wall_time_func()
        prompt_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        envelope = _BridgeEnvelope(
            task=self.task,
            requestId=request_id,
            prompt=f"{self.system_prompt}\n\n入力JSON:\n{prompt_payload}",
            responseSchema=self.response_schema,
            images=self._relative_image_paths(frame_paths),
            model=self.model,
            threadId=self.thread_id,
            threadScope=f"{self.job_id}:{self.clip_id}",
        )
        _write_json_atomic(
            self.request_path(request_id),
            envelope.model_dump(by_alias=True, mode="json", exclude_none=True),
        )

        started_at = self.monotonic_func()
        unavailable_since: float | None = None
        while True:
            if self.response_path(request_id).is_file():
                result = self._read_response(request_id)
                if result is not None:
                    return result
            now = self.monotonic_func()
            elapsed = now - started_at
            if elapsed >= self.timeout_seconds:
                raise CodexTitleHookSuggestionError(
                    "codex_title_hook_timeout",
                    "Codex title/hook response timed out",
                )
            unavailable_reason = self._bridge_unavailable_reason(
                request_id=request_id,
                request_created_at=request_created_at,
                elapsed_seconds=elapsed,
            )
            if unavailable_reason is None:
                unavailable_since = None
            else:
                if unavailable_since is None:
                    unavailable_since = now
                if now - unavailable_since >= BRIDGE_UNAVAILABLE_CONFIRMATION_SECONDS:
                    raise CodexTitleHookSuggestionError(
                        "codex_title_hook_bridge_unavailable",
                        f"Codex title/hook bridge is unavailable ({unavailable_reason})",
                    )
            self.sleep_func(
                min(
                    self.poll_seconds,
                    max(0.01, self.timeout_seconds - elapsed),
                )
            )
