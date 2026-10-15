from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.intelligence import PRIVATE_HEADERS, require_local_origin
from app.config import Settings, get_settings
from app.db import get_db
from app.intelligence.models import ProductionLink
from app.intelligence.production_catalog import read_families
from app.intelligence.production_link_schemas import (
    LinkedVideoRead, ProductionLinkRead, ProductionLinksRead, ProductionLinkUpdate, RecordSummary,
)
from app.intelligence.production_links import own_videos, reconcile, set_manual_link
from app.storage.locking import storage_mutation_lock
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/intelligence/production-links", tags=["intelligence"])


def link_listing(db: Session, paths: StoragePaths) -> ProductionLinksRead:
    families, issues = read_families(paths)
    saved = {link.record_family_id: link for link in db.scalars(select(ProductionLink))}
    videos = {video.id: LinkedVideoRead(id=video.id, channelId=video.channel_id, title=video.title, publishedAt=video.published_at)
              for video in own_videos(db)}
    summaries = {id: RecordSummary(familyId=id, recordId=family.latest.recordId, publicationTitle=family.latest.publicationTitle,
        type=family.latest.type, revision=family.latest.revision, createdAt=family.created_at,
        characterPresetName=family.latest.characterPresetName, ambiguous=family.ambiguous, mode=saved[id].mode if id in saved else None)
        for id, family in families.items()}
    links = [ProductionLinkRead(familyId=id, recordId=link.record_id, mode=link.mode, linkedAt=link.linked_at,
        updatedAt=link.updated_at, record=summaries.get(id), video=videos[link.youtube_video_id])
        for id, link in saved.items() if link.youtube_video_id in videos]
    bound_families, bound_videos = {link.familyId for link in links}, {link.video.id for link in links}
    unlinked_records = [summary for id, summary in summaries.items() if id not in bound_families]
    unlinked_videos = [video for id, video in videos.items() if id not in bound_videos]
    return ProductionLinksRead(links=links, unlinkedRecords=unlinked_records, unlinkedVideos=unlinked_videos,
        linkedCount=len(links), unlinkedRecordCount=len(unlinked_records), unlinkedVideoCount=len(unlinked_videos), issues=issues)


@router.get("", response_model=ProductionLinksRead)
def list_production_links(response: Response, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths)):
    response.headers.update(PRIVATE_HEADERS)
    return link_listing(db, paths)


@router.post("/reconcile", response_model=ProductionLinksRead)
def reconcile_links(request: Request, db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
                    config: Settings = Depends(get_settings)):
    require_local_origin(request, config)
    with storage_mutation_lock(paths.root):
        try:
            reconcile(db, paths)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "結び付きが更新されました。読み直してください。") from None
    return link_listing(db, paths)


@router.put("/{record_family_id}", response_model=ProductionLinksRead)
def update_production_link(record_family_id: str, body: ProductionLinkUpdate, request: Request,
                           db: Session = Depends(get_db), paths: StoragePaths = Depends(get_storage_paths),
                           config: Settings = Depends(get_settings)):
    require_local_origin(request, config)
    with storage_mutation_lock(paths.root):
        try:
            set_manual_link(db, paths, record_family_id, body.youtubeVideoId)
            db.commit()
        except LookupError as error:
            db.rollback()
            raise HTTPException(404, str(error)) from None
        except ValueError as error:
            db.rollback()
            raise HTTPException(409, str(error)) from None
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "この動画は既に結び付いています。読み直してください。") from None
    return link_listing(db, paths)
