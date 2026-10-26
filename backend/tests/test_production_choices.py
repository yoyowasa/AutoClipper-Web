import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, CandidateRejection, write_selected_clips
from app.jobs.clip_plan import build_clip_plan, write_clip_plan, load_clip_plan
from app.jobs.subtitle_review import build_subtitle_review, write_subtitle_review, load_subtitle_review
from app.jobs.title_hook_suggestions import (
    TitleHookSuggestionsDocument, TitleHookDraftSegment, build_title_hook_suggestion_input,
    write_title_hook_suggestions, title_hook_suggestions_path, apply_recommended_title_hook_suggestions,
)
from app.production_choices import ProductionChoice, choice_values
from app.production_choice_capture import thumbnail_choice
from app.production_records import ProductionRecord, write_production_record, refresh_completed_production
from test_production_records import example as example
from test_api_routes import client as client
from test_return_to_clip_plan import approved


def selection():
    return CandidateSelection(shorts=[Candidate(id="cand_example", type="short", start=100, end=175, duration=75,
        title="初期タイトル", transcript_text="PRIVATE TRANSCRIPT", selection_reason="候補の理由",
        opening_score=10, boundary_refined=False)],
        rejectedCandidates=[CandidateRejection(candidateId="rejected", type="short", reasons=["duration_out_of_range"],
                                              details={"start": 50, "end": 160, "path": "/private"})])


def artifact(review):
    request = build_title_hook_suggestion_input(review, "cand_example", [
        TitleHookDraftSegment(segmentId=s.id, text=s.text) for s in review.segments
    ], model="codex-default", provider="codex")
    return TitleHookSuggestionsDocument(clipId="cand_example", state="ready", inputHash=request.input_hash,
        draftHash=request.draft_hash, revisionHash=request.revision_hash, model="codex-default", provider="codex",
        recommendedSuggestionId="a", suggestions=[{
            "id": key, "intent": intent, "publicationTitle": f"公開案{key}", "overlayTitle": f"画面案{key}",
            "hookText": f"題材のフック{key}", "hookDurationSeconds": 3, "hookSceneStart": 1, "hookSceneEnd": 3,
            "reason": f"題材に対応{key}", "evidenceSegmentIds": [review.segments[0].id],
        } for key, intent in [("a", "factual"), ("b", "engagement"), ("c", "concise")]])


def test_choices_survive_recommendation_manual_edit_regeneration_and_output_deletion(example):
    db, job, export, paths = example
    root = paths.job_outputs(job.id)
    selected = selection()
    write_selected_clips(selected, root / "selected_clips.json")
    plan = build_clip_plan(job.id, selected, {})
    plan.state = "awaiting_review"
    write_clip_plan(plan, root / "clip_plan.json", choice_source="automatic")
    review = build_subtitle_review(job.id, selected, [TranscriptSegment(start=100, end=175, text="PRIVATE TRANSCRIPT")])
    write_subtitle_review(review, root / "subtitle_review.json")
    proposal = artifact(review)
    proposal_path = title_hook_suggestions_path(root, "cand_example")
    write_title_hook_suggestions(proposal, proposal_path)
    apply_recommended_title_hook_suggestions(review, proposal)
    write_subtitle_review(review, root / "subtitle_review.json")
    # Genuine new human wording, not a selection of an old proposal.
    review.clips[0].publication_title = "人が修正したタイトル"
    review.clips[0].selected_title_id = None
    write_subtitle_review(review, root / "subtitle_review.json", choice_source="manual")
    manual_ids = [c.id for c in review.choice_history if c.source == "manual"]
    # Re-generation retains the old alternatives; stale evidence must not be selected.
    review.segments[0].text = "更新後のPRIVATE TRANSCRIPT"
    new_proposal = artifact(review)
    new_proposal.suggestions[0].publication_title = "更新後の案"
    write_title_hook_suggestions(new_proposal, proposal_path)
    write_subtitle_review(review, root / "subtitle_review.json", choice_source="manual")
    export.title = review.clips[0].publication_title
    path = write_production_record(job, export, paths)
    record = ProductionRecord.model_validate_json(path.read_bytes())
    proposals = [c for c in record.choiceHistory if c.stage == "proposed"]
    assert len(proposals) == 2
    assert proposals[0].inputRevision != proposals[1].inputRevision
    assert proposals[0].candidates[0].values["publicationTitle"] == "公開案a"
    applied = [c for c in record.choiceHistory if c.kind == "title_hook" and c.stage == "applied"]
    assert any(c.source == "automatic" and c.selectedIds == ["a"] and c.recommendedId == "a" for c in applied)
    assert applied[-1].source == "manual" and applied[-1].selectedIds == []
    assert all(c.outcome != "selected" for c in applied[-1].candidates)
    assert [c.id for c in record.choiceHistory if c.source == "manual"] == manual_ids
    assert applied[-1].values["publicationTitle"] == export.title
    assert any(c.scope == "job" and any(p.id == "rejected" and p.outcome == "rejected" for p in c.candidates)
               for c in record.choiceHistory)
    assert "PRIVATE TRANSCRIPT" not in path.read_text(encoding="utf-8") and "/private" not in path.read_text(encoding="utf-8")
    # Exercise the real cleanup operation, including DB removal, not just a simulated unlink.
    from app.maintenance import delete_jobs
    from app.models import Video
    db.get(Video, job.video_id).stored_path = str(paths.root / "uploads" / "test-source.mp4")
    db.commit()
    before = path.read_bytes()
    delete_jobs(db, paths, [job.id], execute=True)
    assert not root.exists()
    assert path.read_bytes() == before
    assert ProductionRecord.model_validate_json(path.read_bytes()).choiceHistory == record.choiceHistory


def test_status_only_saves_do_not_duplicate_choices_and_plan_changes_keep_prior_range(tmp_path):
    plan = build_clip_plan("job", selection(), {})
    plan.state = "awaiting_review"
    path = tmp_path / "clip_plan.json"
    write_clip_plan(plan, path, choice_source="automatic")
    original = list(plan.choice_history)
    plan.updated_at = "2026-10-22T01:00:00+00:00"
    write_clip_plan(plan, path)
    assert plan.choice_history == original
    plan.state = "preparing"
    plan.clips[0].end = 170
    write_clip_plan(plan, path, choice_source="manual")
    assert plan.choice_history == original  # Queued preparation is not an applied edit.
    plan.state = "awaiting_review"
    write_clip_plan(plan, path, choice_source="manual")
    restored = load_clip_plan(path)
    assert [c.values["end"] for c in restored.choice_history] == [175, 170]
    assert restored.choice_history[-1].source == "manual"


def test_old_records_and_old_review_do_not_invent_history(example):
    _db, job, export, paths = example
    payload = json.loads(write_production_record(job, export, paths).read_bytes())
    del payload["choiceHistory"]
    assert ProductionRecord.model_validate(payload).choiceHistory == []
    review = build_subtitle_review(job.id, selection(), [])
    path = paths.job_outputs(job.id) / "subtitle_review.json"
    path.write_text(review.model_dump_json(by_alias=True), encoding="utf-8")
    assert load_subtitle_review(path).choice_history == []


def test_rerender_keeps_choices_and_lineage(example):
    _db, job, export, paths = example
    first = ProductionRecord.model_validate_json(write_production_record(job, export, paths).read_bytes())
    from app.models import ExportItem
    rerender = ExportItem(id="exp_rerender", job_id=job.id, video_id=job.video_id, candidate_id=export.candidate_id,
                         type=export.type, title=export.title, duration=export.duration, score=export.score,
                         video_path=export.video_path, metadata_path=export.metadata_path)
    second = ProductionRecord.model_validate_json(write_production_record(job, rerender, paths, previous_export=export).read_bytes())
    assert second.revision == 2 and second.createdAt == first.createdAt and second.previousRecordId == export.id
    assert second.choiceHistory[:-1] == first.choiceHistory


def test_completed_thumbnail_refresh_and_record_failure_are_independent(example, monkeypatch, caplog):
    db, job, export, paths = example
    first = ProductionRecord.model_validate_json(write_production_record(job, export, paths).read_bytes())
    metadata = Path(export.metadata_path)
    payload = json.loads(metadata.read_bytes())
    payload.update(thumbnail_line1="編集したサムネ", thumbnail_status="ready", thumbnail_render_revision=2)
    payload = thumbnail_choice(payload, clip_id=export.candidate_id, source="manual")
    metadata.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    refresh_completed_production(db, export, paths)
    second = ProductionRecord.model_validate_json(paths.production_record(export.id).read_bytes())
    assert second.thumbnailLine1 == "編集したサムネ" and second.revision == 2 and second.createdAt == first.createdAt
    assert any(c.kind == "thumbnail" and c.source == "manual" for c in second.choiceHistory)
    def fail(*args, **kwargs):
        raise OSError("secret must not be logged")
    monkeypatch.setattr("app.production_records.write_json_atomic", fail)
    refresh_completed_production(db, export, paths)
    assert job.status == "completed" and json.loads(metadata.read_bytes())["thumbnail_status"] == "ready"
    assert "OSError" in caplog.text and "secret must not be logged" not in caplog.text
    assert ProductionRecord.model_validate_json(paths.production_record(export.id).read_bytes()) == second


def test_allowlist_rejects_paths_and_nested_private_values():
    safe = choice_values({"titleStyle": {"fontSize": 30, "path": "/private"}, "transcript": "PRIVATE", "token": "secret"})
    assert safe == {"titleStyle": {"fontSize": 30}}
    with pytest.raises(ValidationError):
        ProductionChoice(kind="text_style", stage="observed", values={"titleStyle": {"path": "/private"}})


def test_apply_api_keeps_manual_history_through_preview_save_and_return(client):
    data = approved(client)
    review_path = data.output / "subtitle_review.json"
    before = load_subtitle_review(review_path)
    clip = before.clips[0]
    response = client.post(f"/api/jobs/{data.id}/subtitle-review/clips/{clip.id}/apply", json={
        "title": "人が選んだ画面タイトル", "publicationTitle": "人が選んだ公開タイトル", "hookText": "題材のフック",
    })
    assert response.status_code == 200, response.text
    after = load_subtitle_review(review_path)
    choices = [c for c in after.choice_history if c.kind == "title_hook" and c.clipId == clip.id]
    assert choices[-1].source == "manual" and choices[-1].values["title"] == "人が選んだ画面タイトル"
    ids = {c.id for c in after.choice_history}
    assert client.post(data.endpoint).status_code == 200
    plan = load_clip_plan(data.output / "clip_plan.json")
    assert ids <= {c.id for c in plan.choice_history}
    assert not review_path.exists()


def test_manual_title_does_not_claim_old_selected_id(tmp_path):
    review = build_subtitle_review("job", selection(), [TranscriptSegment(start=100, end=175, text="test")])
    proposal = artifact(review)
    apply_recommended_title_hook_suggestions(review, proposal)
    review.clips[0].publication_title = "別の手書きタイトル"
    path = tmp_path / "review.json"
    write_subtitle_review(review, path, choice_source="manual")
    choices = [c for c in load_subtitle_review(path).choice_history if c.kind == "title_hook"]
    assert choices[-1].selectedIds == []
    assert all(c.outcome != "selected" for c in choices[-1].candidates)
