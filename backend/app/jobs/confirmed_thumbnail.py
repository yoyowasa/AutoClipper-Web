"""Prepare existing video/asset choices per confirmed clip; reuse at publication."""

import json
import shutil

from app.jobs.thumbnail_candidates import candidate_directory, extract_thumbnail_candidates, EMPTY_REASON
from app.jobs.thumbnail_character_assets import choose_character_asset_for_clip, SelectedCharacterAsset
from app.models import CharacterAsset
from app.storage.json_io import write_json_atomic


def prepare_confirmed_thumbnail(db, paths, job, video, document, clip, *, extractor=None, selector=None):
    directory = paths.confirmed_thumbnail_frames(job.id, clip.id, clip.start, clip.end)
    manifest = directory / "c.json"
    if manifest.is_file():
        frames = json.loads(manifest.read_text(encoding="utf-8"))
    else:
        frames = (extractor or extract_thumbnail_candidates)(
            paths.resolve_stored_file(video.stored_path), clip_start=clip.start, clip_end=clip.end, directory=directory,
            preferred_second=clip.thumbnail_frame_seconds,
        )
        write_json_atomic(manifest, frames)
    metadata = {"thumbnail_frame_candidates": frames, "thumbnail_candidates_version": 1,
                "thumbnail_candidates_reason": None if frames else EMPTY_REASON}
    if not frames:
        recent = [c.automatic_thumbnail.get("thumbnail_character_asset_id") for c in document.clips if c.automatic_thumbnail]
        asset = choose_character_asset_for_clip(
            db, paths, job, clip_id=clip.id, title=clip.publication_title or clip.title,
            subtitles=[s.text[:300] for s in document.segments if s.id in set(clip.segment_ids)][:8],
            metadata={"thumbnail_kicker": clip.thumbnail_kicker, "thumbnail_line1": clip.thumbnail_line1,
                      "thumbnail_line2": clip.thumbnail_line2}, selector=selector, recent_asset_ids=recent,
        )
        if asset:
            metadata.update(asset.metadata())
    clip.automatic_thumbnail = metadata


def reuse_confirmed_thumbnail(db, paths, job_id, clip, export, output_dir):
    metadata = dict(clip.automatic_thumbnail)
    source = paths.confirmed_thumbnail_frames(job_id, clip.id, clip.start, clip.end)
    target = candidate_directory(output_dir, export.id)
    frames = metadata["thumbnail_frame_candidates"]
    if frames:
        target.mkdir(parents=True, exist_ok=True)
        for frame in frames:
            for suffix in (".jpg", ".small.jpg"):
                shutil.copy2(source / f'{frame["id"]}{suffix}', target / f'{frame["id"]}{suffix}')
    asset = None
    if metadata.get("thumbnail_character_asset_id"):
        row = db.get(CharacterAsset, metadata["thumbnail_character_asset_id"])
        if row is None or not paths.character_asset(row.preset_id, row.emotion, row.id).is_file():
            raise ValueError("確定後に予備素材が削除されました。字幕を再確定してください。")
        asset = SelectedCharacterAsset(row, metadata["thumbnail_emotion_reason"],
                                       metadata["thumbnail_emotion_selection_source"], metadata["thumbnail_warnings"])
    return metadata, frames, asset
