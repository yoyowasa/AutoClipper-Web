from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AutoClipper API"
    backend_cors_origins: str = "http://localhost:3000"
    database_url: str = "sqlite:///../storage/autoclipper.db"
    redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "autoclipper"
    storage_root: str = "../storage"
    max_upload_size_bytes: int = 536_870_912
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
