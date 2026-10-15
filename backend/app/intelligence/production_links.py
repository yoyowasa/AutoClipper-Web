"""One-to-one title matching and persistent manual choices."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence.common import now
from app.intelligence.models import Channel, ProductionLink, YouTubeVideo
from app.intelligence.production_catalog import normalize_title, read_families
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths

logger = logging.getLogger(__name__)


def own_videos(db: Session) -> list[YouTubeVideo]:
    # channels contains only identities verified by mine=true during OAuth.
    return list(db.scalars(select(YouTubeVideo).join(Channel).order_by(YouTubeVideo.id)))


def matching_graph(families, videos):
    candidates = {id: [] for id in families}
    reverse = {video.id: [] for video in videos}
    for id, family in families.items():
        titles = family.titles if family.ambiguous else (normalize_title(family.latest.publicationTitle),)
        for video in videos:
            if (video.availability == "available" and video.published_at is not None and video.title
                    and normalize_title(video.title) in titles
                    and video.published_at >= family.created_at):
                if not family.ambiguous:
                    candidates[id].append(video.id)
                reverse[video.id].append(id)
    return candidates, reverse


def reconcile(db: Session, paths: StoragePaths) -> None:
    """Caller owns the storage lock and transaction; this function never commits."""
    families, _issues = read_families(paths)
    videos = own_videos(db)
    candidates, reverse = matching_graph(families, videos)
    existing = {link.record_family_id: link for link in db.scalars(select(ProductionLink))}
    reserved = {link.youtube_video_id for link in existing.values() if link.mode == "manual"}
    desired = {id: choices[0] for id, choices in candidates.items()
               if len(choices) == 1 and len(reverse[choices[0]]) == 1 and choices[0] not in reserved
               and (id not in existing or existing[id].mode == "auto")}
    for id, link in existing.items():
        family = families.get(id)
        if link.mode == "auto" and desired.get(id) != link.youtube_video_id:
            db.delete(link)
        elif family and not family.ambiguous and link.record_id != family.latest.recordId:
            link.record_id, link.updated_at = family.latest.recordId, now()
    db.flush()  # Release old unique video claims before inserting new matches.
    for id, video_id in desired.items():
        link = existing.get(id)
        if link is not None and link.youtube_video_id == video_id:
            continue
        db.add(ProductionLink(record_family_id=id, record_id=families[id].latest.recordId,
                              youtube_video_id=video_id, mode="auto", linked_at=now(), updated_at=now()))


def reconcile_safely(db: Session, paths: StoragePaths) -> None:
    """Run after publication/sync commit, without changing their success status."""
    try:
        with storage_mutation_lock(paths.root), Session(bind=db.get_bind()) as session:
            reconcile(session, paths)
            session.commit()
    except Exception as error:
        logger.warning("Production links reconciliation failed: errorType=%s", type(error).__name__)


def set_manual_link(db: Session, paths: StoragePaths, family_id: str, video_id: str | None) -> None:
    families, _issues = read_families(paths)
    family = families.get(family_id)
    link = db.get(ProductionLink, family_id)
    if video_id is None and link is not None:
        # An unreadable record must not prevent the user from releasing a video.
        if family and not family.ambiguous:
            link.record_id = family.latest.recordId
        link.youtube_video_id, link.mode, link.linked_at, link.updated_at = None, "manual_unlinked", None, now()
        return
    if family is None:
        raise LookupError("制作記録がありません。")
    if family.ambiguous:
        raise ValueError("制作記録が枝分かれしているため、最新の記録を特定できません。")
    if video_id is not None:
        if video_id not in {video.id for video in own_videos(db)}:
            raise LookupError("自チャンネルの動画がありません。")
        occupied = db.scalar(select(ProductionLink).where(ProductionLink.youtube_video_id == video_id))
        if occupied and occupied.record_family_id != family_id:
            raise ValueError("この動画は別の制作記録に結び付いています。先に結び付きを外してください。")
    if link is None:
        link = ProductionLink(record_family_id=family_id)
        db.add(link)
    link.record_id, link.youtube_video_id = family.latest.recordId, video_id
    link.mode = "manual" if video_id is not None else "manual_unlinked"
    link.linked_at, link.updated_at = now() if video_id is not None else None, now()
