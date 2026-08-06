import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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
)
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import select_candidates
from app.jobs.runner import (
    AutoClipperPipelineDependencies,
    PipelineExpectedError,
    _build_openai_scoring_pool,
    _ensure_selected_candidates_openai_scored,
    _score_candidate_list,
    _transcription_language_setting,
    run_autoclipper_job,
    run_clip_plan_boundary_update,
    run_clip_plan_hook_scene_update,
    run_clip_plan_reselection,
    run_subtitle_review_hook_scene_update,
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
        "video_metadata.json",
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
    assert len(selected_payload["normalClips"]) == 1
    assert len(selected_payload["shorts"]) == 1
    selected_normal = selected_payload["normalClips"][0]
    selected_short = selected_payload["shorts"][0]
    assert selected_normal["title"]
    assert selected_normal["title_source"] == "transcript_fallback"
    assert selected_normal["original_start"] is not None
    assert selected_normal["refined_start"] is not None
    assert selected_normal["boundary_refined"] is not None
    assert selected_short["title"]
    assert selected_short["overlay_title"]
    assert selected_short["title_source"] == "transcript_fallback"
    assert selected_short["original_start"] is not None
    assert selected_short["refined_start"] is not None
    assert selected_short["boundary_refined"] is not None
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
    correction_progress = json.loads(
        (job_dir / "subtitle_correction_progress.json").read_text(encoding="utf-8")
    )
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
    transcript_postprocess_summary = json.loads(
        (job_dir / "transcript_postprocess_summary.json").read_text(encoding="utf-8")
    )
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
    assert "metadata/raw_transcript_segments.json" in names
    assert "metadata/deterministic_transcript_segments.json" in names
    assert "metadata/transcript_correction_summary.json" in names
    assert "metadata/transcript_correction_diff.md" in names
    assert "metadata/subtitle_correction_progress.json" in names
    assert "metadata/transcript_summary.json" in names
    assert "metadata/transcript_postprocess_summary.json" in names
    assert "metadata/selected_clips_summary.json" in names
    assert "normal_01.mp4" not in names
    assert "short_01.ass" not in names


def test_pipeline_uses_exact_manual_ranges_without_scoring_or_boundary_changes(
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
                "shortCount": 2,
                "normalClipTimeRanges": [
                    {"startSeconds": 5, "endSeconds": 55},
                ],
                "shortClipTimeRanges": [
                    {"startSeconds": 60, "endSeconds": 75},
                    {"startSeconds": 150, "endSeconds": 180},
                ],
                "useOpenAIScoring": True,
                "enableBoundaryRefinement": True,
                "burnSubtitles": True,
                "requireClipPlanReview": True,
                "requireSubtitleReview": True,
            },
        },
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

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

    selected = json.loads(
        (storage.job_outputs(created["jobId"]) / "selected_clips.json").read_text(
            encoding="utf-8"
        )
    )
    assert [
        (clip["start"], clip["end"], clip["selection_reason"])
        for clip in selected["normalClips"]
    ] == [(5.0, 55.0, "manual_time_range")]
    assert [
        (clip["start"], clip["end"], clip["selection_reason"])
        for clip in selected["shorts"]
    ] == [
        (60.0, 75.0, "manual_time_range"),
        (150.0, 180.0, "manual_time_range"),
    ]
    assert all(
        clip["boundary_refinement_reason"] == "manual_time_range_locked"
        for clip in [*selected["normalClips"], *selected["shorts"]]
    )
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
        (
            f"/api/jobs/{created['jobId']}/clip-plan/clips/"
            f"{plan['clips'][0]['id']}/transcript-segments"
        ),
        params={"start": 2, "end": 58},
    )
    assert transcript_preview.status_code == 200
    assert [
        (segment["start"], segment["end"], segment["text"])
        for segment in transcript_preview.json()
    ] == [
        (0.0, 30.0, "why automation mistakes matter before launch"),
        (
            35.0,
            80.0,
            "how teams can fix the process with a clear checklist",
        ),
    ]
    invalid_transcript_preview = client.get(
        (
            f"/api/jobs/{created['jobId']}/clip-plan/clips/"
            f"{plan['clips'][0]['id']}/transcript-segments"
        ),
        params={"start": 58, "end": 2},
    )
    assert invalid_transcript_preview.status_code == 422

    with next(app.dependency_overrides[get_db]()) as db:
        stored_job = db.get(Job, created["jobId"])
        assert stored_job is not None
        settings_before_queue_failure = dict(stored_job.settings_json or {})

    def fail_reselection_enqueue(_job_id: str) -> None:
        raise RuntimeError("queue unavailable")

    app.dependency_overrides[get_enqueue_clip_plan_reselection] = (
        lambda: fail_reselection_enqueue
    )
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
    assert client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()[
        "state"
    ] == "awaiting_review"

    queued_reselections: list[str] = []
    app.dependency_overrides[get_enqueue_clip_plan_reselection] = (
        lambda: queued_reselections.append
    )
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
    assert client.get(f"/api/jobs/{created['jobId']}").json()["details"][
        "clipPlanRevision"
    ] == 2

    invalid_boundary = client.patch(
        (
            f"/api/jobs/{created['jobId']}/clip-plan/clips/"
            f"{revised_plan['clips'][0]['id']}/boundary"
        ),
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

    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = (
        lambda: fail_boundary_enqueue
    )
    failed_boundary_response = client.patch(
        (
            f"/api/jobs/{created['jobId']}/clip-plan/clips/"
            f"{revised_plan['clips'][0]['id']}/boundary"
        ),
        json={"start": 2, "end": 58},
    )
    assert failed_boundary_response.status_code == 503
    assert client.get(f"/api/jobs/{created['jobId']}").json()["status"] == (
        "awaiting_clip_review"
    )
    assert client.get(f"/api/jobs/{created['jobId']}/clip-plan").json()[
        "state"
    ] == "awaiting_review"

    queued_boundary_updates: list[tuple[str, str, float, float]] = []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = (
        lambda: lambda job_id, clip_id, start, end: queued_boundary_updates.append(
            (job_id, clip_id, start, end)
        )
    )
    adjusted_clip_id = revised_plan["clips"][0]["id"]
    boundary_response = client.patch(
        f"/api/jobs/{created['jobId']}/clip-plan/clips/{adjusted_clip_id}/boundary",
        json={"start": 2, "end": 58},
    )
    assert boundary_response.status_code == 202
    assert boundary_response.json()["status"] == "preparing_clip_review"
    assert queued_boundary_updates == [
        (created["jobId"], adjusted_clip_id, 2.0, 58.0)
    ]

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
    adjusted_item = next(
        clip for clip in adjusted_plan["clips"] if clip["id"] == adjusted_clip_id
    )
    assert (adjusted_item["start"], adjusted_item["end"]) == (2.0, 58.0)
    assert adjusted_item["duration"] == 56.0
    assert adjusted_item["recommendedStart"] == 5.0
    assert adjusted_item["recommendedEnd"] == 55.0
    assert adjusted_item["manuallyAdjusted"] is True
    selected_after_boundary = json.loads(
        (output_dir / "selected_clips.json").read_text(encoding="utf-8")
    )
    assert (
        selected_after_boundary["normalClips"][0]["start"],
        selected_after_boundary["normalClips"][0]["end"],
    ) == (2.0, 58.0)
    assert selected_after_boundary["normalClips"][0][
        "clip_plan_boundary_adjusted"
    ] is True
    assert len(preview_render_calls) == 4
    assert preview_render_calls[-1][1:] == (2.0, 56.0)

    short_clip = next(
        clip for clip in adjusted_plan["clips"] if clip["type"] == "short"
    )
    queued_hook_updates: list[
        tuple[str, str, float | None, float | None]
    ] = []
    app.dependency_overrides[get_enqueue_clip_plan_hook_scene_update] = (
        lambda: lambda job_id, clip_id, start, end: queued_hook_updates.append(
            (job_id, clip_id, start, end)
        )
    )
    hook_response = client.patch(
        (
            f"/api/jobs/{created['jobId']}/clip-plan/clips/"
            f"{short_clip['id']}/hook-scene"
        ),
        json={"start": 68, "end": 70},
    )
    assert hook_response.status_code == 202
    assert queued_hook_updates == [
        (created["jobId"], short_clip["id"], 68.0, 70.0)
    ]

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
    hook_item = next(
        clip for clip in hook_plan["clips"] if clip["id"] == short_clip["id"]
    )
    assert (hook_item["hookSceneStart"], hook_item["hookSceneEnd"]) == (
        68.0,
        70.0,
    )
    assert preview_render_details[-1]["hook_start"] == 68.0
    assert preview_render_details[-1]["hook_duration"] == 2.0
    selected_after_hook = json.loads(
        (output_dir / "selected_clips.json").read_text(encoding="utf-8")
    )
    assert selected_after_hook["shorts"][0]["hook_scene_start"] == 68.0
    assert selected_after_hook["shorts"][0]["hook_scene_end"] == 70.0

    approve_response = client.post(
        f"/api/jobs/{created['jobId']}/clip-plan/approve"
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "awaiting_subtitle_review"
    review = client.get(f"/api/jobs/{created['jobId']}/subtitle-review").json()
    assert [(clip["start"], clip["end"]) for clip in review["clips"]] == [
        (2.0, 58.0),
        (60.0, 75.0),
        (150.0, 180.0),
    ]
    reviewed_short = next(
        clip for clip in review["clips"] if clip["id"] == short_clip["id"]
    )
    assert (reviewed_short["hookSceneStart"], reviewed_short["hookSceneEnd"]) == (
        68.0,
        70.0,
    )


def test_pipeline_pauses_for_subtitle_review_and_renders_after_confirmation(client: TestClient) -> None:
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
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
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
        subtitle_review_preview_renderer=fake_render,
    )

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

    review = client.get(f"/api/jobs/{created['jobId']}/subtitle-review").json()
    assert all(clip["previewVideoUrl"] for clip in review["clips"])
    preview_response = client.get(review["clips"][0]["previewVideoUrl"])
    assert preview_response.status_code == 200
    assert preview_response.headers["content-type"].startswith("video/mp4")
    assert preview_response.content.startswith(b"rendered")
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
    updated_short = next(
        clip for clip in content_updated.json()["clips"] if clip["id"] == short_clip["id"]
    )
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
    for clip in review["clips"]:
        response = client.post(
            f"/api/jobs/{created['jobId']}/subtitle-review/clips/{clip['id']}/confirm"
        )
        assert response.status_code == 200
        review = response.json()
    assert review["confirmedClipCount"] == review["totalClipCount"] == 2

    queued_jobs: list[str] = []
    app.dependency_overrides[get_enqueue_render_job] = lambda: queued_jobs.append
    finalized = client.post(f"/api/jobs/{created['jobId']}/subtitle-review/finalize")
    assert finalized.status_code == 202
    assert finalized.json()["status"] == "rendering_normal_clips"
    assert queued_jobs == [created["jobId"]]

    resume_statuses = run_subtitle_review_render(
        created["jobId"],
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
    assert client.get(f"/api/jobs/{created['jobId']}").json()["status"] == "completed"
    completed_review = client.get(f"/api/jobs/{created['jobId']}/subtitle-review").json()
    assert completed_review["state"] == "completed"
    assert completed_review["editedSegmentCount"] == 1
    reviewed_transcript = json.loads(
        (storage.job_outputs(created["jobId"]) / "reviewed_transcript_segments.json").read_text(
            encoding="utf-8"
        )
    )
    assert reviewed_transcript[edited_segment["index"]]["text"] == "ManualEdit"
    ass_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (storage.job_outputs(created["jobId"]) / "subtitles").rglob("*.ass")
    )
    assert "ManualEdit" in ass_text
    assert "魚の耳には、本当に「石」が入ってるらしい" in ass_text
    selected_clips = json.loads(
        (storage.job_outputs(created["jobId"]) / "selected_clips.json").read_text(
            encoding="utf-8"
        )
    )
    rendered_short = selected_clips["shorts"][0]
    assert rendered_short["title"] == "魚は「耳石」で音を聞く？"
    assert rendered_short["title_source"] == "manual_review"
    assert rendered_short["hook_text"] == "魚の耳には、本当に「石」が入ってるらしい"
    assert storage.zip_path(created["jobId"]).is_file()

    first_results = client.get(f"/api/jobs/{created['jobId']}/results").json()
    assert first_results["canReopenForEditing"] is True
    assert len(first_results["normalClips"]) == 1
    assert len(first_results["shorts"]) == 1

    reopened = client.post(
        f"/api/jobs/{created['jobId']}/subtitle-review/reopen"
    )
    assert reopened.status_code == 200
    reopened_review = reopened.json()
    assert reopened_review["state"] == "awaiting_review"
    assert reopened_review["renderRevision"] == 2
    assert reopened_review["confirmedClipCount"] == 0
    assert all(not clip["confirmed"] for clip in reopened_review["clips"])
    assert client.get(f"/api/jobs/{created['jobId']}").json()["status"] == (
        "awaiting_subtitle_review"
    )

    reopened_short = next(
        clip for clip in reopened_review["clips"] if clip["type"] == "short"
    )
    retitled = client.patch(
        (
            f"/api/jobs/{created['jobId']}/subtitle-review/clips/"
            f"{reopened_short['id']}/content"
        ),
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
    queued_hook_updates: list[
        tuple[str, str, float | None, float | None]
    ] = []
    app.dependency_overrides[get_enqueue_subtitle_review_hook_scene_update] = (
        lambda: lambda job_id, clip_id, start, end: queued_hook_updates.append(
            (job_id, clip_id, start, end)
        )
    )
    hook_update = client.patch(
        (
            f"/api/jobs/{created['jobId']}/subtitle-review/clips/"
            f"{reopened_short['id']}/hook-scene"
        ),
        json={"start": hook_start, "end": hook_end},
    )
    assert hook_update.status_code == 202
    assert queued_hook_updates == [
        (created["jobId"], reopened_short["id"], hook_start, hook_end)
    ]

    hook_preview_calls: list[dict[str, Any]] = []

    def fake_hook_preview(
        _input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Path:
        hook_preview_calls.append(kwargs)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"updated hook preview")
        return Path(output_path)

    hook_statuses = run_subtitle_review_hook_scene_update(
        created["jobId"],
        reopened_short["id"],
        hook_start,
        hook_end,
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=AutoClipperPipelineDependencies(
            subtitle_review_preview_renderer=fake_hook_preview,
        ),
    )
    assert hook_statuses == [
        "preparing_subtitle_review",
        "awaiting_subtitle_review",
    ]
    assert hook_preview_calls == [
        {
            "start": reopened_short["start"],
            "duration": reopened_short["duration"],
            "hook_start": hook_start,
            "hook_duration": 2.0,
        }
    ]
    reopened_review = client.get(
        f"/api/jobs/{created['jobId']}/subtitle-review"
    ).json()
    updated_short = next(
        clip
        for clip in reopened_review["clips"]
        if clip["id"] == reopened_short["id"]
    )
    assert updated_short["title"] == "完成後に変更したタイトル"
    assert (updated_short["hookSceneStart"], updated_short["hookSceneEnd"]) == (
        hook_start,
        hook_end,
    )
    assert updated_short["confirmed"] is False

    for clip in reopened_review["clips"]:
        response = client.post(
            f"/api/jobs/{created['jobId']}/subtitle-review/clips/{clip['id']}/confirm"
        )
        assert response.status_code == 200
        reopened_review = response.json()

    queued_jobs.clear()
    rerender_queued = client.post(
        f"/api/jobs/{created['jobId']}/subtitle-review/finalize"
    )
    assert rerender_queued.status_code == 202
    assert queued_jobs == [created["jobId"]]
    rerender_statuses = run_subtitle_review_render(
        created["jobId"],
        session_factory=lambda: next(app.dependency_overrides[get_db]()),
        paths=storage,
        dependencies=dependencies,
    )
    assert rerender_statuses[-1] == "completed"

    rerendered_results = client.get(
        f"/api/jobs/{created['jobId']}/results"
    ).json()
    assert rerendered_results["canReopenForEditing"] is True
    assert len(rerendered_results["normalClips"]) == 1
    assert len(rerendered_results["shorts"]) == 1
    assert rerendered_results["shorts"][0]["title"] == "完成後に変更したタイトル"
    rerendered_selection = json.loads(
        (
            storage.job_outputs(created["jobId"]) / "selected_clips.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        rerendered_selection["shorts"][0]["hook_scene_start"],
        rerendered_selection["shorts"][0]["hook_scene_end"],
    ) == (hook_start, hook_end)
    assert not (
        storage.temp
        / "rr"
        / f"{created['jobId'][-12:]}_r2"
    ).exists()

    reopened_again = client.post(
        f"/api/jobs/{created['jobId']}/subtitle-review/reopen"
    ).json()
    for clip in reopened_again["clips"]:
        client.post(
            f"/api/jobs/{created['jobId']}/subtitle-review/clips/{clip['id']}/confirm"
        )
    client.post(f"/api/jobs/{created['jobId']}/subtitle-review/finalize")

    def failing_render(
        _input_path: str | Path,
        _output_path: str | Path,
        **_kwargs: Any,
    ) -> Path:
        raise RuntimeError("intentional rerender failure")

    failed_statuses = run_subtitle_review_render(
        created["jobId"],
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
    scored_payload = json.loads(
        (storage.outputs / created["jobId"] / "scored_candidates.json").read_text(encoding="utf-8")
    )
    assert any("openai_fallback_rule_score" in item["risk_flags"] for item in scored_payload)
    openai_summary = json.loads(
        (storage.outputs / created["jobId"] / "openai_scoring_summary.json").read_text(encoding="utf-8")
    )
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

    transcript_payload = json.loads(
        (storage.outputs / created["jobId"] / "transcript_segments.json").read_text(encoding="utf-8")
    )
    assert transcript_payload[0]["text"].startswith("Why automation mistakes matter before launch.")
    transcript_summary = json.loads(
        (storage.outputs / created["jobId"] / "transcript_summary.json").read_text(encoding="utf-8")
    )
    assert transcript_summary["transcription_engine"] == "e2e_fixture"
    assert transcript_summary["transcription_model"] == "fixture"
    assert transcript_summary["transcription_language"] == "fixture"
    assert transcript_summary["transcription_runtime"]["actual_device"] == "fixture"
    assert transcript_summary["transcription_runtime"]["actual_compute_type"] == "fixture"
    assert transcript_summary["used_fixture_transcript"] is True
    assert not (storage.temp / created["jobId"]).exists()


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
        assert job.error_message == "Pipeline completed analysis but produced no usable clips."
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
                "peak_vram_mb": (
                    4800 if self.options["model_size"] == "turbo" else 6100
                ),
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
    primary = json.loads(
        (job_dir / "primary_raw_transcript_segments.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(primary) == 6
    assert {segment["text"] for segment in primary} == {
        "ご視聴ありがとうございました"
    }
    transcript_summary = json.loads(
        (job_dir / "transcript_summary.json").read_text(encoding="utf-8")
    )
    assert transcript_summary["transcription_model"] == "small"
    runtime = transcript_summary["transcription_runtime"]
    assert runtime["requested_model"] == "turbo"
    assert runtime["actual_model"] == "small"
    assert runtime["fallback_used"] is False
    assert runtime["fallback_reason"] is None
    assert runtime["quality_fallback_used"] is True
    assert runtime["quality_fallback_reason"] == "primary_transcript_unusable"
    assert runtime["primary_transcript_quality"]["reasons"] == [
        "repeated_segment_text"
    ]
    assert runtime["fallback_transcript_quality"]["reasons"] == []
    assert runtime["transcription_seconds"] == 4.0
    assert runtime["peak_vram_mb"] == 6100


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
    assert not (
        storage.outputs
        / created["jobId"]
        / "primary_raw_transcript_segments.json"
    ).exists()


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
