"""User-adopted experiments; equal-window observations are read, never copied."""
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.intelligence.analysis_schema import Proposal
from app.intelligence.dashboard_reports import fresh_video
from app.intelligence.models import AnalysisRun, ImprovementTrial, ProductionLink, YouTubeVideo
from app.intelligence.production_catalog import read_families
from app.intelligence.trial_schemas import TrialRead, TrialVideoRead


def own_video(db, channel_id, id, stamp):
    video = db.get(YouTubeVideo, id)
    if video is None or video.channel_id != channel_id or not fresh_video(video, stamp):
        raise ValueError("このチャンネルの有効な動画を選んでください。メタデータ期限切れの場合は同期してください。")
    return video


def adopt_proposal(db, channel_id, analysis_id, proposal_id, stamp):
    existing = db.scalar(select(ImprovementTrial).where(ImprovementTrial.channel_id == channel_id,
        ImprovementTrial.analysis_id == analysis_id, ImprovementTrial.proposal_id == proposal_id))
    if existing:
        return existing
    analysis = db.get(AnalysisRun, analysis_id)
    if (not analysis or analysis.channel_id != channel_id or analysis.status != "success"
            or analysis.expires_at <= stamp or not analysis.review):
        raise ValueError("有効な分析がありません。期限切れの場合は分析し直してください。")
    raw = next((p for p in analysis.review.get("proposals", []) if p["id"] == proposal_id), None)
    if raw is None:
        raise ValueError("採用する提案がありません。")
    proposal = Proposal.model_validate(raw)
    baseline = own_video(db, channel_id, proposal.baseline_video_id, stamp)
    if baseline.format != {"shorts": "shorts", "videoondemand": "long"}[proposal.format]:
        raise ValueError("基準動画の形式が分析時と異なります。分析し直してください。")
    trial = ImprovementTrial(id="trial_" + uuid4().hex, channel_id=channel_id,
        analysis_id=analysis_id, proposal_id=proposal_id, baseline_video_id=baseline.id,
        change_note=proposal.change_one, keep_fixed=proposal.keep_fixed, primary_metric=proposal.primary_metric,
        rejection_condition=proposal.rejection_condition, result_check=proposal.result_check,
        created_at=stamp, registered_at=stamp, updated_at=stamp)
    db.add(trial)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(ImprovementTrial).where(ImprovementTrial.analysis_id == analysis_id,
                                                           ImprovementTrial.proposal_id == proposal_id))
        if existing is None or existing.channel_id != channel_id:
            raise
        return existing
    return trial


def update_trial(db, paths, trial, body, stamp):
    reassigned = body.baselineVideoId != trial.baseline_video_id or body.targetVideoId != trial.target_video_id
    # Intent remains editable after YouTube metadata expires; reassignments require current evidence.
    baseline = own_video(db, trial.channel_id, body.baselineVideoId, stamp) if (
        body.baselineVideoId != trial.baseline_video_id or body.targetVideoId and reassigned) else None
    if body.targetVideoId and reassigned:
        target = own_video(db, trial.channel_id, body.targetVideoId, stamp)
        if (target.id == baseline.id or target.published_at is None or baseline.published_at is None
                or target.published_at <= baseline.published_at):
            raise ValueError("対象には基準動画より後に公開した別の動画を選んでください。")
        link = db.scalar(select(ProductionLink).where(ProductionLink.youtube_video_id == target.id))
        families, _ = read_families(paths)
        family = families.get(link.record_family_id) if link else None
        if not family or family.ambiguous or family.latest.recordId != link.record_id:
            raise ValueError("対象動画を有効な制作記録と結び付けてから選んでください。")
    changed = any(getattr(trial, key) != value for key, value in (
        ("baseline_video_id", body.baselineVideoId), ("change_note", body.changeNote),
        ("primary_metric", body.primaryMetric), ("rejection_condition", body.rejectionCondition),
        ("result_check", body.resultCheck), ("keep_fixed", body.keepFixed)))
    values = dict(baseline_video_id=body.baselineVideoId, target_video_id=body.targetVideoId,
        target_assigned_at=(stamp if trial.target_video_id != body.targetVideoId else trial.target_assigned_at)
            if body.targetVideoId else None,
        change_note=body.changeNote, keep_fixed=body.keepFixed, primary_metric=body.primaryMetric,
        rejection_condition=body.rejectionCondition, result_check=body.resultCheck, status=body.status,
        registered_at=stamp if changed else trial.registered_at, updated_at=stamp)
    expected = body.expectedUpdatedAt
    if expected.tzinfo:
        from datetime import UTC
        expected = expected.astimezone(UTC).replace(tzinfo=None)
    result = db.execute(update(ImprovementTrial).where(ImprovementTrial.id == trial.id,
        ImprovementTrial.updated_at == expected).values(**values).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        raise RuntimeError("改善試験が更新されています。読み直してから保存してください。")
    db.commit()
    db.refresh(trial)
    return trial


def read_trial(trial, videos):
    baseline, target = videos.get(trial.baseline_video_id), videos.get(trial.target_video_id)
    issues = []
    if not baseline:
        issues.append("BASELINE_UNAVAILABLE")
    if trial.target_video_id is None:
        issues.append("TARGET_NOT_SELECTED")
    elif not target:
        issues.append("TARGET_UNAVAILABLE")
    elif target.production is None:
        issues.append("TARGET_NOT_LINKED")
    if baseline and target:
        formats = (baseline.first7.format, target.first7.format)
        if any(value not in {"shorts", "long"} for value in formats):
            issues.append("FORMAT_UNCONFIRMED")
        elif formats[0] != formats[1]:
            issues.append("FORMAT_MISMATCH")
        if "unknown" in (baseline.durationBand, target.durationBand):
            issues.append("DURATION_UNCONFIRMED")
        elif baseline.durationBand != target.durationBand:
            issues.append("DURATION_MISMATCH")
        if any(video.first7.reason for video in (baseline, target)):
            issues.append("WAITING_FOR_FIRST7")
        before, after = (video.first7.metrics[trial.primary_metric].value for video in (baseline, target))
        if before is None or after is None:
            issues.append("METRIC_UNAVAILABLE")
    direction = None
    if not issues:
        direction = "increase" if after > before else "decrease" if after < before else "same"
    def read(video):
        return TrialVideoRead(id=video.id, title=video.title, publishedAt=video.publishedAt,
            format=video.format, durationBand=video.durationBand, first7=video.first7) if video else None
    return TrialRead(id=trial.id, channelId=trial.channel_id, analysisId=trial.analysis_id, proposalId=trial.proposal_id,
        baselineVideoId=trial.baseline_video_id, targetVideoId=trial.target_video_id, changeNote=trial.change_note,
        keepFixed=trial.keep_fixed, primaryMetric=trial.primary_metric, rejectionCondition=trial.rejection_condition,
        resultCheck=trial.result_check, status=trial.status, createdAt=trial.created_at, registeredAt=trial.registered_at,
        updatedAt=trial.updated_at, baseline=read(baseline), target=read(target), comparisonIssues=issues, direction=direction,
        recordedAfterPublication=bool(target and target.publishedAt and trial.registered_at >= target.publishedAt))
