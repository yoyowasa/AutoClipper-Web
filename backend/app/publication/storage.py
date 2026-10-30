"""Small permanent decision records, including jobs that produced no export."""

from datetime import UTC, datetime
from app.production_choices import append_choice, choice_values, merge_history, value_hash
from app.publication.models import PublicationReport, PublicationRevision, REASONS
from app.storage.json_io import write_json_atomic


def read_report(paths, job_id):
    path = paths.publication_decisions(job_id)
    return PublicationReport.model_validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None


def record_choice(selection, decision):
    append_choice(
        selection.choice_history,
        kind="publication_decision",
        clipId=decision.candidate_id,
        stage="applied",
        source=decision.source,
        policyVersion=decision.policy_version,
        inputRevision=value_hash(decision.model_dump(mode="json")),
        reason=";".join(decision.reasons),
        timeBasis="source",
        values=choice_values(
            {
                "type": decision.type,
                "start": decision.start,
                "end": decision.end,
                "publicationDecision": decision.decision,
                "publicationReasons": decision.reasons,
                "publicationEvidenceHash": value_hash(decision.evidence.model_dump(mode="json")),
                "publicationOriginalDecision": decision.original_decision,
            }
        ),
    )


def report_outcome(selection):
    decisions = selection.publication_decisions
    if any(d.decision == "unknown" for d in decisions):
        return "needs_review"
    if not selection.normal_clips and not selection.shorts and decisions and all(d.decision == "skip" for d in decisions):
        return "no_publication"
    return "partial" if any(d.decision == "skip" for d in decisions) else "publish"


def persist_report(paths, job_id, selection, policy):
    old = read_report(paths, job_id)
    history = merge_history(old.choice_history if old else [], selection.choice_history)
    selection.choice_history = history
    report = PublicationReport(
        jobId=job_id,
        revision=old.revision + 1 if old else 1,
        previousDecisions=[*old.previous_decisions, PublicationRevision(revision=old.revision, decisions=old.decisions)] if old else [],
        policy=policy,
        createdAt=old.created_at if old else datetime.now(UTC),
        outcome=report_outcome(selection),
        selectedCount=len(selection.normal_clips) + len(selection.shorts),
        decisions=selection.publication_decisions,
        choiceHistory=history,
    )
    write_json_atomic(paths.publication_decisions(job_id), report.model_dump(by_alias=True, mode="json"), allow_nan=False)
    return report


def summary(paths, job_id):
    report = read_report(paths, job_id)
    if report is None:
        return None
    return {
        "outcome": report.outcome,
        "policyVersion": report.policy.version,
        "selectedCount": report.selected_count,
        "criteriaValidated": False,
        "decisions": [
            {**d.model_dump(by_alias=True, mode="json"), "reasonText": "。".join(REASONS.get(r, r) for r in d.reasons)}
            for d in report.decisions
        ],
    }
