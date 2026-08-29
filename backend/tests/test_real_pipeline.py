import json
import hashlib
from collections.abc import Generator
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.jobs.runner as runner_module
from app.audio.openai_transcript_correction import OpenAITranscriptCorrector
from app.audio.silence_detect import SilenceSegment
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.audio.volume_features import build_audio_features
from app.db import Base, get_db
from app.jobs.queue import (
    get_enqueue_clip_plan_boundary_update,
    get_enqueue_clip_plan_hook_scene_update,
    get_enqueue_clip_plan_reselection,
    get_enqueue_job,
    get_enqueue_render_job,
    get_enqueue_subtitle_review_hook_scene_update,
    get_enqueue_subtitle_review_preview,
)
from app.candidates.merge_boundaries import Candidate
from app.candidates.codex_initial_selection import CodexInitialSelectionResult
from app.candidates.select_candidates import CandidateSelection, select_candidates
from app.jobs.runner import (
    AutoClipperPipelineDependencies,
    PipelineExpectedError,
    _build_openai_scoring_pool,
    _codex_selection_with_diverse_refined_shorts,
    _ensure_selected_candidates_openai_scored,
    _require_all_requested_heatmap_candidate_types,
    _score_candidate_list,
    _transcript_quality_diagnostics,
    _transcription_language_setting,
    run_autoclipper_job,
    run_clip_plan_boundary_update,
    run_clip_plan_hook_scene_update,
    run_clip_plan_reselection,
    run_subtitle_review_hook_scene_update,
    run_subtitle_review_preview,
    run_subtitle_review_render,
)
from app.jobs.status import SUCCESS_STATUSES
from app.main import app
from app.models import Job
from app.scoring.openai_score import OpenAICandidateScorer
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.black_screen import BlackScreenSegment, VisualQuality
from app.video.probe import VideoMetadata
from app.video.scene_detect import SceneSegment


SUMMARY_FILENAMES = [
    "transcript_summary.json",
    "audio_feature_summary.json",
    "candidate_summary.json",
    "rejection_summary.json",
    "selected_clips_summary.json",
]


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"transcriptionLanguage": "auto"},
        {"transcription_language": "en"},
    ],
)
def test_transcription_language_setting_forces_japanese(settings: dict[str, Any]) -> None:
    assert _transcription_language_setting(settings) == "ja"


def test_clip_plan_selection_empty_uses_dedicated_failure_code(tmp_path: Path) -> None:
    with pytest.raises(PipelineExpectedError) as exc_info:
        runner_module._prepare_clip_plan_review(
            db=None,
            job=None,
            input_path=tmp_path / "input.mp4",
            selection=CandidateSelection(),
            settings={},
            job_dir=tmp_path,
            preview_renderer=lambda *_args, **_kwargs: tmp_path / "unused.mp4",
            source_duration=60.0,
        )

    assert exc_info.value.code == "no_usable_selection"
    assert exc_info.value.message == ("Pipeline completed analysis but selection produced no usable clips.")


def test_heatmap_type_presence_is_relaxed_only_for_codex_strict_quality() -> None:
    strict_codex_selection = CandidateSelection(
        selectionPolicy="strict_quality",
        requestedNormalCount=1,
        requestedShortCount=1,
    )
    fill_codex_selection = strict_codex_selection.model_copy(update={"selection_policy": "fill_requested"})

    assert not _require_all_requested_heatmap_candidate_types(strict_codex_selection)
    assert _require_all_requested_heatmap_candidate_types(fill_codex_selection)
    assert _require_all_requested_heatmap_candidate_types(None)


def test_long_form_quality_detects_clustered_japanese_repetition_and_sparse_coverage() -> None:
    repeated_segments = [
        TranscriptSegment(
            start=float(index * 10),
            end=float(index * 10 + 4),
            text="えー",
            confidence=0.32,
        )
        for index in range(25)
    ]
    repeated_segments.extend(
        TranscriptSegment(
            start=float((index + 25) * 10),
            end=float((index + 25) * 10 + 4),
            text="ご視聴ありがとうございました",
            confidence=0.33,
        )
        for index in range(20)
    )
    repeated_segments.extend(
        TranscriptSegment(
            start=float((index + 45) * 10),
            end=float((index + 45) * 10 + 4),
            text=f"固有の発話内容{index}",
            confidence=0.4,
        )
        for index in range(16)
    )

    quality = _transcript_quality_diagnostics(
        repeated_segments,
        timeline_duration=9312.0,
        expected_speech_seconds=9000.0,
    )

    assert quality["clustered_repeated_segment_count"] == 45
    assert quality["clustered_repeated_segment_ratio"] == pytest.approx(45 / 61)
    assert quality["clustered_repeated_segment_text"] is True
    assert quality["transcript_audio_coverage"] < 0.08
    assert quality["characters_per_minute"] < 12
    assert "clustered_repeated_segment_text" in quality["reasons"]
    assert "long_form_transcript_too_sparse" in quality["reasons"]


def test_clustered_repetition_is_not_a_hard_failure_for_short_high_confidence_audio() -> None:
    segments = [
        TranscriptSegment(
            start=float(index * 3),
            end=float(index * 3 + 2.5),
            text="はい、そうです" if index % 2 == 0 else "その通りです",
            confidence=0.95,
        )
        for index in range(24)
    ]

    quality = _transcript_quality_diagnostics(
        segments,
        timeline_duration=75.0,
        expected_speech_seconds=60.0,
    )

    assert quality["clustered_repeated_segment_text"] is True
    assert "clustered_repeated_segment_text" not in quality["reasons"]


def test_clustered_repetition_is_not_a_hard_failure_when_long_audio_has_good_coverage() -> None:
    phrases = ("司会の定型案内です", "出演者の定型返答です", "次の話題へ移ります")
    segments = [
        TranscriptSegment(
            start=float(index * 100),
            end=float(index * 100 + 20),
            text=phrases[index % len(phrases)],
            confidence=0.95,
        )
        for index in range(30)
    ]

    quality = _transcript_quality_diagnostics(
        segments,
        timeline_duration=3600.0,
        expected_speech_seconds=600.0,
    )

    assert quality["clustered_repeated_segment_text"] is True
    assert quality["characters_per_minute"] < 12
    assert quality["transcript_audio_coverage"] == 1.0
    assert quality["reasons"] == []


class EchoCorrectionResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.output_text = json.dumps(payload, ensure_ascii=False)


class EchoCorrectionResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> EchoCorrectionResponse:
        self.calls.append(kwargs)
        request = json.loads(kwargs["input"][1]["content"])
        return EchoCorrectionResponse(
            {
                "segments": [
                    {
                        "index": segment["index"],
                        "original_text": segment["original_text"],
                        "corrected_text": segment["original_text"],
                        "changed": False,
                        "reason": "unchanged",
                        "confidence": 1.0,
                    }
                    for segment in request["target_segments"]
                ]
            }
        )


class EchoCorrectionClient:
    def __init__(self) -> None:
        self.responses = EchoCorrectionResponses()


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    def override_get_storage_paths() -> StoragePaths:
        return storage

    def override_get_enqueue_job() -> None:
        return lambda job_id: None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_paths] = override_get_storage_paths
    app.dependency_overrides[get_enqueue_job] = override_get_enqueue_job
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = lambda: lambda job_id, clip_id, spec_hash: None

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def fake_transcript() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=0.0, end=30.0, text="why automation mistakes matter before launch", confidence=0.7),
        TranscriptSegment(start=35.0, end=80.0, text="how teams can fix the process with a clear checklist", confidence=0.7),
        TranscriptSegment(start=85.0, end=140.0, text="the final lesson is to measure progress every week", confidence=0.7),
        TranscriptSegment(start=145.0, end=210.0, text="another complete section for a normal clip selection", confidence=0.7),
    ]


def short_spoken_transcript() -> list[TranscriptSegment]:
    text = (
        "ordinary process notes describe plain steps for a calm internal update. "
        "the speaker continues with simple context and finishes the sentence cleanly."
    )
    return [TranscriptSegment(start=0.0, end=60.0, text=text)]


VALID_OPENAI_SCORE = {
    "should_use": True,
    "final_score": 82,
    "hook_score": 80,
    "completeness_score": 82,
    "context_independence_score": 84,
    "information_density_score": 81,
    "title": "Selected clip",
    "overlay_title": "Selected clip",
    "reason": "Structured score for selected candidate.",
    "risk_flags": [],
}


class FakeOpenAIResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.output_text = json.dumps(payload)


class FakeOpenAIResponses:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeOpenAIResponse:
        self.calls.append(kwargs)
        payload = self.payloads.pop(0)
        return FakeOpenAIResponse(payload)


class FakeOpenAIClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.responses = FakeOpenAIResponses(payloads)


def test_openai_scoring_without_api_key_raises_clear_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    candidate = Candidate(
        id="cand_openai_missing_key",
        type="short",
        start=0.0,
        end=30.0,
        duration=30.0,
        transcript_text="a useful spoken candidate with enough context for scoring",
        rule_score=70.0,
    )
    audio_features = build_audio_features(duration=30.0, silence_segments=[], volume_peak=0.5)
    visual_quality = VisualQuality(
        duration=30.0,
        black_screen_ratio=0.0,
        usable_ratio=1.0,
        black_seconds=0.0,
        black_segments=[],
    )

    with pytest.raises(PipelineExpectedError) as exc_info:
        _score_candidate_list(
            [candidate],
            settings={"useOpenAIScoring": True},
            audio_features=audio_features,
            silence_segments=[],
            visual_quality=visual_quality,
            scorer=None,
        )

    assert exc_info.value.code == "openai_configuration_missing"
    assert "OPENAI_API_KEY" in exc_info.value.message


def _candidate(candidate_id: str, candidate_type: str, start: float, end: float, rule_score: float) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,  # type: ignore[arg-type]
        start=start,
        end=end,
        duration=end - start,
        transcript_text="a complete spoken section with enough context for useful scoring.",
        rule_score=rule_score,
    )


def test_openai_scoring_pool_is_type_aware_and_diverse() -> None:
    candidates = [
        *[_candidate(f"normal_{index}", "normal", index * 120.0, index * 120.0 + 120.0, 90 - index) for index in range(6)],
        *[_candidate(f"short_{index}", "short", index * 80.0, index * 80.0 + 40.0, 70 - index) for index in range(6)],
    ]
    audio_features = build_audio_features(duration=800.0, silence_segments=[], volume_peak=0.5)

    pool = _build_openai_scoring_pool(
        candidates,
        settings={
            "normalClipCount": 2,
            "shortCount": 3,
            "openaiCandidateLimit": 6,
            "minFinalScore": 0,
            "rejectIncompleteSentence": False,
        },
        audio_features=audio_features,
        silence_segments=[],
        candidate_limit=6,
    )

    assert len(pool) == 6
    assert {candidate.type for candidate in pool} == {"normal", "short"}
    assert sum(1 for candidate in pool if candidate.type == "normal") >= 2
    assert sum(1 for candidate in pool if candidate.type == "short") >= 2


def test_finalist_on_demand_scores_selected_rule_only_candidates() -> None:
    candidates = [
        _candidate("normal_a", "normal", 0.0, 120.0, 95.0),
        _candidate("normal_b", "normal", 300.0, 420.0, 94.0),
    ]
    audio_features = build_audio_features(duration=500.0, silence_segments=[], volume_peak=0.5)
    visual_quality = VisualQuality(
        duration=500.0,
        black_screen_ratio=0.0,
        usable_ratio=1.0,
        black_seconds=0.0,
        black_segments=[],
    )
    scorer = OpenAICandidateScorer(
        client=FakeOpenAIClient(
            [
                {**VALID_OPENAI_SCORE, "title": "Preselection", "final_score": 88},
                {**VALID_OPENAI_SCORE, "title": "Finalist", "final_score": 86},
            ]
        )
    )
    settings = {
        "mode": "high_quality",
        "normalClipCount": 2,
        "shortCount": 0,
        "minFinalScore": 0,
        "rejectIncompleteSentence": False,
        "useOpenAIScoring": True,
        "openaiCandidateLimit": 1,
        "ensureSelectedOpenAIScored": True,
        "openaiFinalistScoringLimit": 3,
    }

    scoring = _score_candidate_list(
        candidates,
        settings=settings,
        audio_features=audio_features,
        silence_segments=[],
        visual_quality=visual_quality,
        scorer=scorer,
    )
    selection = select_candidates(
        scoring.candidates,
        settings=settings,
        audio_features=audio_features,
        silence_segments=[],
    )
    updated_selection, updated_candidates, updated_summary = _ensure_selected_candidates_openai_scored(
        selection,
        scoring.candidates,
        settings=settings,
        audio_features=audio_features,
        visual_quality=visual_quality,
        scorer=scoring.openai_scorer,
        openai_summary=scoring.openai_summary,
    )

    selected = [*updated_selection.normal_clips, *updated_selection.shorts]
    assert len(selected) == 2
    assert all(candidate.used_ai_score is True for candidate in selected)
    assert {candidate.openai_score_source for candidate in selected} == {"preselection_pool", "finalist_on_demand"}
    assert {candidate.title_source for candidate in selected} == {"openai"}
    assert updated_summary is not None
    assert updated_summary["candidates_sent_preselection"] == 1
    assert updated_summary["candidates_sent_as_finalists"] == 1
    assert updated_summary["successful_scores"] == 2
    assert {candidate.id for candidate in updated_candidates if candidate.used_ai_score is True} == {
        "normal_a",
        "normal_b",
    }


def test_real_pipeline_produces_results_metadata_and_zip(client: TestClient) -> None:
    media = b"fake video bytes"
    sidecar = json.dumps(
        {
            "schema_version": 1,
            "source": {
                "name": "youtube_most_replayed",
                "video_id": "BaW_jenozKc",
                "fetched_at": "2026-08-02T03:30:00Z",
                "extractor": "yt-dlp",
                "extractor_version": "2026.07.04",
            },
            "media": {
                "filename": "sample.mp4",
                "sha256": hashlib.sha256(media).hexdigest(),
                "size_bytes": len(media),
            },
            "duration_seconds": 240.0,
            "heatmap_available": True,
            "heatmap": [{"start_time": 0.0, "end_time": 240.0, "value": 0.75}],
        }
    ).encode("utf-8")
    upload = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": ("sample.mp4.heatmap.json", sidecar, "application/json"),
        },
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": False,
                "subtitleCorrectionMode": "openai",
                "subtitleCorrectionScope": "suspicious",
                "subtitleCorrectionBatchSize": 2,
                "burnSubtitles": True,
                "normalizeAudio": True,
                "transcriptReplacements": {"automation": "AutoClipper"},
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [
            SilenceSegment(start=30.0, end=35.0, duration=5.0),
            SilenceSegment(start=80.0, end=85.0, duration=5.0),
            SilenceSegment(start=140.0, end=145.0, duration=5.0),
        ],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [BlackScreenSegment(start=220.0, end=225.0, duration=5.0)],
        normal_renderer=fake_render,
        short_renderer=fake_render,
        transcript_corrector=OpenAITranscriptCorrector(client=EchoCorrectionClient()),
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert visited_statuses == [*SUCCESS_STATUSES[1:4], "correcting_subtitles", *SUCCESS_STATUSES[4:]]
    assert not (storage.temp / created["jobId"]).exists()

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert status_response.json()["details"]["heatmapStatus"] == "applied"
    assert status_response.json()["details"]["heatmapApplied"] is True
    assert status_response.json()["details"]["heatmapSegmentCount"] == 1
    assert status_response.json()["details"]["automationManifestAvailable"] is True
    assert status_response.json()["details"]["automationMode"] == "manual"
    assert status_response.json()["details"]["automationEffectiveMode"] == "manual"

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    assert results_response.status_code == 200
    results = results_response.json()
    assert len(results["normalClips"]) == 1
    assert len(results["shorts"]) == 1

    normal_download = client.get(results["normalClips"][0]["downloadUrl"])
    short_download = client.get(results["shorts"][0]["downloadUrl"])
    assert normal_download.status_code == 200
    assert short_download.status_code == 200
    assert normal_download.content.startswith(b"rendered normal_")
    assert short_download.content.startswith(b"rendered short_")

    job_dir = storage.outputs / created["jobId"]
    for name in [
        "automation_manifest.json",
        "video_metadata.json",
        "heatmap_validation_summary.json",
        "raw_transcript_segments.json",
        "deterministic_transcript_segments.json",
        "transcript_segments.json",
        "transcript_correction_summary.json",
        "transcript_correction_diff.md",
        "subtitle_correction_progress.json",
        "transcript_suspicion_segments.json",
        "transcript_suspicion_summary.json",
        "subtitle_correction_targets.json",
        "scene_segments.json",
        "silence_segments.json",
        "audio_features.json",
        "visual_quality.json",
        "candidates.json",
        "scored_candidates.json",
        "selected_clips.json",
        "render_failures.json",
        *SUMMARY_FILENAMES,
    ]:
        assert (job_dir / name).is_file()

    selected_payload = json.loads((job_dir / "selected_clips.json").read_text(encoding="utf-8"))
    automation_manifest = json.loads(
        (job_dir / "automation_manifest.json").read_text(encoding="utf-8")
    )
    assert automation_manifest["requestedMode"] == "manual"
    assert automation_manifest["effectiveMode"] == "manual"
    assert automation_manifest["roles"]["initialSelection"] == "legacy"
    assert len(automation_manifest["decisionInputHash"]) == 64
    assert len(selected_payload["normalClips"]) == 1
    assert len(selected_payload["shorts"]) == 1
    selected_normal = selected_payload["normalClips"][0]
    selected_short = selected_payload["shorts"][0]
    assert selected_normal["title"]
    assert selected_normal["title_source"] == "transcript_fallback"
    assert selected_normal["original_start"] is not None
    assert selected_normal["refined_start"] is not None
    assert selected_normal["boundary_refined"] is not None
    assert selected_normal["heatmap_value"] == 0.75
    assert selected_normal["heatmap_score"] == 7.5
    assert selected_short["title"]
    assert selected_short["overlay_title"]
    assert selected_short["title_source"] == "transcript_fallback"
    assert selected_short["original_start"] is not None
    assert selected_short["refined_start"] is not None
    assert selected_short["boundary_refined"] is not None
    assert selected_short["heatmap_value"] == 0.75
    assert selected_short["heatmap_score"] == 7.5
    raw_transcript = json.loads((job_dir / "raw_transcript_segments.json").read_text(encoding="utf-8"))
    processed_transcript = json.loads((job_dir / "transcript_segments.json").read_text(encoding="utf-8"))
    assert raw_transcript[0]["text"] == "why automation mistakes matter before launch"
    assert processed_transcript[0]["text"] == "why AutoClipper mistakes matter before launch"
    transcript_summary = json.loads((job_dir / "transcript_summary.json").read_text(encoding="utf-8"))
    assert transcript_summary["segment_count"] == 4
    assert transcript_summary["total_text_length"] > 20
    assert transcript_summary["total_speech_duration"] == 195.0
    assert transcript_summary["transcription_engine"] == "faster_whisper"
    assert transcript_summary["transcription_model"] == "base"
    assert transcript_summary["transcription_language"] == "ja"
    assert transcript_summary["transcription_runtime"]["requested_device"] == "cpu"
    assert transcript_summary["transcription_runtime"]["actual_device"] == "injected"
    assert transcript_summary["transcription_runtime"]["requested_compute_type"] == "auto"
    assert transcript_summary["transcription_runtime"]["actual_compute_type"] == "injected"
    assert transcript_summary["used_fixture_transcript"] is False
    correction_summary = json.loads((job_dir / "transcript_correction_summary.json").read_text(encoding="utf-8"))
    assert correction_summary["enabled"] is True
    assert correction_summary["scope"] == "suspicious"
    assert correction_summary["target_segment_count"] == 4
    assert correction_summary["api_call_count"] == 2
    correction_progress = json.loads((job_dir / "subtitle_correction_progress.json").read_text(encoding="utf-8"))
    assert correction_progress == {
        "stage": "correcting_subtitles",
        "stageProgress": 100,
        "correctionBatchesCompleted": 2,
        "correctionBatchesTotal": 2,
        "correctionRetryCount": 0,
        "correctionTargetsCompleted": 4,
        "correctionTargetsTotal": 4,
        "transcriptSegmentCount": 4,
        "fallbackUsed": False,
        "finished": True,
    }
    status_details = status_response.json()["details"]
    assert status_details["stageProgress"] == 100
    assert status_details["correctionBatchesCompleted"] == 2
    transcript_postprocess_summary = json.loads((job_dir / "transcript_postprocess_summary.json").read_text(encoding="utf-8"))
    assert transcript_postprocess_summary["enabled"] is True
    assert transcript_postprocess_summary["segment_count"] == 4
    assert transcript_postprocess_summary["changed_segment_count"] == 1
    assert transcript_postprocess_summary["replacement_counts"] == {"automation": 1}

    audio_summary = json.loads((job_dir / "audio_feature_summary.json").read_text(encoding="utf-8"))
    assert audio_summary["has_audio_features"] is True
    assert audio_summary["duration"] == 240.0
    assert audio_summary["volume_peak"] == 0.5

    candidate_summary = json.loads((job_dir / "candidate_summary.json").read_text(encoding="utf-8"))
    assert candidate_summary["total_candidates"] > 0
    assert candidate_summary["normal_candidates"] > 0
    assert candidate_summary["short_candidates"] > 0
    assert candidate_summary["candidates_with_transcript_text"] == candidate_summary["total_candidates"]
    assert candidate_summary["avg_rule_score"] is not None
    assert candidate_summary["avg_final_score"] is not None
    assert candidate_summary["heatmap_annotated_count"] == candidate_summary["total_candidates"]
    assert candidate_summary["avg_heatmap_value"] == 0.75

    selected_summary = json.loads((job_dir / "selected_clips_summary.json").read_text(encoding="utf-8"))
    assert selected_summary["selected_normal_count"] == 1
    assert selected_summary["selected_short_count"] == 1
    assert len(selected_summary["selected_ids"]) == 2
    assert selected_summary["normal"][0]["title"]
    assert selected_summary["normal"][0]["title_source"] == "transcript_fallback"
    assert selected_summary["normal"][0]["original_start"] is not None
    assert selected_summary["normal"][0]["refined_start"] is not None
    assert selected_summary["shorts"][0]["title"]
    assert selected_summary["shorts"][0]["overlay_title"]
    assert selected_summary["shorts"][0]["title_source"] == "transcript_fallback"
    assert selected_summary["shorts"][0]["original_start"] is not None
    assert selected_summary["shorts"][0]["refined_start"] is not None
    assert all(path["video_path"] for path in selected_summary["output_paths"].values())

    rejection_summary = json.loads((job_dir / "rejection_summary.json").read_text(encoding="utf-8"))
    assert "rejected_by_reason" in rejection_summary
    assert rejection_summary["render_failure_count"] == 0
    assert (job_dir / "normal" / "normal_01.json").is_file()
    assert (job_dir / "shorts" / "short_01.json").is_file()
    assert not (job_dir / "normal" / "normal_01.ass").exists()
    assert not (job_dir / "shorts" / "short_01.ass").exists()
    assert (job_dir / "subtitles" / "normal" / "normal_01.ass").is_file()
    assert (job_dir / "subtitles" / "shorts" / "short_01.ass").is_file()
    normal_metadata = json.loads((job_dir / "normal" / "normal_01.json").read_text(encoding="utf-8"))
    short_metadata = json.loads((job_dir / "shorts" / "short_01.json").read_text(encoding="utf-8"))
    assert normal_metadata["title"]
    assert normal_metadata["title_source"] == "transcript_fallback"
    assert normal_metadata["original_start"] is not None
    assert normal_metadata["refined_start"] is not None
    assert normal_metadata["subtitle_path"].replace("\\", "/").endswith("/subtitles/normal/normal_01.ass")
    assert short_metadata["title"]
    assert short_metadata["overlay_title"]
    assert short_metadata["title_source"] == "transcript_fallback"
    assert short_metadata["original_start"] is not None
    assert short_metadata["refined_start"] is not None
    assert short_metadata["subtitle_path"].replace("\\", "/").endswith("/subtitles/shorts/short_01.ass")

    zip_path = storage.zip_path(created["jobId"])
    assert zip_path.is_file()
    with ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "videos/normal/normal_01.mp4" in names
    assert "videos/shorts/short_01.mp4" in names
    assert "subtitles/normal/normal_01.ass" in names
    assert "subtitles/shorts/short_01.ass" in names
    assert "metadata/normal/normal_01.json" in names
    assert "metadata/shorts/short_01.json" in names
    assert "metadata/selected_clips.json" in names
    assert "metadata/automation_manifest.json" in names
    assert "metadata/raw_transcript_segments.json" in names
    assert "metadata/deterministic_transcript_segments.json" in names
    assert "metadata/transcript_correction_summary.json" in names
    assert "metadata/transcript_correction_diff.md" in names
    assert "metadata/subtitle_correction_progress.json" in names
    assert "metadata/transcript_summary.json" in names
    assert "metadata/transcript_postprocess_summary.json" in names
    assert "metadata/heatmap_validation_summary.json" in names
    assert "metadata/selected_clips_summary.json" in names
    assert "normal_01.mp4" not in names
    assert "short_01.ass" not in names


def test_pipeline_uses_heatmap_intervals_as_candidate_source_when_mode_is_on(
    client: TestClient,
) -> None:
    media = b"fake interval mode video"
    sidecar = json.dumps(
        {
            "schema_version": 1,
            "source": {
                "name": "youtube_most_replayed",
                "video_id": "interval-mode-video",
                "fetched_at": "2026-08-02T03:30:00Z",
                "extractor": "yt-dlp",
                "extractor_version": "2026.07.04",
            },
            "media": {
                "filename": "sample.mp4",
                "sha256": hashlib.sha256(media).hexdigest(),
                "size_bytes": len(media),
            },
            "duration_seconds": 240.0,
            "heatmap_available": True,
            "heatmap": [
                {"start_time": 20.0, "end_time": 38.0, "value": 0.2},
                {"start_time": 150.0, "end_time": 168.0, "value": 1.0},
            ],
        }
    ).encode("utf-8")
    upload = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": ("sample.mp4.heatmap.json", sidecar, "application/json"),
        },
    ).json()
    created_response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 90,
                "shortMinDuration": 20,
                "shortMaxDuration": 20,
                "heatmapIntervalMode": True,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "enableBoundaryRefinement": False,
                "useOpenAIScoring": False,
                "burnSubtitles": False,
            },
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"rendered")
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=fake_render,
        short_renderer=fake_render,
    )

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    job_dir = storage.job_outputs(created["jobId"])
    selected = json.loads((job_dir / "selected_clips.json").read_text(encoding="utf-8"))
    clips = [*selected["normalClips"], *selected["shorts"]]
    assert len(clips) == 2
    assert all(clip["start"] < 168.0 and clip["end"] > 150.0 for clip in clips)
    assert all(clip["generation_source"] == "heatmap_interval" for clip in clips)
    assert all(clip["heatmap_seed_value"] == 1.0 for clip in clips)
    assert all(clip["heatmap_direct_score"] > 0 for clip in clips)

    generation_summary = json.loads((job_dir / "candidate_generation_summary.json").read_text(encoding="utf-8"))
    assert generation_summary["by_type"]["normal"]["strategy"] == "heatmap_intervals"
    assert generation_summary["by_type"]["short"]["strategy"] == "heatmap_intervals"
    heatmap_summary = json.loads((job_dir / "heatmap_validation_summary.json").read_text(encoding="utf-8"))
    assert heatmap_summary["interval_mode_requested"] is True
    assert heatmap_summary["interval_mode_applied"] is True
    assert heatmap_summary["selection_behavior"] == "heatmap_intervals"
    status = client.get(f"/api/jobs/{created['jobId']}").json()
    assert status["status"] == "completed"
    assert status["details"]["heatmapIntervalModeApplied"] is True


def test_stale_clip_plan_preview_cleanup_ignores_file_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview_dir = tmp_path / "previews"
    preview_dir.mkdir()
    current_path = preview_dir / "current.mp4"
    failing_stale_path = preview_dir / "a-failing-stale.mp4"
    removable_stale_path = preview_dir / "b-removable-stale.mp4"
    for path in (current_path, failing_stale_path, removable_stale_path):
        path.write_bytes(b"preview")

    original_unlink = Path.unlink

    def fail_one_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path == failing_stale_path:
            raise OSError("preview is locked")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_one_unlink)

    runner_module._cleanup_stale_clip_plan_previews(
        preview_dir,
        {current_path.resolve()},
    )

    assert current_path.is_file()
    assert failing_stale_path.is_file()
    assert not removable_stale_path.exists()


def test_clip_plan_reselection_can_switch_from_heatmap_intervals_to_legacy_candidates(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = b"fake reselection mode video"
    sidecar = json.dumps(
        {
            "schema_version": 1,
            "source": {
                "name": "youtube_most_replayed",
                "video_id": "reselection-mode-video",
                "fetched_at": "2026-08-02T03:30:00Z",
                "extractor": "yt-dlp",
                "extractor_version": "2026.07.04",
            },
            "media": {
                "filename": "sample.mp4",
                "sha256": hashlib.sha256(media).hexdigest(),
                "size_bytes": len(media),
            },
            "duration_seconds": 240.0,
            "heatmap_available": True,
            "heatmap": [
                {"start_time": 20.0, "end_time": 38.0, "value": 0.2},
                {"start_time": 150.0, "end_time": 168.0, "value": 1.0},
            ],
        }
    ).encode("utf-8")
    upload = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": ("sample.mp4.heatmap.json", sidecar, "application/json"),
        },
    ).json()
    created_response = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 90,
                "shortMinDuration": 20,
                "shortMaxDuration": 20,
                "heatmapIntervalMode": True,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "enableBoundaryRefinement": False,
                "useOpenAIScoring": False,
                "burnSubtitles": True,
                "requireClipPlanReview": True,
                "requireSubtitleReview": True,
            },
        },
    )
    assert created_response.status_code == 201
    created = created_response.json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_preview(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(Path(output_path).name.encode("utf-8"))
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        subtitle_review_preview_renderer=fake_preview,
    )
    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    job_dir = storage.job_outputs(created["jobId"])
    initial_candidates = json.loads((job_dir / "candidates.json").read_text(encoding="utf-8"))
    assert initial_candidates
    assert all(candidate["generation_source"] == "heatmap_interval" for candidate in initial_candidates)
    initial_plan = client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()
    initial_clip_ids = {clip["id"] for clip in initial_plan["clips"]}
    initial_preview_payloads = {clip["previewVideoUrl"]: client.get(clip["previewVideoUrl"]).content for clip in initial_plan["clips"]}
    rollback_names = [
        "normal_candidates.json",
        "short_candidates.json",
        "candidates.json",
        "candidate_generation_summary.json",
    ]
    initial_artifacts = {name: (job_dir / name).read_bytes() for name in rollback_names}

    with next(app.dependency_overrides[get_db]()) as db:
        stored_job = db.get(Job, created["jobId"])
        assert stored_job is not None
        legacy_settings = dict(stored_job.settings_json or {})
        legacy_settings.pop("shortTopBannerEnabled", None)
        legacy_settings.pop("shortBottomBannerEnabled", None)
        legacy_settings.pop("shortSubtitleYPercent", None)
        stored_job.settings_json = legacy_settings
        db.commit()

    queued_reselections: list[str] = []
    app.dependency_overrides[get_enqueue_clip_plan_reselection] = lambda: queued_reselections.append

    def reselection_payload(mode: bool | str) -> dict[str, Any]:
        return {
            "normalClipSelectionPreset": "auto",
            "shortClipSelectionPreset": "auto",
            "normalClipGuidance": "",
            "shortClipGuidance": "",
            "excludeIntroOutro": True,
            "excludePromotionalContent": False,
            "selectionPolicy": "fill_requested",
            "useOpenAIScoring": False,
            "heatmapIntervalMode": mode,
        }

    invalid_response = client.post(
        f"/api/jobs/{created['jobId']}/clip-plan/reselect",
        json=reselection_payload("false"),
    )
    assert invalid_response.status_code == 422
    assert queued_reselections == []

    first_reselect_response = client.post(
        f"/api/jobs/{created['jobId']}/clip-plan/reselect",
        json=reselection_payload(False),
    )
    assert first_reselect_response.status_code == 202
    with next(app.dependency_overrides[get_db]()) as db:
        stored_job = db.get(Job, created["jobId"])
        assert stored_job is not None
        assert stored_job.settings_json["heatmapIntervalMode"] is False
        assert stored_job.settings_json["shortTopBannerEnabled"] is False
        assert stored_job.settings_json["shortBottomBannerEnabled"] is False
        assert stored_job.settings_json["shortSubtitleYPercent"] is None

    original_write_clip_plan = runner_module.write_clip_plan
    write_attempt_count = 0
    attempted_clip_ids: set[str] = set()

    def fail_final_clip_plan_write(document: Any, output_path: str | Path) -> Path:
        nonlocal write_attempt_count
        write_attempt_count += 1
        if write_attempt_count == 2:
            attempted_clip_ids.update(clip.id for clip in document.clips)
            raise OSError("final clip plan write failed")
        return original_write_clip_plan(document, output_path)

    monkeypatch.setattr(
        runner_module,
        "write_clip_plan",
        fail_final_clip_plan_write,
    )
    with pytest.raises(OSError, match="final clip plan write failed"):
        run_clip_plan_reselection(
            created["jobId"],
            session_factory=lambda: next(app.dependency_overrides[get_db]()),
            paths=storage,
            dependencies=dependencies,
        )
    monkeypatch.undo()

    for name, initial_payload in initial_artifacts.items():
        assert (job_dir / name).read_bytes() == initial_payload
    rolled_back_plan = client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()
    assert rolled_back_plan["settings"]["heatmapIntervalMode"] is True
    assert {clip["id"] for clip in rolled_back_plan["clips"]} == initial_clip_ids
    assert initial_clip_ids - attempted_clip_ids
    for preview_url, expected_payload in initial_preview_payloads.items():
        preview_response = client.get(preview_url)
        assert preview_response.status_code == 200
        assert preview_response.content == expected_payload
    with next(app.dependency_overrides[get_db]()) as db:
        stored_job = db.get(Job, created["jobId"])
        assert stored_job is not None
        assert stored_job.settings_json["heatmapIntervalMode"] is True

    second_reselect_response = client.post(
        f"/api/jobs/{created['jobId']}/clip-plan/reselect",
        json=reselection_payload(False),
    )
    assert second_reselect_response.status_code == 202
    statuses = run_clip_plan_reselection(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )
    assert statuses[-1] == "awaiting_clip_review"

    legacy_candidates = json.loads((job_dir / "candidates.json").read_text(encoding="utf-8"))
    assert legacy_candidates
    assert all(candidate.get("generation_source") != "heatmap_interval" for candidate in legacy_candidates)
    generation_summary = json.loads((job_dir / "candidate_generation_summary.json").read_text(encoding="utf-8"))
    assert generation_summary["by_type"]["normal"].get("strategy") != "heatmap_intervals"
    assert generation_summary["by_type"]["short"].get("strategy") != "heatmap_intervals"
    heatmap_summary = json.loads((job_dir / "heatmap_validation_summary.json").read_text(encoding="utf-8"))
    assert heatmap_summary["interval_mode_requested"] is False
    assert heatmap_summary["interval_mode_applied"] is False
    assert heatmap_summary["selection_behavior"] == "supporting_score"
    revised_plan = client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()
    assert revised_plan["revision"] == 2
    assert revised_plan["settings"]["heatmapIntervalMode"] is False
    with next(app.dependency_overrides[get_db]()) as db:
        stored_job = db.get(Job, created["jobId"])
        assert stored_job is not None
        assert stored_job.settings_json["heatmapIntervalMode"] is False


def test_pipeline_fails_instead_of_falling_back_when_interval_sidecar_is_tampered(
    client: TestClient,
) -> None:
    media = b"fake tamper video"
    sidecar = json.dumps(
        {
            "schema_version": 1,
            "source": {
                "name": "youtube_most_replayed",
                "video_id": "tamper-video",
                "fetched_at": "2026-08-02T03:30:00Z",
                "extractor": "yt-dlp",
                "extractor_version": "2026.07.04",
            },
            "media": {
                "filename": "sample.mp4",
                "sha256": hashlib.sha256(media).hexdigest(),
                "size_bytes": len(media),
            },
            "duration_seconds": 240.0,
            "heatmap_available": True,
            "heatmap": [{"start_time": 150.0, "end_time": 168.0, "value": 1.0}],
        }
    ).encode("utf-8")
    upload = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": ("sample.mp4.heatmap.json", sidecar, "application/json"),
        },
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {"heatmapIntervalMode": True},
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        sidecar_path = storage.resolve_video_heatmap(job.video.id, job.video.stored_path)
    sidecar_path.write_text("{}", encoding="utf-8")

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            probe_metadata=lambda _path: VideoMetadata(
                duration=240.0,
                width=1920,
                height=1080,
                fps=30.0,
                has_audio=True,
            )
        ),
    )

    status = client.get(f"/api/jobs/{created['jobId']}").json()
    assert status["status"] == "failed"
    assert status["error"]["code"] == "heatmap_interval_mode_unavailable"
    summary = json.loads((storage.job_outputs(created["jobId"]) / "heatmap_validation_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "invalid_fallback"
    assert summary["interval_mode_requested"] is True
    assert summary["interval_mode_applied"] is False


@pytest.mark.parametrize(
    ("stored_overlay_mode", "expected_overlay_mode"),
    [(None, "auto"), ("never", "never")],
    ids=["legacy-missing-mode", "explicit-never"],
)
def test_pipeline_uses_exact_manual_ranges_without_scoring_or_boundary_changes(
    client: TestClient,
    stored_overlay_mode: str | None,
    expected_overlay_mode: str,
) -> None:
    media = b"fake video bytes"
    sidecar = json.dumps(
        {
            "schema_version": 1,
            "source": {
                "name": "youtube_most_replayed",
                "video_id": "manual-range-video",
                "fetched_at": "2026-08-02T03:30:00Z",
                "extractor": "yt-dlp",
                "extractor_version": "2026.07.04",
            },
            "media": {
                "filename": "sample.mp4",
                "sha256": hashlib.sha256(media).hexdigest(),
                "size_bytes": len(media),
            },
            "duration_seconds": 240.0,
            "heatmap_available": True,
            "heatmap": [{"start_time": 0.0, "end_time": 240.0, "value": 0.6}],
        }
    ).encode("utf-8")
    upload = client.post(
        "/api/videos/upload",
        files={
            "file": ("sample.mp4", media, "video/mp4"),
            "heatmap": ("sample.mp4.heatmap.json", sidecar, "application/json"),
        },
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 2,
                "normalClipTimeRanges": [
                    {"startSeconds": 5, "endSeconds": 55},
                ],
                "shortClipTimeRanges": [
                    {"startSeconds": 60, "endSeconds": 75},
                    {"startSeconds": 150, "endSeconds": 180},
                ],
                "heatmapIntervalMode": True,
                "useOpenAIScoring": True,
                "enableBoundaryRefinement": True,
                "burnSubtitles": True,
                "requireClipPlanReview": True,
                "requireSubtitleReview": True,
                "shortOverlayTitleMode": "never",
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        settings = dict(job.settings_json or {})
        if stored_overlay_mode is None:
            settings.pop("shortOverlayTitleMode", None)
        else:
            settings["shortOverlayTitleMode"] = stored_overlay_mode
        job.settings_json = settings
        db.commit()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    preview_render_calls: list[tuple[str, float, float]] = []
    preview_render_details: list[dict[str, Any]] = []

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        preview_render_details.append(dict(kwargs))
        preview_render_calls.append(
            (
                Path(output_path).name,
                float(kwargs["start"]),
                float(kwargs["duration"]),
            )
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"preview")
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        subtitle_review_preview_renderer=fake_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    selected = json.loads((storage.job_outputs(created["jobId"]) / "selected_clips.json").read_text(encoding="utf-8"))
    assert [(clip["start"], clip["end"], clip["selection_reason"]) for clip in selected["normalClips"]] == [
        (5.0, 55.0, "manual_time_range")
    ]
    assert [(clip["start"], clip["end"], clip["selection_reason"]) for clip in selected["shorts"]] == [
        (60.0, 75.0, "manual_time_range"),
        (150.0, 180.0, "manual_time_range"),
    ]
    assert all(clip["boundary_refinement_reason"] == "manual_time_range_locked" for clip in [*selected["normalClips"], *selected["shorts"]])
    assert all(clip["heatmap_value"] == 0.6 for clip in [*selected["normalClips"], *selected["shorts"]])
    assert not (storage.job_outputs(created["jobId"]) / "openai_scoring_summary.json").exists()
    assert visited_statuses[-1] == "awaiting_clip_review"
    output_dir = storage.job_outputs(created["jobId"])
    transcript_before = (output_dir / "transcript_segments.json").read_bytes()
    assert not (output_dir / "subtitle_review.json").exists()

    plan_response = client.get(f"/api/jobs/{created['jobId']}/clip-plan")
    assert plan_response.status_code == 200
    plan = plan_response.json()
    assert plan["state"] == "awaiting_review"
    assert plan["revision"] == 1
    assert plan["sourceDuration"] == 240.0
    assert [(clip["start"], clip["end"]) for clip in plan["clips"]] == [
        (5.0, 55.0),
        (60.0, 75.0),
        (150.0, 180.0),
    ]
    assert all(clip["previewVideoUrl"] for clip in plan["clips"])
    assert client.get(plan["clips"][0]["previewVideoUrl"]).content == b"preview"
    assert len(preview_render_calls) == 3
    transcript_preview = client.get(
        (f"/api/jobs/{created['jobId']}/clip-plan/clips/{plan['clips'][0]['id']}/transcript-segments"),
        params={"start": 2, "end": 58},
    )
    assert transcript_preview.status_code == 200
    assert [(segment["start"], segment["end"], segment["text"]) for segment in transcript_preview.json()] == [
        (0.0, 30.0, "why automation mistakes matter before launch"),
        (
            35.0,
            80.0,
            "how teams can fix the process with a clear checklist",
        ),
    ]
    invalid_transcript_preview = client.get(
        (f"/api/jobs/{created['jobId']}/clip-plan/clips/{plan['clips'][0]['id']}/transcript-segments"),
        params={"start": 58, "end": 2},
    )
    assert invalid_transcript_preview.status_code == 422

    with next(app.dependency_overrides[get_db]()) as db:
        stored_job = db.get(Job, created["jobId"])
        assert stored_job is not None
        settings_before_queue_failure = dict(stored_job.settings_json or {})

    def fail_reselection_enqueue(_job_id: str) -> None:
        raise RuntimeError("queue unavailable")

    app.dependency_overrides[get_enqueue_clip_plan_reselection] = lambda: fail_reselection_enqueue
    failed_reselect_response = client.post(
        f"/api/jobs/{created['jobId']}/clip-plan/reselect",
        json={
            "normalClipSelectionPreset": "important",
            "shortClipSelectionPreset": "funny",
            "normalClipGuidance": "キュー失敗時は保存しない",
            "shortClipGuidance": "",
            "excludeIntroOutro": True,
            "excludePromotionalContent": False,
            "selectionPolicy": "strict_quality",
            "useOpenAIScoring": False,
        },
    )
    assert failed_reselect_response.status_code == 503
    with next(app.dependency_overrides[get_db]()) as db:
        stored_job = db.get(Job, created["jobId"])
        assert stored_job is not None
        assert stored_job.settings_json == settings_before_queue_failure
    assert client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()["state"] == "awaiting_review"

    queued_reselections: list[str] = []
    app.dependency_overrides[get_enqueue_clip_plan_reselection] = lambda: queued_reselections.append
    reselect_response = client.post(
        f"/api/jobs/{created['jobId']}/clip-plan/reselect",
        json={
            "normalClipSelectionPreset": "important",
            "shortClipSelectionPreset": "funny",
            "normalClipGuidance": "結論を優先",
            "shortClipGuidance": "短いリアクションを優先",
            "excludeIntroOutro": True,
            "excludePromotionalContent": True,
            "selectionPolicy": "strict_quality",
            "useOpenAIScoring": False,
        },
    )
    assert reselect_response.status_code == 202
    assert queued_reselections == [created["jobId"]]

    reselection_statuses = run_clip_plan_reselection(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )
    assert reselection_statuses[-1] == "awaiting_clip_review"
    assert (output_dir / "transcript_segments.json").read_bytes() == transcript_before
    assert len(preview_render_calls) == 3
    revised_plan = client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()
    assert revised_plan["revision"] == 2
    assert revised_plan["settings"]["normalClipGuidance"] == "結論を優先"
    assert revised_plan["settings"]["heatmapIntervalMode"] is True
    reselected = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    assert all(clip["heatmap_value"] == 0.6 for clip in [*reselected["normalClips"], *reselected["shorts"]])
    assert client.get(f"/api/jobs/{created['jobId']}").json()["details"]["clipPlanRevision"] == 2

    invalid_boundary = client.patch(
        (f"/api/jobs/{created['jobId']}/clip-plan/clips/{revised_plan['clips'][0]['id']}/boundary"),
        json={"start": 2, "end": 241},
    )
    assert invalid_boundary.status_code == 422

    def fail_boundary_enqueue(
        _job_id: str,
        _clip_id: str,
        _start: float,
        _end: float,
    ) -> None:
        raise RuntimeError("queue unavailable")

    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: fail_boundary_enqueue
    failed_boundary_response = client.patch(
        (f"/api/jobs/{created['jobId']}/clip-plan/clips/{revised_plan['clips'][0]['id']}/boundary"),
        json={"start": 2, "end": 58},
    )
    assert failed_boundary_response.status_code == 503
    assert client.get(f"/api/jobs/{created['jobId']}").json()["status"] == ("awaiting_clip_review")
    assert client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()["state"] == "awaiting_review"

    queued_boundary_updates: list[tuple[str, str, float, float]] = []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: (
        lambda job_id, clip_id, start, end: queued_boundary_updates.append((job_id, clip_id, start, end))
    )
    adjusted_clip_id = revised_plan["clips"][0]["id"]
    boundary_response = client.patch(
        f"/api/jobs/{created['jobId']}/clip-plan/clips/{adjusted_clip_id}/boundary",
        json={"start": 2, "end": 58},
    )
    assert boundary_response.status_code == 202
    assert boundary_response.json()["status"] == "preparing_clip_review"
    assert queued_boundary_updates == [(created["jobId"], adjusted_clip_id, 2.0, 58.0)]

    boundary_statuses = run_clip_plan_boundary_update(
        created["jobId"],
        adjusted_clip_id,
        2.0,
        58.0,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )
    assert boundary_statuses == [
        "preparing_clip_review",
        "awaiting_clip_review",
    ]
    adjusted_plan = client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()
    adjusted_item = next(clip for clip in adjusted_plan["clips"] if clip["id"] == adjusted_clip_id)
    assert (adjusted_item["start"], adjusted_item["end"]) == (2.0, 58.0)
    assert adjusted_item["duration"] == 56.0
    assert adjusted_item["recommendedStart"] == 5.0
    assert adjusted_item["recommendedEnd"] == 55.0
    assert adjusted_item["manuallyAdjusted"] is True
    selected_after_boundary = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    assert (
        selected_after_boundary["normalClips"][0]["start"],
        selected_after_boundary["normalClips"][0]["end"],
    ) == (2.0, 58.0)
    assert selected_after_boundary["normalClips"][0]["clip_plan_boundary_adjusted"] is True
    assert len(preview_render_calls) == 4
    assert preview_render_calls[-1][1:] == (2.0, 56.0)

    short_clip = next(clip for clip in adjusted_plan["clips"] if clip["type"] == "short")
    queued_hook_updates: list[tuple[str, str, float | None, float | None]] = []
    app.dependency_overrides[get_enqueue_clip_plan_hook_scene_update] = lambda: (
        lambda job_id, clip_id, start, end: queued_hook_updates.append((job_id, clip_id, start, end))
    )
    hook_response = client.patch(
        (f"/api/jobs/{created['jobId']}/clip-plan/clips/{short_clip['id']}/hook-scene"),
        json={"start": 68, "end": 70},
    )
    assert hook_response.status_code == 202
    assert queued_hook_updates == [(created["jobId"], short_clip["id"], 68.0, 70.0)]

    hook_statuses = run_clip_plan_hook_scene_update(
        created["jobId"],
        short_clip["id"],
        68.0,
        70.0,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )
    assert hook_statuses == [
        "preparing_clip_review",
        "awaiting_clip_review",
    ]
    hook_plan = client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()
    hook_item = next(clip for clip in hook_plan["clips"] if clip["id"] == short_clip["id"])
    assert (hook_item["hookSceneStart"], hook_item["hookSceneEnd"]) == (
        68.0,
        70.0,
    )
    assert preview_render_details[-1]["hook_start"] == 68.0
    assert preview_render_details[-1]["hook_duration"] == 2.0
    selected_after_hook = json.loads((output_dir / "selected_clips.json").read_text(encoding="utf-8"))
    assert selected_after_hook["shorts"][0]["hook_scene_start"] == 68.0
    assert selected_after_hook["shorts"][0]["hook_scene_end"] == 70.0

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        settings = dict(job.settings_json or {})
        if stored_overlay_mode is None:
            settings.pop("shortOverlayTitleMode", None)
        else:
            settings["shortOverlayTitleMode"] = stored_overlay_mode
        job.settings_json = settings
        db.commit()
    approve_response = client.post(f"/api/jobs/{created['jobId']}/clip-plan/approve")
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "awaiting_subtitle_review"
    stored_review = json.loads((output_dir / "subtitle_review.json").read_text(encoding="utf-8"))
    assert stored_review["shortOverlayTitleMode"] == expected_overlay_mode
    assert all(clip["overlayTitleExpected"] is True for clip in stored_review["clips"] if clip["type"] == "normal")
    assert all(
        clip["overlayTitleExpected"] is (stored_review["shortTopBannerEnabled"] or expected_overlay_mode != "never")
        for clip in stored_review["clips"]
        if clip["type"] == "short"
    )
    review = client.get(f"/api/jobs/{created['jobId']}/subtitle-review").json()
    assert [(clip["start"], clip["end"]) for clip in review["clips"]] == [
        (2.0, 58.0),
        (60.0, 75.0),
        (150.0, 180.0),
    ]
    reviewed_short = next(clip for clip in review["clips"] if clip["id"] == short_clip["id"])
    assert (reviewed_short["hookSceneStart"], reviewed_short["hookSceneEnd"]) == (
        68.0,
        70.0,
    )


@pytest.mark.parametrize(
    ("stored_overlay_mode", "expected_overlay_mode"),
    [
        (None, "auto"),
        ("never", "never"),
        ("high_quality_only", "high_quality_only"),
    ],
    ids=["legacy-missing-mode", "explicit-never", "high-quality-only"],
)
def test_pipeline_pauses_for_subtitle_review_and_renders_after_confirmation(
    client: TestClient,
    stored_overlay_mode: str | None,
    expected_overlay_mode: str,
) -> None:
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    )
    upload = upload_response.json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": False,
                "burnSubtitles": True,
                "requireSubtitleReview": True,
                "shortOverlayTitleMode": "never",
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        settings = dict(job.settings_json or {})
        if stored_overlay_mode is None:
            settings.pop("shortOverlayTitleMode", None)
        else:
            settings["shortOverlayTitleMode"] = stored_overlay_mode
        job.settings_json = settings
        db.commit()
    short_render_kwargs: list[dict[str, Any]] = []

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    def fake_short_render(
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        short_render_kwargs.append(kwargs)
        return fake_render(input_path, output_path, **kwargs)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=fake_render,
        short_renderer=fake_short_render,
        subtitle_review_preview_renderer=fake_render,
    )

    def render_queued_previews(review_payload: dict[str, Any]) -> dict[str, Any]:
        queued_clips = [clip for clip in review_payload["clips"] if clip["previewState"] != "ready"]
        for clip in queued_clips:
            assert run_subtitle_review_preview(
                created["jobId"],
                clip["id"],
                clip["previewSpecHash"],
                session_factory=lambda: next(app.dependency_overrides[get_db]()),
                paths=storage,
                dependencies=dependencies,
            ) == ["ready"]
        refreshed = client.get(f"/api/jobs/{created['jobId']}/subtitle-review")
        assert refreshed.status_code == 200
        assert all(clip["previewState"] == "ready" for clip in refreshed.json()["clips"])
        return refreshed.json()

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert visited_statuses[-1] == "awaiting_subtitle_review"
    status_payload = client.get(f"/api/jobs/{created['jobId']}").json()
    assert status_payload["status"] == "awaiting_subtitle_review"
    assert status_payload["details"]["subtitleReviewConfirmedClips"] == 0
    assert status_payload["details"]["subtitleReviewTotalClips"] == 2
    assert client.get(f"/api/jobs/{created['jobId']}/results").json()["normalClips"] == []
    assert client.get(f"/api/jobs/{created['jobId']}/source-video").content == b"fake video bytes"

    stored_review = json.loads((storage.job_outputs(created["jobId"]) / "subtitle_review.json").read_text(encoding="utf-8"))
    assert stored_review["shortOverlayTitleMode"] == expected_overlay_mode
    assert all(clip["overlayTitleExpected"] is True for clip in stored_review["clips"] if clip["type"] == "normal")
    assert all(
        clip["overlayTitleExpected"] is (stored_review["shortTopBannerEnabled"] or expected_overlay_mode != "never")
        for clip in stored_review["clips"]
        if clip["type"] == "short"
    )
    review = client.get(f"/api/jobs/{created['jobId']}/subtitle-review").json()
    assert review["shortOverlayTitleMode"] == expected_overlay_mode
    assert all(clip["previewVideoUrl"] for clip in review["clips"])
    assert all(clip["livePreviewVideoUrl"] for clip in review["clips"])
    assert all(clip["livePreviewSpecHash"] for clip in review["clips"])
    settings_updated = client.patch(
        f"/api/jobs/{created['jobId']}/subtitle-review/settings",
        json={
            "shortTopBannerEnabled": True,
            "shortBottomBannerEnabled": True,
        },
    )
    assert settings_updated.status_code == 200
    assert settings_updated.json()["shortTopBannerEnabled"] is True
    assert settings_updated.json()["shortBottomBannerEnabled"] is True
    preview_response = client.get(review["clips"][0]["previewVideoUrl"])
    assert preview_response.status_code == 200
    assert preview_response.headers["content-type"].startswith("video/mp4")
    assert preview_response.content.startswith(b"rendered")
    live_preview_response = client.get(review["clips"][0]["livePreviewVideoUrl"])
    assert live_preview_response.status_code == 200
    assert live_preview_response.headers["content-type"].startswith("video/mp4")
    assert live_preview_response.content.startswith(b"rendered")
    short_clip = next(clip for clip in review["clips"] if clip["type"] == "short")
    content_updated = client.patch(
        f"/api/jobs/{created['jobId']}/subtitle-review/clips/{short_clip['id']}/content",
        json={
            "title": "魚は「耳石」で音を聞く？",
            "hookText": "魚の耳には、本当に「石」が入ってるらしい",
            "hookDurationSeconds": 3.0,
        },
    )
    assert content_updated.status_code == 200
    updated_short = next(clip for clip in content_updated.json()["clips"] if clip["id"] == short_clip["id"])
    assert updated_short["titleEdited"] is True
    assert updated_short["hookText"] == "魚の耳には、本当に「石」が入ってるらしい"
    edited_segment = next(
        (segment for segment in review["segments"] if len(segment["affectedClipIds"]) > 1),
        review["segments"][0],
    )
    updated = client.patch(
        f"/api/jobs/{created['jobId']}/subtitle-review/segments/{edited_segment['id']}",
        json={"text": "ManualEdit"},
    )
    assert updated.status_code == 200
    assert updated.json()["editedSegmentCount"] == 1

    blocked = client.post(f"/api/jobs/{created['jobId']}/subtitle-review/finalize")
    assert blocked.status_code == 409

    review = updated.json()
    queued_clip = next(clip for clip in review["clips"] if clip["previewState"] != "ready")
    preview_blocked = client.post((f"/api/jobs/{created['jobId']}/subtitle-review/clips/{queued_clip['id']}/confirm"))
    assert preview_blocked.status_code == 409
    assert preview_blocked.json()["detail"]["code"] == ("subtitle_review_preview_not_ready")
    review = render_queued_previews(review)
    for clip in review["clips"]:
        response = client.post(f"/api/jobs/{created['jobId']}/subtitle-review/clips/{clip['id']}/confirm")
        assert response.status_code == 200
        review = response.json()
    assert review["confirmedClipCount"] == review["totalClipCount"] == 2

    queued_jobs: list[tuple[str, int]] = []
    app.dependency_overrides[get_enqueue_render_job] = lambda: (
        lambda queued_job_id, render_revision: queued_jobs.append(
            (queued_job_id, render_revision)
        )
    )
    finalized = client.post(f"/api/jobs/{created['jobId']}/subtitle-review/finalize")
    assert finalized.status_code == 202
    assert finalized.json()["status"] == "rendering_normal_clips"
    assert queued_jobs == [(created["jobId"], 1)]

    preview_short_render_count = len(short_render_kwargs)
    resume_statuses = run_subtitle_review_render(
        created["jobId"],
        render_revision=1,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert resume_statuses == [
        "rendering_normal_clips",
        "rendering_shorts",
        "packaging_zip",
        "completed",
    ]
    assert len(short_render_kwargs) == preview_short_render_count + 1
    assert Path(short_render_kwargs[-1]["top_banner_path"]).name == "short_top_banner.png"
    assert Path(short_render_kwargs[-1]["bottom_banner_path"]).name == "short_bottom_banner.png"
    assert client.get(f"/api/jobs/{created['jobId']}").json()["status"] == "completed"
    completed_review = client.get(f"/api/jobs/{created['jobId']}/subtitle-review").json()
    assert completed_review["state"] == "completed"
    assert completed_review["editedSegmentCount"] == 1
    reviewed_transcript = json.loads(
        (storage.job_outputs(created["jobId"]) / "reviewed_transcript_segments.json").read_text(encoding="utf-8")
    )
    assert reviewed_transcript[edited_segment["index"]]["text"] == "ManualEdit"
    ass_text = "\n".join(path.read_text(encoding="utf-8") for path in (storage.job_outputs(created["jobId"]) / "subtitles").rglob("*.ass"))
    assert "ManualEdit" in ass_text
    assert "魚の耳には、本当に「石」が入ってるらしい" in ass_text.replace(r"\N", "")
    selected_clips = json.loads((storage.job_outputs(created["jobId"]) / "selected_clips.json").read_text(encoding="utf-8"))
    rendered_short = selected_clips["shorts"][0]
    assert rendered_short["title"] == "魚は「耳石」で音を聞く？"
    assert rendered_short["title_source"] == "manual_review"
    assert rendered_short["hook_text"] == "魚の耳には、本当に「石」が入ってるらしい"
    assert storage.zip_path(created["jobId"]).is_file()

    first_results = client.get(f"/api/jobs/{created['jobId']}/results").json()
    assert first_results["canReopenForEditing"] is True
    assert len(first_results["normalClips"]) == 1
    assert len(first_results["shorts"]) == 1

    reopened = client.post(f"/api/jobs/{created['jobId']}/subtitle-review/reopen")
    assert reopened.status_code == 200
    reopened_review = reopened.json()
    assert reopened_review["state"] == "awaiting_review"
    assert reopened_review["renderRevision"] == 2
    assert reopened_review["confirmedClipCount"] == 0
    assert all(not clip["confirmed"] for clip in reopened_review["clips"])
    assert client.get(f"/api/jobs/{created['jobId']}").json()["status"] == ("awaiting_subtitle_review")

    reopened_short = next(clip for clip in reopened_review["clips"] if clip["type"] == "short")
    retitled = client.patch(
        (f"/api/jobs/{created['jobId']}/subtitle-review/clips/{reopened_short['id']}/content"),
        json={
            "title": "完成後に変更したタイトル",
            "hookText": "完成後に変更したフック",
            "hookDurationSeconds": 2.5,
        },
    )
    assert retitled.status_code == 200
    reopened_review = retitled.json()

    hook_start = reopened_short["start"] + 1.0
    hook_end = hook_start + 2.0
    queued_hook_updates: list[tuple[str, str, float | None, float | None]] = []
    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = lambda: (
        lambda job_id, clip_id, start, end: queued_hook_updates.append((job_id, clip_id, start, end))
    )
    hook_update = client.patch(
        (f"/api/jobs/{created['jobId']}/subtitle-review/clips/{reopened_short['id']}/hook-scene"),
        json={"start": hook_start, "end": hook_end},
    )
    assert hook_update.status_code == 202
    assert queued_hook_updates == [(created["jobId"], reopened_short["id"], hook_start, hook_end)]

    hook_statuses = run_subtitle_review_hook_scene_update(
        created["jobId"],
        reopened_short["id"],
        hook_start,
        hook_end,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )
    assert hook_statuses == [
        "preparing_subtitle_review",
        "awaiting_subtitle_review",
    ]
    reopened_review = client.get(f"/api/jobs/{created['jobId']}/subtitle-review").json()
    updated_short = next(clip for clip in reopened_review["clips"] if clip["id"] == reopened_short["id"])
    assert updated_short["title"] == "完成後に変更したタイトル"
    assert (updated_short["hookSceneStart"], updated_short["hookSceneEnd"]) == (
        hook_start,
        hook_end,
    )
    assert updated_short["confirmed"] is False
    assert updated_short["previewState"] == "ready"

    for clip in reopened_review["clips"]:
        response = client.post(f"/api/jobs/{created['jobId']}/subtitle-review/clips/{clip['id']}/confirm")
        assert response.status_code == 200
        reopened_review = response.json()

    queued_jobs.clear()
    rerender_queued = client.post(f"/api/jobs/{created['jobId']}/subtitle-review/finalize")
    assert rerender_queued.status_code == 202
    assert queued_jobs == [(created["jobId"], 2)]
    rerender_statuses = run_subtitle_review_render(
        created["jobId"],
        render_revision=2,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )
    assert rerender_statuses[-1] == "completed"

    rerendered_results = client.get(f"/api/jobs/{created['jobId']}/results").json()
    assert rerendered_results["canReopenForEditing"] is True
    assert len(rerendered_results["normalClips"]) == 1
    assert len(rerendered_results["shorts"]) == 1
    assert rerendered_results["shorts"][0]["title"] == "完成後に変更したタイトル"
    rerendered_selection = json.loads((storage.job_outputs(created["jobId"]) / "selected_clips.json").read_text(encoding="utf-8"))
    assert (
        rerendered_selection["shorts"][0]["hook_scene_start"],
        rerendered_selection["shorts"][0]["hook_scene_end"],
    ) == (hook_start, hook_end)
    assert not list(
        (storage.temp / "rr").glob(f"{created['jobId'][-12:]}_r2_*")
    )
    assert not (
        storage.job_outputs(created["jobId"])
        / ".rerender_publication_unresolved"
    ).exists()

    reopened_again = client.post(f"/api/jobs/{created['jobId']}/subtitle-review/reopen").json()
    reopened_again = render_queued_previews(reopened_again)
    for clip in reopened_again["clips"]:
        client.post(f"/api/jobs/{created['jobId']}/subtitle-review/clips/{clip['id']}/confirm")
    client.post(f"/api/jobs/{created['jobId']}/subtitle-review/finalize")

    def failing_render(
        _input_path: str | Path,
        _output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        raise RuntimeError("intentional rerender failure")

    failed_statuses = run_subtitle_review_render(
        created["jobId"],
        render_revision=3,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            normal_renderer=failing_render,
            short_renderer=failing_render,
        ),
    )
    assert failed_statuses == ["rendering_normal_clips", "rendering_shorts"]
    failed_job = client.get(f"/api/jobs/{created['jobId']}").json()
    assert failed_job["status"] == "awaiting_subtitle_review"
    assert failed_job["error"]["code"] == "no_usable_output"
    preserved_results = client.get(f"/api/jobs/{created['jobId']}/results").json()
    assert len(preserved_results["normalClips"]) == 1
    assert len(preserved_results["shorts"]) == 1
    assert preserved_results["shorts"][0]["title"] == "完成後に変更したタイトル"
    assert not (
        storage.job_outputs(created["jobId"])
        / ".rerender_publication_unresolved"
    ).exists()


def test_real_pipeline_can_generate_normal_clip_for_60_second_video_with_short_duration_settings(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 0,
                "normalMinDuration": 20,
                "normalMaxDuration": 60,
                "useOpenAIScoring": False,
                "burnSubtitles": False,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=60.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: short_spoken_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=60.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=fake_render,
        short_renderer=fake_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert visited_statuses == SUCCESS_STATUSES[1:]
    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    assert results_response.status_code == 200
    results = results_response.json()
    assert len(results["normalClips"]) == 1
    assert results["shorts"] == []
    assert results["normalClips"][0]["duration"] == 60.0

    job_dir = storage.outputs / created["jobId"]
    candidate_summary = json.loads((job_dir / "candidate_summary.json").read_text(encoding="utf-8"))
    assert candidate_summary["normal_candidates"] > 0
    assert candidate_summary["selected_below_threshold_backfill_count"] == 1
    selected_summary = json.loads((job_dir / "selected_clips_summary.json").read_text(encoding="utf-8"))
    assert selected_summary["selected_normal_count"] == 1
    assert selected_summary["selected_short_count"] == 0
    assert selected_summary["selected_below_threshold_backfill_count"] == 1
    selected_payload = json.loads((job_dir / "selected_clips.json").read_text(encoding="utf-8"))
    selected_normal = selected_payload["normalClips"][0]
    assert selected_normal["hard_gate_passed"] is True
    assert selected_normal["below_quality_threshold"] is True
    assert selected_normal["quality_warning"] == "below_min_final_score"
    assert selected_normal["selection_reason"] == "backfill_below_quality_threshold"


def test_real_pipeline_openai_failure_falls_back_to_rule_scoring(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": True,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    class BrokenScorer:
        def score(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("OpenAI unavailable")

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=fake_render,
        short_renderer=fake_render,
        openai_scorer=BrokenScorer(),  # type: ignore[arg-type]
    )

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.json()["status"] == "completed"
    scored_payload = json.loads((storage.outputs / created["jobId"] / "scored_candidates.json").read_text(encoding="utf-8"))
    assert any("openai_fallback_rule_score" in item["risk_flags"] for item in scored_payload)
    openai_summary = json.loads((storage.outputs / created["jobId"] / "openai_scoring_summary.json").read_text(encoding="utf-8"))
    assert openai_summary["candidates_sent_to_openai"] > 0
    assert openai_summary["fallback_scores"] > 0
    assert openai_summary["candidates_eligible_for_openai_scoring"] > 0
    assert openai_summary["candidates_selected_for_openai"] > 0
    assert openai_summary["selected_fallback_score_count"] > 0
    assert openai_summary["final_selected_clips_using_fallback_score"]


def test_real_pipeline_openai_failure_can_fail_without_fallback(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 0,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": True,
                "openaiCandidateLimit": 3,
                "openaiFallbackToRuleScore": False,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    class BrokenScorer:
        model = "gpt-test"

        def score(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("OpenAI unavailable")

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        openai_scorer=BrokenScorer(),  # type: ignore[arg-type]
    )

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    payload = status_response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "openai_scoring_failed"
    assert "candidates_sent_to_openai" in payload["error"]["message"]


def test_real_pipeline_fixture_transcript_completes_without_transcriber(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "e2eFixtureTranscript": True,
                "normalClipCount": 0,
                "shortCount": 1,
                "shortMinDuration": 20,
                "shortMaxDuration": 25,
                "shortStepSeconds": 5,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "useOpenAIScoring": False,
                "burnSubtitles": False,
                "normalizeAudio": False,
                "shortLayout": "center_crop",
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fail_if_transcribed(_wav_path: str | Path) -> list[TranscriptSegment]:
        raise AssertionError("fixture transcript mode must not call the transcriber")

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=25.0,
            width=320,
            height=180,
            fps=10.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=fail_if_transcribed,
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=25.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        short_renderer=fake_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert visited_statuses == SUCCESS_STATUSES[1:]
    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.json()["status"] == "completed"

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    results = results_response.json()
    assert results["normalClips"] == []
    assert len(results["shorts"]) == 1
    assert client.get(results["shorts"][0]["downloadUrl"]).content.startswith(b"rendered short_")

    transcript_payload = json.loads((storage.outputs / created["jobId"] / "transcript_segments.json").read_text(encoding="utf-8"))
    assert transcript_payload[0]["text"].startswith("Why automation mistakes matter before launch.")
    transcript_summary = json.loads((storage.outputs / created["jobId"] / "transcript_summary.json").read_text(encoding="utf-8"))
    assert transcript_summary["transcription_engine"] == "e2e_fixture"
    assert transcript_summary["transcription_model"] == "fixture"
    assert transcript_summary["transcription_language"] == "fixture"
    assert transcript_summary["transcription_runtime"]["actual_device"] == "fixture"
    assert transcript_summary["transcription_runtime"]["actual_compute_type"] == "fixture"
    assert transcript_summary["used_fixture_transcript"] is True
    assert not (storage.temp / created["jobId"]).exists()


def test_real_pipeline_reports_selection_failure_before_rendering(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    render_calls: list[str] = []

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def unexpected_render(
        _input_path: str | Path,
        _output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        render_calls.append("called")
        raise AssertionError("render must not run when selection is empty")

    monkeypatch.setattr(
        runner_module,
        "select_candidates",
        lambda *_args, **_kwargs: CandidateSelection(),
    )
    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=unexpected_render,
        short_renderer=unexpected_render,
    )

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    payload = client.get(f"/api/jobs/{created['jobId']}").json()
    assert payload["status"] == "failed"
    assert payload["error"] == {
        "code": "no_usable_selection",
        "message": "分析は完了しましたが、選定基準を満たす切り抜き候補がありませんでした。",
    }
    assert render_calls == []


def test_real_pipeline_marks_failed_without_unhandled_exception_when_no_output_is_usable(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def failing_render(
        _input_path: str | Path,
        _output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        raise RuntimeError("all renders failed")

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: fake_transcript(),
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=failing_render,
        short_renderer=failing_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "no_usable_output"
    assert visited_statuses[-1] == "rendering_shorts"
    assert not (storage.temp / created["jobId"]).exists()

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        assert job.error_message == "Selected clips did not produce usable rendered output."
    job_dir = storage.outputs / created["jobId"]
    for name in SUMMARY_FILENAMES:
        assert (job_dir / name).is_file()
    rejection_summary = json.loads((job_dir / "rejection_summary.json").read_text(encoding="utf-8"))
    assert rejection_summary["render_failure_count"] == 2
    assert rejection_summary["render_failures_by_type"] == {"normal": 1, "short": 1}
    selected_summary = json.loads((job_dir / "selected_clips_summary.json").read_text(encoding="utf-8"))
    assert selected_summary["selected_normal_count"] == 1
    assert selected_summary["selected_short_count"] == 1


def test_real_pipeline_marks_failed_for_missing_audio_without_unhandled_exception(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post("/api/jobs", json={"videoId": upload["videoId"], "settings": {}}).json()
    storage = app.dependency_overrides[get_storage_paths]()
    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=120.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=False,
        )
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    payload = status_response.json()
    assert visited_statuses == ["probing"]
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "missing_audio"
    assert "no audio track" in payload["error"]["message"]
    assert not (storage.temp / created["jobId"]).exists()


def test_real_pipeline_rejects_mismatched_media_stream_durations_before_audio_extraction(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post("/api/jobs", json={"videoId": upload["videoId"], "settings": {}}).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fail_if_audio_extracted(_input_path: str | Path, _output_path: str | Path) -> Path:
        raise AssertionError("mismatched streams must fail before audio extraction")

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=1301.47,
            width=1920,
            height=1080,
            fps=60.0,
            has_audio=True,
            video_stream_duration=1301.47,
            audio_stream_duration=3832.08,
            container_duration=3832.08,
        ),
        extract_audio=fail_if_audio_extracted,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    payload = client.get(f"/api/jobs/{created['jobId']}").json()
    assert visited_statuses == ["probing"]
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "media_stream_duration_mismatch"
    assert "映像 21:41 / 音声 1:03:52" in payload["error"]["message"]
    assert "再ダウンロード" in payload["error"]["message"]
    assert not (storage.temp / created["jobId"]).exists()


def test_real_pipeline_fails_silent_audio_before_transcription_and_candidates(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fail_if_transcribed(_wav_path: str | Path) -> list[TranscriptSegment]:
        raise AssertionError("silent audio must fail before transcription")

    def fail_if_scene_detected(_input_path: str | Path) -> list[SceneSegment]:
        raise AssertionError("silent audio must fail before scene detection")

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=120.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=fail_if_transcribed,
        detect_scenes=fail_if_scene_detected,
        detect_silence=lambda _path, _duration: [SilenceSegment(start=0.0, end=120.0, duration=120.0)],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.0,
        ),
        detect_black_screen=lambda _path: [],
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    payload = status_response.json()
    assert visited_statuses == ["probing", "extracting_audio"]
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "audio_silent_or_unusable"
    assert payload["details"]["duration"] == 120.0
    assert payload["details"]["silence_ratio"] == 1.0
    assert payload["details"]["speech_seconds"] == 0.0
    assert payload["details"]["speech_density"] == 0.0
    assert payload["details"]["volume_peak"] == 0.0
    job_dir = storage.outputs / created["jobId"]
    assert (job_dir / "audio_features.json").is_file()
    for name in SUMMARY_FILENAMES:
        assert (job_dir / name).is_file()
    audio_summary = json.loads((job_dir / "audio_feature_summary.json").read_text(encoding="utf-8"))
    assert audio_summary["silence_ratio"] == 1.0
    assert audio_summary["speech_seconds"] == 0.0
    transcript_summary = json.loads((job_dir / "transcript_summary.json").read_text(encoding="utf-8"))
    assert transcript_summary["segment_count"] == 0
    candidate_summary = json.loads((job_dir / "candidate_summary.json").read_text(encoding="utf-8"))
    assert candidate_summary["total_candidates"] == 0
    assert not (job_dir / "transcript_segments.json").exists()
    assert not (job_dir / "candidates.json").exists()
    assert not (storage.temp / created["jobId"]).exists()


def test_initial_codex_selection_bypasses_legacy_generation_and_scoring(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("codex-source.mp4", b"fake media", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "initialSelectionProvider": "codex",
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "enableBoundaryRefinement": False,
                "burnSubtitles": False,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    selector_calls: list[dict[str, Any]] = []

    normal = Candidate(
        id="codex-normal",
        type="normal",
        start=0.0,
        end=100.0,
        duration=100.0,
        transcript_text="why automation mistakes matter before launch",
        rule_score=95.0,
        ai_score=95.0,
        final_score=95.0,
        should_use=True,
        reason="Codex selected a complete topic.",
        selection_reason="codex_direct",
        used_ai_score=True,
    )
    short = Candidate(
        id="codex-short",
        type="short",
        start=145.0,
        end=175.0,
        duration=30.0,
        transcript_text="another complete section for a normal clip selection",
        rule_score=92.0,
        ai_score=92.0,
        final_score=92.0,
        should_use=True,
        reason="Codex selected a concise section.",
        selection_reason="codex_direct",
        used_ai_score=True,
    )

    def fake_codex_selector(**kwargs: Any) -> CodexInitialSelectionResult:
        selector_calls.append(kwargs)
        selection = CandidateSelection(
            normalClips=[normal],
            shorts=[short],
            selectionPolicy="strict_quality",
            requestedNormalCount=1,
            requestedShortCount=1,
        )
        return CodexInitialSelectionResult(
            selection=selection,
            candidates=[normal, short],
            summary={
                "provider": "codex",
                "status": "completed",
                "fallbackUsed": False,
                "error": None,
                "requestedNormalCount": 1,
                "requestedShortCount": 1,
                "selectedNormalCount": 1,
                "selectedShortCount": 1,
                "threadId": "019fc2f6-d3cc-72b1-a68e-cd810a2e1fa6",
            },
        )

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("legacy selection path must not run")

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"rendered")
        return Path(output_path)

    monkeypatch.setattr(runner_module, "generate_normal_candidates_with_summary", forbidden)
    monkeypatch.setattr(runner_module, "generate_short_candidates_with_summary", forbidden)
    monkeypatch.setattr(runner_module, "_score_candidate_list", forbidden)

    visited = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            probe_metadata=lambda _path: VideoMetadata(
                duration=240.0,
                width=1920,
                height=1080,
                fps=30.0,
                has_audio=True,
            ),
            extract_audio=fake_extract,
            transcribe_audio=lambda _path: fake_transcript(),
            detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
            detect_silence=lambda _path, _duration: [],
            compute_audio_features=lambda _path, duration, segments: build_audio_features(
                duration=duration,
                silence_segments=segments,
                volume_peak=0.5,
            ),
            detect_black_screen=lambda _path: [],
            normal_renderer=fake_render,
            short_renderer=fake_render,
            codex_initial_selector=fake_codex_selector,
        ),
    )

    assert len(selector_calls) == 1
    assert selector_calls[0]["job_id"] == created["jobId"]
    assert "scoring_candidates" not in visited
    selected = json.loads((storage.job_outputs(created["jobId"]) / "selected_clips.json").read_text(encoding="utf-8"))
    assert selected["normalClips"][0]["start"] == 0.0
    assert selected["shorts"][0]["start"] == 145.0
    summary = json.loads((storage.job_outputs(created["jobId"]) / "codex_initial_selection_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "completed"
    status = client.get(f"/api/jobs/{created['jobId']}").json()
    assert status["details"]["codexInitialSelectionSelectedNormalCount"] == 1
    assert status["details"]["codexInitialSelectionSelectedShortCount"] == 1


def test_codex_short_pool_rejects_duplicate_and_backfills_after_refinement() -> None:
    first = Candidate(
        id="short-first",
        type="short",
        start=0,
        end=20,
        duration=20,
        transcript_text="最初の独立した見せ場",
        final_score=95,
        moment_key="first",
        parent_start=0,
        parent_end=40,
        evidence_segment_ids=["seg_1"],
    )
    duplicate = Candidate(
        id="short-shifted",
        type="short",
        start=18.5,
        end=38.5,
        duration=20,
        transcript_text="同じ場面を少しずらした候補",
        final_score=94,
        moment_key="first-shifted",
        parent_start=0,
        parent_end=45,
        evidence_segment_ids=["seg_1"],
    )
    replacement = Candidate(
        id="short-replacement",
        type="short",
        start=60,
        end=80,
        duration=20,
        transcript_text="別の独立した見せ場",
        final_score=90,
        moment_key="replacement",
        parent_start=50,
        parent_end=90,
        evidence_segment_ids=["seg_2"],
    )
    result = CodexInitialSelectionResult(
        selection=CandidateSelection(
            shorts=[first, replacement],
            selectionPolicy="strict_quality",
            requestedShortCount=2,
        ),
        candidates=[first, duplicate, replacement],
        summary={},
    )

    selection, scored, diversity = _codex_selection_with_diverse_refined_shorts(
        result,
        transcript_segments=[],
        silence_segments=[],
        scene_segments=[],
        settings={
            "enableBoundaryRefinement": False,
            "normalClipCount": 0,
            "shortCount": 2,
            "selectionPolicy": "strict_quality",
        },
        timeline_duration=100,
    )

    assert [candidate.id for candidate in selection.shorts] == [
        "short-first",
        "short-replacement",
    ]
    assert {candidate.id for candidate in scored} == {
        "short-first",
        "short-shifted",
        "short-replacement",
    }
    assert diversity.unfilled_count == 0
    assert selection.unfilled_requested_counts["short"] == 0
    assert any(rejection.candidate_id == "short-shifted" for rejection in selection.rejected_candidates)


def test_codex_short_pool_does_not_pad_when_distinct_moments_are_insufficient() -> None:
    first = Candidate(
        id="short-first",
        type="short",
        start=0,
        end=20,
        duration=20,
        transcript_text="同じ見せ場",
        final_score=95,
        moment_key="same-moment",
        parent_start=0,
        parent_end=40,
    )
    duplicate = first.model_copy(
        update={
            "id": "short-duplicate",
            "start": 40,
            "end": 60,
            "refined_start": None,
            "refined_end": None,
            "parent_start": 30,
            "parent_end": 70,
            "final_score": 90,
        }
    )
    result = CodexInitialSelectionResult(
        selection=CandidateSelection(
            shorts=[first],
            selectionPolicy="fill_requested",
            requestedShortCount=2,
        ),
        candidates=[first, duplicate],
        summary={},
    )

    selection, _, diversity = _codex_selection_with_diverse_refined_shorts(
        result,
        transcript_segments=[],
        silence_segments=[],
        scene_segments=[],
        settings={
            "enableBoundaryRefinement": False,
            "normalClipCount": 0,
            "shortCount": 2,
            "selectionPolicy": "fill_requested",
        },
        timeline_duration=80,
    )

    assert [candidate.id for candidate in selection.shorts] == ["short-first"]
    assert diversity.unfilled_count == 1
    assert selection.unfilled_requested_counts["short"] == 1
    assert selection.unfilled_reason_counts["short"]["insufficient_distinct_moments"] == 1


def test_real_pipeline_fails_unusable_transcript_before_candidates(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fail_if_scene_detected(_input_path: str | Path) -> list[SceneSegment]:
        raise AssertionError("unusable transcript must fail before scene detection")

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=120.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: [
            TranscriptSegment(start=0.0, end=10.0, text="You You You You You", confidence=0.95),
            TranscriptSegment(start=10.0, end=20.0, text="You You You You You", confidence=0.95),
        ],
        detect_scenes=fail_if_scene_detected,
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    payload = status_response.json()
    assert visited_statuses == ["probing", "extracting_audio", "transcribing"]
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "transcript_unusable"
    assert "repeated_low_information_text" in payload["error"]["message"]
    assert payload["details"]["segment_count"] == 2
    assert payload["details"]["total_speech_duration"] == 20.0
    assert payload["details"]["average_confidence"] == 0.95
    job_dir = storage.outputs / created["jobId"]
    assert (job_dir / "transcript_segments.json").is_file()
    for name in SUMMARY_FILENAMES:
        assert (job_dir / name).is_file()
    transcript_summary = json.loads((job_dir / "transcript_summary.json").read_text(encoding="utf-8"))
    assert transcript_summary["segment_count"] == 2
    assert transcript_summary["average_confidence"] == 0.95
    candidate_summary = json.loads((job_dir / "candidate_summary.json").read_text(encoding="utf-8"))
    assert candidate_summary["total_candidates"] == 0
    assert not (job_dir / "candidates.json").exists()
    assert not (storage.temp / created["jobId"]).exists()


def test_real_pipeline_retries_repeated_turbo_transcript_with_small_on_cuda(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "heatmapIntervalMode": False,
                "useOpenAIScoring": False,
                "subtitleCorrectionMode": "off",
                "whisperModelSize": "turbo",
                "transcriptionLanguage": "ja",
                "transcriptionDevice": "cuda",
                "transcriptionComputeType": "float16",
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    engine_calls: list[dict[str, Any]] = []

    class FakeEngine:
        def __init__(self, **kwargs: Any) -> None:
            self.options = kwargs

        @property
        def diagnostics(self) -> dict[str, Any]:
            return {
                "requested_device": self.options["device"],
                "actual_device": "cuda",
                "requested_compute_type": self.options["compute_type"],
                "actual_compute_type": "float16",
                "model": self.options["model_size"],
                "language": self.options["language"],
                "gpu_name": "Fake GPU",
                "gpu_memory_total_mb": 16384,
                "model_load_seconds": 1.0,
                "transcription_seconds": 2.0,
                "peak_vram_mb": (4800 if self.options["model_size"] == "turbo" else 6100),
                "fallback_used": False,
                "fallback_reason": None,
            }

        def transcribe(self, _path: str | Path) -> list[TranscriptSegment]:
            engine_calls.append(self.options)
            if self.options["model_size"] == "turbo":
                return [
                    TranscriptSegment(
                        start=float(index * 10),
                        end=float(index * 10 + 8),
                        text="ご視聴ありがとうございました",
                        confidence=0.9,
                    )
                    for index in range(6)
                ]
            return fake_transcript()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(b"rendered")
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=240.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcription_engine_factory=FakeEngine,
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=240.0)],
        detect_silence=lambda _path, _duration: [
            SilenceSegment(start=30.0, end=35.0, duration=5.0),
            SilenceSegment(start=80.0, end=85.0, duration=5.0),
            SilenceSegment(start=140.0, end=145.0, duration=5.0),
        ],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=fake_render,
        short_renderer=fake_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert visited_statuses == SUCCESS_STATUSES[1:]
    assert [call["model_size"] for call in engine_calls] == ["turbo", "small"]
    job_dir = storage.outputs / created["jobId"]
    primary = json.loads((job_dir / "primary_raw_transcript_segments.json").read_text(encoding="utf-8"))
    assert len(primary) == 6
    assert {segment["text"] for segment in primary} == {"ご視聴ありがとうございました"}
    transcript_summary = json.loads((job_dir / "transcript_summary.json").read_text(encoding="utf-8"))
    assert transcript_summary["transcription_model"] == "small"
    runtime = transcript_summary["transcription_runtime"]
    assert runtime["requested_model"] == "turbo"
    assert runtime["actual_model"] == "small"
    assert runtime["fallback_used"] is False
    assert runtime["fallback_reason"] is None
    assert runtime["quality_fallback_used"] is True
    assert runtime["quality_fallback_reason"] == "primary_transcript_unusable"
    assert runtime["primary_transcript_quality"]["reasons"] == ["repeated_segment_text"]
    assert runtime["fallback_transcript_quality"]["reasons"] == []
    assert runtime["transcription_seconds"] == 4.0
    assert runtime["peak_vram_mb"] == 6100


@pytest.mark.parametrize("small_fallback_fails", [False, True])
def test_real_pipeline_recovers_long_form_transcript_without_user_action(
    client: TestClient,
    small_fallback_fails: bool,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake long video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
                "normalMinDuration": 90,
                "normalMaxDuration": 180,
                "shortMinDuration": 20,
                "shortMaxDuration": 75,
                "minFinalScore": 0,
                "rejectIncompleteSentence": False,
                "heatmapIntervalMode": False,
                "useOpenAIScoring": False,
                "subtitleCorrectionMode": "off",
                "whisperModelSize": "turbo",
                "transcriptionDevice": "cuda",
                "transcriptionComputeType": "float16",
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    engine_calls: list[tuple[str, str]] = []

    broken_segments = [
        TranscriptSegment(
            start=float(index * 10),
            end=float(index * 10 + 4),
            text="えー" if index < 25 else "ご視聴ありがとうございました",
            confidence=0.32,
        )
        for index in range(45)
    ]
    broken_segments.extend(
        TranscriptSegment(
            start=float((index + 45) * 10),
            end=float((index + 45) * 10 + 4),
            text=f"短い固有発話{index}",
            confidence=0.4,
        )
        for index in range(16)
    )
    recovered_segments = [
        TranscriptSegment(
            start=float(index * 55),
            end=float(index * 55 + 45),
            text=f"第{index}区間では長尺動画の具体的な話題と結論を十分な長さで説明します",
            confidence=0.9,
        )
        for index in range(60)
    ]

    class FakeEngine:
        def __init__(self, **kwargs: Any) -> None:
            self.options = kwargs
            self.chunked = False

        @property
        def diagnostics(self) -> dict[str, Any]:
            return {
                "requested_device": self.options["device"],
                "actual_device": "cuda",
                "requested_compute_type": self.options["compute_type"],
                "actual_compute_type": "float16",
                "model": self.options["model_size"],
                "language": self.options["language"],
                "model_load_seconds": 1.0,
                "transcription_seconds": 2.0,
                "peak_vram_mb": 6100,
                "fallback_used": False,
                "fallback_reason": None,
                "chunked": self.chunked,
                "chunk_count": 43 if self.chunked else None,
            }

        def transcribe(self, _path: str | Path) -> list[TranscriptSegment]:
            engine_calls.append(("whole", self.options["model_size"]))
            return broken_segments

        def transcribe_chunked(
            self,
            _path: str | Path,
            **kwargs: Any,
        ) -> list[TranscriptSegment]:
            self.chunked = True
            engine_calls.append(("chunked", self.options["model_size"]))
            progress_callback = kwargs.get("progress_callback")
            if progress_callback is not None:
                progress_callback(1, 2)
                progress_callback(2, 2)
            if self.options["model_size"] == "small" and small_fallback_fails:
                raise RuntimeError("small chunk transcription failed")
            return broken_segments if self.options["model_size"] == "turbo" else recovered_segments

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    def fake_render(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        Path(output_path).write_bytes(b"rendered")
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=3600.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcription_engine_factory=FakeEngine,
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=3600.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
        normal_renderer=fake_render,
        short_renderer=fake_render,
    )

    visited_statuses = run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    assert engine_calls == [
        ("whole", "turbo"),
        ("chunked", "turbo"),
        ("chunked", "small"),
    ]
    job_dir = storage.outputs / created["jobId"]
    assert (job_dir / "primary_raw_transcript_segments.json").is_file()
    assert (job_dir / "chunked_raw_transcript_segments.json").is_file()
    recovery_summary = json.loads((job_dir / "transcription_recovery_summary.json").read_text(encoding="utf-8"))
    if small_fallback_fails:
        payload = client.get(f"/api/jobs/{created['jobId']}").json()
        assert payload["status"] == "failed"
        assert payload["error"]["code"] == "transcription_quality_fallback_failed"
        assert recovery_summary["recovery_failed"] is True
        assert recovery_summary["runtime"]["selected_attempt"] is None
        assert recovery_summary["runtime"]["failed_attempt"] == "small_ja_chunked"
        assert [attempt["name"] for attempt in recovery_summary["attempts"]] == [
            "primary_whole_file",
            "chunked_same_model",
            "small_ja_chunked",
        ]
        assert [attempt["status"] for attempt in recovery_summary["attempts"]] == [
            "completed_unusable",
            "completed_unusable",
            "failed",
        ]
        assert recovery_summary["attempts"][-1]["error_type"] == "RuntimeError"
        assert "transcription_recovery_summary.json" in payload["error"]["message"]
        return

    assert visited_statuses == SUCCESS_STATUSES[1:]
    assert recovery_summary["runtime"]["selected_attempt"] == "small_ja_chunked"
    assert recovery_summary["selected_quality"]["reasons"] == []
    transcript_summary = json.loads((job_dir / "transcript_summary.json").read_text(encoding="utf-8"))
    runtime = transcript_summary["transcription_runtime"]
    assert transcript_summary["transcription_model"] == "small"
    assert runtime["requested_model"] == "turbo"
    assert runtime["actual_model"] == "small"
    assert runtime["fallback_transcription"]["chunked"] is True
    assert runtime["primary_transcription"]["chunked_quality_fallback_used"] is True
    assert "clustered_repeated_segment_text" in runtime["primary_transcript_quality"]["reasons"]
    assert "long_form_transcript_too_sparse" in runtime["primary_transcript_quality"]["reasons"]
    assert runtime["fallback_transcript_quality"]["reasons"] == []


def test_real_pipeline_rejects_repeated_japanese_transcript_without_cuda_fallback(
    client: TestClient,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=120.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: [
            TranscriptSegment(
                start=float(index * 10),
                end=float(index * 10 + 8),
                text="ご視聴ありがとうございました",
                confidence=0.9,
            )
            for index in range(6)
        ],
        detect_scenes=lambda _path: [],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
    )

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    payload = client.get(f"/api/jobs/{created['jobId']}").json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "transcript_unusable"
    assert "repeated_segment_text" in payload["error"]["message"]
    assert '"dominant_segment_count": 6' in payload["error"]["message"]
    assert '"dominant_segment_ratio": 1.0' in payload["error"]["message"]
    assert not (storage.outputs / created["jobId"] / "primary_raw_transcript_segments.json").exists()


def test_real_pipeline_marks_failed_when_no_candidates_found(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={
            "videoId": upload["videoId"],
            "settings": {
                "normalClipCount": 1,
                "shortCount": 1,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_extract(_input_path: str | Path, output_path: str | Path) -> Path:
        Path(output_path).write_bytes(b"fake wav")
        return Path(output_path)

    dependencies = AutoClipperPipelineDependencies(
        probe_metadata=lambda _path: VideoMetadata(
            duration=10.0,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
        ),
        extract_audio=fake_extract,
        transcribe_audio=lambda _path: [
            TranscriptSegment(
                start=0.0,
                end=10.0,
                text="this transcript is usable but the video is too short for candidates",
            )
        ],
        detect_scenes=lambda _path: [SceneSegment(start=0.0, end=10.0)],
        detect_silence=lambda _path, _duration: [],
        compute_audio_features=lambda _path, duration, segments: build_audio_features(
            duration=duration,
            silence_segments=segments,
            volume_peak=0.5,
        ),
        detect_black_screen=lambda _path: [],
    )

    run_autoclipper_job(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )

    status_response = client.get(f"/api/jobs/{created['jobId']}")
    payload = status_response.json()
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "no_candidates_found"
    assert "No clip candidates" in payload["error"]["message"]
    job_dir = storage.outputs / created["jobId"]
    for name in SUMMARY_FILENAMES:
        assert (job_dir / name).is_file()
    candidate_summary = json.loads((job_dir / "candidate_summary.json").read_text(encoding="utf-8"))
    assert candidate_summary["total_candidates"] == 0
