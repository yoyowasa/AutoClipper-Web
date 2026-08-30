from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppPreference
from app.schemas import SubtitleStylePresetDocument, YouTubePostingProfileDocument


router = APIRouter(prefix="/api/preferences", tags=["preferences"])
SUBTITLE_STYLE_PRESETS_KEY = "subtitle_style_presets"
YOUTUBE_POSTING_PROFILE_KEY = "youtube_posting_profile"


@router.get(
    "/subtitle-style-presets",
    response_model=SubtitleStylePresetDocument,
    response_model_exclude_none=True,
)
def get_subtitle_style_presets(
    db: Session = Depends(get_db),
) -> SubtitleStylePresetDocument:
    preference = db.get(AppPreference, SUBTITLE_STYLE_PRESETS_KEY)
    if preference is None:
        return SubtitleStylePresetDocument()
    return SubtitleStylePresetDocument.model_validate(preference.value_json)


@router.put(
    "/subtitle-style-presets",
    response_model=SubtitleStylePresetDocument,
    response_model_exclude_none=True,
)
def save_subtitle_style_presets(
    document: SubtitleStylePresetDocument,
    db: Session = Depends(get_db),
) -> SubtitleStylePresetDocument:
    payload = document.model_dump(mode="json", by_alias=True, exclude_none=True)
    preference = db.get(AppPreference, SUBTITLE_STYLE_PRESETS_KEY)
    if preference is None:
        preference = AppPreference(
            key=SUBTITLE_STYLE_PRESETS_KEY,
            value_json=payload,
        )
        db.add(preference)
    else:
        preference.value_json = payload
    db.commit()
    return document


@router.get(
    "/youtube-posting-profile",
    response_model=YouTubePostingProfileDocument,
)
def get_youtube_posting_profile(
    db: Session = Depends(get_db),
) -> YouTubePostingProfileDocument:
    preference = db.get(AppPreference, YOUTUBE_POSTING_PROFILE_KEY)
    if preference is None:
        return YouTubePostingProfileDocument()
    return YouTubePostingProfileDocument.model_validate(preference.value_json)


@router.put(
    "/youtube-posting-profile",
    response_model=YouTubePostingProfileDocument,
)
def save_youtube_posting_profile(
    document: YouTubePostingProfileDocument,
    db: Session = Depends(get_db),
) -> YouTubePostingProfileDocument:
    payload = document.model_dump(mode="json", by_alias=True)
    preference = db.get(AppPreference, YOUTUBE_POSTING_PROFILE_KEY)
    if preference is None:
        preference = AppPreference(
            key=YOUTUBE_POSTING_PROFILE_KEY,
            value_json=payload,
        )
        db.add(preference)
    else:
        preference.value_json = payload
    db.commit()
    return document
