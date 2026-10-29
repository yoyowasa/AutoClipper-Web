from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_MAX_UPLOAD_SIZE_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_MAX_HEATMAP_SIDECAR_SIZE_BYTES = 5 * 1024 * 1024
DEFAULT_BACKEND_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
DEFAULT_STORAGE_LIMIT_BYTES = 50 * 1024 * 1024 * 1024
DEFAULT_STORAGE_MIN_FREE_PERCENT = 20.0
DEFAULT_STORAGE_TERMINAL_RETENTION_DAYS = 7
DEFAULT_STORAGE_ORPHAN_RETENTION_HOURS = 24


class Settings(BaseSettings):
    app_name: str = "AutoClipper API"
    backend_cors_origins: str = DEFAULT_BACKEND_CORS_ORIGINS
    database_url: str = "sqlite:///../storage/autoclipper.db"
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "autoclipper"
    rq_intelligence_queue_name: str = Field(default="autoclipper-intelligence", min_length=1)
    autoclipper_runtime_profile: Literal["cpu", "gpu"] = "cpu"
    storage_root: str = "../storage"
    youtube_oauth_redirect_uri: str = "http://localhost:8000/api/intelligence/oauth/callback"
    youtube_sync_budget_seconds: int = Field(default=120, ge=30, le=300)
    youtube_automation_enabled: bool = True
    youtube_auto_sync_hour_utc: int = Field(default=3, ge=0, le=23)
    youtube_auto_analysis_weekday: int = Field(default=0, ge=0, le=6)
    youtube_maintenance_interval_seconds: int = Field(default=60, ge=30, le=3600)
    youtube_derived_allowed: bool = True
    youtube_extended_storage: bool = True
    youtube_policy_reviewed_at: str = "2026-10-15"
    youtube_policy_reference: str = "https://developers.google.com/youtube/terms/derived-metrics-policy"
    source_library_root: str = "../youtube"
    max_upload_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES
    max_heatmap_sidecar_size_bytes: int = DEFAULT_MAX_HEATMAP_SIDECAR_SIZE_BYTES
    storage_limit_bytes: int = Field(default=DEFAULT_STORAGE_LIMIT_BYTES, gt=0)
    storage_min_free_percent: float = Field(
        default=DEFAULT_STORAGE_MIN_FREE_PERCENT,
        ge=0,
        le=100,
    )
    storage_terminal_retention_days: int = Field(
        default=DEFAULT_STORAGE_TERMINAL_RETENTION_DAYS,
        ge=0,
    )
    storage_orphan_retention_hours: int = Field(
        default=DEFAULT_STORAGE_ORPHAN_RETENTION_HOURS,
        ge=0,
    )
    storage_cleanup_on_upload: bool = False
    allowed_video_extensions: str = ".mp4,.mov,.mkv,.webm"
    allowed_video_content_types: str = "video/mp4,video/quicktime,video/x-matroska,video/webm"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def distinct_worker_queues(self):
        if not self.rq_intelligence_queue_name.strip() or self.rq_intelligence_queue_name == self.rq_queue_name:
            raise ValueError("Intelligence queue must be nonempty and separate from the media queue")
        return self

    @field_validator("youtube_oauth_redirect_uri")
    @classmethod
    def validate_youtube_loopback(cls, value: str) -> str:
        url = urlsplit(value)
        if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                or url.username or url.password or not url.port or url.query or url.fragment
                or url.path != "/api/intelligence/oauth/callback"):
            raise ValueError("YouTube OAuth redirect must be a loopback callback with an explicit port")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def upload_extensions(self) -> set[str]:
        return {
            extension.strip().lower()
            for extension in self.allowed_video_extensions.split(",")
            if extension.strip()
        }

    @property
    def upload_content_types(self) -> set[str]:
        return {
            content_type.strip().lower()
            for content_type in self.allowed_video_content_types.split(",")
            if content_type.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
