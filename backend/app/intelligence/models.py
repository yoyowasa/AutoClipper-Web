from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.intelligence.common import now


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(24), unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    metadata_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ProductionLink(Base):
    __tablename__ = "production_links"
    __table_args__ = (CheckConstraint("mode IN ('auto', 'manual', 'manual_unlinked')"),
                     CheckConstraint("(mode = 'manual_unlinked' AND youtube_video_id IS NULL) OR "
                                     "(mode IN ('auto', 'manual') AND youtube_video_id IS NOT NULL)"))
    record_family_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(100))
    youtube_video_id: Mapped[str | None] = mapped_column(ForeignKey("youtube_videos.id"), unique=True)
    mode: Mapped[str] = mapped_column(String(20))
    linked_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChannelConnection(Base):
    __tablename__ = "channel_connections"
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="connected")
    error_code: Mapped[str | None] = mapped_column(String(40))
    verified_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AnalysisRun(Base):
    __tablename__ = "channel_analysis_runs"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    active_channel_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    sync_before: Mapped[str] = mapped_column(String(8), default="auto")
    sync_run_id: Mapped[str | None] = mapped_column(String(40))
    requested_model: Mapped[str] = mapped_column(String(64), default="gpt-6-astra")
    requested_effort: Mapped[str] = mapped_column(String(16), default="high")
    request_id: Mapped[str | None] = mapped_column(String(32))
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(40))
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    review: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    validation: Mapped["AnalysisValidationDiagnostics | None"] = relationship(cascade="all, delete-orphan", uselist=False)


class AnalysisValidationDiagnostics(Base):
    """Content-free diagnostics; create_all also adds this to existing databases."""
    __tablename__ = "channel_analysis_validation"
    run_id: Mapped[str] = mapped_column(ForeignKey("channel_analysis_runs.id"), primary_key=True)
    report: Mapped[dict[str, Any]] = mapped_column(JSON)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    # NULL for finished runs; a unique channel claim for queued/running work.
    active_channel_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(40))
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(default=False)
    requested_start: Mapped[date | None] = mapped_column(Date)
    requested_end: Mapped[date | None] = mapped_column(Date)
    last_report_date: Mapped[date | None] = mapped_column(Date)
    missing_reports: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class YouTubeVideo(Base):
    __tablename__ = "youtube_videos"
    id: Mapped[str] = mapped_column(String(11), primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    title: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_seconds: Mapped[float | None] = mapped_column()
    format: Mapped[str] = mapped_column(String(16), default="unknown")
    format_source: Mapped[str] = mapped_column(String(32), default="unknown")
    metadata_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    availability: Mapped[str] = mapped_column(String(32), default="available")
    public_statistics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    public_observed_at: Mapped[datetime | None] = mapped_column(DateTime)


class VideoDailyStat(Base):
    """Native day/video and period reports: never re-average daily averages."""

    __tablename__ = "video_daily_stats"
    __table_args__ = (UniqueConstraint("channel_id", "kind", "dimension_key", "period_start", "period_end"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("youtube_videos.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"))
    kind: Mapped[str] = mapped_column(String(24))
    dimension_key: Mapped[str] = mapped_column(String(100))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    report_timezone: Mapped[str] = mapped_column(String(32), default="America/Los_Angeles")
    source: Mapped[str] = mapped_column(String(32), default="youtube_analytics")
    definition_version: Mapped[str] = mapped_column(String(32), default="youtube-native-2026-10-v1")
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    missing_reasons: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
