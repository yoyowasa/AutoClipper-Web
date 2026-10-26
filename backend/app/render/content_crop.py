"""Resolve content intent with existing detectors/planners, never bypassing their limits."""

from dataclasses import replace

from app.render.crop_strategy import plan_short_crop


def resolve_content_crop(input_path, start, end, *, strategy, width, height, target_height,
                         dialogue_windows, face_detector, speaker_detector, person_detector, subject_detector):
    from app.render.render_short import (
        _detect_faces_for_layout, _detect_person_for_layout, _detect_speaker_for_layout, _detect_subject_for_layout,
    )
    options = dict(source_width=width, source_height=height, target_height=target_height)
    faces = []
    if strategy in {"blur_background", "center_crop"}:
        return plan_short_crop(strategy, **options), faces
    if strategy == "face_tracking_crop":
        faces = _detect_faces_for_layout("auto", input_path, start, end, face_detector)
        options["detections"] = faces
    elif strategy == "speaker_tracking_crop":
        options["speaker_signal"] = _detect_speaker_for_layout(
            "auto", input_path, start, end, dialogue_windows, speaker_detector, face_detector, person_detector,
        )
    elif strategy == "person_tracking_crop":
        options["person_signal"] = _detect_person_for_layout("auto", input_path, start, end, person_detector)
    elif strategy == "subject_tracking_crop":
        options["subject_signal"] = _detect_subject_for_layout("auto", input_path, start, end, subject_detector)
    else:
        raise ValueError("Unknown short framing strategy")
    plan = plan_short_crop("auto", **options)
    if plan.strategy_order[0] != strategy:
        # A content preference cannot authorize a crop without geometric evidence.
        return replace(plan, strategy_order=("blur_background",),
                       fallback_reason=f"content_crop_unavailable:{strategy}:{plan.fallback_reason}"), faces
    # Do not silently change the content target to an unrelated central crop on an encoder error.
    return replace(plan, strategy_order=(strategy, "blur_background")), faces
