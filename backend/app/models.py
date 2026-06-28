from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.utcnow()


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
