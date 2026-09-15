"""Apply a saved character to an existing review, preserving its selected content."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.character_presets import get_presets
from app.jobs.subtitle_review import SubtitleReviewDocument
from app.posting_metadata import build_youtube_posting_copy, ensure_publication_title_suffix
from app.short_banners import banner_asset_path
from app.storage.paths import StoragePaths


def apply_review_character(
    db: Session, paths: StoragePaths, name: str,
    settings: dict[str, Any], document: SubtitleReviewDocument,
) -> dict[str, Any]:
    preset = next((p for p in get_presets(db).presets if p.name == name), None)
    if preset is None:
        raise HTTPException(404, "保存したキャラ設定が見つかりません。")
    snapshot = preset.settings.model_dump(by_alias=True, mode="json")
    image_ids = [snapshot["shortTopBannerAssetId"], snapshot["shortBottomBannerAssetId"]]
    background = preset.settings.normal_thumbnail_style.background_asset_id
    if background:
        image_ids.append(background)
    if any(not banner_asset_path(asset_id, paths).is_file() for asset_id in image_ids):
        raise HTTPException(422, "キャラ設定の画像が見つかりません。TOP画面で保存し直してください。")
    # Output counts belong to selection; loading a design must not reselect clips.
    snapshot.pop("normalClipCount")
    snapshot.pop("shortCount")
    updated = {**settings, **snapshot, "characterPresetName": preset.name}
    for clip in document.clips:
        clip.title_style = None
        clip.hook_style = None
        clip.subtitle_style = None
        clip.subtitle_styles = []
        old_suffix = clip.normal_title_suffix
        new_suffix = preset.settings.normal_title_suffix
        if clip.type == "normal":
            def replace_suffix(title: str) -> str:
                if old_suffix and title.endswith(old_suffix):
                    title = title[:-len(old_suffix)].rstrip()
                return ensure_publication_title_suffix(title, clip_type="normal", suffix=new_suffix)
            clip.publication_title = replace_suffix(clip.publication_title or clip.title)
            for candidate in clip.title_candidates:
                candidate.title = replace_suffix(candidate.title)
        clip.normal_title_suffix = new_suffix
        old_copy = build_youtube_posting_copy(
            clip_type=clip.type,
            source_title=str(settings.get("youtubeSourceTitle") or ""),
            source_url=str(settings.get("youtubeSourceUrl") or ""),
            profile=settings.get("youtubePostingProfile"),
        )
        description = clip.youtube_description
        # Remove only exact generated credit blocks, preserving the content text.
        for block in old_copy.description.split("\n\n"):
            if block and block in description.split("\n\n"):
                description = "\n\n".join(p for p in description.split("\n\n") if p != block)
        copy = build_youtube_posting_copy(
            clip_type=clip.type,
            source_title=str(settings.get("youtubeSourceTitle") or ""),
            source_url=str(settings.get("youtubeSourceUrl") or ""),
            profile=preset.settings.youtube_posting_profile,
            fallback_description=description,
        )
        clip.youtube_description = copy.description
        clip.youtube_hashtags = copy.hashtags
        clip.youtube_tags = copy.tags
    return updated
