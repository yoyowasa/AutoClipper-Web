from __future__ import annotations

from pathlib import Path

import pytest

from app.jobs.thumbnail_frame_selection import select_thumbnail_frame_seconds
from app.video.face_detect import FaceDetection


def test_frame_selection_cycles_through_distinct_face_samples() -> None:
    detections = [
        FaceDetection(
            start=float(timestamp),
            end=float(timestamp),
            center_x=0.82,
            center_y=0.58,
            width=0.10,
            height=0.16,
        )
        for timestamp in (108, 124, 140, 156, 172, 188)
    ]

    def detector(
        _path: str | Path,
        _start: float,
        _end: float,
        sample_count: int,
    ) -> list[FaceDetection]:
        assert sample_count == 24
        return detections

    selected = [
        select_thumbnail_frame_seconds(
            "source.mp4",
            clip_start=100,
            clip_end=200,
            variant_index=index,
            face_detector=detector,
        )
        for index in range(6)
    ]

    assert selected == pytest.approx([8, 24, 40, 56, 72, 88])
    assert len(set(selected)) == 6


def test_frame_selection_falls_back_to_evenly_spaced_clip_positions() -> None:
    selected = select_thumbnail_frame_seconds(
        "source.mp4",
        clip_start=20,
        clip_end=70,
        variant_index=2,
        face_detector=lambda *_args: [],
    )

    assert selected == pytest.approx(20)


def test_frame_selection_never_fills_face_sequence_with_unverified_times() -> None:
    detections = [
        FaceDetection(
            start=timestamp,
            end=timestamp,
            center_x=0.67,
            center_y=0.29,
            width=0.08,
            height=0.15,
        )
        for timestamp in (30.0, 50.0, 70.0)
    ]

    selected = [
        select_thumbnail_frame_seconds(
            "source.mp4",
            clip_start=20,
            clip_end=120,
            variant_index=index,
            face_detector=lambda *_args: detections,
        )
        for index in range(6)
    ]

    assert selected == pytest.approx([10, 30, 50, 10, 30, 50])


def test_frame_selection_rejects_lower_body_false_positive() -> None:
    detections = [
        FaceDetection(
            start=40.0,
            end=40.0,
            center_x=0.67,
            center_y=0.29,
            width=0.08,
            height=0.15,
        ),
        FaceDetection(
            start=40.0,
            end=40.0,
            center_x=0.66,
            center_y=0.51,
            width=0.13,
            height=0.24,
        ),
        FaceDetection(
            start=80.0,
            end=80.0,
            center_x=0.66,
            center_y=0.75,
            width=0.08,
            height=0.15,
        ),
    ]

    selected = select_thumbnail_frame_seconds(
        "source.mp4",
        clip_start=20,
        clip_end=120,
        variant_index=0,
        face_detector=lambda *_args: detections,
    )

    assert selected == pytest.approx(20)
