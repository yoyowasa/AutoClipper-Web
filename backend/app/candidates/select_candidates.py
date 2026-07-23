import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.audio.silence_detect import SilenceSegment
from app.audio.volume_features import AudioFeatures
from app.candidates.deduplicate import time_overlap_ratio
from app.candidates.merge_boundaries import Candidate, CandidateType
from app.scoring.quality_gate import (
    QualityGateSettings,
    effective_final_score,
    evaluate_hard_gate,
    evaluate_quality_gate,
)


SELECTED_CLIPS_FILENAME = "selected_clips.json"
SelectionPolicy = Literal["fill_requested", "strict_quality"]


class CandidateRejection(BaseModel):
    candidate_id: str = Field(alias="candidateId")
    type: CandidateType
    reasons: list[str]
    details: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)


class CandidateSelection(BaseModel):
    normal_clips: list[Candidate] = Field(default_factory=list, alias="normalClips")
    shorts: list[Candidate] = Field(default_factory=list)
    rejected_candidates: list[CandidateRejection] = Field(default_factory=list, alias="rejectedCandidates")
    selection_policy: SelectionPolicy = Field(default="fill_requested", alias="selectionPolicy")
    requested_normal_count: int = Field(default=0, alias="requestedNormalCount")
    requested_short_count: int = Field(default=0, alias="requestedShortCount")
    hard_gate_passed_count: int = Field(default=0, alias="hardGatePassedCount")
    hard_gate_rejected_count: int = Field(default=0, alias="hardGateRejectedCount")
    normal_hard_gate_passed_count: int = Field(default=0, alias="normalHardGatePassedCount")
    short_hard_gate_passed_count: int = Field(default=0, alias="shortHardGatePassedCount")
    selected_above_threshold_count: int = Field(default=0, alias="selectedAboveThresholdCount")
    selected_below_threshold_backfill_count: int = Field(default=0, alias="selectedBelowThresholdBackfillCount")
    overlap_relaxed_count: int = Field(default=0, alias="overlapRelaxedCount")
    high_overlap_rejected_by_type: dict[str, int] = Field(default_factory=dict, alias="highOverlapRejectedByType")
    cross_type_overlap_dedupe: bool = Field(default=False, alias="crossTypeOverlapDedupe")
    cross_type_overlap_rejected_count: int = Field(default=0, alias="crossTypeOverlapRejectedCount")
    time_cluster_count: dict[str, int] = Field(default_factory=dict, alias="timeClusterCount")
    selected_clusters: dict[str, list[int]] = Field(default_factory=dict, alias="selectedClusters")
    unfilled_requested_counts: dict[str, int] = Field(default_factory=dict, alias="unfilledRequestedCounts")
    unfilled_reason_counts: dict[str, dict[str, int]] = Field(default_factory=dict, alias="unfilledReasonCounts")

    model_config = ConfigDict(populate_by_name=True)


class CandidateSelectionSettings(BaseModel):
    normal_clip_count: int = Field(default=2, ge=0)
    short_count: int = Field(default=3, ge=0)
    max_overlap_ratio: float = Field(default=0.8, ge=0, le=1)
    cross_type_overlap_dedupe: bool = False
    selection_policy: SelectionPolicy = "fill_requested"
    quality_gate: QualityGateSettings = Field(default_factory=QualityGateSettings)


@dataclass(frozen=True)
class TypeSelectionResult:
    selected: list[Candidate]
    rejected: list[CandidateRejection]
    hard_gate_passed_count: int
    hard_gate_rejected_count: int
    time_cluster_count: int
    selected_clusters: list[int]


def selected_clips_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / SELECTED_CLIPS_FILENAME


def parse_selection_settings(
    settings: CandidateSelectionSettings | dict[str, Any] | None,
) -> CandidateSelectionSettings:
    if settings is None:
        return CandidateSelectionSettings()
    if isinstance(settings, CandidateSelectionSettings):
        return settings

    aliases = {
        "normalClipCount": "normal_clip_count",
        "shortCount": "short_count",
        "maxOverlapRatio": "max_overlap_ratio",
        "crossTypeOverlapDedupe": "cross_type_overlap_dedupe",
        "selectionPolicy": "selection_policy",
        "qualityGate": "quality_gate",
    }
    quality_aliases = {
        "maxSilenceRatio": "max_silence_ratio",
        "minSpeechDensity": "min_speech_density",
        "minFinalScore": "min_final_score",
        "rejectIncompleteSentence": "reject_incomplete_sentence",
        "incompletePenaltyThreshold": "incomplete_penalty_threshold",
        "rejectModelRejectedCandidates": "reject_model_rejected_candidates",
    }
    normalized: dict[str, Any] = {}
    quality_gate: dict[str, Any] = {}

    for key, value in settings.items():
        if key in quality_aliases:
            quality_gate[quality_aliases[key]] = value
            continue
        normalized[aliases.get(key, key)] = value

    if isinstance(normalized.get("quality_gate"), dict):
        nested_quality_gate = {
            quality_aliases.get(key, key): value
            for key, value in normalized["quality_gate"].items()
        }
        quality_gate = {**nested_quality_gate, **quality_gate}
    if quality_gate:
        normalized["quality_gate"] = quality_gate

    return CandidateSelectionSettings(**normalized)


def _rank_key(candidate: Candidate) -> tuple[float, int, float, float, int, float]:
    return (
        effective_final_score(candidate),
        1 if candidate.should_use is True else 0,
        candidate.rule_score if candidate.rule_score is not None else 0.0,
        -candidate.duration,
        len(candidate.transcript_text),
        -candidate.start,
    )


def _score_passes_threshold(candidate: Candidate, settings: CandidateSelectionSettings) -> bool:
    return effective_final_score(candidate) >= settings.quality_gate.min_final_score


def _candidate_with_selection_metadata(
    candidate: Candidate,
    *,
    below_quality_threshold: bool,
    selection_reason: str,
    overlap_relaxed: bool = False,
    overlap_ratio_used: float | None = None,
    time_cluster: int | None = None,
) -> Candidate:
    return candidate.model_copy(
        update={
            "hard_gate_passed": True,
            "below_quality_threshold": below_quality_threshold,
            "quality_warning": "below_min_final_score" if below_quality_threshold else None,
            "selection_reason": selection_reason,
            "overlap_relaxed": overlap_relaxed,
            "overlap_ratio_used": round(overlap_ratio_used, 6) if overlap_ratio_used is not None else None,
            "time_cluster": time_cluster,
        }
    )


def _gate_rejection(candidate: Candidate, gate: Any) -> CandidateRejection:
    return CandidateRejection(
        candidate_id=candidate.id,
        type=candidate.type,
        reasons=gate.reasons,
        details=gate.model_dump(exclude={"candidate_id", "passed", "reasons"}),
    )


def _overlap_rejection(
    candidate: Candidate,
    selected: Sequence[Candidate],
    max_overlap_ratio: float,
    *,
    cross_type: bool = False,
) -> CandidateRejection | None:
    for selected_candidate in selected:
        ratio = time_overlap_ratio(candidate, selected_candidate)
        if ratio >= max_overlap_ratio:
            return CandidateRejection(
                candidate_id=candidate.id,
                type=candidate.type,
                reasons=["cross_type_high_overlap" if cross_type else "high_overlap"],
                details={
                    "overlapWith": selected_candidate.id,
                    "overlapRatio": round(ratio, 6),
                    "crossType": cross_type,
                },
            )
    return None


def _max_overlap_ratio(candidate: Candidate, selected: Sequence[Candidate]) -> float:
    if not selected:
        return 0.0
    return max(time_overlap_ratio(candidate, selected_candidate) for selected_candidate in selected)


def _relaxed_overlap_thresholds(max_overlap_ratio: float) -> list[float]:
    values = [max_overlap_ratio + 0.1, 0.9, 0.95, 0.99, 1.01]
    return sorted({round(value, 6) for value in values if value > max_overlap_ratio})


def _cluster_size(candidates: Sequence[Candidate], requested_count: int) -> float:
    if not candidates:
        return 60.0
    durations = sorted(candidate.duration for candidate in candidates)
    median_duration = durations[len(durations) // 2]
    min_start = min(candidate.start for candidate in candidates)
    max_end = max(candidate.end for candidate in candidates)
    span = max(max_end - min_start, 1.0)
    requested = max(requested_count, 1)
    return max(60.0, median_duration, span / (requested * 3))


def _cluster_ids(candidates: Sequence[Candidate], requested_count: int) -> dict[str, int]:
    size = _cluster_size(candidates, requested_count)
    return {
        candidate.id: int(((candidate.start + candidate.end) / 2) // size)
        for candidate in candidates
    }


def _cluster_diverse_order(candidates: Sequence[Candidate], cluster_ids: dict[str, int]) -> list[Candidate]:
    grouped: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(cluster_ids.get(candidate.id, 0), []).append(candidate)
    for items in grouped.values():
        items.sort(key=_rank_key, reverse=True)

    cluster_order = sorted(
        grouped,
        key=lambda cluster: (
            _rank_key(grouped[cluster][0])
            if grouped[cluster]
            else (0.0, 0, 0.0, 0.0, 0, 0.0)
        ),
        reverse=True,
    )
    ordered: list[Candidate] = []
    while any(grouped[cluster] for cluster in cluster_order):
        for cluster in cluster_order:
            if grouped[cluster]:
                ordered.append(grouped[cluster].pop(0))
    return ordered


def _append_selected_from_pool(
    pool: Sequence[Candidate],
    selected: list[Candidate],
    overlap_rejections_by_id: dict[str, CandidateRejection],
    requested_count: int,
    settings: CandidateSelectionSettings,
    *,
    selection_reason: str,
    cluster_ids: dict[str, int],
    selected_ids: set[str],
    cross_type_selected: Sequence[Candidate] = (),
    overlap_threshold: float | None = None,
    overlap_relaxed: bool = False,
) -> None:
    threshold = settings.max_overlap_ratio if overlap_threshold is None else overlap_threshold
    for candidate in pool:
        if len(selected) >= requested_count:
            return
        if candidate.id in selected_ids:
            continue
        overlap_rejection = _overlap_rejection(
            candidate,
            selected=selected,
            max_overlap_ratio=threshold,
        )
        if overlap_rejection is not None:
            overlap_rejections_by_id[candidate.id] = overlap_rejection
            continue
        cross_type_overlap_rejection = _overlap_rejection(
            candidate,
            selected=cross_type_selected,
            max_overlap_ratio=settings.max_overlap_ratio,
            cross_type=True,
        )
        if cross_type_overlap_rejection is not None:
            overlap_rejections_by_id[candidate.id] = cross_type_overlap_rejection
            continue
        selected_for_overlap = [*selected, *cross_type_selected]
        overlap_ratio = _max_overlap_ratio(candidate, selected_for_overlap)
        selected.append(
            _candidate_with_selection_metadata(
                candidate,
                below_quality_threshold=not _score_passes_threshold(candidate, settings),
                selection_reason=selection_reason,
                overlap_relaxed=overlap_relaxed,
                overlap_ratio_used=overlap_ratio,
                time_cluster=cluster_ids.get(candidate.id),
            )
        )
        selected_ids.add(candidate.id)
        overlap_rejections_by_id.pop(candidate.id, None)


def _record_final_overlap_rejections(
    candidates: Sequence[Candidate],
    selected: Sequence[Candidate],
    overlap_rejections_by_id: dict[str, CandidateRejection],
    settings: CandidateSelectionSettings,
    *,
    selected_ids: set[str],
    cross_type_selected: Sequence[Candidate] = (),
) -> None:
    for candidate in candidates:
        if candidate.id in selected_ids:
            continue
        overlap_rejection = _overlap_rejection(
            candidate,
            selected=selected,
            max_overlap_ratio=settings.max_overlap_ratio,
        )
        if overlap_rejection is not None:
            overlap_rejections_by_id.setdefault(candidate.id, overlap_rejection)
            continue
        cross_type_overlap_rejection = _overlap_rejection(
            candidate,
            selected=cross_type_selected,
            max_overlap_ratio=settings.max_overlap_ratio,
            cross_type=True,
        )
        if cross_type_overlap_rejection is not None:
            overlap_rejections_by_id.setdefault(candidate.id, cross_type_overlap_rejection)


def _select_strict_for_type(
    candidate_type: CandidateType,
    requested_count: int,
    candidates: Sequence[Candidate],
    settings: CandidateSelectionSettings,
    audio_features: AudioFeatures | dict | None,
    silence_segments: Sequence[SilenceSegment] | None,
    cross_type_selected: Sequence[Candidate] = (),
) -> TypeSelectionResult:
    if requested_count <= 0:
        return TypeSelectionResult([], [], 0, 0, 0, [])

    ranked = sorted(
        (candidate for candidate in candidates if candidate.type == candidate_type),
        key=_rank_key,
        reverse=True,
    )
    cluster_ids = _cluster_ids(ranked, requested_count)
    selected: list[Candidate] = []
    rejected: list[CandidateRejection] = []
    overlap_rejections_by_id: dict[str, CandidateRejection] = {}
    hard_gate_passed_count = 0
    hard_gate_rejected_count = 0

    for candidate in ranked:
        if len(selected) >= requested_count:
            continue

        gate = evaluate_quality_gate(
            candidate,
            settings=settings.quality_gate,
            audio_features=audio_features,
            silence_segments=silence_segments,
        )
        if not gate.passed:
            rejected.append(_gate_rejection(candidate, gate))
            hard_gate_rejected_count += 1
            continue
        hard_gate_passed_count += 1

        overlap_rejection = _overlap_rejection(
            candidate,
            selected=selected,
            max_overlap_ratio=settings.max_overlap_ratio,
        )
        if overlap_rejection is not None:
            overlap_rejections_by_id[candidate.id] = overlap_rejection
            continue
        cross_type_overlap_rejection = _overlap_rejection(
            candidate,
            selected=cross_type_selected,
            max_overlap_ratio=settings.max_overlap_ratio,
            cross_type=True,
        )
        if cross_type_overlap_rejection is not None:
            overlap_rejections_by_id[candidate.id] = cross_type_overlap_rejection
            continue

        selected.append(
            _candidate_with_selection_metadata(
                candidate,
                below_quality_threshold=False,
                selection_reason="above_quality_threshold",
                overlap_ratio_used=_max_overlap_ratio(candidate, [*selected, *cross_type_selected]),
                time_cluster=cluster_ids.get(candidate.id),
            )
        )
        overlap_rejections_by_id.pop(candidate.id, None)

    selected_ids = {candidate.id for candidate in selected}
    quality_passed = [
        candidate for candidate in ranked
        if evaluate_quality_gate(
            candidate,
            settings=settings.quality_gate,
            audio_features=audio_features,
            silence_segments=silence_segments,
        ).passed
    ]
    _record_final_overlap_rejections(
        quality_passed,
        selected,
        overlap_rejections_by_id,
        settings,
        selected_ids=selected_ids,
        cross_type_selected=cross_type_selected,
    )

    return TypeSelectionResult(
        selected=selected,
        rejected=[*rejected, *overlap_rejections_by_id.values()],
        hard_gate_passed_count=hard_gate_passed_count,
        hard_gate_rejected_count=hard_gate_rejected_count,
        time_cluster_count=len(set(cluster_ids.values())),
        selected_clusters=sorted({candidate.time_cluster for candidate in selected if candidate.time_cluster is not None}),
    )


def _select_fill_requested_for_type(
    candidate_type: CandidateType,
    requested_count: int,
    candidates: Sequence[Candidate],
    settings: CandidateSelectionSettings,
    audio_features: AudioFeatures | dict | None,
    silence_segments: Sequence[SilenceSegment] | None,
    cross_type_selected: Sequence[Candidate] = (),
) -> TypeSelectionResult:
    if requested_count <= 0:
        return TypeSelectionResult([], [], 0, 0, 0, [])

    ranked = sorted(
        (candidate for candidate in candidates if candidate.type == candidate_type),
        key=_rank_key,
        reverse=True,
    )
    selected: list[Candidate] = []
    rejected: list[CandidateRejection] = []
    hard_gate_passed: list[Candidate] = []
    overlap_rejections_by_id: dict[str, CandidateRejection] = {}
    selected_ids: set[str] = set()

    for candidate in ranked:
        gate = evaluate_hard_gate(
            candidate,
            settings=settings.quality_gate,
            audio_features=audio_features,
            silence_segments=silence_segments,
        )
        if not gate.passed:
            rejected.append(_gate_rejection(candidate, gate))
            continue
        hard_gate_passed.append(candidate)

    cluster_ids = _cluster_ids(hard_gate_passed, requested_count)
    above_threshold = [
        candidate for candidate in hard_gate_passed if _score_passes_threshold(candidate, settings)
    ]
    below_threshold = [
        candidate for candidate in hard_gate_passed if not _score_passes_threshold(candidate, settings)
    ]
    ordered_above_threshold = _cluster_diverse_order(above_threshold, cluster_ids)
    ordered_below_threshold = _cluster_diverse_order(below_threshold, cluster_ids)

    _append_selected_from_pool(
        ordered_above_threshold,
        selected,
        overlap_rejections_by_id,
        requested_count,
        settings,
        selection_reason="above_quality_threshold",
        cluster_ids=cluster_ids,
        selected_ids=selected_ids,
        cross_type_selected=cross_type_selected,
    )
    _append_selected_from_pool(
        ordered_below_threshold,
        selected,
        overlap_rejections_by_id,
        requested_count,
        settings,
        selection_reason="backfill_below_quality_threshold",
        cluster_ids=cluster_ids,
        selected_ids=selected_ids,
        cross_type_selected=cross_type_selected,
    )

    if len(selected) < requested_count:
        relaxed_pool = _cluster_diverse_order(hard_gate_passed, cluster_ids)
        for threshold in _relaxed_overlap_thresholds(settings.max_overlap_ratio):
            _append_selected_from_pool(
                relaxed_pool,
                selected,
                overlap_rejections_by_id,
                requested_count,
                settings,
                selection_reason="backfill_overlap_relaxed",
                cluster_ids=cluster_ids,
                selected_ids=selected_ids,
                cross_type_selected=cross_type_selected,
                overlap_threshold=threshold,
                overlap_relaxed=True,
            )
            if len(selected) >= requested_count:
                break

    _record_final_overlap_rejections(
        hard_gate_passed,
        selected,
        overlap_rejections_by_id,
        settings,
        selected_ids=selected_ids,
        cross_type_selected=cross_type_selected,
    )

    return TypeSelectionResult(
        selected=selected,
        rejected=[*rejected, *overlap_rejections_by_id.values()],
        hard_gate_passed_count=len(hard_gate_passed),
        hard_gate_rejected_count=len(ranked) - len(hard_gate_passed),
        time_cluster_count=len(set(cluster_ids.values())),
        selected_clusters=sorted({candidate.time_cluster for candidate in selected if candidate.time_cluster is not None}),
    )


def _hard_gate_counts(
    candidates: Sequence[Candidate],
    settings: CandidateSelectionSettings,
    audio_features: AudioFeatures | dict | None,
    silence_segments: Sequence[SilenceSegment] | None,
) -> tuple[int, int]:
    passed = 0
    rejected = 0
    for candidate in candidates:
        gate = evaluate_hard_gate(
            candidate,
            settings=settings.quality_gate,
            audio_features=audio_features,
            silence_segments=silence_segments,
        )
        if gate.passed:
            passed += 1
        else:
            rejected += 1
    return passed, rejected


def _rejection_reason_counts_by_type(
    rejections: Sequence[CandidateRejection],
    candidate_type: CandidateType,
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for rejection in rejections:
        if rejection.type == candidate_type:
            counter.update(rejection.reasons)
    return dict(sorted(counter.items()))


def _high_overlap_rejected_by_type(rejections: Sequence[CandidateRejection]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for rejection in rejections:
        if "high_overlap" in rejection.reasons:
            counter[str(rejection.type)] += 1
    return dict(sorted(counter.items()))


def _cross_type_overlap_rejected_count(rejections: Sequence[CandidateRejection]) -> int:
    return sum(1 for rejection in rejections if "cross_type_high_overlap" in rejection.reasons)


def _unfilled_reason_counts(
    rejections: Sequence[CandidateRejection],
    *,
    normal_unfilled: int,
    short_unfilled: int,
    normal_hard_gate_passed: int,
    short_hard_gate_passed: int,
    selected_normal_count: int,
    selected_short_count: int,
) -> dict[str, dict[str, int]]:
    payload: dict[str, dict[str, int]] = {}
    if normal_unfilled > 0:
        counts = _rejection_reason_counts_by_type(rejections, "normal")
        if normal_hard_gate_passed <= selected_normal_count:
            counts["insufficient_hard_gate_candidates"] = normal_unfilled
        payload["normal"] = counts or {"unknown": normal_unfilled}
    if short_unfilled > 0:
        counts = _rejection_reason_counts_by_type(rejections, "short")
        if short_hard_gate_passed <= selected_short_count:
            counts["insufficient_hard_gate_candidates"] = short_unfilled
        payload["short"] = counts or {"unknown": short_unfilled}
    return payload


def select_candidates(
    candidates: Sequence[Candidate],
    settings: CandidateSelectionSettings | dict[str, Any] | None = None,
    audio_features: AudioFeatures | dict | None = None,
    silence_segments: Sequence[SilenceSegment] | None = None,
) -> CandidateSelection:
    parsed_settings = parse_selection_settings(settings)
    selector = (
        _select_strict_for_type
        if parsed_settings.selection_policy == "strict_quality"
        else _select_fill_requested_for_type
    )
    normal_result = selector(
        "normal",
        requested_count=parsed_settings.normal_clip_count,
        candidates=candidates,
        settings=parsed_settings,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )
    shorts_result = selector(
        "short",
        requested_count=parsed_settings.short_count,
        candidates=candidates,
        settings=parsed_settings,
        audio_features=audio_features,
        silence_segments=silence_segments,
        cross_type_selected=normal_result.selected if parsed_settings.cross_type_overlap_dedupe else (),
    )
    normal_clips = normal_result.selected
    shorts = shorts_result.selected
    selected = [*normal_clips, *shorts]
    rejections = [*normal_result.rejected, *shorts_result.rejected]
    hard_gate_passed_count, hard_gate_rejected_count = _hard_gate_counts(
        candidates,
        settings=parsed_settings,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )
    normal_unfilled = max(0, parsed_settings.normal_clip_count - len(normal_clips))
    short_unfilled = max(0, parsed_settings.short_count - len(shorts))

    return CandidateSelection(
        normal_clips=normal_clips,
        shorts=shorts,
        rejected_candidates=rejections,
        selection_policy=parsed_settings.selection_policy,
        requested_normal_count=parsed_settings.normal_clip_count,
        requested_short_count=parsed_settings.short_count,
        hard_gate_passed_count=hard_gate_passed_count,
        hard_gate_rejected_count=hard_gate_rejected_count,
        normal_hard_gate_passed_count=normal_result.hard_gate_passed_count,
        short_hard_gate_passed_count=shorts_result.hard_gate_passed_count,
        selected_above_threshold_count=sum(
            1 for candidate in selected if candidate.below_quality_threshold is False
        ),
        selected_below_threshold_backfill_count=sum(
            1 for candidate in selected if candidate.below_quality_threshold is True
        ),
        overlap_relaxed_count=sum(1 for candidate in selected if candidate.overlap_relaxed is True),
        high_overlap_rejected_by_type=_high_overlap_rejected_by_type(rejections),
        cross_type_overlap_dedupe=parsed_settings.cross_type_overlap_dedupe,
        cross_type_overlap_rejected_count=_cross_type_overlap_rejected_count(rejections),
        time_cluster_count={
            "normal": normal_result.time_cluster_count,
            "short": shorts_result.time_cluster_count,
        },
        selected_clusters={
            "normal": normal_result.selected_clusters,
            "short": shorts_result.selected_clusters,
        },
        unfilled_requested_counts={
            "normal": normal_unfilled,
            "short": short_unfilled,
        },
        unfilled_reason_counts=_unfilled_reason_counts(
            rejections,
            normal_unfilled=normal_unfilled,
            short_unfilled=short_unfilled,
            normal_hard_gate_passed=normal_result.hard_gate_passed_count,
            short_hard_gate_passed=shorts_result.hard_gate_passed_count,
            selected_normal_count=len(normal_clips),
            selected_short_count=len(shorts),
        ),
    )


def selected_clips_to_jsonable(selection: CandidateSelection) -> dict[str, Any]:
    return selection.model_dump(by_alias=True, mode="json")


def write_selected_clips(selection: CandidateSelection, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(selected_clips_to_jsonable(selection), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def select_and_write_candidates(
    candidates: Sequence[Candidate],
    output_dir: str | Path,
    settings: CandidateSelectionSettings | dict[str, Any] | None = None,
    audio_features: AudioFeatures | dict | None = None,
    silence_segments: Sequence[SilenceSegment] | None = None,
) -> Path:
    selection = select_candidates(
        candidates,
        settings=settings,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )
    return write_selected_clips(selection, selected_clips_output_path(output_dir))
