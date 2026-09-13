import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)


HEATMAP_SCHEMA_VERSION = 1
HEATMAP_SIDECAR_SUFFIX = ".heatmap.json"
DEFAULT_DURATION_TOLERANCE_SECONDS = 2.0
DURATION_TOLERANCE_RATIO = 0.001
READ_CHUNK_SIZE = 1024 * 1024


class HeatmapSidecarError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _ContractModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class HeatmapSource(_ContractModel):
    name: Literal["youtube_most_replayed"]
    video_id: StrictStr = Field(min_length=1)
    fetched_at: StrictStr = Field(min_length=1)
    extractor: Literal["yt-dlp"]
    extractor_version: StrictStr = Field(min_length=1)

    @field_validator("video_id", "extractor_version")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("fetched_at")
    @classmethod
    def validate_utc_timestamp(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("must be an ISO 8601 datetime") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            raise ValueError("must be a UTC datetime")
        return value


class HeatmapMedia(_ContractModel):
    filename: StrictStr = Field(min_length=1)
    sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: StrictInt = Field(ge=0)

    @field_validator("filename")
    @classmethod
    def validate_plain_filename(cls, value: str) -> str:
        if Path(value).name != value:
            raise ValueError("must be a filename without a path")
        return value


class HeatmapSegment(_ContractModel):
    start_time: StrictFloat = Field(ge=0, allow_inf_nan=False)
    end_time: StrictFloat = Field(ge=0, allow_inf_nan=False)
    value: StrictFloat = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_interval(self) -> "HeatmapSegment":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")
        return self


class HeatmapSidecar(_ContractModel):
    schema_version: StrictInt
    source: HeatmapSource
    media: HeatmapMedia
    duration_seconds: StrictFloat | None = Field(ge=0, allow_inf_nan=False)
    heatmap_available: StrictBool
    heatmap: list[HeatmapSegment]

    @model_validator(mode="after")
    def validate_contract(self) -> "HeatmapSidecar":
        if self.schema_version != HEATMAP_SCHEMA_VERSION:
            raise ValueError("schema_version must be 1")
        if self.heatmap_available != bool(self.heatmap):
            raise ValueError("heatmap_available must match whether heatmap is non-empty")
        intervals = [(segment.start_time, segment.end_time) for segment in self.heatmap]
        if intervals != sorted(intervals):
            raise ValueError("heatmap intervals must be ordered by start_time and end_time")
        return self


@dataclass(frozen=True)
class HeatmapLoadResult:
    segments: list[HeatmapSegment]
    summary: dict[str, object]


def heatmap_sidecar_filename(media_filename: str) -> str:
    return f"{media_filename}{HEATMAP_SIDECAR_SUFFIX}"


def heatmap_sidecar_path(media_path: Path) -> Path:
    return media_path.with_name(heatmap_sidecar_filename(media_path.name))


def duration_tolerance_seconds(actual_duration: float) -> float:
    return max(DEFAULT_DURATION_TOLERANCE_SECONDS, abs(actual_duration) * DURATION_TOLERANCE_RATIO)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON number: {value}")


def parse_heatmap_sidecar(raw: bytes) -> HeatmapSidecar:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise HeatmapSidecarError(
            "heatmap_utf8_bom_not_allowed",
            "heatmap sidecar must be UTF-8 without BOM",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HeatmapSidecarError(
            "heatmap_utf8_invalid",
            "heatmap sidecar must be valid UTF-8",
        ) from exc
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HeatmapSidecarError(
            "heatmap_json_invalid",
            "heatmap sidecar must contain valid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise HeatmapSidecarError(
            "heatmap_contract_invalid",
            "heatmap sidecar root must be an object",
        )
    try:
        return HeatmapSidecar.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ())) or "root"
        raise HeatmapSidecarError(
            "heatmap_contract_invalid",
            f"heatmap sidecar contract is invalid at {location}",
        ) from exc


def validate_heatmap_binding(
    sidecar: HeatmapSidecar,
    *,
    expected_filename: str,
    actual_size_bytes: int,
    actual_sha256: str,
    actual_duration: float | None = None,
) -> None:
    if sidecar.media.filename != expected_filename:
        raise HeatmapSidecarError(
            "heatmap_media_filename_mismatch",
            "heatmap sidecar media.filename does not match the uploaded video filename",
        )
    if sidecar.media.size_bytes != actual_size_bytes:
        raise HeatmapSidecarError(
            "heatmap_media_size_mismatch",
            "heatmap sidecar media.size_bytes does not match the uploaded video",
        )
    if sidecar.media.sha256 != actual_sha256:
        raise HeatmapSidecarError(
            "heatmap_media_sha256_mismatch",
            "heatmap sidecar media.sha256 does not match the uploaded video",
        )
    if actual_duration is None or sidecar.duration_seconds is None:
        return
    if not math.isfinite(actual_duration) or actual_duration < 0:
        raise HeatmapSidecarError(
            "heatmap_actual_duration_invalid",
            "video duration is unavailable for heatmap validation",
        )
    tolerance = duration_tolerance_seconds(actual_duration)
    if abs(sidecar.duration_seconds - actual_duration) > tolerance:
        raise HeatmapSidecarError(
            "heatmap_duration_mismatch",
            "heatmap sidecar duration_seconds does not match the uploaded video",
        )


def validate_heatmap_sidecar(
    raw: bytes,
    *,
    expected_filename: str,
    actual_size_bytes: int,
    actual_sha256: str,
    actual_duration: float | None = None,
) -> HeatmapSidecar:
    sidecar = parse_heatmap_sidecar(raw)
    validate_heatmap_binding(
        sidecar,
        expected_filename=expected_filename,
        actual_size_bytes=actual_size_bytes,
        actual_sha256=actual_sha256,
        actual_duration=actual_duration,
    )
    return sidecar


def write_heatmap_sidecar(sidecar: HeatmapSidecar, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(
            json.dumps(
                sidecar.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, output_path)
    finally:
        temp_path.unlink(missing_ok=True)
    return output_path


def _fingerprint_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as stream:
        while chunk := stream.read(READ_CHUNK_SIZE):
            size_bytes += len(chunk)
            digest.update(chunk)
    return size_bytes, digest.hexdigest()


def _summary(
    status: str,
    *,
    applied: bool,
    fallback_used: bool,
    fallback_reason: str | None,
    sidecar: HeatmapSidecar | None = None,
) -> dict[str, object]:
    return {
        "schema_version": HEATMAP_SCHEMA_VERSION,
        "status": status,
        "applied": applied,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "heatmap_available": sidecar.heatmap_available if sidecar is not None else False,
        "segment_count": len(sidecar.heatmap) if sidecar is not None else 0,
        "source_video_id": sidecar.source.video_id if sidecar is not None else None,
        "source_fetched_at": sidecar.source.fetched_at if sidecar is not None else None,
        "value_semantics": "relative_in_video_0_to_1_not_view_count",
    }


def load_heatmap_for_video(
    media_path: Path,
    *,
    original_filename: str,
    actual_duration: float,
    max_sidecar_size_bytes: int,
    sidecar_path: Path | None = None,
) -> HeatmapLoadResult:
    sidecar_path = sidecar_path or heatmap_sidecar_path(media_path)
    if not sidecar_path.is_file():
        return HeatmapLoadResult(
            segments=[],
            summary=_summary(
                "not_provided",
                applied=False,
                fallback_used=True,
                fallback_reason="heatmap_sidecar_not_provided",
            ),
        )

    try:
        if sidecar_path.stat().st_size > max_sidecar_size_bytes:
            raise HeatmapSidecarError(
                "heatmap_sidecar_too_large",
                "heatmap sidecar exceeds the configured size limit",
            )
        size_bytes, sha256_hex = _fingerprint_file(media_path)
        sidecar = validate_heatmap_sidecar(
            sidecar_path.read_bytes(),
            expected_filename=original_filename,
            actual_size_bytes=size_bytes,
            actual_sha256=sha256_hex,
            actual_duration=actual_duration,
        )
    except (HeatmapSidecarError, OSError) as exc:
        reason = exc.code if isinstance(exc, HeatmapSidecarError) else "heatmap_sidecar_read_failed"
        return HeatmapLoadResult(
            segments=[],
            summary=_summary(
                "invalid_fallback",
                applied=False,
                fallback_used=True,
                fallback_reason=reason,
            ),
        )

    if not sidecar.heatmap_available:
        return HeatmapLoadResult(
            segments=[],
            summary=_summary(
                "unavailable",
                applied=False,
                fallback_used=True,
                fallback_reason="heatmap_unavailable",
                sidecar=sidecar,
            ),
        )
    return HeatmapLoadResult(
        segments=list(sidecar.heatmap),
        summary=_summary(
            "applied",
            applied=True,
            fallback_used=False,
            fallback_reason=None,
            sidecar=sidecar,
        ),
    )
