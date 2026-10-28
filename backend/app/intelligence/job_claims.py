"""Serialize manual/scheduled channel work with the existing SQLite row and run claims."""
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select, update

from app.intelligence.models import AnalysisRun, Channel, ChannelConnection, SyncRun


class ChannelClaimError(ValueError):
    pass


def claim_channel_run(db, channel_id, kind, stamp, *, sync_before="auto", slot=None):
    # SQLite ignores SELECT FOR UPDATE. This no-op UPDATE takes its write lock
    # before checking both run tables, without changing channel metadata.
    result = db.execute(update(Channel).where(Channel.id == channel_id).values(id=Channel.id))
    if result.rowcount != 1:
        db.rollback()
        raise ChannelClaimError("CHANNEL_NOT_FOUND")
    connection = db.get(ChannelConnection, channel_id)
    if not connection or connection.status != "connected":
        db.rollback()
        raise ChannelClaimError("RECONNECT_REQUIRED")
    for model in (SyncRun, AnalysisRun):
        if db.scalar(select(model.id).where(model.active_channel_id == channel_id)):
            db.rollback()
            raise ChannelClaimError("CHANNEL_BUSY")
    model = AnalysisRun if kind == "analysis" else SyncRun
    if slot is not None and db.scalar(select(model.id).where(model.channel_id == channel_id, model.queued_at >= slot)):
        db.rollback()
        return None
    run = model(id=("analysis_" if kind == "analysis" else "sync_") + uuid4().hex,
                channel_id=channel_id, active_channel_id=channel_id, queued_at=stamp)
    if kind == "analysis":
        run.sync_before, run.expires_at = sync_before, stamp + timedelta(days=30)
    db.add(run)
    db.commit()
    return run
