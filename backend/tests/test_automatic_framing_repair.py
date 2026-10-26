"""Saved task-230 geometry replay; FFmpeg/probing are stubbed, gates are real."""

from dataclasses import replace
import json
from pathlib import Path

import pytest
from sqlalchemy import select

import app.jobs.quality_gate as gates
import app.jobs.runner as runner
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.jobs.automatic_framing_repair import repair_automatic_short_framing
from app.jobs.automatic_review_status import automatic_stop_reasons
from app.jobs.subtitle_review import load_subtitle_review, write_subtitle_review
from app.models import ExportItem, Job, Video
from app.render.render_short import render_short_clip
from app.render.short_crop_decision import ShortCropDecision
from app.video.probe import VideoMetadata
from app.storage.paths import StoragePaths
from test_guarded_quality_gate_integration import guarded_client as guarded_client, _decision
from test_subtitle_only_auto import setup_auto, confirm, decide


SAVED = json.loads((Path(__file__).parent / "fixtures/task230_saved_framing.json").read_text(encoding="utf-8"))


def load_selected_clips(path):
    return CandidateSelection.model_validate_json(path.read_text(encoding="utf-8"))


def prepare_saved_job(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    data.run()
    confirm(data, load_subtitle_review(data.review_path).clips[0])
    assert decide(data) == "ready"
    review = load_subtitle_review(data.review_path)
    template = review.clips[0]
    segment = review.segments[0]
    selection_path = data.storage.job_outputs(data.job_id) / "selected_clips.json"
    selection = load_selected_clips(selection_path)
    candidate = selection.shorts[0]
    review.clips, review.segments, selection.shorts = [], [], []
    for index, saved in enumerate(SAVED["clips"]):
        fields = {key: saved[key] for key in ("id", "start", "end", "duration")}
        clip = template.model_copy(deep=True, update={
            **fields, "automatic_crop": ShortCropDecision.model_validate(saved["automatic_crop"]),
            "short_layout": "auto", "segment_ids": [f"segment_{index}"],
            "hook_scene_start": None, "hook_scene_end": None, "hook_text": "",
            "preview_state": "ready", "preview_deferred": False, "preview_width": 1080, "preview_height": 1920,
        })
        review.clips.append(clip)
        review.segments.append(segment.model_copy(update={
            "id": clip.segment_ids[0], "index": index, "start": clip.start, "end": clip.start + 2,
            "text": "確認した字幕", "original_text": "確認した字幕", "affected_clip_ids": [clip.id],
        }))
        selection.shorts.append(candidate.model_copy(update=fields))
    review.short_top_banner_enabled = review.short_bottom_banner_enabled = True
    review.confirmed_clip_count = review.total_clip_count = 5
    review.state = "render_queued"
    write_subtitle_review(review, data.review_path)
    write_selected_clips(selection, selection_path)
    with data.factory() as db:
        job = db.get(Job, data.job_id)
        job.status = "rendering_normal_clips"
        job.settings_json = {**job.settings_json, "shortTopBannerEnabled": True, "shortBottomBannerEnabled": True}
        db.get(Video, job.video_id).duration = 6000
        db.commit()
    # This regression begins after subtitle confirmation/content validation. The
    # saved incident has all non-visual post-render checks passing.
    monkeypatch.setattr(runner, "evaluate_content_quality_gate",
                        lambda **kw: _decision(kw["job_id"], stage="content", outcome="pass", mode="auto"))
    monkeypatch.setattr(runner, "generate_export_thumbnails", lambda **kw: None)
    return data, review


@pytest.mark.parametrize("repair_failure", [False, True])
@pytest.mark.parametrize("rerender", [False, True])
def test_saved_five_shorts_complete_without_human_or_stop_after_one_repair(
    guarded_client, monkeypatch, tmp_path, repair_failure, rerender,
):
    data, original = prepare_saved_job(guarded_client, monkeypatch, tmp_path)
    from app.production_choices import append_choice
    for clip in original.clips:
        append_choice(original.choice_history, kind="framing", clipId=clip.id, stage="applied", source="automatic",
                      reason="表情のリアクションを見せる", values={"contentPreferredLayout": clip.automatic_crop.plan.strategy_order[0],
                      "highlightType": "expression_reaction", "framingEvidenceIds": [clip.segment_ids[0], "frame-0"],
                      "framingDecisionRevision": "test-input", "framingReason": "表情のリアクションを見せる"})
    write_subtitle_review(original, data.review_path)
    previous_ids = set()
    previous_files = {}
    if rerender:
        from app.video.tracking_sample import TrackingSample
        original.render_revision += 1
        clip = original.clips[1]
        plan = clip.automatic_crop.plan
        clip.automatic_crop.plan = replace(plan, tracking_samples=tuple(
            TrackingSample(start=t, end=t, box=plan.speaker_region_box,
                           confidence=plan.speaker_region_confidence, source="test_outside_observation")
            for t in (clip.start, (clip.start + clip.end) / 2, clip.end)
        ))
        write_subtitle_review(original, data.review_path)
        with data.factory() as db:
            job = db.get(Job, data.job_id)
            for index, clip in enumerate(original.clips, 1):
                root = data.storage.job_outputs(data.job_id) / "shorts"
                root.mkdir(exist_ok=True)
                video = root / f"short_{index:02d}.mp4"
                metadata = video.with_suffix(".json")
                video.write_bytes(b"existing published video")
                metadata.write_text("{}", encoding="utf-8")
                previous_files.update({video: video.read_bytes(), metadata: metadata.read_bytes()})
                export = ExportItem(id=f"exp_previous_{index}", job_id=job.id, video_id=job.video_id,
                                    candidate_id=clip.id, type="short", title=clip.title, duration=clip.duration,
                                    score=1, video_path=str(video), metadata_path=str(metadata))
                previous_ids.add(export.id)
                db.add(export)
            db.commit()
    renders = []
    def renderer(source, target, **kwargs):
        renders.append((Path(target).name, kwargs["layout"]))
        if repair_failure and kwargs["layout"] == "blur_background":
            raise RuntimeError("test repair could not render")
        def command(argv):
            Path(argv[-1]).write_bytes(b"mock encoded media")
        return render_short_clip(source, target, **kwargs, command_runner=command,
                                 face_detector=lambda *a: pytest.fail("saved crop must be reused"))

    def probe(path):
        metadata = json.loads(Path(path).with_suffix(".json").read_text(encoding="utf-8"))
        duration = metadata.get("output_duration", metadata["duration"])
        return VideoMetadata(duration=duration, width=1080, height=1920, fps=30, has_audio=True,
                             video_stream_duration=duration, audio_stream_duration=duration)
    monkeypatch.setattr(gates, "probe_metadata", probe)
    statuses = runner.run_subtitle_review_render(
        data.job_id, render_revision=original.render_revision, paths=data.storage, session_factory=data.factory,
        dependencies=replace(data.deps, short_renderer=renderer),
    )
    decision = gates.load_quality_gate_decision(
        gates.quality_gate_decision_path(data.storage.job_outputs(data.job_id), "post_render"),
    )
    visual = next((check for check in decision.checks if check.code == "post_render.visual_framing_layout"), None)
    assert visual is not None, decision.model_dump()
    assert len(renders) == 8, [check.model_dump() for check in decision.checks if check.outcome != "pass"]
    assert renders[5:] == [("short_01.mp4", "blur_background"), ("short_02.mp4", "blur_background"),
                          ("short_05.mp4", "blur_background")]
    repair = visual.evidence["automaticFramingRepair"]
    assert repair["maxAttempts"] == 1
    assert len(repair["before"]["evidence"]["unknown"]) == (2 if rerender else 3)
    assert len(repair["before"]["evidence"]["failures"]) == (1 if rerender else 0)
    updated = load_subtitle_review(data.review_path)
    choices = [c for c in updated.choice_history if c.policyVersion == "safe_full_frame_v1"]
    assert len(choices) == 3
    assert all(c.source == "fallback" and c.values["resolvedLayout"] == "blur_background" for c in choices)
    with data.factory() as db:
        exports = db.scalars(select(ExportItem).where(ExportItem.job_id == data.job_id)).all()
        if repair_failure:
            if not rerender:
                assert statuses[-1] == "awaiting_subtitle_review"
            assert db.get(Job, data.job_id).status == "awaiting_subtitle_review"
            assert {export.id for export in exports} == previous_ids and decision.outcome == "fail"
            assert all(path.read_bytes() == content for path, content in previous_files.items())
            messages = automatic_stop_reasons(updated, data.storage.job_outputs(data.job_id))
            assert messages and all(clip.id not in message for clip in updated.clips for message in messages)
            assert any("ショート2" in message and "再書き出し" in message for message in messages)
        else:
            assert statuses[-1] == "completed"
            assert db.get(Job, data.job_id).status == "completed"
            assert len(exports) == 5 and decision.route == "continue"
            assert all(check.outcome == "pass" for check in decision.checks)
            for export in exports:
                metadata = json.loads(Path(export.metadata_path).read_text(encoding="utf-8"))
                assert metadata["crop_strategy"] == "blur_background"
                record = json.loads(data.storage.production_record(export.id).read_text(encoding="utf-8"))
                history = [c for c in record["choiceHistory"] if c.get("policyVersion") == "safe_full_frame_v1"]
                assert bool(history) == (export.candidate_id in repair["attemptedClipIds"])
                if history:
                    assert "完成検査のため" in history[0]["reason"] and "automatic_framing_repair:" in history[0]["reason"]
                    assert history[0]["values"]["highlightType"] == "expression_reaction"
                    assert history[0]["values"]["framingEvidenceIds"]
                    assert history[0]["values"]["contentPreferredLayout"].endswith("tracking_crop")
    assert all(c.confirmed for c in updated.clips)


@pytest.mark.parametrize("protected", ["manual", "legacy", "other_gate"])
def test_repair_does_not_override_manual_legacy_or_other_quality_failures(
    guarded_client, monkeypatch, tmp_path, protected,
):
    from app.jobs.quality_gate import QualityGateCheck
    from app.render.render_short import ShortRenderBatchResult
    from types import SimpleNamespace
    data, review = prepare_saved_job(guarded_client, monkeypatch, tmp_path)
    selection = load_selected_clips(data.storage.job_outputs(data.job_id) / "selected_clips.json")
    decision = _decision(data.job_id, stage="post_render", outcome="fail", mode="auto")
    decision.checks = [QualityGateCheck.model_validate(SAVED["visualBefore"])]
    if protected == "manual":
        for clip in review.clips:
            clip.manual_decision_fields = ["framing"]
    elif protected == "legacy":
        review.subtitle_only_auto = False
    else:
        decision.checks.append(QualityGateCheck(code="post_render.media_artifacts", outcome="fail", reasonCode="test_invalid_media"))
    result = ShortRenderBatchResult(
        exports=[SimpleNamespace(candidate_id=clip.id) for clip in review.clips], failures=[],
    )
    with data.factory() as db:
        actual, evidence = repair_automatic_short_framing(
            db=db, document=review, selection=selection, decision=decision, result=result,
            render_shorts=lambda **kw: pytest.fail("protected framing must not be changed"),
        )
    assert actual is result and evidence is None


@pytest.mark.parametrize("automatic,manual", [(True, False), (False, False), (True, True)])
def test_render_budget_includes_one_automatic_short_repair(tmp_path, monkeypatch, automatic, manual):
    import app.jobs.timeouts as timeouts
    paths = StoragePaths(tmp_path / "storage")
    path = paths.job_outputs("test") / "subtitle_review.json"
    path.write_text(json.dumps({
        "subtitleOnlyAuto": automatic,
        "clips": [
            {"id": "normal", "type": "normal", "start": 0, "end": 600},
            {"id": "short", "type": "short", "start": 0, "end": 75, "hookSceneStart": 1, "hookSceneEnd": 4,
             "manualDecisionFields": ["framing"] if manual else []},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(timeouts, "get_storage_paths", lambda: paths)
    assert timeouts.job_media_timeout("test") == timeouts.media_timeout(678 + (78 if automatic and not manual else 0))
    assert timeouts.job_media_timeout("test", clip_id="short") == timeouts.media_timeout(78)
