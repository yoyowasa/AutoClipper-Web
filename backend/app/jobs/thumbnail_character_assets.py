"""Resolve registered character assets, choose an emotion and rotate recent usage."""

from dataclasses import dataclass
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.character_presets import get_presets
from app.audio.transcribe_faster_whisper import transcript_output_path
from app.character_asset_rules import CHARACTER_EMOTIONS
from app.jobs.subtitle_review import reviewed_transcript_output_path, subtitle_review_output_path
from app.models import CharacterAsset, ExportItem, Job
from app.scoring.thumbnail_emotion import CodexThumbnailEmotionSelector, ThumbnailEmotion
from app.storage.paths import StoragePaths


EMOTION_LABELS = {"joy": "喜", "anger": "怒", "sorrow": "哀", "fun": "楽"}


def character_preset_id(db: Session, settings: dict[str, Any]) -> str | None:
    presets = get_presets(db).presets
    identifier = settings.get("characterPresetId")
    if identifier:
        return next((p.id for p in presets if p.id == identifier), None)
    name = settings.get("characterPresetName")
    return next((p.id for p in presets if p.name == name), None)


def available_character_assets(db: Session, paths: StoragePaths, settings: dict[str, Any]) -> list[CharacterAsset]:
    preset = character_preset_id(db, settings)
    if not preset:
        return []
    return [asset for asset in db.scalars(select(CharacterAsset).where(
        CharacterAsset.preset_id == preset,
    ).order_by(CharacterAsset.slot, CharacterAsset.id)) if paths.character_asset(
        asset.preset_id, asset.emotion, asset.id,
    ).is_file()]


def explicit_character_asset(db: Session, paths: StoragePaths, settings: dict[str, Any],
                             asset_id: str | None, emotion: str | None = None) -> CharacterAsset:
    assets = available_character_assets(db, paths, settings)
    if asset_id:
        selected = next((asset for asset in assets if asset.id == asset_id and (not emotion or asset.emotion == emotion)), None)
    else:
        selected = next((asset for asset in assets if asset.emotion == emotion), None)
    if selected is None:
        raise ValueError("このキャラ・表情の素材が見つかりません。素材を選び直してください。")
    return selected


def nearby_thumbnail_subtitles(paths: StoragePaths, export: ExportItem, metadata: dict[str, Any]) -> list[str]:
    directory = paths.job_outputs(export.job_id)
    for file in (subtitle_review_output_path(directory), reviewed_transcript_output_path(directory), transcript_output_path(directory)):
        if not file.is_file():
            continue
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            segments = data.get("segments", []) if isinstance(data, dict) else data
            start = float(metadata.get("start", 0))
            end = float(metadata.get("end", start + export.duration))
            second = start + float(metadata.get("thumbnail_frame_seconds", export.duration * .38))
            nearby = [s for s in segments if float(s["end"]) > start and float(s["start"]) < end]
            nearby.sort(key=lambda s: abs((float(s["start"]) + float(s["end"])) / 2 - second))
            return [str(s["text"])[:300] for s in nearby[:8]]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return []


@dataclass(frozen=True)
class SelectedCharacterAsset:
    asset: CharacterAsset
    reason: str
    selection_source: str
    warnings: list[str]

    def metadata(self) -> dict[str, Any]:
        return {
            "thumbnail_subject_source": "asset", "thumbnail_character_asset_id": self.asset.id,
            "thumbnail_character_preset_id": self.asset.preset_id, "thumbnail_emotion": self.asset.emotion,
            "thumbnail_emotion_reason": self.reason, "thumbnail_emotion_selection_source": self.selection_source,
            "thumbnail_warnings": self.warnings,
        }


def choose_character_asset(
    db: Session, paths: StoragePaths, job: Job, export: ExportItem, metadata: dict[str, Any],
    *, selector: Any = None, emotion: str | None = None, asset_id: str | None = None,
    recent_asset_ids: list[str] | None = None,
) -> SelectedCharacterAsset | None:
    assets = available_character_assets(db, paths, job.settings_json or {})
    if not assets:
        return None
    available = [e for e in CHARACTER_EMOTIONS if any(a.emotion == e for a in assets)]
    warnings = []
    if asset_id or emotion:
        asset = explicit_character_asset(db, paths, job.settings_json or {}, asset_id, emotion)
        return SelectedCharacterAsset(asset, "ユーザーが選択", "manual", list(asset.warnings or []))
    if len(available) == 1:
        emotion, reason, source = available[0], "登録済みの表情は1種類です。", "single_emotion"
    else:
        try:
            active = selector or CodexThumbnailEmotionSelector(storage_root=paths.root, job_id=job.id, clip_id=f"emotion_{export.id}")
            result = ThumbnailEmotion.model_validate(active.generate({
                "thumbnailText": {key: str(metadata.get(field) or "") for key, field in (
                    ("heading", "thumbnail_kicker"), ("upper", "thumbnail_line1"), ("lower", "thumbnail_line2"),
                )},
                "videoTitle": export.title, "nearbySubtitles": nearby_thumbnail_subtitles(paths, export, metadata),
                "availableEmotions": available,
            }, []))
            if result.emotion not in available:
                raise ValueError("選ばれた表情は未登録です。")
            emotion, reason, source = result.emotion, result.reason, "codex"
        except Exception:
            emotion, reason, source = available[0], "表情の自動選択に失敗しました。", "fallback"
            warnings.append(f"表情を自動で選べませんでした（仮に{EMOTION_LABELS[emotion]}を使用）")
    usage = {}
    # Published metadata is the usage ledger, including manual thumbnail regenerations.
    from app.jobs.thumbnails import read_export_metadata
    for previous in db.scalars(select(ExportItem).order_by(ExportItem.created_at, ExportItem.id)):
        saved = read_export_metadata(previous)
        if saved.get("thumbnail_character_preset_id") == assets[0].preset_id:
            identifier = saved.get("thumbnail_character_asset_id")
            stamp = str(saved.get("thumbnail_character_asset_used_at") or previous.created_at.isoformat())
            usage[identifier] = max(usage.get(identifier, ""), stamp)
    # Exports in the current unpublished batch may not yet have DB rows.
    for index, identifier in enumerate(recent_asset_ids or []):
        usage[identifier] = f"9999-{index:09d}"
    options = [a for a in assets if a.emotion == emotion]
    asset = min(options, key=lambda a: (usage.get(a.id, ""), a.slot, a.id))
    return SelectedCharacterAsset(asset, reason, source, warnings + list(asset.warnings or []))


def video_subject_metadata() -> dict[str, Any]:
    return {
        "thumbnail_subject_source": "video", "thumbnail_character_asset_id": None,
        "thumbnail_character_preset_id": None, "thumbnail_emotion": None, "thumbnail_emotion_reason": None,
        "thumbnail_emotion_selection_source": None, "thumbnail_warnings": [],
        "thumbnail_character_asset_upscale": None, "thumbnail_character_asset_used_at": None,
    }
