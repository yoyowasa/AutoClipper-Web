import json
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.audio.silence_detect import SilenceSegment
from app.audio.volume_features import AudioFeatures
from app.candidates.deduplicate import time_overlap_ratio
from app.candidates.merge_boundaries import Candidate, CandidateType
from app.scoring.quality_gate import (
    QualityGateSettings,
    effective_final_score,
    evaluate_quality_gate,
)


SELECTED_CLIPS_FILENAME = "selected_clips.json"


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

    model_config = ConfigDict(populate_by_name=True)


class CandidateSelectionSettings(BaseModel):
    normal_clip_count: int = Field(default=2, ge=0)
    short_count: int = Field(default=3, ge=0)
    max_overlap_ratio: float = Field(default=0.8, ge=0, le=1)
    quality_gate: QualityGateSettings = Field(default_factory=QualityGateSettings)


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


def _rank_key(candidate: Candidate) -> tuple[float, int, float, int, float]:
    return (
        effective_final_score(candidate),
        1 if candidate.should_use is True else 0,
        candidate.rule_score if candidate.rule_score is not None else 0.0,
        len(candidate.transcript_text),
        -candidate.start,
    )


def _overlap_rejection(
    candidate: Candidate,
    selected: Sequence[Candidate],
    max_overlap_ratio: float,
) -> CandidateRejection | None:
    for selected_candidate in selected:
        ratio = time_overlap_ratio(candidate, selected_candidate)
        if ratio >= max_overlap_ratio:
            return CandidateRejection(
                candidate_id=candidate.id,
                type=candidate.type,
                reasons=["high_overlap"],
                details={
                    "overlapWith": selected_candidate.id,
                    "overlapRatio": round(ratio, 6),
                },
            )
    return None


def _select_for_type(
    candidate_type: CandidateType,
    requested_count: int,
    candidates: Sequence[Candidate],
    settings: CandidateSelectionSettings,
    audio_features: AudioFeatures | dict | None,
    silence_segments: Sequence[SilenceSegment] | None,
) -> tuple[list[Candidate], list[CandidateRejection]]:
    ranked = sorted(
        (candidate for candidate in candidates if candidate.type == candidate_type),
        key=_rank_key,
        reverse=True,
    )
    selected: list[Candidate] = []
    rejected: list[CandidateRejection] = []

    for candidate in ranked:
        if len(selected) >= requested_count:
            break

        gate = evaluate_quality_gate(
            candidate,
            settings=settings.quality_gate,
            audio_features=audio_features,
            silence_segments=silence_segments,
        )
        if not gate.passed:
            rejected.append(
                CandidateRejection(
                    candidate_id=candidate.id,
                    type=candidate.type,
                    reasons=gate.reasons,
                    details=gate.model_dump(exclude={"candidate_id", "passed", "reasons"}),
                )
            )
            continue

        overlap_rejection = _overlap_rejection(
            candidate,
            selected=selected,
            max_overlap_ratio=settings.max_overlap_ratio,
        )
        if overlap_rejection is not None:
            rejected.append(overlap_rejection)
            continue

        selected.append(candidate)

    return selected, rejected


def select_candidates(
    candidates: Sequence[Candidate],
    settings: CandidateSelectionSettings | dict[str, Any] | None = None,
    audio_features: AudioFeatures | dict | None = None,
    silence_segments: Sequence[SilenceSegment] | None = None,
) -> CandidateSelection:
    parsed_settings = parse_selection_settings(settings)
    normal_clips, normal_rejections = _select_for_type(
        "normal",
        requested_count=parsed_settings.normal_clip_count,
        candidates=candidates,
        settings=parsed_settings,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )
    shorts, short_rejections = _select_for_type(
        "short",
        requested_count=parsed_settings.short_count,
        candidates=candidates,
        settings=parsed_settings,
        audio_features=audio_features,
        silence_segments=silence_segments,
    )

    return CandidateSelection(
        normal_clips=normal_clips,
        shorts=shorts,
        rejected_candidates=[*normal_rejections, *short_rejections],
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
