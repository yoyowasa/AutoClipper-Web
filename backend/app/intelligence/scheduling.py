"""Bounded daily sync / weekly analysis from intelligence-worker maintenance."""
from datetime import timedelta

from sqlalchemy import select

from app.intelligence.analysis_runner import mark_analysis_failed
from app.intelligence.job_claims import ChannelClaimError, claim_channel_run
from app.intelligence.models import ChannelConnection
from app.intelligence.queue import enqueue_channel_analysis, enqueue_youtube_sync
from app.intelligence.sync import mark_sync_failed


def schedule_slots(stamp, config):
    day = stamp.replace(hour=config.youtube_auto_sync_hour_utc, minute=0, second=0, microsecond=0)
    if day > stamp:
        day -= timedelta(days=1)
    week = day - timedelta(days=(day.weekday() - config.youtube_auto_analysis_weekday) % 7)
    return day, week


def schedule_due_channels(db, config, stamp, *, enqueue_sync=None, enqueue_analysis=None):
    if not config.youtube_automation_enabled:
        return []
    enqueue_sync = enqueue_sync or enqueue_youtube_sync
    enqueue_analysis = enqueue_analysis or enqueue_channel_analysis
    day, week = schedule_slots(stamp, config)
    channels = list(db.scalars(select(ChannelConnection.channel_id).where(ChannelConnection.status == "connected")))
    scheduled = []
    for channel_id in channels:
        # Weekly analysis performs the daily sync itself. Do not enqueue two
        # independent jobs which would race over the same channel's evidence.
        for kind, slot in (("analysis", week), ("sync", day)):
            if kind == "analysis" and not config.youtube_derived_allowed:
                continue
            try:
                run = claim_channel_run(db, channel_id, kind, stamp, slot=slot, sync_before="always")
            except ChannelClaimError:
                break  # A manual/scheduled run owns this channel, or OAuth expired.
            if run is None:
                continue
            try:
                (enqueue_analysis if kind == "analysis" else enqueue_sync)(run.id)
            except Exception:
                (mark_analysis_failed if kind == "analysis" else mark_sync_failed)(db, run.id, "QUEUE_FAILED")
            scheduled.append(run.id)
            break
    return scheduled
