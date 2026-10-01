from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_audio: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    jobs: Mapped[list["Job"]] = relationship(back_populates="video")
    exports: Mapped[list["ExportItem"]] = relationship(back_populates="video")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    current_step: Mapped[str] = mapped_column(String(255), nullable=False, default="Queued")
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    video: Mapped[Video] = relationship(back_populates="jobs")
    exports: Mapped[list["ExportItem"]] = relationship(back_populates="job")


class AppPreference(Base):
    __tablename__ = "app_preferences"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class CharacterAsset(Base):
    """Preset images retained independently of job and preset-list cleanup."""

    __tablename__ = "character_assets"
    __table_args__ = (
        UniqueConstraint("preset_id", "emotion", "slot"),
        CheckConstraint("slot >= 1 AND slot <= 5"),
        CheckConstraint("emotion IN ('joy', 'anger', 'sorrow', 'fun')"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    preset_id: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    emotion: Mapped[str] = mapped_column(String(16), nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    face_box: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    has_alpha: Mapped[bool] = mapped_column(Boolean, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class CharacterAssetCandidate(Base):
    __tablename__ = "character_asset_candidates"
    __table_args__ = (
        UniqueConstraint("preset_id", "video_id", "source_second"),
        CheckConstraint("status IN ('pending', 'adopted', 'rejected')"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    preset_id: Mapped[str] = mapped_column(String(48), index=True)
    video_id: Mapped[str] = mapped_column(String(40), index=True)
    source_second: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text)
    face_box: Mapped[dict[str, float]] = mapped_column(JSON)
    suggested_emotion: Mapped[str | None] = mapped_column(String(16), nullable=True)
    usable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    issues: Mapped[list[str]] = mapped_column(JSON, default=list)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    same_character: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    has_alpha: Mapped[bool] = mapped_column(Boolean)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class CharacterAssetHarvest(Base):
    """Persistent queue/progress information, including a scan that finds zero frames."""

    __tablename__ = "character_asset_harvests"
    __table_args__ = (UniqueConstraint("preset_id", "video_id"),)
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    preset_id: Mapped[str] = mapped_column(String(48), index=True)
    video_id: Mapped[str] = mapped_column(String(40), index=True)
    state: Mapped[str] = mapped_column(String(16), default="queued")
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ExportItem(Base):
    __tablename__ = "export_items"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), nullable=False, index=True)
    candidate_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    video_path: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    job: Mapped[Job] = relationship(back_populates="exports")
    video: Mapped[Video] = relationship(back_populates="exports")


class SourceClipUsage(Base):
    """Small, permanent source-time ledger; deliberately independent of job cleanup."""

    __tablename__ = "source_clip_usage"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(40), nullable=False)
    clip_type: Mapped[str] = mapped_column(String(16), nullable=False)
    start: Mapped[float] = mapped_column(Float, nullable=False)
    end: Mapped[float] = mapped_column(Float, nullable=False)
    source_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class ClipRejection(Base):
    """Append-only human decisions, independent of media and job cleanup."""

    __tablename__ = "clip_rejections"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    video_id: Mapped[str] = mapped_column(String(40), nullable=False)
    source_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    clip_plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    clip_id: Mapped[str] = mapped_column(String(40), nullable=False)
    clip_type: Mapped[str] = mapped_column(String(16), nullable=False)
    start: Mapped[float] = mapped_column(Float, nullable=False)
    end: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
