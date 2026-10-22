"""Retrieve bounded, unexpired hints. Empty/off paths do not change prompts."""

from datetime import UTC

from sqlalchemy import select
from app.config import get_settings

from app.intelligence.common import now
from app.intelligence.models import AnalysisRun, ChannelConnection, ProductionLink
from app.intelligence.performance_schema import PerformanceHint, UsedPerformanceHint

HINT_GUIDANCE = ("過去の投稿実績からの参考情報（決まりではない）。独自集計に基づく仮説で、効果は未検証。"
                 "字幕の根拠、本数・尺の上下限、既存の選定・生成の検証規則を優先し、ヒントで上書きしない。")


def active_hint_uses(hints, *, target=None, format=None, stamp=None) -> list[dict]:
    stamp = stamp or now()
    stamp = stamp.astimezone(UTC) if stamp.tzinfo else stamp.replace(tzinfo=UTC)
    result = []
    for raw in hints or []:
        try:
            hint = UsedPerformanceHint.model_validate(raw)
        except ValueError:
            continue
        expires = hint.expires_at
        if expires.tzinfo is None or expires <= stamp or (target and hint.target != target) or (format and hint.format != format):
            continue
        result.append(hint.model_dump(by_alias=True, mode="json"))
    return result[:10]


def load_performance_hints(db, settings, *, target=None, format=None, stamp=None, config=None) -> list[dict]:
    character = settings.get("characterPresetName")
    if not character or settings.get("usePerformanceHints", True) is False or not (config or get_settings()).youtube_derived_allowed:
        return []
    stamp = stamp or now()
    result, seen, formats = [], set(), set()
    runs = db.scalars(select(AnalysisRun).join(ChannelConnection, ChannelConnection.channel_id == AnalysisRun.channel_id)
        .where(AnalysisRun.status == "success", AnalysisRun.expires_at > stamp, ChannelConnection.status == "connected")
        .order_by(AnalysisRun.finished_at.desc(), AnalysisRun.id.desc()))
    for run in runs:
        if run.channel_id in seen:
            continue
        seen.add(run.channel_id)
        new_formats = set()
        for raw in (run.review or {}).get("performance_hints", []):
            try:
                hint = PerformanceHint.model_validate(raw)
            except ValueError:
                continue
            if hint.character_preset_name != character or hint.format in formats or (format and hint.format != format):
                continue
            new_formats.add(hint.format)
            if target and hint.target != target:
                continue
            linked = set(db.scalars(select(ProductionLink.youtube_video_id).where(ProductionLink.youtube_video_id.in_(hint.video_ids))))
            if not set(hint.video_ids) <= linked:
                continue
            result.append(UsedPerformanceHint(analysisId=run.id, generatedAt=run.finished_at.replace(tzinfo=UTC),
                expiresAt=run.expires_at.replace(tzinfo=UTC), target=hint.target, text=hint.text, format=hint.format)
                .model_dump(by_alias=True, mode="json"))
        formats.update(new_formats)
    return active_hint_uses(result, target=target, format=format, stamp=stamp)


def hint_payload(hints) -> dict:
    return {"performanceHints": hints, "performanceHintGuidance": HINT_GUIDANCE} if hints else {}


def attach_performance_hints(db, settings):
    hints = load_performance_hints(db, settings)
    clean = {key: value for key, value in settings.items() if key != "_performanceHints"}
    return {**clean, "_performanceHints": hints} if hints else clean
