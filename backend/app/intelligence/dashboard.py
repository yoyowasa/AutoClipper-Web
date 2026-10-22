"""Read-only dashboard; page navigation never triggers Google or Codex requests."""
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from app.intelligence.dashboard_reports import (
    derived_window, duration_band, first7_report, fresh_video, missing_report, native_window, valid_stat,
)
from app.intelligence.dashboard_schemas import DashboardRead, DashboardVideoRead
from app.intelligence.models import ProductionLink, SyncRun, VideoDailyStat, YouTubeVideo
from app.intelligence.production_catalog import read_families
from app.intelligence.production_dimensions import attributes, group_id


def dashboard_data(db, paths, config, channel_id, format, stamp):
    batch = db.scalar(select(SyncRun).where(SyncRun.channel_id == channel_id, SyncRun.status.in_(["success", "partial"]))
                      .order_by(SyncRun.queued_at.desc(), SyncRun.id.desc()).limit(1))
    last = batch.last_report_date if batch else None
    all_videos = list(db.scalars(select(YouTubeVideo).where(YouTubeVideo.channel_id == channel_id)
                                .order_by(YouTubeVideo.published_at.desc(), YouTubeVideo.id)))
    available = [video for video in all_videos if fresh_video(video, stamp)]
    selected = [video for video in available if format == "all" or video.format == format]
    rows = [row for row in db.scalars(select(VideoDailyStat).where(VideoDailyStat.channel_id == channel_id,
            VideoDailyStat.expires_at > stamp)) if valid_stat(row, config, stamp)]
    per_video = defaultdict(list)
    for row in rows:
        per_video[row.video_id].append(row)
    families, _ = read_families(paths)
    links = {link.youtube_video_id: link for link in db.scalars(select(ProductionLink).where(
        ProductionLink.youtube_video_id.in_([video.id for video in selected])))}
    videos = []
    for video in selected:
        current = (native_window(per_video[video.id], "video_period", last - timedelta(days=27), last)
                   if last else missing_report("NO_SYNC"))
        entry = DashboardVideoRead(id=video.id, title=video.title, publishedAt=video.published_at,
            durationSeconds=video.duration_seconds, format=video.format, durationBand=duration_band(video.duration_seconds, video.format),
            current=current, first7=first7_report(video, per_video[video.id], last))
        link = links.get(video.id)
        family = families.get(link.record_family_id) if link else None
        if family and not family.ambiguous and family.latest.recordId == link.record_id:
            record = family.latest
            entry.production = record.model_dump(mode="json", exclude={"source", "jobId"})
            entry.aggregateGroupIds = [group_id(record.characterPresetName or "未設定", record.type, key, value)
                                       for key, value in attributes(record).items()]
        else:
            entry.productionMissing = "RECORD_UNAVAILABLE" if link else "NOT_LINKED"
        videos.append(entry)
    current = previous = missing_report("NO_SYNC")
    daily = []
    if last:
        start, previous_start, previous_end = last - timedelta(days=27), last - timedelta(days=55), last - timedelta(days=28)
        # Match the latest batch for channel reports; never silently reuse an older window.
        channel_rows = [row for row in per_video[None] if row.sync_run_id == batch.id]
        if format == "all":
            current = native_window(channel_rows, "current", start, last)
            previous = native_window(channel_rows, "previous", previous_start, previous_end)
        elif config.youtube_derived_allowed:
            current = derived_window(selected, rows, start, last)
            previous = derived_window(selected, rows, previous_start, previous_end)
        else:
            current = previous = missing_report("DERIVED_NOT_ALLOWED", source="independent_aggregation")
        for offset in range(56):
            day = previous_start + timedelta(days=offset)
            daily.append(native_window(channel_rows, "daily", day, day) if format == "all" else
                         derived_window(selected, rows, day, day) if config.youtube_derived_allowed else
                         missing_report("DERIVED_NOT_ALLOWED", day, day, source="independent_aggregation"))
    return DashboardRead(channelId=channel_id, format=format, lastReportDate=last, syncRunId=batch.id if batch else None,
        current=current, previous=previous, daily=daily, videos=videos, excludedMetadataCount=len(all_videos) - len(available),
        unknownFormatCount=sum(video.format == "unknown" for video in available),
        scopeNote="全体はYouTube公式の期間値。形式別は保存済み・メタデータ有効な動画の日次値の独自集計です。"
                  "形式不明・未取得・削除済みの動画を含まないため、チャンネル全体とは一致しない場合があります。")


def evidence_video_ids(snapshot):
    result = {}
    for video in snapshot.get("videos", []):
        for report in video.get("reports", []):
            for metric in report.get("values", {}):
                result[report["id"] + ":" + metric] = [video["id"]]
        if video.get("production"):
            result[video["production"]["id"]] = [video["id"]]
    # Older snapshots used the expanded evidence map.
    for key, item in snapshot.get("evidence", {}).items():
        if item.get("video_id"):
            result[key] = [item["video_id"]]
    for group in snapshot.get("production_aggregates", {}).get("groups", []):
        result[group["id"]] = group["video_ids"]
    return result
