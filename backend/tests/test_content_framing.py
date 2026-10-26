from pathlib import Path
from types import SimpleNamespace
import json

import pytest
from pydantic import ValidationError

from app.jobs.content_framing import choose_content_framing, framing_input
from app.jobs.quality_gate import _tracking_crop_containment
from app.production_choices import dump_history
from app.render.render_short import _tracking_evidence_for_render, resolve_short_crop_plan
from app.scoring.short_framing import CodexShortFramingSelector, SHORT_FRAMING_SCHEMA, ShortFramingChoice
from app.storage.paths import StoragePaths
from app.video.face_detect import FaceDetection
from test_automatic_visual_decisions import decide, visual_example


def choice(payload, strategy="face_tracking_crop"):
    return ShortFramingChoice(strategy=strategy, highlightType="expression_reaction", reason="驚いた表情が見どころです。",
                              evidenceIds=[payload["subtitles"][0]["id"], payload["frames"][0]["id"]])


def test_request_uses_confirmed_content_and_clip_local_frames_then_reuses_result(tmp_path):
    doc, clip, *_ = visual_example()
    clip.hook_scene_start, clip.hook_scene_end = 12, 14
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    calls, times = [], []
    def generate(payload, images):
        calls.append(payload)
        assert len(images) == 4
        return choice(payload)
    def extract(source, path, time):
        times.append(time)
        path.write_bytes(b"image")
        return path
    paths = StoragePaths(root=tmp_path / "storage")
    def run():
        return choose_content_framing(doc, clip, paths=paths, source=source,
                                      selector=SimpleNamespace(generate=generate), extractor=extract)
    first = run()
    assert first == run() and len(calls) == 1
    assert calls[0]["title"] == clip.title and calls[0]["hook"] == clip.hook_text
    assert calls[0]["subtitles"][0]["text"] == doc.segments[0].text
    assert times == [16, 40, 64, 13]  # hook uses source seconds, not start + source seconds
    doc.segments[0].text = "確定した字幕の変更"
    assert run()[1] != first[1] and len(calls) == 2


@pytest.mark.parametrize("ids", [["unknown", "frame-0"], ["frame-0", "frame-1"], ["segment"]])
def test_unverifiable_content_evidence_rejected(ids):
    doc, clip, *_ = visual_example()
    with pytest.raises(ValueError):
        result = choice(framing_input(doc, clip)).model_copy(update={"evidence_ids": ids})
        result.validate_evidence(framing_input(doc, clip))


def test_schema_and_bridge_contract(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from launcher.codex_bridge import EXPECTED_RESPONSE_SCHEMA_SHA256, _response_schema_sha256, validate_request
    assert EXPECTED_RESPONSE_SCHEMA_SHA256["short_framing_select"] == _response_schema_sha256(SHORT_FRAMING_SCHEMA)
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"jpeg")
    request = validate_request({"schemaVersion": 1, "task": "short_framing_select", "requestId": "framing",
                                "prompt": "confirmed input", "responseSchema": SHORT_FRAMING_SCHEMA,
                                "images": [image.name], "threadScope": "job:clip"}, tmp_path)
    assert request.image_paths == (image,)
    with pytest.raises(ValidationError):
        ShortFramingChoice(strategy="new_layout", highlightType="motion", reason="test", evidenceIds=["a", "b"])


def test_content_intent_is_recorded_and_manual_framing_is_preserved():
    doc, clip, _, _, settings, video = visual_example()
    selected = choice(framing_input(doc, clip))
    decide(doc, clip, settings, video, content_choice=selected, framing_revision="input-hash")
    record = next(c for c in doc.choice_history if c.kind == "framing")
    assert record.values["contentPreferredLayout"] == selected.strategy
    assert record.values["framingEvidenceIds"] == selected.evidence_ids
    assert record.values["highlightType"] == selected.highlight_type
    assert dump_history([record])[0]["values"]["framingDecisionRevision"] == "input-hash"
    clip.manual_decision_fields = ["framing"]
    clip.short_layout, clip.framing_offset_x = "center_crop", 20
    decide(doc, clip, settings, video, content_choice=selected)
    record = [c for c in doc.choice_history if c.kind == "framing"][-1]
    assert record.source == "manual" and "contentPreferredLayout" not in record.values
    assert clip.short_layout == "center_crop" and clip.framing_offset_x == 20


@pytest.mark.parametrize("strategy", ["face_tracking_crop", "speaker_tracking_crop"])
def test_content_selected_tracking_passes_with_actual_safe_samples(strategy):
    from app.video.speaker_detect import DialogueWindow
    def faces(_path, start, end):
        return [FaceDetection(t, t, .65, .35, .12, .15, .95) for t in (start, (start + end) / 2, end)]
    plan, detections = resolve_short_crop_plan(
        "unused", 0, 30, layout="auto", width=1920, height=1080, target_height=1200,
        preferred_strategy=strategy, face_detector=faces, dialogue_windows=[DialogueWindow(t, t + 2) for t in (1, 14, 26)],
        person_detector=lambda *a: pytest.fail("not needed"), subject_detector=lambda *a: pytest.fail("not needed"),
    )
    assert plan.strategy_order[0] == strategy
    evidence = _tracking_evidence_for_render(strategy, crop_plan=plan, detections=detections,
        start=0, end=30, source_width=1920, source_height=1080, target_height=1200,
        framing_offset_x=0, framing_offset_y=0, framing_zoom=1)
    metadata = {"tracking_evidence": evidence, "speaker_region_confidence": plan.speaker_region_confidence,
                "crop_stability_score": plan.stability_score, "speaker_window_count": plan.speaker_window_count}
    assert _tracking_crop_containment(metadata, strategy=strategy, top_banner_enabled=True, bottom_banner_enabled=True)[0] is True
    evidence["samples"][0]["box"] = [0, 0, 1, 1]
    assert _tracking_crop_containment(metadata, strategy=strategy, top_banner_enabled=True, bottom_banner_enabled=True)[0] is False


def test_missing_detections_do_not_authorize_preferred_crop():
    plan, _ = resolve_short_crop_plan(Path("unused"), 0, 30, layout="auto", width=1920, height=1080,
                                      target_height=1200, preferred_strategy="face_tracking_crop", face_detector=lambda *a: [])
    assert plan.strategy_order == ("blur_background",)
    assert plan.fallback_reason.startswith("content_crop_unavailable:face_tracking_crop:")


def test_transport_accepts_new_task_and_returns_validated_choice(tmp_path):
    doc, clip, *_ = visual_example()
    payload = framing_input(doc, clip)
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"jpeg")
    def respond(_seconds):
        request = json.loads(next((tmp_path / "codex_bridge/requests").glob("*.json")).read_text(encoding="utf-8"))
        assert request["task"] == "short_framing_select"
        assert request["images"] == ["frame.jpg"]
        path = tmp_path / "codex_bridge/responses" / (request["requestId"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schemaVersion": 1, "requestId": request["requestId"], "state": "ready",
                                   "output": choice(payload).model_dump(by_alias=True)}), encoding="utf-8")
    selector = CodexShortFramingSelector(storage_root=tmp_path, job_id="job", clip_id="clip",
                                         timeout_seconds=1, poll_seconds=.01, sleep_func=respond)
    assert selector.generate(payload, [image]) == choice(payload)


def test_anime_face_samples_do_not_mix_background_false_detections():
    import numpy as np
    from app.video.content_face_detect import detect_content_faces_for_clip
    class Capture:
        released = False
        def isOpened(self): return True
        def set(self, key, value): pass
        def read(self): return True, np.zeros((108, 192, 3), dtype=np.uint8)
        def release(self): self.released = True
    capture = Capture()
    faces = detect_content_faces_for_clip("unused", 10, 50, capture_factory=lambda p: capture,
        detector=lambda image: (.54, .45, .17, .30), fallback=lambda *a: pytest.fail("unrelated background faces"))
    assert capture.released and len(faces) == 5 and len({f.start for f in faces}) == 5
    assert all(f.center_x == .54 and f.height == .30 for f in faces)
    original = [FaceDetection(0, 1, .5, .4, .1, .2)]
    assert detect_content_faces_for_clip("unused", 10, 50, capture_factory=lambda p: Capture(),
        detector=lambda image: None, fallback=lambda *a: original) == original


@pytest.mark.parametrize("saved", json.loads(
    (Path(__file__).parent / "fixtures/task232_content_faces.json").read_text(encoding="utf-8")))
def test_saved_reaction_clips_pass_unchanged_geometry_check(saved):
    faces = [FaceDetection(**item) for item in saved["faces"]]
    plan, detected = resolve_short_crop_plan("unused", faces[0].start, faces[-1].end, layout="auto", width=1920, height=1080,
        target_height=1200, preferred_strategy="face_tracking_crop", face_detector=lambda *a: faces)
    assert plan.strategy_order[0] == "face_tracking_crop"
    evidence = _tracking_evidence_for_render("face_tracking_crop", crop_plan=plan, detections=detected,
        start=faces[0].start, end=faces[-1].end, source_width=1920, source_height=1080, target_height=1200,
        framing_offset_x=0, framing_offset_y=0, framing_zoom=1)
    assert evidence["crop"] == saved["expectedCrop"]
    assert _tracking_crop_containment({"tracking_evidence": evidence}, strategy="face_tracking_crop",
                                      top_banner_enabled=True, bottom_banner_enabled=True)[0] is True
