from collections.abc import Generator
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.db import Base, get_db
from app.jobs.queue import get_enqueue_job
from app.main import app
from app.models import ExportItem, Job
from app.render.crop_strategy import (
    build_blur_background_filter,
    build_center_crop_filter,
    build_face_tracking_crop_filter,
    build_person_tracking_crop_filter,
    build_speaker_tracking_crop_filter,
    build_subject_tracking_crop_filter,
    plan_short_crop,
    strategy_order,
)
from app.render.render_short import (
    ShortRenderResult,
    build_render_short_command,
    render_selected_short_candidates,
    render_short_clip,
)
from app.storage.paths import StoragePaths, get_storage_paths
from app.video.face_detect import FaceDetection, best_face_center
from app.video.person_detect import PersonBox, PersonDetection, _create_hog_detector, aggregate_person_detections
from app.video.probe import VideoMetadata
from app.video.speaker_detect import (
    DialogueWindow,
    SpeakerDetection,
    SpeakerRegion,
    aggregate_speaker_regions,
    dialogue_windows_for_clip,
)
from app.video.subject_detect import SubjectDetection, estimate_subject_from_frames


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


def make_short(
    candidate_id: str,
    start: float,
    end: float,
    title: str,
    final_score: float,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type="short",
        start=start,
        end=end,
        duration=end - start,
        transcript_text=f"{title} transcript",
        title=title,
        overlay_title=f"{title} overlay",
        final_score=final_score,
    )


def test_crop_strategy_filters_target_1080x1920() -> None:
    assert build_center_crop_filter("subtitles.ass") == (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "ass='subtitles.ass'"
    )
    assert build_face_tracking_crop_filter(
        source_width=1920,
        source_height=1080,
        face_center=(0.25, 0.5),
    ) == "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:313:0"

    blur_filter = build_blur_background_filter("subtitles.ass")
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in blur_filter
    assert "crop=1080:1920" in blur_filter
    assert "gblur=sigma=24" in blur_filter
    assert "ass='subtitles.ass'" in blur_filter

    assert build_subject_tracking_crop_filter(
        source_width=1920,
        source_height=1080,
        subject_center=(0.75, 0.5),
    ) == "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:2020:0"
    assert build_person_tracking_crop_filter(
        source_width=1920,
        source_height=1080,
        person_center=(0.75, 0.5),
    ) == "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:2020:0"
    assert build_speaker_tracking_crop_filter(
        source_width=1920,
        source_height=1080,
        speaker_center=(0.75, 0.5),
    ) == "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:2020:0"


def test_face_center_and_strategy_order() -> None:
    detections = [
        FaceDetection(start=1, end=1, center_x=0.55, center_y=0.5, width=0.2, height=0.2),
    ]

    center = best_face_center(detections)

    assert center is not None
    assert center[0] > 0.5
    assert strategy_order("auto", detections=detections, source_width=1920, source_height=1080) == [
        "face_tracking_crop",
        "center_crop",
        "blur_background",
    ]
    assert strategy_order("auto", detections=[], source_width=1920, source_height=1080) == [
        "blur_background",
        "center_crop",
    ]


def test_short_crop_plan_uses_blur_background_for_wide_face_group() -> None:
    detections = [
        FaceDetection(start=0, end=0, center_x=0.18, center_y=0.35, width=0.12, height=0.18),
        FaceDetection(start=1, end=1, center_x=0.82, center_y=0.35, width=0.12, height=0.18),
    ]

    plan = plan_short_crop("auto", detections=detections, source_width=1920, source_height=1080)

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "face_detection"
    assert plan.fallback_reason == "face_group_too_wide_for_9x16_crop"
    assert plan.detection_count == 2


def test_short_crop_plan_weak_face_signal_uses_full_frame_fallback_for_landscape() -> None:
    detections = [
        FaceDetection(start=0, end=0, center_x=0.5, center_y=0.5, width=0.01, height=0.01),
    ]

    plan = plan_short_crop("auto", detections=detections, source_width=1920, source_height=1080)

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "full_frame_fallback"
    assert plan.fallback_reason == "weak_face_signal"


def test_short_crop_plan_no_face_landscape_uses_blur_background_before_center_crop() -> None:
    plan = plan_short_crop("auto", detections=[], source_width=1920, source_height=1080)

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "full_frame_fallback"
    assert plan.fallback_reason == "no_face_detections"
    assert plan.confidence == 0.0
    assert plan.detection_count == 0


def reliable_person_detection() -> PersonDetection:
    return PersonDetection(
        center_x=0.72,
        center_y=0.52,
        width=0.22,
        height=0.52,
        confidence=0.83,
        stability_score=0.82,
        sampled_frames=3,
        detection_count=3,
        box=(0.61, 0.26, 0.83, 0.78),
    )


def test_short_render_command_prepends_hook_scene_before_body() -> None:
    command = build_render_short_command(
        "source.mp4",
        "short.mp4",
        start=60.0,
        end=75.0,
        layout="center_crop",
        hook_scene_start=68.0,
        hook_scene_end=70.0,
    )

    seek_values = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "-ss"
    ]
    duration_values = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "-t"
    ]
    filter_graph = command[command.index("-filter_complex") + 1]

    assert seek_values == ["68.000", "60.000"]
    assert duration_values == ["2.000", "15.000"]
    assert "[hook_v][hook_a][main_v][main_a]concat=n=2:v=1:a=1" in filter_graph
    assert command.count("-i") == 2


def reliable_speaker_detection() -> SpeakerDetection:
    return SpeakerDetection(
        center_x=0.72,
        center_y=0.42,
        width=0.14,
        height=0.2,
        confidence=0.86,
        stability_score=0.84,
        window_count=3,
        detection_count=3,
        box=(0.65, 0.32, 0.79, 0.52),
    )


def test_short_crop_plan_wide_face_group_reliable_speaker_uses_speaker_tracking_crop() -> None:
    detections = [
        FaceDetection(start=0, end=0, center_x=0.25, center_y=0.38, width=0.18, height=0.22),
        FaceDetection(start=0, end=0, center_x=0.75, center_y=0.38, width=0.18, height=0.22),
    ]

    plan = plan_short_crop(
        "auto",
        detections=detections,
        source_width=1920,
        source_height=1080,
        speaker_signal=reliable_speaker_detection(),
    )

    assert plan.strategy_order == ("speaker_tracking_crop", "blur_background", "center_crop")
    assert plan.signal_source == "dialogue_face_person"
    assert plan.fallback_reason == "wide_face_group_speaker_signal"
    assert plan.speaker_center is not None
    assert plan.speaker_window_count == 3
    assert plan.speaker_region_confidence == 0.86
    assert plan.speaker_region_box == (0.65, 0.32, 0.79, 0.52)


def test_short_crop_plan_ambiguous_speaker_signal_uses_blur_background() -> None:
    speaker = SpeakerDetection(
        center_x=0.72,
        center_y=0.42,
        width=0.14,
        height=0.2,
        confidence=0.86,
        stability_score=0.84,
        window_count=3,
        detection_count=6,
        box=(0.65, 0.32, 0.79, 0.52),
        ambiguous=True,
    )
    detections = [
        FaceDetection(start=0, end=0, center_x=0.25, center_y=0.38, width=0.18, height=0.22),
        FaceDetection(start=0, end=0, center_x=0.75, center_y=0.38, width=0.18, height=0.22),
    ]

    plan = plan_short_crop(
        "auto",
        detections=detections,
        source_width=1920,
        source_height=1080,
        speaker_signal=speaker,
    )

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "full_frame_fallback"
    assert plan.fallback_reason == "ambiguous_speaker_signal"
    assert plan.speaker_window_count == 3
    assert plan.speaker_region_confidence == 0.86
    assert plan.speaker_region_box == (0.65, 0.32, 0.79, 0.52)


def test_short_crop_plan_no_face_reliable_person_signal_uses_person_tracking_crop() -> None:
    person = reliable_person_detection()

    plan = plan_short_crop("auto", detections=[], source_width=1920, source_height=1080, person_signal=person)

    assert plan.strategy_order == ("person_tracking_crop", "blur_background", "center_crop")
    assert plan.signal_source == "person_detection"
    assert plan.fallback_reason == "no_face_person_signal"
    assert plan.person_center is not None
    assert plan.crop_x == 1917
    assert plan.crop_y == 0
    assert plan.sampled_frame_count == 3
    assert plan.stability_score == 0.82
    assert plan.person_detection_count == 3
    assert plan.person_detection_confidence == 0.83
    assert plan.person_box == (0.61, 0.26, 0.83, 0.78)


def test_short_crop_plan_no_face_person_signal_takes_priority_over_subject_signal() -> None:
    person = reliable_person_detection()
    subject = SubjectDetection(center_x=0.76, confidence=0.84, stability_score=0.88, sampled_frames=5)

    plan = plan_short_crop(
        "auto",
        detections=[],
        source_width=1920,
        source_height=1080,
        person_signal=person,
        subject_signal=subject,
    )

    assert plan.strategy_order[0] == "person_tracking_crop"
    assert plan.signal_source == "person_detection"


def test_short_crop_plan_reliable_face_signal_keeps_face_priority_over_person_signal() -> None:
    detections = [FaceDetection(start=0, end=0, center_x=0.35, center_y=0.45, width=0.18, height=0.2)]

    plan = plan_short_crop(
        "auto",
        detections=detections,
        source_width=1920,
        source_height=1080,
        person_signal=reliable_person_detection(),
    )

    assert plan.strategy_order[0] == "face_tracking_crop"
    assert plan.signal_source == "face_detection"


def test_short_crop_plan_ambiguous_person_signal_uses_blur_background() -> None:
    person = PersonDetection(
        center_x=0.72,
        center_y=0.52,
        width=0.22,
        height=0.52,
        confidence=0.86,
        stability_score=0.82,
        sampled_frames=3,
        detection_count=6,
        box=(0.61, 0.26, 0.83, 0.78),
        ambiguous=True,
    )

    plan = plan_short_crop("auto", detections=[], source_width=1920, source_height=1080, person_signal=person)

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "full_frame_fallback"
    assert plan.fallback_reason == "ambiguous_person_signal"
    assert plan.person_detection_count == 6
    assert plan.person_detection_confidence == 0.86
    assert plan.person_box == (0.61, 0.26, 0.83, 0.78)


def test_short_crop_plan_low_confidence_person_signal_uses_blur_background() -> None:
    person = PersonDetection(
        center_x=0.72,
        center_y=0.52,
        width=0.22,
        height=0.52,
        confidence=0.42,
        stability_score=0.82,
        sampled_frames=3,
        detection_count=3,
        box=(0.61, 0.26, 0.83, 0.78),
    )

    plan = plan_short_crop("auto", detections=[], source_width=1920, source_height=1080, person_signal=person)

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "full_frame_fallback"
    assert plan.fallback_reason == "weak_person_signal"
    assert plan.confidence == 0.42


def test_short_crop_plan_no_face_strong_subject_signal_uses_subject_tracking_crop() -> None:
    subject = SubjectDetection(center_x=0.76, confidence=0.82, stability_score=0.91, sampled_frames=5)

    plan = plan_short_crop("auto", detections=[], source_width=1920, source_height=1080, subject_signal=subject)

    assert plan.strategy_order == ("subject_tracking_crop", "blur_background", "center_crop")
    assert plan.signal_source == "motion_edge_saliency"
    assert plan.fallback_reason == "no_face_subject_signal"
    assert plan.subject_center is not None
    assert plan.crop_x == 2054
    assert plan.crop_y == 0
    assert plan.sampled_frame_count == 5
    assert plan.subject_x == 0.76
    assert plan.stability_score == 0.91


def test_short_crop_plan_no_face_weak_subject_signal_uses_blur_background() -> None:
    subject = SubjectDetection(center_x=0.76, confidence=0.42, stability_score=0.91, sampled_frames=5)

    plan = plan_short_crop("auto", detections=[], source_width=1920, source_height=1080, subject_signal=subject)

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "full_frame_fallback"
    assert plan.fallback_reason == "weak_subject_signal"
    assert plan.confidence == 0.42
    assert plan.sampled_frame_count == 5
    assert plan.subject_x == 0.76
    assert plan.stability_score == 0.91


def test_short_crop_plan_no_face_ambiguous_center_subject_signal_uses_blur_background() -> None:
    subject = SubjectDetection(center_x=0.52, confidence=0.69, stability_score=0.76, sampled_frames=5)

    plan = plan_short_crop("auto", detections=[], source_width=1920, source_height=1080, subject_signal=subject)

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "full_frame_fallback"
    assert plan.fallback_reason == "ambiguous_subject_signal"
    assert plan.confidence == 0.69
    assert plan.subject_x == 0.52


def test_short_crop_plan_no_face_portrait_keeps_center_crop_fallback() -> None:
    plan = plan_short_crop("auto", detections=[], source_width=1080, source_height=1920)

    assert plan.strategy_order == ("center_crop", "blur_background")
    assert plan.signal_source == "center_fallback"
    assert plan.fallback_reason == "no_face_detections"


def test_short_crop_plan_forced_center_crop_keeps_center_first() -> None:
    plan = plan_short_crop("center_crop", detections=[], source_width=1920, source_height=1080)

    assert plan.strategy_order == ("center_crop", "blur_background")
    assert plan.signal_source == "forced_layout"
    assert plan.confidence == 1.0


def test_short_crop_plan_forced_face_tracking_weak_signal_uses_safe_fallback() -> None:
    detections = [
        FaceDetection(start=0, end=0, center_x=0.5, center_y=0.5, width=0.01, height=0.01),
    ]

    plan = plan_short_crop("face_tracking_crop", detections=detections, source_width=1920, source_height=1080)

    assert plan.strategy_order == ("blur_background", "center_crop")
    assert plan.signal_source == "full_frame_fallback"
    assert plan.fallback_reason == "weak_face_signal"


def test_short_crop_plan_moves_low_face_out_of_subtitle_area_when_possible() -> None:
    detections = [
        FaceDetection(start=0, end=0, center_x=0.5, center_y=0.82, width=0.18, height=0.18),
    ]

    plan = plan_short_crop("auto", detections=detections, source_width=1080, source_height=2400)

    assert plan.strategy_order[0] == "face_tracking_crop"
    assert plan.face_center is not None
    assert plan.crop_y is not None
    assert plan.crop_y > 0
    assert plan.signal_source == "face_detection"
    assert plan.crop_x is not None

    video_filter = build_face_tracking_crop_filter(1080, 2400, plan.face_center)
    assert f"crop=1080:1920:{plan.crop_x}:{plan.crop_y}" in video_filter


def test_render_short_clip_auto_falls_back_to_center_crop(tmp_path: Path) -> None:
    output_path = tmp_path / "short.mp4"
    commands: list[list[str]] = []

    def fake_face_detector(_input_path: str | Path, _start: float, _end: float) -> list[FaceDetection]:
        return [FaceDetection(start=0, end=0, center_x=0.25, center_y=0.5, width=0.2, height=0.2)]

    def fake_metadata_probe(_input_path: str | Path) -> VideoMetadata:
        return VideoMetadata(duration=60.0, width=1920, height=1080, fps=30.0, has_audio=True)

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        video_filter = command[command.index("-vf") + 1]
        if "crop=1080:1920:313:0" in video_filter:
            raise RuntimeError("face crop failed")
        output_path.write_bytes(b"short mp4")

    result = render_short_clip(
        "input.mp4",
        output_path,
        start=0.0,
        end=30.0,
        subtitle_path="subtitles.ass",
        layout="auto",
        face_detector=fake_face_detector,
        metadata_probe=fake_metadata_probe,
        command_runner=fake_runner,
    )

    assert result.strategy == "center_crop"
    assert output_path.read_bytes() == b"short mp4"
    assert len(commands) == 2
    assert "crop=1080:1920:313:0" in commands[0][commands[0].index("-vf") + 1]
    assert commands[1][commands[1].index("-vf") + 1].startswith(
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    )


def test_render_short_clip_records_composition_diagnostics(tmp_path: Path) -> None:
    output_path = tmp_path / "short.mp4"
    commands: list[list[str]] = []

    def fake_face_detector(_input_path: str | Path, _start: float, _end: float) -> list[FaceDetection]:
        return [
            FaceDetection(start=0, end=0, center_x=0.18, center_y=0.35, width=0.12, height=0.18),
            FaceDetection(start=1, end=1, center_x=0.82, center_y=0.35, width=0.12, height=0.18),
        ]

    def fake_metadata_probe(_input_path: str | Path) -> VideoMetadata:
        return VideoMetadata(duration=60.0, width=1920, height=1080, fps=30.0, has_audio=True)

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        output_path.write_bytes(b"short mp4")

    result = render_short_clip(
        "input.mp4",
        output_path,
        start=0.0,
        end=30.0,
        layout="auto",
        face_detector=fake_face_detector,
        metadata_probe=fake_metadata_probe,
        command_runner=fake_runner,
    )

    assert result.strategy == "blur_background"
    assert result.crop_signal_source == "face_detection"
    assert result.crop_fallback_reason == "face_group_too_wide_for_9x16_crop"
    assert result.crop_detection_count == 2
    assert result.crop_attempted_strategies == ("blur_background",)
    assert "gblur=sigma=24" in commands[0][commands[0].index("-vf") + 1]


def test_render_short_clip_no_face_landscape_uses_blur_background(tmp_path: Path) -> None:
    output_path = tmp_path / "short.mp4"
    commands: list[list[str]] = []

    def fake_face_detector(_input_path: str | Path, _start: float, _end: float) -> list[FaceDetection]:
        return []

    def fake_metadata_probe(_input_path: str | Path) -> VideoMetadata:
        return VideoMetadata(duration=60.0, width=1920, height=1080, fps=30.0, has_audio=True)

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        output_path.write_bytes(b"short mp4")

    result = render_short_clip(
        "input.mp4",
        output_path,
        start=0.0,
        end=30.0,
        layout="auto",
        face_detector=fake_face_detector,
        metadata_probe=fake_metadata_probe,
        command_runner=fake_runner,
    )

    assert result.strategy == "blur_background"
    assert result.crop_signal_source == "full_frame_fallback"
    assert result.crop_fallback_reason == "no_face_detections"
    assert result.crop_confidence == 0.0
    assert result.crop_detection_count == 0
    assert result.crop_attempted_strategies == ("blur_background",)
    assert "gblur=sigma=24" in commands[0][commands[0].index("-vf") + 1]


def test_render_short_clip_no_face_strong_subject_signal_uses_subject_tracking_crop(tmp_path: Path) -> None:
    output_path = tmp_path / "short.mp4"
    commands: list[list[str]] = []

    def fake_face_detector(_input_path: str | Path, _start: float, _end: float) -> list[FaceDetection]:
        return []

    def fake_subject_detector(_input_path: str | Path, _start: float, _end: float) -> SubjectDetection:
        return SubjectDetection(center_x=0.74, confidence=0.84, stability_score=0.88, sampled_frames=5)

    def fake_metadata_probe(_input_path: str | Path) -> VideoMetadata:
        return VideoMetadata(duration=60.0, width=1920, height=1080, fps=30.0, has_audio=True)

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        output_path.write_bytes(b"short mp4")

    result = render_short_clip(
        "input.mp4",
        output_path,
        start=0.0,
        end=30.0,
        layout="auto",
        face_detector=fake_face_detector,
        subject_detector=fake_subject_detector,
        metadata_probe=fake_metadata_probe,
        command_runner=fake_runner,
    )

    assert result.strategy == "subject_tracking_crop"
    assert result.crop_signal_source == "motion_edge_saliency"
    assert result.crop_fallback_reason == "no_face_subject_signal"
    assert result.crop_confidence == 0.84
    assert result.crop_sampled_frames == 5
    assert result.crop_subject_x == 0.74
    assert result.crop_stability_score == 0.88
    assert result.crop_attempted_strategies == ("subject_tracking_crop",)
    assert "crop=1080:1920:1986:0" in commands[0][commands[0].index("-vf") + 1]


def test_render_short_clip_no_face_reliable_person_signal_uses_person_tracking_crop(tmp_path: Path) -> None:
    output_path = tmp_path / "short.mp4"
    commands: list[list[str]] = []

    def fake_face_detector(_input_path: str | Path, _start: float, _end: float) -> list[FaceDetection]:
        return []

    def fake_person_detector(_input_path: str | Path, _start: float, _end: float) -> PersonDetection:
        return reliable_person_detection()

    def fake_subject_detector(_input_path: str | Path, _start: float, _end: float) -> SubjectDetection:
        return SubjectDetection(center_x=0.76, confidence=0.84, stability_score=0.88, sampled_frames=5)

    def fake_metadata_probe(_input_path: str | Path) -> VideoMetadata:
        return VideoMetadata(duration=60.0, width=1920, height=1080, fps=30.0, has_audio=True)

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        output_path.write_bytes(b"short mp4")

    result = render_short_clip(
        "input.mp4",
        output_path,
        start=0.0,
        end=30.0,
        layout="auto",
        face_detector=fake_face_detector,
        person_detector=fake_person_detector,
        subject_detector=fake_subject_detector,
        metadata_probe=fake_metadata_probe,
        command_runner=fake_runner,
    )

    assert result.strategy == "person_tracking_crop"
    assert result.crop_signal_source == "person_detection"
    assert result.crop_fallback_reason == "no_face_person_signal"
    assert result.crop_confidence == 0.83
    assert result.person_detection_count == 3
    assert result.person_detection_confidence == 0.83
    assert result.person_box == (0.61, 0.26, 0.83, 0.78)
    assert result.crop_attempted_strategies == ("person_tracking_crop",)
    assert "crop=1080:1920:1917:0" in commands[0][commands[0].index("-vf") + 1]


def test_render_short_clip_wide_face_group_reliable_speaker_uses_speaker_tracking_crop(tmp_path: Path) -> None:
    output_path = tmp_path / "short.mp4"
    commands: list[list[str]] = []

    def fake_face_detector(_input_path: str | Path, _start: float, _end: float) -> list[FaceDetection]:
        return [
            FaceDetection(start=0, end=0, center_x=0.25, center_y=0.38, width=0.18, height=0.22),
            FaceDetection(start=0, end=0, center_x=0.75, center_y=0.38, width=0.18, height=0.22),
        ]

    def fake_speaker_detector(
        _input_path: str | Path,
        _start: float,
        _end: float,
        dialogue_windows: list[DialogueWindow],
        **_kwargs: Any,
    ) -> SpeakerDetection:
        assert len(dialogue_windows) == 2
        return reliable_speaker_detection()

    def fake_person_detector(_input_path: str | Path, _start: float, _end: float) -> PersonDetection:
        raise AssertionError("person detector should not be needed when speaker signal is reliable")

    def fake_subject_detector(_input_path: str | Path, _start: float, _end: float) -> SubjectDetection:
        raise AssertionError("subject detector should not be needed when speaker signal is reliable")

    def fake_metadata_probe(_input_path: str | Path) -> VideoMetadata:
        return VideoMetadata(duration=60.0, width=1920, height=1080, fps=30.0, has_audio=True)

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        output_path.write_bytes(b"short mp4")

    result = render_short_clip(
        "input.mp4",
        output_path,
        start=0.0,
        end=30.0,
        layout="auto",
        face_detector=fake_face_detector,
        speaker_detector=fake_speaker_detector,
        person_detector=fake_person_detector,
        subject_detector=fake_subject_detector,
        metadata_probe=fake_metadata_probe,
        command_runner=fake_runner,
        dialogue_windows=[
            DialogueWindow(start=4.0, end=6.0, text_length=8),
            DialogueWindow(start=12.0, end=14.0, text_length=10),
        ],
    )

    assert result.strategy == "speaker_tracking_crop"
    assert result.crop_signal_source == "dialogue_face_person"
    assert result.crop_fallback_reason == "wide_face_group_speaker_signal"
    assert result.crop_confidence == 0.86
    assert result.speaker_window_count == 3
    assert result.speaker_region_confidence == 0.86
    assert result.speaker_region_box == (0.65, 0.32, 0.79, 0.52)
    assert result.crop_attempted_strategies == ("speaker_tracking_crop",)
    assert "crop=1080:1920:1917:0" in commands[0][commands[0].index("-vf") + 1]


def test_person_detection_aggregation_rejects_ambiguous_multi_person_layout() -> None:
    boxes = [
        [
            PersonBox(center_x=0.28, center_y=0.55, width=0.2, height=0.5, confidence=0.9),
            PersonBox(center_x=0.74, center_y=0.55, width=0.2, height=0.5, confidence=0.88),
        ],
        [
            PersonBox(center_x=0.29, center_y=0.55, width=0.2, height=0.5, confidence=0.9),
            PersonBox(center_x=0.75, center_y=0.55, width=0.2, height=0.5, confidence=0.88),
        ],
    ]

    signal = aggregate_person_detections(boxes)

    assert signal is not None
    assert signal.ambiguous is True
    assert signal.detection_count == 4


def test_person_detection_aggregation_accepts_stable_single_person_layout() -> None:
    boxes = [
        [PersonBox(center_x=0.7, center_y=0.55, width=0.2, height=0.5, confidence=0.9)],
        [PersonBox(center_x=0.71, center_y=0.55, width=0.2, height=0.51, confidence=0.88)],
        [PersonBox(center_x=0.7, center_y=0.54, width=0.2, height=0.5, confidence=0.9)],
    ]

    signal = aggregate_person_detections(boxes)

    assert signal is not None
    assert signal.ambiguous is False
    assert signal.center_x > 0.68
    assert signal.confidence > 0.75
    assert signal.stability_score > 0.9


def test_dialogue_windows_for_clip_prefers_overlapping_text_segments() -> None:
    segments = [
        TranscriptSegment(start=0.0, end=1.0, text="outside"),
        TranscriptSegment(start=5.0, end=7.0, text="short"),
        TranscriptSegment(start=10.0, end=15.0, text="very important dialogue"),
        TranscriptSegment(start=20.0, end=21.0, text="tiny"),
    ]

    windows = dialogue_windows_for_clip(4.0, 18.0, segments, max_windows=2)

    assert [(window.start, window.end) for window in windows] == [(5.0, 7.0), (10.0, 15.0)]
    assert [window.text_length for window in windows] == [5, 23]


def test_speaker_region_aggregation_rejects_ambiguous_layout() -> None:
    regions = [
        SpeakerRegion(center_x=0.70, center_y=0.42, width=0.12, height=0.18, confidence=0.9, source="dialogue_face"),
        SpeakerRegion(center_x=0.71, center_y=0.43, width=0.12, height=0.18, confidence=0.88, source="dialogue_face"),
    ]

    signal = aggregate_speaker_regions(regions, window_count=2, detection_count=4, ambiguous_windows=1)

    assert signal is not None
    assert signal.ambiguous is True
    assert signal.detection_count == 4


def test_speaker_region_aggregation_accepts_stable_single_region() -> None:
    regions = [
        SpeakerRegion(center_x=0.70, center_y=0.42, width=0.12, height=0.18, confidence=0.9, source="dialogue_face"),
        SpeakerRegion(center_x=0.71, center_y=0.43, width=0.12, height=0.18, confidence=0.88, source="dialogue_face"),
        SpeakerRegion(center_x=0.70, center_y=0.42, width=0.13, height=0.19, confidence=0.89, source="dialogue_face"),
    ]

    signal = aggregate_speaker_regions(regions, window_count=3, detection_count=3)

    assert signal is not None
    assert signal.ambiguous is False
    assert signal.center_x > 0.68
    assert signal.confidence > 0.78
    assert signal.stability_score > 0.9


def test_person_detector_returns_unavailable_when_hog_api_is_missing() -> None:
    class FakeCv2:
        pass

    assert _create_hog_detector(FakeCv2()) is None


def test_subject_estimation_uses_off_center_motion_signal() -> None:
    import numpy as np

    frames = []
    for offset in (0, 6, 12, 18):
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[55:135, 215 + offset : 260 + offset] = 255
        frames.append(frame)

    signal = estimate_subject_from_frames(frames, max_width=320)

    assert signal is not None
    assert signal.center_x > 0.62
    assert signal.confidence >= 0.5
    assert signal.sampled_frames == 4


def test_render_selected_short_candidates_creates_exports_visible_in_results(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()
    renderer_calls: list[dict[str, Any]] = []

    def fake_renderer(
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> ShortRenderResult:
        renderer_calls.append({"input_path": input_path, "output_path": output_path, **kwargs})
        if Path(output_path).name == "short_02.mp4":
            raise RuntimeError("short render failed")
        Path(output_path).write_bytes(f"rendered {Path(output_path).name}".encode("utf-8"))
        return ShortRenderResult(path=Path(output_path), strategy="center_crop")

    candidates = [
        make_short("cand_short_1", 0.0, 45.0, "First short", 93.0).model_copy(
            update={
                "hook_scene_start": 5.0,
                "hook_scene_end": 7.0,
            }
        ),
        make_short("cand_short_fail", 50.0, 95.0, "Broken short", 90.0),
        make_short("cand_short_2", 100.0, 145.0, "Second short", 84.0),
        Candidate(
            id="cand_normal_ignored",
            type="normal",
            start=0.0,
            end=120.0,
            duration=120.0,
            transcript_text="ignored normal",
            final_score=99.0,
        ),
    ]
    transcript_segments = [
        TranscriptSegment(start=0.0, end=10.0, text="first subtitle"),
        TranscriptSegment(start=100.0, end=110.0, text="second subtitle"),
    ]

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None

        result = render_selected_short_candidates(
            db=db,
            job=job,
            input_path=Path(storage.uploads) / "sample.mp4",
            selected_candidates=candidates,
            transcript_segments=transcript_segments,
            burn_subtitles=True,
            normalize_audio=True,
            layout="auto",
            paths=storage,
            renderer=fake_renderer,
            source_width=1920,
            source_height=1080,
        )

        exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all()

    assert [export.candidate_id for export in result.exports] == ["cand_short_1", "cand_short_2"]
    assert [failure.candidate_id for failure in result.failures] == ["cand_short_fail"]
    assert [export.candidate_id for export in exports] == ["cand_short_1", "cand_short_2"]
    assert len(renderer_calls) == 3
    assert all(call["subtitle_path"] is not None for call in renderer_calls)
    assert all(call["layout"] == "auto" for call in renderer_calls)
    assert all(call["source_width"] == 1920 for call in renderer_calls)
    assert renderer_calls[0]["hook_scene_start"] == 5.0
    assert renderer_calls[0]["hook_scene_end"] == 7.0

    shorts_dir = storage.outputs / created["jobId"] / "shorts"
    subtitle_dir = storage.outputs / created["jobId"] / "subtitles" / "shorts"
    assert (shorts_dir / "short_01.mp4").is_file()
    assert not (shorts_dir / "short_01.ass").exists()
    assert (subtitle_dir / "short_01.ass").is_file()
    assert not (shorts_dir / "short_02.mp4").is_file()
    assert (shorts_dir / "short_03.mp4").is_file()
    short_metadata = json.loads((shorts_dir / "short_01.json").read_text(encoding="utf-8"))
    assert short_metadata["title"] == "First short"
    assert short_metadata["overlay_title"] == "First short overlay"
    assert short_metadata["title_source"] == "existing"
    assert short_metadata["duration"] == 47.0
    assert short_metadata["body_duration"] == 45.0
    assert short_metadata["hook_scene_start"] == 5.0
    assert short_metadata["hook_scene_end"] == 7.0
    assert short_metadata["hook_scene_duration"] == 2.0
    assert short_metadata["hook_scene_rendered"] is True
    assert "original_start" in short_metadata
    assert "refined_start" in short_metadata
    assert "boundary_refined" in short_metadata
    assert short_metadata["subtitle_path"].replace("\\", "/").endswith("/subtitles/shorts/short_01.ass")
    assert short_metadata["crop_strategy"] == "center_crop"
    assert "crop_signal_source" in short_metadata
    assert "crop_fallback_reason" in short_metadata
    assert "crop_sampled_frames" in short_metadata
    assert "crop_subject_x" in short_metadata
    assert "crop_stability_score" in short_metadata
    assert "person_detection_count" in short_metadata
    assert "person_detection_confidence" in short_metadata
    assert "person_box" in short_metadata
    assert "speaker_window_count" in short_metadata
    assert "speaker_region_confidence" in short_metadata
    assert "speaker_region_box" in short_metadata
    assert renderer_calls[0]["dialogue_windows"]
    assert isinstance(renderer_calls[0]["dialogue_windows"][0], DialogueWindow)
    assert result.exports[0].duration == 47.0

    results_response = client.get(f"/api/jobs/{created['jobId']}/results")
    assert results_response.status_code == 200
    shorts = results_response.json()["shorts"]
    assert len(shorts) == 2
    assert {short["title"] for short in shorts} == {"First short", "Second short"}

    download_response = client.get(shorts[0]["downloadUrl"])
    assert download_response.status_code == 200
    assert download_response.content.startswith(b"rendered short_")


def test_render_selected_short_candidates_writes_fallback_title_metadata(client: TestClient) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> ShortRenderResult:
        Path(output_path).write_bytes(b"rendered short")
        return ShortRenderResult(path=Path(output_path), strategy="center_crop")

    candidate = Candidate(
        id="cand_short_title_fallback",
        type="short",
        start=0.0,
        end=45.0,
        duration=45.0,
        transcript_text="まあ インフレの見方が変わる重要な場面です。",
        final_score=82.0,
    )

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        result = render_selected_short_candidates(
            db=db,
            job=job,
            input_path=Path(storage.uploads) / "sample.mp4",
            selected_candidates=[candidate],
            burn_subtitles=True,
            paths=storage,
            renderer=fake_renderer,
            mode="low_cost",
        )
        exports = db.scalars(select(ExportItem).where(ExportItem.job_id == job.id)).all()

    assert result.exports[0].title == "インフレの見方が変わる重要な場面です"
    assert exports[0].title == "インフレの見方が変わる重要な場面です"
    shorts_dir = storage.outputs / created["jobId"] / "shorts"
    short_metadata = json.loads((shorts_dir / "short_01.json").read_text(encoding="utf-8"))
    assert short_metadata["title"] == "インフレの見方が変わる重要な場面です"
    assert short_metadata["overlay_title"] == "インフレの見方が変わる重要な場面です"
    assert short_metadata["title_source"] == "transcript_fallback"
    assert short_metadata["overlay_title_expected"] is False
    assert short_metadata["overlay_title_rendered"] is False
    assert short_metadata["overlay_title_mode"] == "auto"
    subtitle_dir = storage.outputs / created["jobId"] / "subtitles" / "shorts"
    assert not (shorts_dir / "short_01.ass").exists()
    ass_text = (subtitle_dir / "short_01.ass").read_text(encoding="utf-8")
    assert ",Title,," not in ass_text


@pytest.mark.parametrize(
    ("mode", "overlay_mode", "title_source", "expect_title_event"),
    [
        ("high_quality", "auto", None, True),
        ("low_cost", "always", None, True),
        ("high_quality", "never", None, False),
        ("low_cost", "auto", "manual_review", True),
        ("low_cost", "never", "manual_review", False),
    ],
)
def test_render_selected_short_candidates_applies_overlay_title_policy(
    client: TestClient,
    mode: str,
    overlay_mode: str,
    title_source: str | None,
    expect_title_event: bool,
) -> None:
    upload = client.post(
        "/api/videos/upload",
        files={"file": ("sample.mp4", b"fake video bytes", "video/mp4")},
    ).json()
    created = client.post(
        "/api/jobs",
        json={"videoId": upload["videoId"], "settings": {}},
    ).json()
    storage = app.dependency_overrides[get_storage_paths]()

    def fake_renderer(
        _input_path: str | Path,
        output_path: str | Path,
        **_kwargs: Any,
    ) -> ShortRenderResult:
        Path(output_path).write_bytes(b"rendered short")
        return ShortRenderResult(path=Path(output_path), strategy="center_crop")

    candidate = Candidate(
        id="cand_short_overlay_policy",
        type="short",
        start=0.0,
        end=45.0,
        duration=45.0,
        transcript_text="投資判断が変わる場面です。",
        title="投資判断の転換点",
        overlay_title="投資判断の転換点",
        title_source=title_source,
        final_score=82.0,
    )

    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, created["jobId"])
        assert job is not None
        result = render_selected_short_candidates(
            db=db,
            job=job,
            input_path=Path(storage.uploads) / "sample.mp4",
            selected_candidates=[candidate],
            burn_subtitles=True,
            paths=storage,
            renderer=fake_renderer,
            mode=mode,
            short_overlay_title_mode=overlay_mode,
        )

    assert len(result.exports) == 1
    output_dir = storage.outputs / created["jobId"]
    short_metadata = json.loads((output_dir / "shorts" / "short_01.json").read_text(encoding="utf-8"))
    ass_text = (output_dir / "subtitles" / "shorts" / "short_01.ass").read_text(encoding="utf-8")

    assert short_metadata["overlay_title_expected"] is expect_title_event
    assert short_metadata["overlay_title_rendered"] is expect_title_event
    assert short_metadata["overlay_title_mode"] == overlay_mode
    assert (",Title,," in ass_text) is expect_title_event
