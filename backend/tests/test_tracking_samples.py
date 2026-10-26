from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest

from app.jobs.quality_gate import _tracking_crop_containment
from app.render.crop_strategy import plan_short_crop
from app.render.render_short import _tracking_evidence_for_render
from app.render.short_crop_decision import ShortCropDecision
from app.video.face_detect import FaceDetection
from app.video.person_detect import PersonBox, aggregate_person_detections
from app.video.speaker_detect import DialogueWindow, detect_speaker_for_clip
from app.video.subject_detect import estimate_subject_from_frames
from app.render.crop_strategy import CropPlan


def test_legacy_crop_serialization_preserves_preview_identity():
    saved = ShortCropDecision(start=0, end=30, width=1920, height=1080, target_height=1920,
                              layout="auto", plan=CropPlan(strategy_order=("blur_background",)), faces=[])
    assert "tracking_samples" not in saved.model_dump()["plan"]
    assert ShortCropDecision.model_validate_json(saved.model_dump_json()).model_dump() == saved.model_dump()


def test_speaker_keeps_actual_frame_times_and_boxes_through_saved_crop():
    def faces(_path, start, end):
        return [FaceDetection(start=start, end=start, center_x=0.70 + start / 1000, center_y=0.35,
                              width=0.12, height=0.14, confidence=0.95)]
    signal = detect_speaker_for_clip(
        Path("unused"), 0, 30, [DialogueWindow(start=t, end=t + 1) for t in (2, 15, 28)],
        face_detector=faces, person_detector=lambda *a: pytest.fail("unneeded detection"),
    )
    assert signal is not None
    assert [sample.start for sample in signal.samples] == [2, 15, 28]
    assert len({sample.box for sample in signal.samples}) == 3
    plan = plan_short_crop("auto", [], source_width=1920, source_height=1080, speaker_signal=signal)
    assert plan.strategy_order[0] == "speaker_tracking_crop"
    stored = ShortCropDecision(start=0, end=30, width=1920, height=1080, target_height=1920,
                               layout="auto", plan=plan, faces=[])
    restored = ShortCropDecision.model_validate_json(stored.model_dump_json())
    evidence = _tracking_evidence_for_render(
        "speaker_tracking_crop", crop_plan=restored.plan, detections=[], start=0, end=30,
        source_width=1920, source_height=1080, target_height=1920,
        framing_offset_x=0, framing_offset_y=0, framing_zoom=1,
    )
    assert evidence["samples"] == [asdict(sample) | {"box": list(sample.box)} for sample in signal.samples]


def test_subject_records_measured_extent_at_each_time():
    frames = []
    for offset in range(5):
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[50:110, 220 + offset:250 + offset] = 255
        frames.append(frame)
    signal = estimate_subject_from_frames(frames, sample_times=[1, 4, 8, 12, 15])
    assert signal is not None
    assert [sample.start for sample in signal.samples] == [1, 4, 8, 12, 15]
    assert len({sample.box for sample in signal.samples}) > 1
    for sample in signal.samples:
        left, top, right, bottom = sample.box
        assert 0.65 < left < right < 0.85
        assert 0.20 < top < bottom < 0.70
    plan = plan_short_crop("auto", [], source_width=1920, source_height=1080, subject_signal=signal)
    assert plan.strategy_order[0] == "subject_tracking_crop"
    evidence = _tracking_evidence_for_render(
        "subject_tracking_crop", crop_plan=plan, detections=[], start=0, end=16,
        source_width=1920, source_height=1080, target_height=1920,
        framing_offset_x=0, framing_offset_y=0, framing_zoom=1,
    )
    assert evidence is not None and len(evidence["samples"]) == 5


def test_person_samples_do_not_fabricate_times_for_old_aggregate_callers():
    boxes = [[PersonBox(center_x=0.7 + i / 100, center_y=0.45, width=0.12, height=0.3)] for i in range(3)]
    old = aggregate_person_detections(boxes)
    current = aggregate_person_detections(boxes, sample_times=[1, 8, 15])
    assert not old.samples
    assert [sample.start for sample in current.samples] == [1, 8, 15]
    assert len({sample.box for sample in current.samples}) == 3


@pytest.mark.parametrize("strategy", ["face", "speaker", "person", "subject"])
@pytest.mark.parametrize("count,outside,status", [(1, True, None), (2, True, None), (3, True, False), (3, False, True)])
def test_tracking_needs_three_distinct_observations_before_containment(strategy, count, outside, status):
    strategy += "_tracking_crop"
    evidence = {
        "schema_version": 1, "strategy": strategy, "source": {"width": 1080, "height": 1920},
        "scaled": {"width": 1080, "height": 1920},
        "crop": {"x": 0, "y": 0, "width": 1080, "height": 1920},
        "safe_area": {"x": 100, "y": 120, "width": 880, "height": 1400},
        "samples": [{"start": i * 5, "end": i * 5, "box": [0.2, 0.2, 0.8, 0.6],
                     "confidence": 0.9} for i in range(count)],
    }
    if outside:
        evidence["samples"][0]["box"] = [0, 0.2, 0.8, 0.6]
    metadata = {"tracking_evidence": evidence, "speaker_region_confidence": 0.9, "crop_confidence": 0.9,
                "person_detection_confidence": 0.9, "crop_stability_score": 0.9,
                "crop_sampled_frames": 5, "speaker_window_count": 5}
    actual, detail = _tracking_crop_containment(metadata, strategy=strategy,
                                               top_banner_enabled=False, bottom_banner_enabled=False)
    assert actual is status
    if count < 3:
        assert detail["reason"] == "tracking_time_coverage_insufficient"
    # Duplicating one observation must never turn it into temporal evidence.
    evidence["samples"] = evidence["samples"][:1] * 5
    assert _tracking_crop_containment(metadata, strategy=strategy,
                                     top_banner_enabled=False, bottom_banner_enabled=False)[0] is None
