from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import json
import pytest
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.inspection.models import Check, InspectionRecord
from app.inspection.media import file_hash
from app.inspection.service import inspect_final_outputs, FinalInspectionFailed, read_inspection_attention, production_inspection
from app.jobs.subtitle_review import build_subtitle_review
from app.storage.paths import StoragePaths


@pytest.fixture
def context(tmp_path):
    paths = StoragePaths(tmp_path)
    candidate = Candidate(
        id="cand_private_1", type="short", start=10, end=20, duration=10, transcript_text="The confirmed caption", title="Automatic title"
    )
    selection = CandidateSelection(shorts=[candidate])
    segments = [TranscriptSegment(start=11, end=14, text="The confirmed caption")]
    document = build_subtitle_review("job_test", selection, segments)
    clip = document.clips[0]
    clip.confirmed = True
    clip.automatic_decision_state = "ready"
    file = paths.job_outputs("job_test") / "video.mp4"
    file.write_bytes(b"owned unit fixture; decoding is tested separately")
    export = SimpleNamespace(job_id="job_test", candidate_id=candidate.id, video_path=str(file))
    kwargs = dict(
        exports=[export],
        selection=selection,
        source=tmp_path / "source.mp4",
        segments=segments,
        settings={},
        video=SimpleNamespace(width=1920, height=1080),
        paths=paths,
        job_id="job_test",
        document=document,
    )
    return SimpleNamespace(**kwargs, kwargs=kwargs, export=export, clip=clip, candidate=candidate)


def check(code="DURATION_MISMATCH", outcome="pass"):
    return Check(code=code, outcome=outcome, second=1.2)


def saved(e):
    return InspectionRecord.model_validate_json(e.paths.final_output_inspection("job_test", e.candidate.id).read_text(encoding="utf-8"))


def test_bad_output_is_repaired_and_reinspected_before_passing(context):
    e = context
    seen, repairs = [], []

    def inspect(export, candidate, **kw):
        seen.append(export)
        return file_hash(export.video_path), [check(outcome="pass" if repairs else "fail")]

    def repair(id, action):
        repairs.append((id, action))
        return e.export, e.candidate

    before = deepcopy(e.document)
    result = inspect_final_outputs(**e.kwargs, inspector=inspect, repair=repair)
    record = saved(e)
    assert result == [e.export] and len(seen) == 2 and len(repairs) == 1
    assert record.outcome == "pass" and len(record.attempts) == 2
    assert record.attempts[0].repair_result == "rendered; reinspection_required"
    assert e.document == before
    permanent = production_inspection(e.paths, e.export)
    assert permanent["repairCount"] == 1 and permanent["outcome"] == "pass"
    e.paths.resolve_stored_file(e.export.video_path).write_bytes(b"different output")
    assert production_inspection(e.paths, e.export) is None


def test_repair_cap_persists_and_cannot_be_reset_by_worker_retry(context):
    e = context
    codes = iter(["DURATION_MISMATCH", "SUBTITLE_OUT_OF_FRAME", "SUBTITLE_PIXELS_MISMATCH"])
    actions = []

    def inspect(*args, **kw):
        return "hash", [check(next(codes), "fail")]

    def repair(id, action):
        actions.append(action)
        return e.export, e.candidate

    with pytest.raises(FinalInspectionFailed, match="ショート1"):
        inspect_final_outputs(**e.kwargs, inspector=inspect, repair=repair)
    assert actions == ["rerender_same", "refit_subtitle"]
    record = saved(e)
    assert record.outcome == "incomplete" and len(record.attempts) == 3
    assert sum(bool(a.repair) for a in record.attempts) == 2
    with pytest.raises(FinalInspectionFailed):
        inspect_final_outputs(**e.kwargs, inspector=lambda *a, **kw: ("hash", [check(outcome="fail")]), repair=repair)
    assert len(actions) == 2
    attention = read_inspection_attention(e.paths, "job_test")
    assert attention[0]["repairCount"] == 2 and attention[0]["clipLabel"] == "ショート1"
    assert "cand_" not in json.dumps(attention, ensure_ascii=False)


@pytest.mark.parametrize("field", ["caption", "framing", "title"])
def test_a_repair_cannot_change_human_confirmed_values(context, field):
    e = context
    e.clip.manual_decision_fields = ["title", "framing"]
    original = deepcopy(e.document)

    def repair(id, action):
        if field == "caption":
            e.document.segments[0].text = "do not adopt this"
        elif field == "framing":
            e.clip.framing_offset_x = 30
        else:
            e.clip.title = "do not adopt this"
        return e.export, e.candidate

    with pytest.raises(FinalInspectionFailed):
        inspect_final_outputs(**e.kwargs, inspector=lambda *a, **kw: ("hash", [check(outcome="fail")]), repair=repair)
    assert e.document == original
    assert saved(e).attempts[-1].checks[-1].code == "REPAIR_FAILED"


@pytest.mark.parametrize("code,outcome", [("SEMANTIC_UNVERIFIED", "unknown"), ("CONTENT_MISMATCH", "fail")])
def test_unknown_or_manually_selected_content_is_not_silently_replaced(context, code, outcome):
    e = context
    e.clip.manual_decision_fields = ["publication_title"]
    calls = []
    with pytest.raises(FinalInspectionFailed):
        inspect_final_outputs(**e.kwargs, inspector=lambda *a, **kw: ("hash", [check(code, outcome)]), repair=lambda *a: calls.append(a))
    assert calls == [] and saved(e).outcome == "incomplete"


def test_only_requested_clips_are_inspected_and_missing_targets_cannot_complete(context):
    e = context
    other = e.candidate.model_copy(update={"id": "retained"})
    e.selection.shorts.append(other)
    calls = []
    inspect_final_outputs(
        **e.kwargs, clip_ids={e.candidate.id}, inspector=lambda export, candidate, **kw: (calls.append(candidate.id) or "hash", [check()])
    )
    assert calls == [e.candidate.id] and not e.paths.final_output_inspection("job_test", "retained").exists()
    with pytest.raises(FinalInspectionFailed):
        inspect_final_outputs(**e.kwargs, clip_ids={"retained"})
    assert read_inspection_attention(e.paths, "job_test")[0]["clipLabel"] == "ショート2"


def test_reading_missing_inspection_does_not_create_output_folder(tmp_path):
    paths = StoragePaths(tmp_path)
    assert read_inspection_attention(paths, "old_completed") == []
    assert not paths.outputs.exists()


@pytest.mark.parametrize("change", ["thumbnail", "title", "post_copy"])
def test_semantic_pass_is_not_reused_after_publication_edits(context, monkeypatch, change):
    from app.inspection.content import content_binding
    from app.storage.json_io import write_json_atomic
    import app.jobs.thumbnails as thumbnails

    e = context
    image = e.paths.job_outputs("job_test") / "thumbnail.jpg"
    image.write_bytes(b"original thumbnail")
    metadata = {"publication_title": "Original title", "youtube_description": "Original post"}
    e.export.title = metadata["publication_title"]
    e.export.metadata_path = str(image.with_suffix(".json"))
    write_json_atomic(Path(e.export.metadata_path), metadata)
    monkeypatch.setattr(thumbnails, "thumbnail_path_from_export", lambda export: image)
    binding = content_binding(metadata, image)
    inspect_final_outputs(
        **e.kwargs,
        inspector=lambda *a, **kw: (
            file_hash(e.export.video_path),
            [
                Check(code="CONTENT_MISMATCH", outcome="pass", evidence=binding),
            ],
        ),
    )
    assert production_inspection(e.paths, e.export)["outcome"] == "pass"
    if change == "thumbnail":
        image.write_bytes(b"edited thumbnail")
    elif change == "title":
        e.export.title = "Edited title"
    else:
        metadata["youtube_description"] = "Edited post"
        write_json_atomic(Path(e.export.metadata_path), metadata)
    assert production_inspection(e.paths, e.export) is None


def test_interrupted_inspection_is_visible_without_claiming_failure_or_pass(context):
    from app.inspection.service import persist

    e = context
    persist(e.paths, InspectionRecord(job_id="job_test", clip_id=e.clip.id, label="ショート1", input_revision="pending"))
    attention = read_inspection_attention(e.paths, "job_test")
    assert attention[0]["repairCount"] == 0
    assert "中断" in attention[0]["reason"] and "未完成" in attention[0]["reason"]


def test_targeted_repair_preserves_export_order_and_unchanged_clip(context):
    e = context
    other = e.candidate.model_copy(update={"id": "other"})
    e.selection.shorts.append(other)
    export2 = SimpleNamespace(job_id="job_test", candidate_id="other", video_path=e.export.video_path)
    e.kwargs["exports"] = [e.export, export2]
    calls = []

    def inspect(export, candidate, **kwargs):
        outcome = "fail" if candidate.id == e.candidate.id and not calls else "pass"
        return "hash", [check(outcome=outcome)]

    replacement = SimpleNamespace(job_id="job_test", candidate_id=e.candidate.id, video_path=e.export.video_path)

    def repair(*args):
        calls.append(args)
        return replacement, e.candidate

    result = inspect_final_outputs(**e.kwargs, inspector=inspect, repair=repair)
    assert result == [replacement, export2]
    assert calls == [(e.candidate.id, "rerender_same")]


def test_new_human_confirmed_input_gets_a_new_budget_but_delivery_retry_does_not(context):
    e = context
    calls = []

    def repair(id, action):
        calls.append(action)
        return e.export, e.candidate

    bad = lambda *a, **kw: ("hash", [check(outcome="fail")])
    with pytest.raises(FinalInspectionFailed):
        inspect_final_outputs(**e.kwargs, inspector=bad, repair=repair)
    before = saved(e).input_revision
    assert calls == ["rerender_same"]
    with pytest.raises(FinalInspectionFailed):
        inspect_final_outputs(**e.kwargs, inspector=bad, repair=repair)
    assert calls == ["rerender_same"]
    e.document.segments[0].text = "Human corrected subtitle"
    with pytest.raises(FinalInspectionFailed):
        inspect_final_outputs(**e.kwargs, inspector=bad, repair=repair)
    assert saved(e).input_revision != before
    assert calls == ["rerender_same", "rerender_same"]


def test_legacy_missing_candidate_or_deleted_media_does_not_block_record_building(context):
    e = context
    inspect_final_outputs(**e.kwargs, inspector=lambda *a, **kw: (file_hash(e.export.video_path), [check()]))
    Path(e.export.video_path).unlink()
    assert production_inspection(e.paths, e.export) is None
    e.export.candidate_id = None
    assert production_inspection(e.paths, e.export) is None
