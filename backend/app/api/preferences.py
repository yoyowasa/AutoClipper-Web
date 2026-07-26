from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppPreference
from app.schemas import SubtitleStylePresetDocument


router = APIRouter(prefix="/api/preferences", tags=["preferences"])
SUBTITLE_STYLE_PRESETS_KEY = "subtitle_style_presets"


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
