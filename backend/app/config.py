from functools import lru_cache
from typing import Literal

from pydantic import Field
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
    autoclipper_runtime_profile: Literal["cpu", "gpu"] = "cpu"
    storage_root: str = "../storage"
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
