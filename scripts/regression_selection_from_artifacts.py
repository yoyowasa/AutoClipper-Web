from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.audio.silence_detect import SilenceSegment  # noqa: E402
from app.audio.transcribe_faster_whisper import TranscriptSegment  # noqa: E402
from app.audio.volume_features import AudioFeatures  # noqa: E402
from app.candidates.generate_normal_candidates import (  # noqa: E402
    generate_normal_candidates_with_summary,
)
from app.candidates.generate_short_candidates import (  # noqa: E402
    generate_short_candidates_with_summary,
)
from app.candidates.merge_boundaries import (  # noqa: E402
    NORMAL_DURATION_BANDS,
    SHORT_DURATION_BANDS,
    Candidate,
    CandidateGenerationSettings,
    DurationBand,
    duration_band_index,
    duration_band_label,
    parse_generation_settings,
)
from app.candidates.select_candidates import (  # noqa: E402
    CandidateSelection,
    CandidateSelectionSettings,
    select_candidates,
)
from app.scoring.clip_preferences import build_clip_selection_preferences  # noqa: E402
from app.scoring.rule_score import score_candidates  # noqa: E402
from app.video.scene_detect import SceneSegment  # noqa: E402


REQUIRED_ARTIFACTS = (
    "transcript_segments.json",
    "silence_segments.json",
    "scene_segments.json",
    "audio_features.json",
)
HASH_CHECK_ARTIFACTS = (
    *REQUIRED_ARTIFACTS,
    "clip_plan.json",
    "normal_candidates.json",
    "short_candidates.json",
    "selected_clips.json",
)
GENERATION_SETTING_KEYS = (
    "shortMinDuration",
    "shortMaxDuration",
    "normalMinDuration",
    "normalMaxDuration",
    "shortStepSeconds",
    "normalStepSeconds",
    "speechBoundaryTolerance",
    "maxCandidates",
    "maxRawCandidatesPerType",
    "maxKeptCandidatesPerType",
    "maxCandidatesPerTimeBucket",
    "candidateTimeBucketSeconds",
    "maxCandidatesPerStartBucket",
    "candidateStartBucketSeconds",
    "maxCandidateGenerationMemoryMb",
    "candidateChunkSeconds",
    "candidateChunkOverlapSeconds",
)
SELECTION_SETTING_KEYS = (
    "normalClipCount",
    "shortCount",
    "maxOverlapRatio",
    "crossTypeOverlapDedupe",
    "selectionPolicy",
)
PREFERENCE_SETTING_KEYS = (
    "normalClipSelectionPreset",
    "shortClipSelectionPreset",
    "normalClipGuidance",
    "shortClipGuidance",
    "excludeIntroOutro",
    "excludePromotionalContent",
)
THANK_PATTERNS = ("ありがとう", "有難う")
SUPERCHAT_PATTERNS = ("スーパーチャット", "スパチャ")
LEGACY_TARGET_SECONDS = {"normal": 150.0, "short": 42.0}


@dataclass(frozen=True)
class ExpectedRange:
    label: str
    start: float
    end: float


def _read_json(path: Path, *, required: bool = True) -> Any:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"required artifact is missing: {path.name}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_hashes(artifact_dir: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for filename in HASH_CHECK_ARTIFACTS:
        path = artifact_dir / filename
        if path.is_file():
            hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _resolve_artifact_dir(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise NotADirectoryError(f"artifact directory does not exist: {path}")
    missing = [name for name in REQUIRED_ARTIFACTS if not (path / name).is_file()]
    if missing:
        raise FileNotFoundError(f"required artifacts are missing: {', '.join(missing)}")
    return path


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_output_path(value: str | Path, artifact_dir: Path) -> Path:
    path = Path(value).expanduser().resolve()
    if _is_relative_to(path, artifact_dir):
        raise ValueError("output must not overwrite or be created inside the source artifact directory")
    return path


def _load_job_settings(artifact_dir: Path) -> dict[str, Any]:
    clip_plan = _read_json(artifact_dir / "clip_plan.json", required=False)
    if not isinstance(clip_plan, dict) or not isinstance(clip_plan.get("settings"), dict):
        return {}
    return dict(clip_plan["settings"])


def _filtered_settings(source: dict[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    return {key: source[key] for key in keys if source.get(key) is not None}


def _generation_settings(job_settings: dict[str, Any], max_candidates: int | None) -> CandidateGenerationSettings:
    payload = _filtered_settings(job_settings, GENERATION_SETTING_KEYS)
    if max_candidates is not None:
        payload["maxCandidates"] = max_candidates
        payload["maxKeptCandidatesPerType"] = max_candidates
    return parse_generation_settings(payload)


def _selection_settings(
    job_settings: dict[str, Any],
    *,
    normal_count: int | None,
    short_count: int | None,
) -> CandidateSelectionSettings:
    payload = _filtered_settings(job_settings, SELECTION_SETTING_KEYS)
    payload["selectionPolicy"] = "strict_quality"
    if normal_count is not None:
        payload["normalClipCount"] = normal_count
    if short_count is not None:
        payload["shortCount"] = short_count
    return CandidateSelectionSettings(
        normal_clip_count=int(payload.get("normalClipCount", 2)),
        short_count=int(payload.get("shortCount", 3)),
        max_overlap_ratio=float(payload.get("maxOverlapRatio", 0.8)),
        cross_type_overlap_dedupe=bool(payload.get("crossTypeOverlapDedupe", False)),
        selection_policy="strict_quality",
    )


def _load_inputs(artifact_dir: Path) -> tuple[
    list[TranscriptSegment],
    list[SilenceSegment],
    list[SceneSegment],
    AudioFeatures,
]:
    transcripts = [
        TranscriptSegment.model_validate(item)
        for item in _read_json(artifact_dir / "transcript_segments.json")
    ]
    silences = [
        SilenceSegment.model_validate(item)
        for item in _read_json(artifact_dir / "silence_segments.json")
    ]
    scenes = [
        SceneSegment.model_validate(item)
        for item in _read_json(artifact_dir / "scene_segments.json")
    ]
    audio = AudioFeatures.model_validate(_read_json(artifact_dir / "audio_features.json"))
    return transcripts, silences, scenes, audio


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def _duration_distribution(candidates: Sequence[Candidate], bands: Sequence[DurationBand]) -> dict[str, Any]:
    durations = [float(candidate.duration) for candidate in candidates]
    rounded_seconds = Counter(round(duration) for duration in durations)
    dominant_second, dominant_count = rounded_seconds.most_common(1)[0] if rounded_seconds else (None, 0)
    band_counts = {duration_band_label(band): 0 for band in bands}
    for duration in durations:
        band_counts[duration_band_label(bands[duration_band_index(duration, bands)])] += 1
    legacy_target = LEGACY_TARGET_SECONDS[candidates[0].type] if candidates else None
    legacy_near_count = (
        sum(1 for duration in durations if abs(duration - legacy_target) <= 1.0)
        if legacy_target is not None
        else 0
    )
    total = len(durations)
    return {
        "candidateCount": total,
        "minSeconds": round(min(durations), 3) if durations else None,
        "maxSeconds": round(max(durations), 3) if durations else None,
        "meanSeconds": round(statistics.fmean(durations), 3) if durations else None,
        "p50Seconds": _percentile(durations, 0.5),
        "p90Seconds": _percentile(durations, 0.9),
        "durationBandCounts": band_counts,
        "missingDurationBands": [label for label, count in band_counts.items() if count == 0],
        "dominantRoundedSecond": dominant_second,
        "dominantRoundedSecondCount": dominant_count,
        "dominantRoundedSecondShare": round(dominant_count / total, 6) if total else None,
        "legacyTargetSeconds": legacy_target,
        "legacyTargetNearCount": legacy_near_count,
        "legacyTargetNearShare": round(legacy_near_count / total, 6) if total else None,
    }


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def _phrase_count(text: str, patterns: Sequence[str]) -> int:
    normalized = _normalized_text(text)
    return sum(normalized.count(_normalized_text(pattern)) for pattern in patterns)


def _format_time(seconds: float) -> str:
    whole_minutes, second = divmod(max(0.0, seconds), 60.0)
    hour, minute = divmod(int(whole_minutes), 60)
    if hour:
        return f"{hour}:{minute:02d}:{second:04.1f}"
    return f"{minute}:{second:04.1f}"


def _display_title(candidate: Candidate) -> tuple[str, str]:
    if candidate.title:
        return candidate.title, "title"
    if candidate.overlay_title:
        return candidate.overlay_title, "overlayTitle"
    compact = re.sub(r"\s+", " ", candidate.transcript_text).strip()
    return (compact[:77] + "...") if len(compact) > 80 else compact, "transcriptExcerpt"


def _selected_item(candidate: Candidate) -> dict[str, Any]:
    title, title_source = _display_title(candidate)
    thank_count = _phrase_count(candidate.transcript_text, THANK_PATTERNS)
    superchat_count = _phrase_count(candidate.transcript_text, SUPERCHAT_PATTERNS)
    duration_minutes = candidate.duration / 60.0
    return {
        "id": candidate.id,
        "type": candidate.type,
        "title": title,
        "titleSource": title_source,
        "startSeconds": round(candidate.start, 3),
        "endSeconds": round(candidate.end, 3),
        "range": f"{_format_time(candidate.start)} - {_format_time(candidate.end)}",
        "durationSeconds": round(candidate.duration, 3),
        "topicKey": candidate.topic_key,
        "momentKey": candidate.moment_key,
        "ruleScore": candidate.rule_score,
        "finalScore": candidate.final_score,
        "selectionReason": candidate.selection_reason,
        "thankCount": thank_count,
        "thankPerMinute": round(thank_count / duration_minutes, 3) if duration_minutes else 0.0,
        "superchatCount": superchat_count,
        "riskFlags": candidate.risk_flags,
    }


def _pairwise_overlap_summary(candidates: Sequence[Candidate]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            overlap = max(0.0, min(left.end, right.end) - max(left.start, right.start))
            denominator = min(left.duration, right.duration)
            ratio = overlap / denominator if denominator > 0 else 0.0
            pairs.append(
                {
                    "leftId": left.id,
                    "rightId": right.id,
                    "overlapSeconds": round(overlap, 3),
                    "overlapRatioOfShorter": round(ratio, 6),
                }
            )
    return {
        "pairs": pairs,
        "maxOverlapRatioOfShorter": max(
            (pair["overlapRatioOfShorter"] for pair in pairs),
            default=0.0,
        ),
    }


def _selection_summary(selection: CandidateSelection) -> dict[str, Any]:
    normal_items = [_selected_item(candidate) for candidate in selection.normal_clips]
    short_items = [_selected_item(candidate) for candidate in selection.shorts]
    topic_keys = [item["topicKey"] for item in normal_items]
    nonempty_topic_keys = [str(key).casefold() for key in topic_keys if key]
    normal_durations = [float(item["durationSeconds"]) for item in normal_items]
    short_durations = [float(item["durationSeconds"]) for item in short_items]
    return {
        "normal": normal_items,
        "short": short_items,
        "normalTopicKeys": topic_keys,
        "normalTopicKeysPresent": len(nonempty_topic_keys) == len(normal_items),
        "normalTopicKeysDistinct": len(nonempty_topic_keys) == len(set(nonempty_topic_keys)),
        "normalPairwiseOverlap": _pairwise_overlap_summary(selection.normal_clips),
        "normalDurationSpreadSeconds": round(max(normal_durations) - min(normal_durations), 3)
        if normal_durations
        else None,
        "shortDurationSpreadSeconds": round(max(short_durations) - min(short_durations), 3)
        if short_durations
        else None,
        "requestedCounts": {
            "normal": selection.requested_normal_count,
            "short": selection.requested_short_count,
        },
        "selectedCounts": {"normal": len(normal_items), "short": len(short_items)},
        "unfilledRequestedCounts": selection.unfilled_requested_counts,
        "selectedBelowThresholdBackfillCount": selection.selected_below_threshold_backfill_count,
    }


def _load_baseline_candidates(artifact_dir: Path) -> tuple[list[Candidate], list[Candidate]]:
    loaded: list[list[Candidate]] = []
    for filename in ("normal_candidates.json", "short_candidates.json"):
        payload = _read_json(artifact_dir / filename, required=False)
        loaded.append(
            [Candidate.model_validate(item) for item in payload]
            if isinstance(payload, list)
            else []
        )
    return loaded[0], loaded[1]


def _load_baseline_selection(artifact_dir: Path) -> CandidateSelection | None:
    payload = _read_json(artifact_dir / "selected_clips.json", required=False)
    return CandidateSelection.model_validate(payload) if isinstance(payload, dict) else None


def parse_expected_range(value: str) -> ExpectedRange:
    label, separator, range_value = value.partition("=")
    if not separator:
        range_value = label
        label = "expected"
    start_text, separator, end_text = range_value.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError("expected range must be LABEL=START:END or START:END")
    try:
        start = float(start_text)
        end = float(end_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected range START and END must be seconds") from exc
    if start < 0 or end <= start:
        raise argparse.ArgumentTypeError("expected range must satisfy 0 <= START < END")
    return ExpectedRange(label=label.strip() or "expected", start=start, end=end)


def _expected_range_summary(
    selected: Sequence[Candidate],
    expected_ranges: Sequence[ExpectedRange],
    minimum_overlap_seconds: float,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for expected in expected_ranges:
        overlaps = []
        for candidate in selected:
            overlap = max(0.0, min(candidate.end, expected.end) - max(candidate.start, expected.start))
            if overlap > 0:
                overlaps.append({"candidateId": candidate.id, "overlapSeconds": round(overlap, 3)})
        max_overlap = max((item["overlapSeconds"] for item in overlaps), default=0.0)
        items.append(
            {
                "label": expected.label,
                "startSeconds": expected.start,
                "endSeconds": expected.end,
                "minimumOverlapSeconds": minimum_overlap_seconds,
                "hit": max_overlap >= minimum_overlap_seconds,
                "overlaps": overlaps,
            }
        )
    return {
        "ranges": items,
        "hitCount": sum(1 for item in items if item["hit"]),
        "anyHit": any(item["hit"] for item in items) if items else None,
    }


def _regression_checks(
    *,
    candidate_metrics: dict[str, dict[str, Any]],
    selection_summary: dict[str, Any],
    expected_range_summary: dict[str, Any],
    max_duration_mode_share: float,
    max_normal_thank_per_minute: float,
    max_normal_selected_overlap_ratio: float,
    source_artifact_hashes_unchanged: bool,
) -> dict[str, Any]:
    selected_normal = selection_summary["normal"]
    requested_counts = selection_summary["requestedCounts"]
    selected_counts = selection_summary["selectedCounts"]
    checks: dict[str, bool] = {
        "normalSelectedWhenRequested": (
            requested_counts["normal"] == 0 or selected_counts["normal"] >= 1
        ),
        "shortSelectedWhenRequested": (
            requested_counts["short"] == 0 or selected_counts["short"] >= 1
        ),
        "normalAllDurationBandsPopulated": not candidate_metrics["normal"]["missingDurationBands"],
        "shortAllDurationBandsPopulated": not candidate_metrics["short"]["missingDurationBands"],
        "normalDurationModeNotCollapsed": (
            candidate_metrics["normal"]["dominantRoundedSecondShare"] is not None
            and candidate_metrics["normal"]["dominantRoundedSecondShare"] <= max_duration_mode_share
        ),
        "shortDurationModeNotCollapsed": (
            candidate_metrics["short"]["dominantRoundedSecondShare"] is not None
            and candidate_metrics["short"]["dominantRoundedSecondShare"] <= max_duration_mode_share
        ),
        "normalTopicKeysPresent": selection_summary["normalTopicKeysPresent"],
        "normalTopicKeysDistinct": selection_summary["normalTopicKeysDistinct"],
        "normalSelectedOverlapWithinLimit": (
            selection_summary["normalPairwiseOverlap"]["maxOverlapRatioOfShorter"]
            <= max_normal_selected_overlap_ratio
        ),
        "noBelowThresholdBackfill": selection_summary["selectedBelowThresholdBackfillCount"] == 0,
        "sourceArtifactHashesUnchanged": source_artifact_hashes_unchanged,
        "normalThankDensityWithinLimit": all(
            item["thankPerMinute"] <= max_normal_thank_per_minute for item in selected_normal
        ),
    }
    if expected_range_summary["ranges"]:
        checks["expectedNormalTopicRangeHit"] = bool(expected_range_summary["anyHit"])
    return {
        "thresholds": {
            "maxDominantRoundedSecondShare": max_duration_mode_share,
            "maxNormalThankPerMinute": max_normal_thank_per_minute,
            "maxNormalSelectedOverlapRatioOfShorter": max_normal_selected_overlap_ratio,
        },
        "checks": checks,
        "passed": all(checks.values()),
        "failed": [name for name, passed in checks.items() if not passed],
    }


def build_report(
    artifact_dir: Path,
    *,
    max_candidates: int | None = None,
    normal_count: int | None = None,
    short_count: int | None = None,
    expected_ranges: Sequence[ExpectedRange] = (),
    minimum_expected_overlap_seconds: float = 30.0,
    max_duration_mode_share: float = 0.4,
    max_normal_thank_per_minute: float = 2.0,
    max_normal_selected_overlap_ratio: float = 0.5,
) -> dict[str, Any]:
    artifact_dir = _resolve_artifact_dir(artifact_dir)
    hashes_before = _artifact_hashes(artifact_dir)
    job_settings = _load_job_settings(artifact_dir)
    generation_settings = _generation_settings(job_settings, max_candidates)
    selection_settings = _selection_settings(
        job_settings,
        normal_count=normal_count,
        short_count=short_count,
    )
    transcripts, silences, scenes, audio = _load_inputs(artifact_dir)

    normal_result = generate_normal_candidates_with_summary(
        transcripts,
        scenes,
        silences,
        settings=generation_settings,
    )
    short_result = generate_short_candidates_with_summary(
        transcripts,
        scenes,
        silences,
        settings=generation_settings,
    )
    preferences = build_clip_selection_preferences(
        _filtered_settings(job_settings, PREFERENCE_SETTING_KEYS)
    )
    scored = score_candidates(
        [*normal_result.candidates, *short_result.candidates],
        audio_features=audio,
        silence_segments=silences,
        selection_preferences=preferences,
    )
    selection = select_candidates(
        scored,
        settings=selection_settings,
        audio_features=audio,
        silence_segments=silences,
    )
    new_candidate_metrics = {
        "normal": _duration_distribution(normal_result.candidates, NORMAL_DURATION_BANDS),
        "short": _duration_distribution(short_result.candidates, SHORT_DURATION_BANDS),
    }
    new_selection_summary = _selection_summary(selection)
    expected_summary = _expected_range_summary(
        selection.normal_clips,
        expected_ranges,
        minimum_expected_overlap_seconds,
    )

    baseline_normal, baseline_short = _load_baseline_candidates(artifact_dir)
    baseline_selection = _load_baseline_selection(artifact_dir)
    baseline: dict[str, Any] = {
        "candidateDistribution": {
            "normal": _duration_distribution(baseline_normal, NORMAL_DURATION_BANDS),
            "short": _duration_distribution(baseline_short, SHORT_DURATION_BANDS),
        }
    }
    if baseline_selection is not None:
        baseline["selection"] = _selection_summary(baseline_selection)

    hashes_after = _artifact_hashes(artifact_dir)
    changed_artifacts = sorted(
        filename
        for filename in set(hashes_before) | set(hashes_after)
        if hashes_before.get(filename) != hashes_after.get(filename)
    )
    hash_check = {
        "algorithm": "SHA-256",
        "checkedFiles": sorted(hashes_before),
        "unchanged": not changed_artifacts,
        "changedFiles": changed_artifacts,
    }

    report = {
        "schemaVersion": 1,
        "jobArtifactName": artifact_dir.name,
        "executionMode": "artifact-only-local-reselection",
        "safety": {
            "databaseRead": False,
            "databaseWrite": False,
            "videoReadOrProcessing": False,
            "sourceArtifactsWritten": False,
            "externalAiCalled": False,
            "sourceArtifactHashCheck": hash_check,
        },
        "inputCounts": {
            "transcriptSegments": len(transcripts),
            "silenceSegments": len(silences),
            "sceneSegments": len(scenes),
        },
        "effectiveSettings": {
            "generation": generation_settings.model_dump(mode="json"),
            "selection": selection_settings.model_dump(mode="json"),
            "preferences": {
                candidate_type: preference.to_payload()
                for candidate_type, preference in preferences.items()
            },
        },
        "baseline": baseline,
        "recomputed": {
            "generationSummary": {
                "normal": normal_result.summary,
                "short": short_result.summary,
            },
            "candidateDistribution": new_candidate_metrics,
            "selection": new_selection_summary,
            "expectedNormalRanges": expected_summary,
        },
    }
    report["regression"] = _regression_checks(
        candidate_metrics=new_candidate_metrics,
        selection_summary=new_selection_summary,
        expected_range_summary=expected_summary,
        max_duration_mode_share=max_duration_mode_share,
        max_normal_thank_per_minute=max_normal_thank_per_minute,
        max_normal_selected_overlap_ratio=max_normal_selected_overlap_ratio,
        source_artifact_hashes_unchanged=hash_check["unchanged"],
    )
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute candidate generation and local selection from saved JSON artifacts only. "
            "The database, video, and source artifacts are never modified."
        )
    )
    parser.add_argument("--job-output-dir", required=True, help="Existing Job artifact directory")
    parser.add_argument("--output", help="Optional JSON output path outside the source artifact directory")
    parser.add_argument("--max-candidates", type=int, help="Override per-type candidate cap")
    parser.add_argument("--normal-count", type=int, help="Override requested normal clip count")
    parser.add_argument("--short-count", type=int, help="Override requested Short count")
    parser.add_argument(
        "--expect-normal-range",
        action="append",
        type=parse_expected_range,
        default=[],
        metavar="LABEL=START:END",
        help="Expected normal-topic interval in source seconds; repeatable",
    )
    parser.add_argument("--minimum-expected-overlap-seconds", type=float, default=30.0)
    parser.add_argument("--max-duration-mode-share", type=float, default=0.4)
    parser.add_argument("--max-normal-thank-per-minute", type=float, default=2.0)
    parser.add_argument("--max-normal-selected-overlap-ratio", type=float, default=0.5)
    parser.add_argument("--fail-on-regression", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    artifact_dir = _resolve_artifact_dir(args.job_output_dir)
    if args.max_candidates is not None and args.max_candidates <= 0:
        raise ValueError("max-candidates must be greater than zero")
    if args.normal_count is not None and args.normal_count < 0:
        raise ValueError("normal-count must be zero or greater")
    if args.short_count is not None and args.short_count < 0:
        raise ValueError("short-count must be zero or greater")
    if args.minimum_expected_overlap_seconds < 0:
        raise ValueError("minimum-expected-overlap-seconds must be zero or greater")
    if not 0 <= args.max_duration_mode_share <= 1:
        raise ValueError("max-duration-mode-share must be between zero and one")
    if args.max_normal_thank_per_minute < 0:
        raise ValueError("max-normal-thank-per-minute must be zero or greater")
    if not 0 <= args.max_normal_selected_overlap_ratio <= 1:
        raise ValueError("max-normal-selected-overlap-ratio must be between zero and one")

    report = build_report(
        artifact_dir,
        max_candidates=args.max_candidates,
        normal_count=args.normal_count,
        short_count=args.short_count,
        expected_ranges=args.expect_normal_range,
        minimum_expected_overlap_seconds=args.minimum_expected_overlap_seconds,
        max_duration_mode_share=args.max_duration_mode_share,
        max_normal_thank_per_minute=args.max_normal_thank_per_minute,
        max_normal_selected_overlap_ratio=args.max_normal_selected_overlap_ratio,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output_path = _validate_output_path(args.output, artifact_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(output_path)
    else:
        sys.stdout.write(rendered)
    if args.fail_on_regression and not report["regression"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
