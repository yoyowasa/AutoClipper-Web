"""Apply attribution is based on changed values, never a changed subtitle hash."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from app.jobs.subtitle_review import load_subtitle_review, write_subtitle_review
from app.production_choices import ProductionChoice
from app.production_choice_repair import identical_apply_repairs, repair_unchanged_manual_choices
from app.production_records import write_production_record
from app.schemas import SubtitleReviewClipApplyRequest
from app.storage.json_io import write_json_atomic
from test_production_records import example as example
from test_subtitle_only_auto import setup_auto, confirm, decide
from test_guarded_quality_gate_integration import guarded_client as guarded_client


def full_draft(clip):
    payload = clip.model_dump(mode="json", by_alias=True)
    result = {field.alias or key: payload[field.alias or key]
              for key, field in SubtitleReviewClipApplyRequest.model_fields.items()
              if (field.alias or key) in payload}
    if clip.type == "short":
        result["framing"] = {key: payload[key] for key in ("framingOffsetX", "framingOffsetY", "framingZoom", "shortLayout")}
    return result


@pytest.mark.parametrize("short", [False, True])
@pytest.mark.parametrize("after_automatic", [False, True])
@pytest.mark.parametrize("full_payload", [False, True])
def test_subtitle_only_apply_never_claims_manual_choices(guarded_client, monkeypatch, tmp_path, after_automatic, full_payload, short):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=short)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    if after_automatic:
        confirm(data, clip)
        assert decide(data) == "ready"
    before = load_subtitle_review(data.review_path)
    clip = before.clips[0]
    payload = full_draft(clip) if full_payload else {}
    payload["segments"] = [{"segmentId": clip.segment_ids[0], "text": "字幕の文字だけを修正しました"}]
    confirm(data, clip, **payload)
    saved = load_subtitle_review(data.review_path)
    assert saved.segments[0].text == "字幕の文字だけを修正しました"
    assert saved.clips[0].manual_decision_fields == []
    assert [c for c in saved.choice_history if c.source == "manual"] == []
    old_auto = [c for c in before.choice_history if c.source == "automatic"]
    assert all(c in saved.choice_history for c in old_auto)


@pytest.mark.parametrize(("edit", "field", "kind"), [
    ({"title": "人が変えたタイトル"}, "title", "title_hook"),
    ({"youtubeDescription": "人が変えた説明"}, "youtube_description", "post_copy"),
    ({"framing": {"framingOffsetX": 10, "framingOffsetY": 0, "framingZoom": 1}}, "framing", "framing"),
    ({"subtitleStyle": {"fontSize": 60}}, "subtitle_style", "text_style"),
])
def test_only_real_detail_changes_are_manual_and_protected(guarded_client, monkeypatch, tmp_path, edit, field, kind):
    data = setup_auto(guarded_client, monkeypatch, tmp_path, short=True)
    data.run()
    clip = load_subtitle_review(data.review_path).clips[0]
    if field == "framing":
        confirm(data, clip)
        assert decide(data) == "ready"
        clip = load_subtitle_review(data.review_path).clips[0]
    payload = {**full_draft(clip), **edit}
    confirm(data, clip, **payload)
    saved = load_subtitle_review(data.review_path)
    assert saved.clips[0].manual_decision_fields == [field]
    assert {c.kind for c in saved.choice_history if c.source == "manual"} == {kind}
    selected = getattr(saved.clips[0], field) if field != "framing" else saved.clips[0].framing_offset_x
    assert decide(data) == "ready"
    after_decisions = load_subtitle_review(data.review_path)
    assert {c.kind for c in after_decisions.choice_history if c.source == "manual"} == {kind}
    result = after_decisions.clips[0]
    assert (getattr(result, field) if field != "framing" else result.framing_offset_x) == selected
    # Reconfirming unchanged values must not revoke an earlier explicit override.
    confirm(data, result, **full_draft(result))
    assert field in load_subtitle_review(data.review_path).clips[0].manual_decision_fields


def test_plain_review_save_does_not_manualize_other_shared_clip_on_subtitle_revision(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    document = load_subtitle_review(data.review_path)
    other = document.clips[0].model_copy(deep=True, update={"id": "other"})
    document.clips.append(other)
    write_subtitle_review(document, data.review_path)
    document.segments[0].text = "共有字幕の修正"
    write_subtitle_review(document, data.review_path, choice_source="manual")
    assert not [c for c in document.choice_history if c.source == "manual"]


def apply_burst(clip_id="cand_example", source="automatic", *, changed_kind=None):
    start = datetime(2026, 10, 25, 14, 12, tzinfo=UTC)
    result = []
    values = {"title_hook": {"title": "元のタイトル"}, "framing": {"framingZoom": 1},
              "text_style": {"titleStyle": {"fontSize": 80}}, "post_copy": {"descriptionHash": "old"}}
    for index, (kind, value) in enumerate(values.items()):
        result.append(ProductionChoice(id=f"{clip_id}-before-{kind}", kind=kind, clipId=clip_id,
            stage="observed" if source == "unrecorded" else "applied", source=source,
            inputRevision="before", policyVersion="subtitle-review-v1", recordedAt=start + timedelta(microseconds=index), values=value))
    for index, (kind, value) in enumerate(values.items()):
        result.append(ProductionChoice(id=f"{clip_id}-after-{kind}", kind=kind, clipId=clip_id,
            stage="applied", source="manual", inputRevision="after", policyVersion="subtitle-review-v1",
            recordedAt=start + timedelta(minutes=30, microseconds=index),
            values={**value, "title": "本当の手直し"} if kind == changed_kind else value))
    return result


@pytest.mark.parametrize("source", ["automatic", "unrecorded"])
def test_burst_requires_exact_baseline_values_and_preserves_source(source):
    history = apply_burst(source=source, changed_kind="title_hook")
    repairs, retained = identical_apply_repairs(history)
    assert len(repairs) == 3 and len(retained) == 1
    assert {r["source"] for r in repairs.values()} == {source}
    assert retained[0]["kind"] == "title_hook"


@pytest.mark.parametrize("case", ["prior_manual", "missing_baseline", "separate_actions", "partial_burst", "same_revision"])
def test_unproven_manual_choices_are_retained(case):
    history = apply_burst(source="manual" if case == "prior_manual" else "automatic")
    if case == "missing_baseline":
        history = history[4:]
    if case == "separate_actions":
        for i, choice in enumerate(history[4:]):
            choice.recordedAt += timedelta(seconds=i * 5)
    if case == "partial_burst":
        history.pop()
    if case == "same_revision":
        for choice in history:
            choice.inputRevision = "same"
    assert identical_apply_repairs(history)[0] == {}


def repair_fixture(example, *, changed_kind=None):
    db, job, export, paths = example
    job.status = "completed"
    db.commit()
    history = [choice.model_dump(mode="json") for choice in apply_burst(source="unrecorded", changed_kind=changed_kind)]
    output = paths.job_outputs(job.id)
    review = output / "subtitle_review.json"
    write_json_atomic(review, {"choiceHistory": history, "clips": [{"id": export.candidate_id, "manualDecisionFields": []}],
                               "state": "approved", "jobId": job.id})
    record = write_production_record(job, export, paths)
    return db, job, export, paths, review, record


def test_repair_dry_run_execute_records_and_repeat_are_safe(example):
    db, job, export, paths, review, record = repair_fixture(example, changed_kind="title_hook")
    before_review, before_record = review.read_bytes(), record.read_bytes()
    result = repair_unchanged_manual_choices(db, paths, job.id)
    assert result["repaired_choice_count"] == 3
    assert review.read_bytes() == before_review and record.read_bytes() == before_record
    repair_unchanged_manual_choices(db, paths, job.id, execute=True)
    saved_review, saved_record = json.loads(review.read_bytes()), json.loads(record.read_bytes())
    assert saved_review["state"] == "approved" and saved_review["clips"][0]["manualDecisionFields"] == []
    previous = json.loads(before_record)
    assert saved_record["revision"] == previous["revision"] + 1
    assert saved_record["createdAt"] == previous["createdAt"]
    for payload in [saved_review, saved_record]:
        changed = {c["kind"]: c for c in payload["choiceHistory"] if "-after-" in c["id"]}
        assert changed["title_hook"]["source"] == "manual"
        assert all(changed[k]["source"] == "unrecorded" for k in ("framing", "text_style", "post_copy"))
    repaired = review.read_bytes(), record.read_bytes()
    assert repair_unchanged_manual_choices(db, paths, job.id, execute=True)["repaired_choice_count"] == 0
    assert repaired == (review.read_bytes(), record.read_bytes())
    # Future production-record refresh must not bring back the bad source from retained copies.
    write_production_record(job, export, paths)
    latest = json.loads(record.read_bytes())
    assert sum(c["source"] == "manual" for c in latest["choiceHistory"]) == 1


def test_repair_refuses_active_job_and_does_not_modify_it(example):
    db, job, _, paths, review, record = repair_fixture(example)
    job.status = "rendering_shorts"
    db.commit()
    original = review.read_bytes(), record.read_bytes()
    with pytest.raises(ValueError, match="Only idle"):
        repair_unchanged_manual_choices(db, paths, job.id, execute=True)
    assert original == (review.read_bytes(), record.read_bytes())


def test_repair_rolls_back_a_failed_file_write(example, monkeypatch):
    db, job, _, paths, review, record = repair_fixture(example)
    original = json.loads(review.read_bytes()), json.loads(record.read_bytes())
    calls = 0

    def fail_second(path, payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("locked file")
        return write_json_atomic(path, payload)

    monkeypatch.setattr("app.production_choice_repair.write_json_atomic", fail_second)
    with pytest.raises(PermissionError):
        repair_unchanged_manual_choices(db, paths, job.id, execute=True)
    assert original == (json.loads(review.read_bytes()), json.loads(record.read_bytes()))
    assert repair_unchanged_manual_choices(db, paths, job.id)["repaired_choice_count"] == 4


def test_cli_defaults_to_dry_run_and_accepts_explicit_execute(example, monkeypatch, capsys):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from app.maintenance import main
    db, job, _, paths, review, record = repair_fixture(example)
    original = review.read_bytes(), record.read_bytes()
    monkeypatch.setattr("app.maintenance.SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr("app.maintenance.get_settings", lambda: SimpleNamespace(storage_root=paths.root))
    assert main(["repair-unchanged-manual-choices", "--job", job.id]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert original == (review.read_bytes(), record.read_bytes())
    assert main(["repair-unchanged-manual-choices", "--job", job.id, "--execute"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is False
    assert original != (review.read_bytes(), record.read_bytes())


def test_repeated_bad_applies_are_corrected_together():
    history = apply_burst(source="unrecorded")
    second = [c.model_copy(update={"id": "repeat-" + c.id, "inputRevision": "third",
                                  "recordedAt": c.recordedAt + timedelta(minutes=10)}) for c in history[4:]]
    repairs, retained = identical_apply_repairs(history + second)
    assert len(repairs) == 8 and retained == []
    assert {r["source"] for r in repairs.values()} == {"unrecorded"}


def test_changed_line_emphasis_is_manual_but_unchanged_payload_is_not(guarded_client, monkeypatch, tmp_path):
    data = setup_auto(guarded_client, monkeypatch, tmp_path)
    data.run()
    document = load_subtitle_review(data.review_path)
    clip, segment = document.clips[0], document.segments[0]
    confirm(data, clip, subtitleStyles=[{"start": segment.start, "end": segment.end, "style": {"fontSize": 60, "primaryColor": "#FFFF00"}}])
    saved = load_subtitle_review(data.review_path)
    assert saved.clips[0].manual_decision_fields == ["subtitle_styles"]
    choices = [c for c in saved.choice_history if c.source == "manual"]
    assert len(choices) == 1 and choices[0].kind == "effects"
