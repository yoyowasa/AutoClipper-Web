"""Permanent decisions survive disposable outputs; no source text is copied."""

import json
from pathlib import Path
import pytest
from datetime import UTC, datetime, timedelta

from app.candidates.select_candidates import CandidateSelection
from app.jobs.clip_plan import build_clip_plan
from app.jobs.quality_gate import evaluate_selection_quality_gate
from app.jobs.reselection_keep import prepare_kept_candidates
from app.maintenance import delete_jobs
from app.production_records import write_production_record
from app.publication.pipeline import apply_publication_decisions
from app.publication.storage import persist_report, read_report
from app.storage.paths import StoragePaths
from app.publication.models import PublicationPolicy
from app.storage.lifecycle import cleanup_expired_storage
from test_publication_decisions import candidate, settings, apply
from test_production_records import example as example
from test_maintenance import storage_db as storage_db, seed


def test_export_record_includes_decision_and_choice_provenance(example):
    db, job, export, paths = example
    c = candidate(export.candidate_id, type="short", start=100, end=175, duration=75)
    selection = apply_publication_decisions(
        CandidateSelection(shorts=[c]), [c], settings=settings(), paths=paths, job_id=job.id, source_duration=300
    )
    record = json.loads(write_production_record(job, export, paths).read_text(encoding="utf-8"))
    assert record["publicationDecision"]["candidateId"] == export.candidate_id
    assert record["publicationDecision"]["policyVersion"] == "weak-material-v1"
    assert record["publicationDecision"]["evidence"]["transcriptHash"]
    choices = [c for c in record["choiceHistory"] if c["kind"] == "publication_decision"]
    assert len(choices) == 1 and choices[0]["source"] == "automatic"
    assert choices[0]["values"]["publicationDecision"] == "publish"
    assert c.transcript_text not in json.dumps(record, ensure_ascii=False)
    # An unrelated later edit must not silently inherit the earlier decision.
    metadata = Path(export.metadata_path)
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["end"] = 174
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    assert "publicationDecision" not in json.loads(write_production_record(job, export, paths).read_text(encoding="utf-8"))
    assert selection.publication_decisions[0].decision == "publish"


def test_revision_preserves_previous_decision_evidence(tmp_path):
    apply(tmp_path, [candidate(score=62)])
    paths = StoragePaths(tmp_path)
    original = read_report(paths, "job_test")
    result = apply(tmp_path, [candidate(score=80)])
    report = read_report(paths, "job_test")
    assert report.revision == 2
    assert report.previous_decisions[0].revision == 1
    assert report.previous_decisions[0].decisions == original.decisions
    assert report.decisions[0].decision == "publish"
    assert len([c for c in result.choice_history if c.kind == "publication_decision"]) == 2


def test_reselection_can_keep_a_withheld_candidate_without_changing_its_source_values(tmp_path):
    previous = apply(tmp_path, [candidate("skipped", score=62), candidate("unknown", score=None)])
    raw = settings(keptClipIds=["skipped"])
    plan = build_clip_plan("job_test", previous, raw, source_duration=300)
    reduced, kept = prepare_kept_candidates(raw, plan, previous)
    assert [c.id for c in kept] == ["skipped"] and reduced["normalClipCount"] == 1
    result = apply_publication_decisions(
        CandidateSelection(normalClips=kept), kept, settings=raw, paths=StoragePaths(tmp_path), job_id="job_test", source_duration=300
    )
    d = result.publication_decisions[0]
    assert d.decision == "publish" and d.source == "manual" and d.original_decision == "skip"
    assert result.normal_clips[0].final_score == 62


def test_intentional_shortfall_does_not_disable_other_quality_checks(tmp_path):
    c = candidate("publish", start=100, end=190)
    result = apply(tmp_path, [candidate("skip", score=62), c])
    raw = settings(automationMode="auto")

    def gate():
        return evaluate_selection_quality_gate(
            job_id="job_test", selection=result, transcript_segments=[], settings=raw, source_duration=300, mode="auto"
        )

    counts = next(c for c in gate().checks if c.code == "selection.requested_counts")
    assert counts.outcome == "pass" and counts.evidence["shortfall"]["normal"] == 1
    assert counts.evidence["publicationWithheld"]["normal"] == 1
    result.normal_clips[0] = c.model_copy(update={"end": 400, "duration": 300})
    assert gate().outcome == "fail"
    result.publication_withheld_counts = {}
    assert next(c for c in gate().checks if c.code == "selection.requested_counts").outcome == "fail"


@pytest.mark.parametrize("method", ["expiry", "explicit"])
def test_decision_report_survives_expiry_and_explicit_job_deletion(storage_db, method):
    db, paths = storage_db
    job, blob = seed(db, paths)
    selected = CandidateSelection(normalClips=[candidate()])
    from app.publication.evaluate import evaluate_candidate

    selected.publication_decisions = [evaluate_candidate(candidate(), policy=PublicationPolicy(), settings=settings(), source_duration=300)]
    persist_report(paths, job.id, selected, PublicationPolicy())
    report_path = paths.publication_decisions(job.id)
    before = report_path.read_bytes()
    job.updated_at = datetime.now(UTC) - timedelta(days=100)
    db.commit()
    job_id = job.id
    if method == "expiry":
        result = cleanup_expired_storage(db, paths, terminal_retention_days=1, orphan_retention_hours=1, now=datetime.now(UTC))
        assert result.removed_jobs == 1
    else:
        delete_jobs(db, paths, [job_id], execute=True)
    assert db.get(type(job), job_id) is None
    assert report_path.read_bytes() == before
