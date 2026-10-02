import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.codex_initial_selection import (
    CODEX_INITIAL_SELECTION_PROMPT, CODEX_TOPIC_SELECTION_PROMPT,
    build_codex_initial_selection_request, convert_codex_initial_selection_response,
)
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, partition_candidates_by_duration
from app.candidates.user_rejections import rejection_context_guidance
from app.db import Base
from app.duration_rules import selection_duration_rejection
from app.jobs.clip_plan import build_clip_plan, load_clip_plan, write_clip_plan
from app.jobs import pipeline_common as pipeline, queue, timeouts
from app.jobs import thumbnail_candidates
from PIL import Image
import numpy as np
from types import SimpleNamespace
from app.jobs.quality_gate import evaluate_selection_quality_gate
from app.models import ExportItem, Job, Video
from app.storage.paths import StoragePaths
from test_codex_initial_selection import _response, _settings


REASON = "初配信の人物紹介から活動方針の説明と結論までが一つのテーマで、途中では文脈が切れるため。"
TRANSCRIPT = [TranscriptSegment(start=i, end=i + 30, text="紹介から結論まで連続した説明です。") for i in range(0, 2010, 30)]


def long_request(**settings):
    return build_codex_initial_selection_request(
        job_id="longform", transcript_segments=TRANSCRIPT, heatmap_segments=[], video_duration=2100,
        settings=_settings(normalMaxDuration=600, normalClipCount=1, shortCount=0, **settings),
    )


@pytest.mark.parametrize("duration,reason,expected", [
    (600, "", None), (601, "", "longform_without_reason"), (601, " \n ", "longform_without_reason"),
    (601, REASON, None), (1800, REASON, None), (1801, REASON, "duration_out_of_range"),
])
def test_longform_selection_boundaries(duration, reason, expected):
    request = long_request()
    response = _response(request)
    proposal = response.selected_clips[0].model_copy(update={"end": duration, "longform_reason": reason})
    result = convert_codex_initial_selection_response(request, response.model_copy(update={"selected_clips": [proposal]}))
    assert request.constraints.normal.max_duration == 600
    assert request.constraints.normal.longform_max_duration == 1800
    if expected:
        assert result.selection.normal_clips == []
        assert result.dropped_normal_candidates[0].code == expected
        assert result.selection.rejected_candidates[0].reasons == [expected]
    else:
        assert result.selection.normal_clips[0].duration == duration
        assert result.selection.normal_clips[0].longform_reason == (reason if duration > 600 else "")


def long_candidate(duration=900, **updates):
    candidate = Candidate(
        id="normal", type="normal", start=0, end=duration, duration=duration, transcript_text="一つの話題の説明と結論です。",
        title="人物紹介", longform_reason=REASON, selection_reason="codex_direct", boundary_refined=False,
    )
    return candidate.model_copy(update=updates)


def test_longform_reason_survives_candidate_plan_and_legacy_read(tmp_path):
    candidate = long_candidate()
    restored = Candidate.model_validate_json(candidate.model_dump_json())
    assert restored.longform_reason == REASON
    plan = build_clip_plan("job_long", CandidateSelection(normalClips=[restored]), settings={})
    path = tmp_path / "clip_plan.json"
    write_clip_plan(plan, path)
    assert load_clip_plan(path).clips[0].longform_reason == REASON
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["clips"][0].pop("longformReason") == REASON
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_clip_plan(path).clips[0].longform_reason == ""
    candidate_payload = restored.model_dump()
    candidate_payload.pop("longform_reason")
    assert Candidate.model_validate(candidate_payload).longform_reason == ""


def test_missing_context_reselection_can_expand_past_ten_minutes():
    settings = {"normalMinDuration": 90, "normalMaxDuration": 600, "excludePreviousSelection": False,
                "_previousProposedRanges": [[90, 600]],
                "_rejectedRanges": [{"start": 90, "end": 600, "type": "normal", "reason": "missing_context", "note": ""}]}
    candidate = long_candidate(900)
    selection, pool = pipeline._selection_with_refined_boundaries(
        CandidateSelection(normalClips=[candidate], requestedNormalCount=1), [candidate],
        transcript_segments=TRANSCRIPT, silence_segments=[], scene_segments=[], settings=settings, timeline_duration=2100,
    )
    assert not pipeline._is_repeated_normal_proposal(selection.normal_clips[0], settings)
    assert len(selection.normal_clips) == len(pool) == 1
    assert 600 < selection.normal_clips[0].duration <= 1800
    assert selection.normal_clips[0].longform_reason == REASON
    guidance = rejection_context_guidance("normal", settings, max_length=1000)
    assert "最長30分" in guidance and "longformReason" in guidance
    for prompt in (CODEX_INITIAL_SELECTION_PROMPT, CODEX_TOPIC_SELECTION_PROMPT):
        assert "最長30分" in prompt and "水増し" in prompt


def test_post_refinement_keeps_reason_and_rejects_over_thirty_minutes(monkeypatch):
    monkeypatch.setattr(pipeline, "refine_selected_candidates", lambda items, **kwargs: [
        c.model_copy(update={"end": 1801, "duration": 1801}) for c in items])
    candidate = long_candidate()
    selection, pool = pipeline._selection_with_refined_boundaries(
        CandidateSelection(normalClips=[candidate], requestedNormalCount=1), [candidate],
        transcript_segments=TRANSCRIPT, silence_segments=[], scene_segments=[], settings={}, timeline_duration=2100,
    )
    assert selection.normal_clips == pool == []
    assert selection.rejected_candidates[0].reasons == ["duration_out_of_range"]


@pytest.mark.parametrize("manual", ["manual_time_range", "manual_edit", "boundary"])
def test_manual_longform_needs_no_ai_reason(manual):
    candidate = long_candidate(1800, longform_reason="", selection_reason=manual, clip_plan_boundary_adjusted=manual == "boundary")
    valid, rejected = partition_candidates_by_duration([candidate], {})
    assert valid == [candidate] and rejected == []
    assert selection_duration_rejection("normal", 1801, short_max=75, manual=True) == "duration_out_of_range"
    decision = evaluate_selection_quality_gate(
        job_id="job_long", selection=CandidateSelection(normalClips=[candidate]), transcript_segments=TRANSCRIPT,
        settings={"normalMaxDuration": 600}, source_duration=2100,
    )
    check = next(c for c in decision.checks if c.code == "selection.range_duration")
    assert check.outcome == "pass"


def test_longform_queue_budgets_use_clip_and_batch_lengths(tmp_path, monkeypatch):
    paths = StoragePaths(tmp_path)
    monkeypatch.setattr(timeouts, "get_storage_paths", lambda: paths)
    output = paths.job_outputs("job_long")
    output.mkdir(parents=True, exist_ok=True)
    (output / "clip_plan.json").write_text(json.dumps({"clips": [
        {"id": "a", "type": "normal", "start": 0, "end": 1800},
        {"id": "b", "type": "normal", "start": 1800, "end": 3600},
    ]}), encoding="utf-8")
    assert timeouts.job_media_timeout("job_long", clip_id="a") == 11400
    assert timeouts.job_media_timeout("job_long") == 22200
    assert timeouts.job_media_timeout("job_long", proposed_duration=1800) == 11400
    calls = []
    class FakeQueue:
        def enqueue(self, *args, **kwargs):
            calls.append(kwargs)
    monkeypatch.setattr(queue, "get_queue", FakeQueue)
    queue.enqueue_clip_plan_boundary_update("job_long", "a", 0, 1800)
    assert calls[0]["job_timeout"] == 11400


def test_initial_and_reselection_reserve_new_longform_not_old_plan(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + (tmp_path / "test.db").as_posix())
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(timeouts, "SessionLocal", factory)
    monkeypatch.setattr(timeouts, "get_storage_paths", lambda: StoragePaths(tmp_path))
    with factory() as db:
        db.add(Video(id="video", original_filename="test.mp4", stored_path="test.mp4", duration=2100))
        db.add(Job(id="job_long", video_id="video", settings_json={"normalClipCount": 2, "shortCount": 0}))
        db.add(ExportItem(
            id="exp_long", job_id="job_long", video_id="video", type="normal", title="test", score=1, video_path="test.mp4", duration=1800,
        ))
        db.commit()
    output = tmp_path / "outputs/job_long"
    output.mkdir(parents=True, exist_ok=True)
    (output / "clip_plan.json").write_text(json.dumps({"clips": [{"id": "a", "type": "normal", "start": 0, "end": 90}]}))
    assert timeouts.job_media_timeout("job_long", selection=True) == 22200
    assert timeouts.thumbnail_candidates_timeout("exp_long") == 6000
    calls = []
    class FakeQueue:
        def enqueue(self, *args, **kwargs):
            calls.append(kwargs)
    monkeypatch.setattr(queue, "get_queue", FakeQueue)
    queue.enqueue_clip_plan_reselection("job_long")
    queue.enqueue_thumbnail_candidates("exp_long", "request")
    assert [c["job_timeout"] for c in calls] == [22200, 6000]
    engine.dispose()


def test_thirty_minute_thumbnail_scan_processes_all_3600_frames_and_keeps_twelve(tmp_path, monkeypatch):
    monkeypatch.setattr(thumbnail_candidates, "probe_metadata", lambda _: SimpleNamespace(width=1920, height=1080))
    image = Image.fromarray(np.random.default_rng(183).integers(0, 256, (540, 960, 3), dtype=np.uint8))
    scanned = []
    extracted = []
    def scanner(source, start, end, size):
        assert (start, end) == (0, 1800)
        for index in range(3600):
            scanned.append(index)
            yield index / 2, image
    def extractor(source, path, second):
        extracted.append(second)
        image.resize((1920, 1080)).save(path)
    saved = thumbnail_candidates.extract_thumbnail_candidates(
        "synthetic.mp4", clip_start=0, clip_end=1800, directory=tmp_path,
        scanner=scanner, extractor=extractor, detector=lambda _: (.5, .3, .15, .18),
    )
    assert len(scanned) == 3600
    assert len(saved) == len(extracted) == 12
    assert all(0 <= c["second"] < 1800 for c in saved)
    assert len(list(tmp_path.glob("*.small.jpg"))) == 12


def test_manual_type_conversion_and_shortening_clear_old_longform_reason():
    from app.candidates.select_candidates import convert_selected_clip_to_normal, convert_selected_clip_to_short
    from app.jobs.clip_plan import update_clip_plan_boundary
    candidate = long_candidate()
    selection = convert_selected_clip_to_normal(CandidateSelection(shorts=[candidate.model_copy(update={"type": "short"})]), candidate.id)
    assert partition_candidates_by_duration(selection.normal_clips, {})[1] == []
    plan = build_clip_plan("job_long", CandidateSelection(normalClips=[candidate]), {})
    update_clip_plan_boundary(plan, candidate.id, start=0, end=600, transcript_excerpt="結論です。")
    assert plan.clips[0].longform_reason == ""
    converted = convert_selected_clip_to_short(CandidateSelection(normalClips=[candidate]), candidate.id)
    assert converted.shorts[0].longform_reason == ""
