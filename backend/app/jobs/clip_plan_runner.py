from app.clip_allocation import is_ai_allocation, allocate_selection, candidate_pool_counts, allocation_summary
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from app.duration_rules import (
    completed_clip_duration, effective_short_max, validate_clip_duration, duration_search_settings, NORMAL_MAX_SECONDS,
)
from sqlalchemy.orm import Session
from app.candidates.user_rejections import REJECTED_RANGES_SETTING
from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import (
    TranscriptSegment,
    transcript_output_path,
)
from app.audio.volume_features import (
    AudioFeatures,
)
from app.candidates.deduplicate import time_overlap_ratio
from app.candidates.codex_initial_selection import (
    CodexInitialSelectionError,
    CodexInitialSelectionResult,
    codex_reselection_summary_output_path,
    write_codex_initial_selection_summary,
)
from app.candidates.generate_normal_candidates import generate_normal_candidates_with_summary
from app.candidates.generate_short_candidates import generate_short_candidates_with_summary
from app.candidates.manual_ranges import (
    MANUAL_SELECTION_REASON,
    automatic_selection_settings,
    build_manual_candidates,
    manual_ranges_for_type,
    merge_manual_candidates_into_selection,
)
from app.candidates.merge_boundaries import (
    Candidate,
    CandidateGenerationMemoryLimitError,
    merge_candidate_generation_summaries,
    write_candidates,
)
from app.candidates.select_candidates import (
    CandidateRejection,
    CandidateSelection,
    parse_selection_settings,
    select_candidates,
    write_selected_clips,
)
from app.config import get_settings
from app.jobs.reselection_keep import prepare_kept_candidates, merge_kept_candidates
from app.db import SessionLocal
from app.jobs.clip_plan import (
    clip_plan_output_path,
    load_clip_plan,
    mark_clip_plan_awaiting_review,
    update_clip_plan_boundary,
    update_clip_plan_hook_scene,
    write_clip_plan,
)
from app.jobs.quality_gate import (
    invalidate_quality_gate_decisions,
    quality_gate_decision_path,
)
from app.jobs.manual_workflow import (
    is_manual_workflow,
)
from app.candidates.short_diversity import (
    ShortDiversityResult,
    ShortDiversitySettings,
    select_diverse_shorts,
)
from app.jobs.summaries import write_generation_summaries
from app.jobs.status import PROGRESS_MAP
from app.jobs.subtitle_review import (
    subtitle_review_preview_path,
)
from app.models import Job, Video, utc_now
from app.candidates.used_ranges import (
    unused_items,
    with_reselection_exclusions,
)
from app.scoring.heatmap import annotate_candidates_with_heatmap
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.black_screen import (
    VisualQuality,
)
from app.video.heatmap import HeatmapSegment, load_heatmap_for_video
from app.video.scene_detect import SceneSegment

from app.jobs.pipeline_common import (
    AutoClipperPipelineDependencies,
    PipelineExpectedError,
    SessionFactory,
    _active_quality_gate_mode,
    _bool_setting,
    _codex_initial_selection_enabled,
    _evaluate_selection_quality_gate_for_mode,
    _heartbeat_job,
    _heatmap_summary_for_selection_mode,
    _int_setting,
    _is_repeated_normal_proposal,
    _prepare_clip_plan_review,
    _read_json_file,
    _read_transcript_segments,
    _render_candidate_review_preview,
    _score_local_candidates,
    _selection_with_fallback_titles,
    _selection_with_refined_boundaries,
    _filter_user_rejections,
    _set_status,
    _settings_with_source_history,
    _transcript_text,
    _unused_candidates,
    _write_json,
)

def _generate_candidates_for_reselection_mode(
    *,
    settings: dict[str, Any],
    transcript_segments: list[TranscriptSegment],
    scene_segments: list[SceneSegment],
    silence_segments: list[SilenceSegment],
    heatmap_segments: Sequence[HeatmapSegment],
    video_duration: float,
    heartbeat: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[Candidate], list[Candidate], dict[str, Any]]:
    normal_manual_ranges = manual_ranges_for_type(settings, "normal")
    short_manual_ranges = manual_ranges_for_type(settings, "short")
    heatmap_interval_mode = _bool_setting(settings, "heatmapIntervalMode", False)

    reference_segments = heatmap_segments if heatmap_interval_mode else ()
    normal_generation_result = (
        build_manual_candidates(
            "normal",
            normal_manual_ranges,
            transcript_segments,
        )
        if normal_manual_ranges and not is_ai_allocation(settings)
        else generate_normal_candidates_with_summary(
            unused_items(transcript_segments, settings),
            scene_segments,
            silence_segments,
            settings=settings,
            heartbeat=heartbeat,
        )
    )
    short_generation_result = (
        build_manual_candidates(
            "short",
            short_manual_ranges,
            transcript_segments,
        )
        if short_manual_ranges and not is_ai_allocation(settings)
        else generate_short_candidates_with_summary(
            unused_items(transcript_segments, settings),
            scene_segments,
            silence_segments,
            settings=settings,
            heartbeat=heartbeat,
        )
    )
    normal_candidates = annotate_candidates_with_heatmap(
        normal_generation_result.candidates,
        reference_segments,
    )
    short_candidates = annotate_candidates_with_heatmap(
        short_generation_result.candidates,
        reference_segments,
    )
    summary = merge_candidate_generation_summaries(
        [normal_generation_result.summary, short_generation_result.summary],
        video_duration=video_duration,
        transcript_segment_count=len(transcript_segments),
    )

    if not normal_candidates and not short_candidates:
        raise PipelineExpectedError(
            "no_candidates_found",
            "No clip candidates were found for the selected settings.",
        )
    return normal_candidates, short_candidates, summary

def _codex_selection_with_diverse_refined_shorts(
    result: CodexInitialSelectionResult,
    *,
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment],
    scene_segments: Sequence[SceneSegment],
    settings: dict[str, Any],
    timeline_duration: float,
    heatmap_segments: Sequence[HeatmapSegment] = (),
) -> tuple[CandidateSelection, list[Candidate], ShortDiversityResult]:
    from app.scoring.rule_score import codex_opening_bonus, opening_score

    def rank_key(candidate: Candidate) -> tuple[float, str]:
        score = candidate.final_score
        if score is None:
            score = candidate.ai_score
        bonus = (100 * codex_opening_bonus(candidate.opening_score, str(settings.get("audienceFamiliarity", "known")))
                 if candidate.type == "short" else 0)
        return (-((score if score is not None else 0.0) + bonus), candidate.id)

    pool_normal_count, pool_short_count = candidate_pool_counts(settings) if is_ai_allocation(settings) else (
        result.selection.requested_normal_count, result.selection.requested_short_count)
    candidate_pool = [
        candidate
        for candidate in _unused_candidates(result.candidates, settings)
        if not _is_repeated_normal_proposal(candidate, settings)
    ]
    normal_pool = sorted(
        (candidate for candidate in candidate_pool if candidate.type == "normal"),
        key=rank_key,
    )
    short_pool = sorted(
        (candidate for candidate in candidate_pool if candidate.type == "short"),
        key=rank_key,
    )
    pool_selection = result.selection.model_copy(
        update={"normal_clips": normal_pool, "shorts": short_pool}
    )
    refined_pool_selection, refined_candidates = _selection_with_refined_boundaries(
        pool_selection,
        candidate_pool,
        transcript_segments=transcript_segments,
        silence_segments=silence_segments,
        scene_segments=scene_segments,
        settings=settings,
        timeline_duration=timeline_duration,
        heatmap_segments=heatmap_segments,
    )

    cross_type_rejections: list[CandidateRejection] = []
    eligible_shorts: list[Candidate] = []
    parsed_settings = parse_selection_settings(settings)
    missing_topic_rejections = [
        CandidateRejection(
            candidateId=candidate.id,
            type="normal",
            reasons=["post_refinement_missing_topic_key"],
        )
        for candidate in refined_pool_selection.normal_clips
        if not (candidate.topic_key or "").strip()
    ]
    previous_duplicate_rejections = [
        CandidateRejection(
            candidateId=candidate.id,
            type="normal",
            reasons=["near_duplicate_previous_proposal"],
        )
        for candidate in refined_pool_selection.normal_clips
        if _is_repeated_normal_proposal(candidate, settings)
    ]
    normal_selection = select_candidates(
        [
            candidate
            for candidate in refined_pool_selection.normal_clips
            if (candidate.topic_key or "").strip()
            and not _is_repeated_normal_proposal(candidate, settings)
        ],
        settings=parsed_settings.model_copy(
            update={
                "normal_clip_count": pool_normal_count,
                "short_count": 0,
                "selection_policy": "strict_quality",
            }
        ),
        silence_segments=silence_segments,
    )
    selected_normals = normal_selection.normal_clips
    normal_pool_rejections = [
        *missing_topic_rejections,
        *previous_duplicate_rejections,
        *normal_selection.rejected_candidates,
    ]
    for candidate in refined_pool_selection.shorts:
        conflicting_normal = next(
            (
                normal
                for normal in selected_normals
                if parsed_settings.cross_type_overlap_dedupe and time_overlap_ratio(candidate, normal) >= parsed_settings.max_overlap_ratio
            ),
            None,
        )
        if conflicting_normal is None:
            eligible_shorts.append(candidate)
            continue
        cross_type_rejections.append(
            CandidateRejection(
                candidateId=candidate.id,
                type="short",
                reasons=["post_refinement_cross_type_overlap"],
                details={"overlapWith": conflicting_normal.id},
            )
        )

    eligible_shorts = [candidate.model_copy(update={"opening_score": opening_score(candidate, transcript_segments)})
                       for candidate in eligible_shorts]
    if settings.get("audienceFamiliarity") == "unknown":
        eligible_shorts.sort(key=rank_key)
    replacements = {candidate.id: candidate for candidate in eligible_shorts}
    refined_candidates = [replacements.get(candidate.id, candidate) for candidate in refined_candidates]
    diversity = select_diverse_shorts(
        eligible_shorts,
        requested_count=pool_short_count,
        settings=ShortDiversitySettings(enforce_heatmap_segment_uniqueness=False),
    )
    diversity_rejections = [
        CandidateRejection(
            candidateId=rejection.candidate_id,
            type="short",
            reasons=[f"post_refinement_{reason}" for reason in rejection.reasons],
            details={
                "duplicateOf": rejection.duplicate_of,
                "overlapSeconds": rejection.overlap_seconds,
                "parentOverlapRatio": rejection.parent_overlap_ratio,
                "textSimilarity": rejection.text_similarity,
                "evidenceSimilarity": rejection.evidence_similarity,
            },
        )
        for rejection in diversity.rejected
    ]
    normal_unfilled = max(
        0,
        pool_normal_count - len(selected_normals),
    )
    short_unfilled = diversity.unfilled_count
    unfilled_reason_counts: dict[str, dict[str, int]] = {}
    if normal_unfilled:
        normal_rejection_counts = Counter(
            reason
            for rejection in normal_pool_rejections
            for reason in rejection.reasons
        )
        unfilled_reason_counts["normal"] = {
            "insufficient_codex_candidates": normal_unfilled,
            **normal_rejection_counts,
        }
    if short_unfilled:
        unfilled_reason_counts["short"] = {
            "insufficient_distinct_moments": short_unfilled,
            "post_refinement_duplicate": len(diversity.rejected),
            "post_refinement_cross_type_overlap": len(cross_type_rejections),
        }

    final_selection = refined_pool_selection.model_copy(
        update={
            "normal_clips": selected_normals,
            "shorts": list(diversity.selected),
            "rejected_candidates": [
                *refined_pool_selection.rejected_candidates,
                *normal_pool_rejections,
                *cross_type_rejections,
                *diversity_rejections,
            ],
            "cross_type_overlap_rejected_count": len(cross_type_rejections),
            "unfilled_requested_counts": {
                "normal": normal_unfilled,
                "short": short_unfilled,
            },
            "unfilled_reason_counts": unfilled_reason_counts,
        }
    )
    return final_selection, refined_candidates, diversity

def _automatic_selection_with_diverse_refined_shorts(
    scored_candidates: Sequence[Candidate],
    *,
    transcript_segments: Sequence[TranscriptSegment],
    silence_segments: Sequence[SilenceSegment],
    scene_segments: Sequence[SceneSegment],
    settings: dict[str, Any],
    timeline_duration: float,
    audio_features: AudioFeatures,
    heatmap_segments: Sequence[HeatmapSegment] = (),
) -> tuple[CandidateSelection, list[Candidate], ShortDiversityResult]:
    """境界補正後の自動候補だけを再選定し、ショートの重複をhard除外する。"""

    automatic_candidates = [
        candidate
        for candidate in scored_candidates
        if candidate.selection_reason != MANUAL_SELECTION_REASON
    ]
    pool_selection = CandidateSelection(
        normalClips=[
            candidate for candidate in automatic_candidates if candidate.type == "normal"
        ],
        shorts=[
            candidate for candidate in automatic_candidates if candidate.type == "short"
        ],
    )
    refined_pool_selection, refined_candidates = _selection_with_refined_boundaries(
        pool_selection,
        automatic_candidates,
        transcript_segments=transcript_segments,
        silence_segments=silence_segments,
        scene_segments=scene_segments,
        settings=settings,
        timeline_duration=timeline_duration,
        heatmap_segments=heatmap_segments,
    )

    parsed_settings = parse_selection_settings(settings)
    diversity_settings = ShortDiversitySettings(
        enforce_heatmap_segment_uniqueness=False
    )
    excluded_short_ids: set[str] = set()
    diversity_rejections = []

    while True:
        selectable_candidates = [
            candidate
            for candidate in refined_candidates
            if candidate.type != "short" or candidate.id not in excluded_short_ids
        ]
        selection = select_candidates(
            selectable_candidates,
            settings=settings,
            audio_features=audio_features,
            silence_segments=silence_segments,
        )
        diversity = select_diverse_shorts(
            selection.shorts,
            requested_count=parsed_settings.short_count,
            settings=diversity_settings,
        )
        new_rejections = [
            rejection
            for rejection in diversity.rejected
            if rejection.candidate_id not in excluded_short_ids
        ]
        if not new_rejections:
            break
        diversity_rejections.extend(new_rejections)
        excluded_short_ids.update(
            rejection.candidate_id for rejection in new_rejections
        )

    translated_rejections = [
        CandidateRejection(
            candidateId=rejection.candidate_id,
            type="short",
            reasons=[f"post_refinement_{reason}" for reason in rejection.reasons],
            details={
                "duplicateOf": rejection.duplicate_of,
                "overlapSeconds": rejection.overlap_seconds,
                "parentOverlapRatio": rejection.parent_overlap_ratio,
                "textSimilarity": rejection.text_similarity,
                "evidenceSimilarity": rejection.evidence_similarity,
            },
        )
        for rejection in diversity_rejections
    ]
    short_unfilled = max(
        0,
        parsed_settings.short_count - len(diversity.selected),
    )
    unfilled_requested_counts = dict(selection.unfilled_requested_counts)
    unfilled_requested_counts["short"] = short_unfilled
    unfilled_reason_counts = {
        candidate_type: dict(counts)
        for candidate_type, counts in selection.unfilled_reason_counts.items()
    }
    if short_unfilled:
        short_reasons = unfilled_reason_counts.setdefault("short", {})
        short_reasons["post_refinement_duplicate"] = len(diversity_rejections)
        short_reasons["insufficient_distinct_moments"] = short_unfilled

    final_selection = selection.model_copy(
        update={
            "shorts": list(diversity.selected),
            "rejected_candidates": [
                *selection.rejected_candidates,
                *refined_pool_selection.rejected_candidates,
                *translated_rejections,
            ],
            "unfilled_requested_counts": unfilled_requested_counts,
            "unfilled_reason_counts": unfilled_reason_counts,
        }
    )
    aggregate_diversity = ShortDiversityResult(
        selected=tuple(diversity.selected),
        rejected=tuple(diversity_rejections),
        requested_count=parsed_settings.short_count,
    )
    return final_selection, refined_candidates, aggregate_diversity

def _restore_clip_plan_after_reselection_failure(
    db: Session,
    job: Job,
    *,
    job_dir: Path,
    previous_plan: Any,
    previous_artifacts: dict[Path, bytes | None],
    code: str,
    message: str,
) -> None:
    for path, payload in previous_artifacts.items():
        if payload is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if previous_plan is not None:
        previous_plan.state = "awaiting_review"
        requested_keep_ids = (job.settings_json or {}).get("keptClipIds")
        if isinstance(requested_keep_ids, list):
            valid_clip_ids = {clip.id for clip in previous_plan.clips}
            previous_plan.settings["keptClipIds"] = [
                clip_id for clip_id in requested_keep_ids
                if isinstance(clip_id, str) and clip_id in valid_clip_ids
            ]
        if REJECTED_RANGES_SETTING in (job.settings_json or {}):
            previous_plan.settings[REJECTED_RANGES_SETTING] = list(job.settings_json[REJECTED_RANGES_SETTING])
        write_clip_plan(previous_plan, clip_plan_output_path(job_dir))
        job.settings_json = dict(previous_plan.settings)
    job.status = "awaiting_clip_review"
    job.progress = PROGRESS_MAP["awaiting_clip_review"]
    job.current_step = "再選定に失敗しました。設定を確認して再試行してください"
    job.error_code = code
    job.error_message = message
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)

def _candidate_with_clip_plan_boundary(
    candidate: Candidate,
    transcript_segments: Sequence[TranscriptSegment],
    *,
    start: float,
    end: float,
) -> Candidate:
    overlapping = [(index, segment) for index, segment in enumerate(transcript_segments) if segment.end > start and segment.start < end]
    transcript_text = _transcript_text([segment for _, segment in overlapping])
    recommended_start = candidate.clip_plan_recommended_start if candidate.clip_plan_recommended_start is not None else candidate.start
    recommended_end = candidate.clip_plan_recommended_end if candidate.clip_plan_recommended_end is not None else candidate.end
    updated = candidate.model_dump()
    updated.update(
        {
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "longform_reason": candidate.longform_reason if candidate.type == "normal" and end - start > NORMAL_MAX_SECONDS else "",
            "transcript_text": transcript_text,
            "segment_start_index": overlapping[0][0] if overlapping else None,
            "segment_end_index": overlapping[-1][0] + 1 if overlapping else None,
            "transcript_char_count": sum(len(segment.text.strip()) for _, segment in overlapping),
            "speech_seconds": round(
                sum(
                    max(
                        0.0,
                        min(float(segment.end), end) - max(float(segment.start), start),
                    )
                    for _, segment in overlapping
                    if segment.text.strip()
                ),
                3,
            ),
            "clip_plan_recommended_start": recommended_start,
            "clip_plan_recommended_end": recommended_end,
            "clip_plan_boundary_adjusted": not (abs(start - recommended_start) < 0.001 and abs(end - recommended_end) < 0.001),
        }
    )
    return Candidate.model_validate(updated)

def _restore_clip_plan_after_boundary_failure(
    db: Session,
    job: Job,
    *,
    document: Any,
    plan_path: Path,
    selected_path: Path,
    selected_payload: bytes | None,
    preview_path: Path,
    preview_payload: bytes | None,
    code: str,
    message: str,
    current_step: str = "範囲の更新に失敗しました。時間を確認して再試行してください",
) -> None:
    if selected_payload is not None:
        selected_path.write_bytes(selected_payload)
    if preview_payload is None:
        preview_path.unlink(missing_ok=True)
    else:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(preview_payload)
    if document is not None:
        document.state = "awaiting_review"
        write_clip_plan(document, plan_path)
    job.status = "awaiting_clip_review"
    job.progress = PROGRESS_MAP["awaiting_clip_review"]
    job.current_step = current_step
    job.error_code = code
    job.error_message = message
    job.updated_at = utc_now()
    db.commit()
    db.refresh(job)

def run_clip_plan_boundary_update(
    job_id: str,
    clip_id: str,
    start: float,
    end: float,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        job_dir = storage_paths.job_outputs(job.id)
        plan_path = clip_plan_output_path(job_dir)
        selected_path = job_dir / "selected_clips.json"
        preview_path = subtitle_review_preview_path(job_dir, clip_id)
        document = None
        selected_payload = selected_path.read_bytes() if selected_path.is_file() else None
        preview_payload = preview_path.read_bytes() if preview_path.is_file() else None
        try:
            document = load_clip_plan(plan_path)
            selection = CandidateSelection.model_validate(_read_json_file(selected_path))
            transcript_segments = _read_transcript_segments(transcript_output_path(job_dir))
            planned_clip = next(
                (clip for clip in document.clips if clip.id == clip_id),
                None,
            )
            if planned_clip is None:
                raise ValueError(f"clip plan item not found: {clip_id}")
            candidates = [*selection.normal_clips, *selection.shorts]
            candidate = next(
                (item for item in candidates if item.id == clip_id),
                None,
            )
            if candidate is None:
                raise ValueError(f"selected clip not found: {clip_id}")

            source_duration = float(video.duration or document.source_duration or max((clip.end for clip in document.clips), default=0.0))
            if start < 0 or end <= start or end > source_duration + 0.001:
                raise ValueError("requested clip boundary is outside the source video")

            reason = validate_clip_duration(
                planned_clip.type,
                completed_clip_duration(planned_clip.type, start, end, planned_clip.hook_scene_start, planned_clip.hook_scene_end),
                short_max=effective_short_max(dict(job.settings_json or {})),
            )
            if reason:
                raise ValueError(reason)

            _set_status(db, job, "preparing_clip_review")
            job.current_step = "調整した範囲の確認動画を準備中"
            job.error_code = None
            job.error_message = None
            job.updated_at = utc_now()
            document.state = "preparing"
            write_clip_plan(document, plan_path)
            db.commit()
            db.refresh(job)
            visited_statuses.append("preparing_clip_review")

            updated_candidate = _candidate_with_clip_plan_boundary(
                candidate,
                transcript_segments,
                start=start,
                end=end,
            )
            _render_candidate_review_preview(
                deps.subtitle_review_preview_renderer,
                storage_paths.resolve_stored_file(video.stored_path),
                preview_path,
                updated_candidate,
            )
            target_collection = selection.normal_clips if updated_candidate.type == "normal" else selection.shorts
            target_index = next(index for index, item in enumerate(target_collection) if item.id == clip_id)
            target_collection[target_index] = updated_candidate
            write_selected_clips(selection, selected_path)

            update_clip_plan_boundary(
                document,
                clip_id,
                start=start,
                end=end,
                transcript_excerpt=updated_candidate.transcript_text,
            )
            document.source_duration = source_duration
            available_clip_ids = [clip.id for clip in document.clips if subtitle_review_preview_path(job_dir, clip.id).is_file()]
            mark_clip_plan_awaiting_review(
                document,
                preview_clip_ids=available_clip_ids,
            )
            write_clip_plan(document, plan_path)
            invalidate_quality_gate_decisions(
                job_dir,
                ("selection", "content", "post_render"),
            )
            _set_status(db, job, "awaiting_clip_review")
            job.error_code = None
            job.error_message = None
            db.commit()
            db.refresh(job)
            visited_statuses.append("awaiting_clip_review")
        except Exception as exc:
            _restore_clip_plan_after_boundary_failure(
                db,
                job,
                document=document,
                plan_path=plan_path,
                selected_path=selected_path,
                selected_payload=selected_payload,
                preview_path=preview_path,
                preview_payload=preview_payload,
                code="clip_plan_boundary_update_failed",
                message=str(exc),
            )
            raise

    return visited_statuses

def run_clip_plan_hook_scene_update(
    job_id: str,
    clip_id: str,
    start: float | None,
    end: float | None,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        job_dir = storage_paths.job_outputs(job.id)
        plan_path = clip_plan_output_path(job_dir)
        selected_path = job_dir / "selected_clips.json"
        preview_path = subtitle_review_preview_path(job_dir, clip_id)
        document = None
        selected_payload = selected_path.read_bytes() if selected_path.is_file() else None
        preview_payload = preview_path.read_bytes() if preview_path.is_file() else None
        try:
            document = load_clip_plan(plan_path)
            selection = CandidateSelection.model_validate(_read_json_file(selected_path))
            planned_clip = next(
                (clip for clip in document.clips if clip.id == clip_id),
                None,
            )
            if planned_clip is None:
                raise ValueError(f"clip plan item not found: {clip_id}")
            target_candidates = selection.shorts if planned_clip.type == "short" else selection.normal_clips
            candidate = next(
                (item for item in target_candidates if item.id == clip_id),
                None,
            )
            if candidate is None:
                raise ValueError(f"selected clip not found: {clip_id}")
            if (start is None) != (end is None):
                raise ValueError("hook scene requires both start and end")
            if start is not None and end is not None:
                hook_duration = end - start
                if not 0.5 <= hook_duration <= 3.0:
                    raise ValueError("hook scene duration must be between 0.5 and 3 seconds")
                if start < candidate.start - 0.001 or end > candidate.end + 0.001:
                    raise ValueError("hook scene must stay within the selected clip")
            reason = validate_clip_duration(
                candidate.type, completed_clip_duration(candidate.type, candidate.start, candidate.end, start, end),
                short_max=effective_short_max(dict(job.settings_json or {})),
            )
            if reason:
                raise ValueError(reason)

            candidate_payload = candidate.model_dump(mode="python")
            candidate_payload["hook_scene_start"] = start
            candidate_payload["hook_scene_end"] = end
            updated_candidate = Candidate.model_validate(candidate_payload)

            _set_status(db, job, "preparing_clip_review")
            job.current_step = "冒頭フック映像の確認動画を準備中"
            job.error_code = None
            job.error_message = None
            job.updated_at = utc_now()
            document.state = "preparing"
            write_clip_plan(document, plan_path)
            db.commit()
            db.refresh(job)
            visited_statuses.append("preparing_clip_review")

            _render_candidate_review_preview(
                deps.subtitle_review_preview_renderer,
                storage_paths.resolve_stored_file(video.stored_path),
                preview_path,
                updated_candidate,
            )
            target_index = next(index for index, item in enumerate(target_candidates) if item.id == clip_id)
            target_candidates[target_index] = updated_candidate
            write_selected_clips(selection, selected_path)

            update_clip_plan_hook_scene(
                document,
                clip_id,
                start=start,
                end=end,
            )
            available_clip_ids = [clip.id for clip in document.clips if subtitle_review_preview_path(job_dir, clip.id).is_file()]
            mark_clip_plan_awaiting_review(
                document,
                preview_clip_ids=available_clip_ids,
            )
            write_clip_plan(document, plan_path)
            invalidate_quality_gate_decisions(
                job_dir,
                ("selection", "content", "post_render"),
            )
            _set_status(db, job, "awaiting_clip_review")
            job.error_code = None
            job.error_message = None
            db.commit()
            db.refresh(job)
            visited_statuses.append("awaiting_clip_review")
        except Exception as exc:
            _restore_clip_plan_after_boundary_failure(
                db,
                job,
                document=document,
                plan_path=plan_path,
                selected_path=selected_path,
                selected_payload=selected_payload,
                preview_path=preview_path,
                preview_payload=preview_payload,
                code="clip_plan_hook_scene_update_failed",
                message=str(exc),
                current_step=("冒頭フック映像の更新に失敗しました。時間を確認して再試行してください"),
            )
            raise

    return visited_statuses

def run_clip_plan_reselection(
    job_id: str,
    session_factory: SessionFactory = SessionLocal,
    paths: StoragePaths | None = None,
    dependencies: AutoClipperPipelineDependencies | None = None,
) -> list[str]:
    storage_paths = paths or get_storage_paths()
    deps = dependencies or AutoClipperPipelineDependencies()
    visited_statuses: list[str] = []

    with session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        video = db.get(Video, job.video_id)
        if video is None:
            raise ValueError(f"video not found for job: {job_id}")

        job_dir = storage_paths.job_outputs(job.id)
        settings = duration_search_settings(dict(job.settings_json or {}))
        input_path = storage_paths.resolve_stored_file(video.stored_path)
        previous_plan_path = clip_plan_output_path(job_dir)
        previous_plan = load_clip_plan(previous_plan_path) if previous_plan_path.is_file() else None
        previous_artifact_paths = [
            job_dir / "normal_candidates.json",
            job_dir / "short_candidates.json",
            job_dir / "candidates.json",
            job_dir / "candidate_generation_summary.json",
            job_dir / "selected_clips.json",
            job_dir / "scored_candidates.json",
            job_dir / "candidate_summary.json",
            job_dir / "rejection_summary.json",
            job_dir / "selected_clips_summary.json",
            job_dir / "heatmap_validation_summary.json",
            codex_reselection_summary_output_path(job_dir),
            quality_gate_decision_path(job_dir, "selection"),
            quality_gate_decision_path(job_dir, "content"),
            quality_gate_decision_path(job_dir, "post_render"),
        ]
        previous_artifacts = {path: path.read_bytes() if path.is_file() else None for path in previous_artifact_paths}

        try:
            _set_status(db, job, "reselecting_clips")
            visited_statuses.append("reselecting_clips")
            transcript_segments = _read_transcript_segments(transcript_output_path(job_dir))
            audio_features = AudioFeatures.model_validate(_read_json_file(job_dir / "audio_features.json"))
            silence_segments = [SilenceSegment.model_validate(item) for item in _read_json_file(job_dir / "silence_segments.json")]
            scene_segments = [SceneSegment.model_validate(item) for item in _read_json_file(job_dir / "scene_segments.json")]
            visual_quality = VisualQuality.model_validate(_read_json_file(job_dir / "visual_quality.json"))
            heatmap_result = load_heatmap_for_video(
                input_path,
                original_filename=video.original_filename,
                actual_duration=float(video.duration or visual_quality.duration),
                max_sidecar_size_bytes=get_settings().max_heatmap_sidecar_size_bytes,
                sidecar_path=storage_paths.resolve_video_heatmap(
                    video.id,
                    video.stored_path,
                ),
            )
            heatmap_summary, _ = _heatmap_summary_for_selection_mode(
                heatmap_result.summary,
                heatmap_result.segments,
                settings,
                video_duration=float(video.duration or visual_quality.duration),
            )
            _write_json(
                job_dir / "heatmap_validation_summary.json",
                heatmap_summary,
            )
            settings = _settings_with_source_history(db, job, video, storage_paths)
            settings = with_reselection_exclusions(settings, previous_plan)
            full_reselection_settings = dict(settings)
            previous_selection = (CandidateSelection.model_validate(_read_json_file(job_dir / "selected_clips.json"))
                                  if settings.get("keptClipIds") else CandidateSelection())
            settings, kept_candidates = prepare_kept_candidates(settings, previous_plan, previous_selection)
            normal_manual_ranges = manual_ranges_for_type(settings, "normal")
            short_manual_ranges = manual_ranges_for_type(settings, "short")
            automatic_settings = automatic_selection_settings(
                settings,
                manual_normal=bool(normal_manual_ranges),
                manual_short=bool(short_manual_ranges),
            )
            heatmap_interval_mode = _bool_setting(
                settings,
                "heatmapIntervalMode",
                False,
            )
            heatmap_reference_segments = (
                heatmap_result.segments if heatmap_interval_mode else ()
            )
            candidate_generation_summary_path = job_dir / "candidate_generation_summary.json"
            codex_summary_path = codex_reselection_summary_output_path(job_dir)
            codex_reselection_result: CodexInitialSelectionResult | None = None
            codex_requested = _codex_initial_selection_enabled(
                settings,
                manual_workflow=is_manual_workflow(settings),
                has_manual_ranges=bool(normal_manual_ranges or short_manual_ranges),
            )

            def candidate_generation_heartbeat(summary: dict[str, Any]) -> None:
                _write_json(candidate_generation_summary_path, summary)
                _heartbeat_job(db, job)

            if codex_requested:
                def codex_reselection_heartbeat(summary: dict[str, Any]) -> None:
                    write_codex_initial_selection_summary(
                        {**summary, "phase": "reselection"},
                        codex_summary_path,
                    )
                    _heartbeat_job(db, job)

                try:
                    codex_reselection_result = deps.codex_initial_selector(
                        job_id=job.id,
                        storage_root=storage_paths.root,
                        transcript_segments=transcript_segments,
                        heatmap_segments=heatmap_reference_segments,
                        video_duration=float(video.duration or visual_quality.duration),
                        settings=settings,
                        heartbeat=codex_reselection_heartbeat,
                    )
                    write_codex_initial_selection_summary(
                        {**codex_reselection_result.summary, "phase": "reselection"},
                        codex_summary_path,
                    )
                except CodexInitialSelectionError as exc:
                    write_codex_initial_selection_summary(
                        {
                            **exc.fallback_summary(
                                requested_normal_count=_int_setting(settings, "normalClipCount", 2),
                                requested_short_count=_int_setting(settings, "shortCount", 3),
                            ),
                            "phase": "reselection",
                        },
                        codex_summary_path,
                    )
                except Exception:
                    write_codex_initial_selection_summary(
                        {
                            "provider": "codex",
                            "phase": "reselection",
                            "status": "fallback",
                            "fallbackUsed": True,
                            "error": {
                                "code": "codex_initial_selection_unexpected_error",
                                "message": "Codex再選定を完了できなかったため、字幕候補へ切り替えました。",
                            },
                            "requestedNormalCount": _int_setting(settings, "normalClipCount", 2),
                            "requestedShortCount": _int_setting(settings, "shortCount", 3),
                            "selectedNormalCount": 0,
                            "selectedShortCount": 0,
                            "threadId": None,
                        },
                        codex_summary_path,
                    )

            try:
                if codex_reselection_result is not None:
                    normal_candidates = [
                        candidate
                        for candidate in codex_reselection_result.candidates
                        if candidate.type == "normal"
                    ]
                    short_candidates = [
                        candidate
                        for candidate in codex_reselection_result.candidates
                        if candidate.type == "short"
                    ]
                    candidate_generation_summary = merge_candidate_generation_summaries(
                        [
                            {
                                "type": "normal",
                                "strategy": "codex_content_selection",
                                "raw_candidates_considered": len(normal_candidates),
                                "candidates_kept_by_type": {"normal": len(normal_candidates)},
                            },
                            {
                                "type": "short",
                                "strategy": "codex_content_selection",
                                "raw_candidates_considered": len(short_candidates),
                                "candidates_kept_by_type": {"short": len(short_candidates)},
                            },
                        ],
                        video_duration=float(video.duration or visual_quality.duration),
                        transcript_segment_count=len(transcript_segments),
                    )
                else:
                    (
                        normal_candidates,
                        short_candidates,
                        candidate_generation_summary,
                    ) = _generate_candidates_for_reselection_mode(
                        settings=settings,
                        transcript_segments=transcript_segments,
                        scene_segments=scene_segments,
                        silence_segments=silence_segments,
                        heatmap_segments=heatmap_result.segments,
                        video_duration=float(video.duration or visual_quality.duration),
                        heartbeat=candidate_generation_heartbeat,
                    )
            except CandidateGenerationMemoryLimitError as exc:
                _write_json(candidate_generation_summary_path, exc.summary)
                raise PipelineExpectedError(
                    "candidate_generation_memory_limit",
                    "Candidate generation exceeded the configured memory limit.",
                    details=exc.summary,
                ) from exc
            except PipelineExpectedError:
                raise
            except Exception as exc:
                raise PipelineExpectedError(
                    "candidate_generation_failed",
                    f"Could not generate clip candidates: {exc}",
                ) from exc

            if is_ai_allocation(settings):
                normal_candidates.extend(annotate_candidates_with_heatmap(
                    build_manual_candidates('normal', normal_manual_ranges, transcript_segments).candidates, heatmap_reference_segments))
                short_candidates.extend(annotate_candidates_with_heatmap(
                    build_manual_candidates('short', short_manual_ranges, transcript_segments).candidates, heatmap_reference_segments))
            normal_candidates = [
                candidate
                for candidate in _unused_candidates(normal_candidates, settings)
                if not _is_repeated_normal_proposal(candidate, settings)
            ]
            short_candidates = _unused_candidates(short_candidates, settings)
            write_candidates(normal_candidates, job_dir / "normal_candidates.json")
            write_candidates(short_candidates, job_dir / "short_candidates.json")
            write_candidates(
                [*normal_candidates, *short_candidates],
                job_dir / "candidates.json",
            )
            _write_json(
                candidate_generation_summary_path,
                candidate_generation_summary,
            )
            manual_candidates = [c for c in [*normal_candidates, *short_candidates] if c.selection_reason == MANUAL_SELECTION_REASON]
            automatic_candidates = [c for c in [*normal_candidates, *short_candidates] if c.selection_reason != MANUAL_SELECTION_REASON]

            if codex_reselection_result is not None:
                automatic_selection, automatic_scored, _ = (
                    _codex_selection_with_diverse_refined_shorts(
                        codex_reselection_result,
                        transcript_segments=transcript_segments,
                        silence_segments=silence_segments,
                        scene_segments=scene_segments,
                        settings=settings,
                        timeline_duration=float(video.duration or visual_quality.duration),
                        heatmap_segments=heatmap_reference_segments,
                    )
                )
                write_codex_initial_selection_summary(
                    {
                        **codex_reselection_result.summary,
                        "phase": "reselection",
                        "selectedNormalCount": len(automatic_selection.normal_clips),
                        "selectedShortCount": len(automatic_selection.shorts),
                    },
                    codex_summary_path,
                )
            else:
                automatic_scored = _score_local_candidates(
                    automatic_candidates, settings=automatic_settings,
                    audio_features=audio_features, silence_segments=silence_segments,
                    transcript_segments=transcript_segments,
                )
                automatic_selection = select_candidates(
                    automatic_scored,
                    settings=automatic_settings,
                    audio_features=audio_features,
                    silence_segments=silence_segments,
                )
                automatic_selection, automatic_scored, _ = (
                    _automatic_selection_with_diverse_refined_shorts(
                        automatic_scored,
                        transcript_segments=transcript_segments,
                        silence_segments=silence_segments,
                        scene_segments=scene_segments,
                        settings=automatic_settings,
                        timeline_duration=float(video.duration or visual_quality.duration),
                        audio_features=audio_features,
                        heatmap_segments=heatmap_reference_segments,
                    )
                )
            scored_candidates = [*automatic_scored, *manual_candidates]
            selection = merge_manual_candidates_into_selection(
                automatic_selection,
                settings=settings,
                manual_normal_candidates=[c for c in manual_candidates if c.type == "normal"],
                manual_short_candidates=[c for c in manual_candidates if c.type == "short"],
            )
            selection, scored_candidates = _filter_user_rejections(selection, scored_candidates, settings)
            selection, scored_candidates = _selection_with_fallback_titles(
                selection,
                scored_candidates,
                transcript_segments,
            )
            if is_ai_allocation(full_reselection_settings):
                selection = allocate_selection(selection, full_reselection_settings, confirmed=kept_candidates)
                scored_candidates = list({c.id: c for c in [*scored_candidates, *kept_candidates]}.values())
            elif kept_candidates:
                if not selection.normal_clips and not selection.shorts:
                    raise PipelineExpectedError(
                        "reselection_no_alternatives",
                        "キープ以外の新しい候補が見つかりませんでした。前の候補を保持しています。",
                    )
                selection = merge_kept_candidates(selection, kept_candidates, previous_plan)
                scored_candidates = [*scored_candidates, *kept_candidates]
            if is_ai_allocation(full_reselection_settings) and not selection.normal_clips and not selection.shorts:
                raise PipelineExpectedError('no_usable_selection', '強い候補が1本も選べませんでした。')
            settings = full_reselection_settings
            if is_ai_allocation(settings) and codex_reselection_result is not None:
                write_codex_initial_selection_summary({
                    **codex_reselection_result.summary, **allocation_summary(selection), 'phase': 'reselection',
                    'selectedNormalCount': len(selection.normal_clips), 'selectedShortCount': len(selection.shorts),
                }, codex_summary_path)
            write_candidates(
                scored_candidates,
                job_dir / "scored_candidates.json",
            )
            write_selected_clips(selection, job_dir / "selected_clips.json")
            quality_gate_mode = _active_quality_gate_mode(job_dir, settings)
            if quality_gate_mode is None:
                invalidate_quality_gate_decisions(
                    job_dir,
                    ("selection", "content", "post_render"),
                )
            else:
                _evaluate_selection_quality_gate_for_mode(
                    job_id=job.id,
                    job_dir=job_dir,
                    selection=selection,
                    transcript_segments=transcript_segments,
                    settings=settings,
                    source_duration=float(
                        video.duration or visual_quality.duration
                    ),
                    mode=quality_gate_mode,
                )

            candidate_generation_summary = _read_json_file(job_dir / "candidate_generation_summary.json")
            transcript_summary_path = job_dir / "transcript_summary.json"
            transcript_summary = _read_json_file(transcript_summary_path) if transcript_summary_path.is_file() else {}
            write_generation_summaries(
                job_dir,
                transcript_segments=transcript_segments,
                audio_features=audio_features,
                normal_candidates=normal_candidates,
                short_candidates=short_candidates,
                candidate_generation_summary=candidate_generation_summary,
                scored_candidates=scored_candidates,
                selection=selection,
                transcription_engine=str(transcript_summary.get("transcription_engine", "not_run")),
                used_fixture_transcript=bool(transcript_summary.get("used_fixture_transcript", False)),
                transcription_model=transcript_summary.get("transcription_model"),
                transcription_language=transcript_summary.get("transcription_language"),
                transcription_diagnostics=transcript_summary.get("transcription_runtime"),
            )
            _prepare_clip_plan_review(
                kept_plan=previous_plan,
                db=db,
                job=job,
                input_path=input_path,
                selection=selection,
                settings=settings,
                job_dir=job_dir,
                preview_renderer=deps.subtitle_review_preview_renderer,
                source_duration=float(video.duration or visual_quality.duration),
            )
            visited_statuses.extend(["preparing_clip_review", "awaiting_clip_review"])
        except PipelineExpectedError as exc:
            _restore_clip_plan_after_reselection_failure(
                db,
                job,
                job_dir=job_dir,
                previous_plan=previous_plan,
                previous_artifacts=previous_artifacts,
                code=exc.code,
                message=exc.message,
            )
        except Exception as exc:
            _restore_clip_plan_after_reselection_failure(
                db,
                job,
                job_dir=job_dir,
                previous_plan=previous_plan,
                previous_artifacts=previous_artifacts,
                code="clip_plan_reselection_failed",
                message=str(exc),
            )
            raise

    return visited_statuses
