"""Immutable versions and append-only decisions, with one mutable active pointer."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.intelligence.common import now


class ChoicePolicyHead(Base):
    __tablename__ = "choice_policy_heads"
    __table_args__ = (UniqueConstraint("channel_id", "character", "format"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    character: Mapped[str] = mapped_column(String(200))
    format: Mapped[str] = mapped_column(String(12))
    current_id: Mapped[str] = mapped_column(String(48))


class ChoicePolicyVersion(Base):
    __tablename__ = "choice_policy_versions"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey("choice_policy_heads.id"), index=True)
    previous_id: Mapped[str | None] = mapped_column(String(48))
    values: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChoicePolicyDecision(Base):
    __tablename__ = "choice_policy_decisions"
    __table_args__ = (UniqueConstraint("policy_id", "analysis_id"),)
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey("choice_policy_heads.id"), index=True)
    analysis_id: Mapped[str] = mapped_column(String(48))
    action: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(48))
    from_id: Mapped[str] = mapped_column(String(48))
    to_id: Mapped[str] = mapped_column(String(48))
    evidence: Mapped[dict | None] = mapped_column(JSON)
    evidence_expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


@event.listens_for(ChoicePolicyVersion, "before_update")
def immutable_version(mapper, connection, target):
    raise ValueError("POLICY_VERSION_IS_IMMUTABLE")
