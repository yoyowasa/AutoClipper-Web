"""Conservative, explicit repair of identical four-field apply history bursts."""

from copy import deepcopy
from datetime import UTC, datetime
import json
import re

from sqlalchemy import select, update

from app.jobs.publication_state import rerender_publication_is_unresolved
from app.jobs.subtitle_review import subtitle_review_output_path
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.models import ExportItem, Job
from app.production_choices import ProductionChoice, merge_history
from app.production_records import ProductionRecord
from app.storage.json_io import write_json_atomic
from app.storage.lifecycle import _is_reparse_or_symlink, _resolve_stored_path
from app.storage.locking import storage_mutation_lock


APPLY_KINDS = frozenset({"title_hook", "framing", "text_style", "post_copy"})
# Four synchronous capture writes, not separate editing actions.
APPLY_BURST_SECONDS = 1.0
IDLE_STATUSES = {"completed", "failed", "awaiting_subtitle_review", "awaiting_clip_review"}


def identical_apply_repairs(history):
    """Require a complete apply burst and exact prior values; never infer automatic provenance."""
    previous = {}
    groups = []
    group = []
    for choice in merge_history(history):
        eligible = (choice.source == "manual" and choice.stage == "applied"
                    and choice.policyVersion == "subtitle-review-v1" and choice.kind in APPLY_KINDS
                    and choice.scope == "clip" and choice.clipId and choice.inputRevision)
        if eligible:
            if group and (choice.clipId != group[0][0].clipId or choice.inputRevision != group[0][0].inputRevision
                          or (choice.recordedAt - group[0][0].recordedAt).total_seconds() > APPLY_BURST_SECONDS):
                groups.append(group)
                group = []
            group.append((choice, previous.get((choice.clipId, choice.kind))))
        elif group:
            groups.append(group)
            group = []
        if choice.stage != "proposed":
            previous[choice.clipId, choice.kind] = choice
    if group:
        groups.append(group)
    repairs, retained = {}, []
    for group in groups:
        if len(group) != 4 or {c.kind for c, _ in group} != APPLY_KINDS:
            continue
        for choice, prior in group:
            prior_source = repairs.get(prior.id, {}).get("source", prior.source) if prior else None
            if (prior is None or prior_source not in {"automatic", "unrecorded"} or not choice.values
                    or prior.inputRevision == choice.inputRevision or prior.values != choice.values):
                retained.append({"choice_id": choice.id, "clip_id": choice.clipId, "kind": choice.kind,
                                 "reason": "different_values_or_unproven_baseline"})
                continue
            repairs[choice.id] = {"source": prior_source, "previous_id": prior.id,
                                  "clip_id": choice.clipId, "kind": choice.kind}
    return repairs, retained


def _safe_path(path, root):
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Repair artifact is outside storage")
    for item in (path, *path.parents):
        if _is_reparse_or_symlink(item):
            raise ValueError("Symlink or reparse point refused")
        if item == root:
            break
    return path


def repair_unchanged_manual_choices(db, paths, job_id: str, *, execute: bool = False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise ValueError("Unsafe job identifier")
    output = _safe_path(paths.outputs / job_id, paths.root)
    # No missing job directory is created by a dry-run.
    if not output.is_dir():
        raise ValueError("Job output directory is unavailable")
    with storage_mutation_lock(paths.root), subtitle_review_document_lock(output):
        job = db.get(Job, job_id, populate_existing=True)
        if job is None or job.status not in IDLE_STATUSES or rerender_publication_is_unresolved(output):
            raise ValueError("Only idle jobs without unresolved publication can be repaired")
        artifact_paths = {subtitle_review_output_path(output), output / "clip_plan.json", output / "selected_clips.json"}
        for export in db.scalars(select(ExportItem).where(ExportItem.job_id == job_id)):
            if export.metadata_path:
                artifact_paths.add(_resolve_stored_path(export.metadata_path, paths.root))
        artifacts = {}
        for path in sorted(artifact_paths):
            _safe_path(path, paths.root)
            if path.is_file():
                artifacts[path] = json.loads(path.read_text(encoding="utf-8"))
        record_paths = set()
        # Include retained records whose ExportItem row no longer exists.
        for path in sorted(paths.production_records.glob("*.json")):
            _safe_path(path, paths.root)
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("jobId") == job_id:
                ProductionRecord.model_validate(payload)
                artifacts[path] = payload
                record_paths.add(path)
        review = artifacts.get(subtitle_review_output_path(output), {})
        if any(c.get("automaticDecisionState") in {"queued", "generating"} for c in review.get("clips", [])):
            raise ValueError("Automatic clip decisions are still running")
        # Refuse inconsistent copies rather than silently picking one provenance.
        unique = {}
        for payload in artifacts.values():
            for raw in payload.get("choiceHistory", []):
                choice = ProductionChoice.model_validate(raw)
                if choice.id in unique and choice != unique[choice.id]:
                    raise ValueError("Choice history copies disagree; repair requires inspection")
                unique[choice.id] = choice
        repairs, retained = identical_apply_repairs(list(unique.values()))
        report = {"command": "repair-unchanged-manual-choices", "job_id": job_id, "dry_run": not execute,
                  "repaired_choice_count": len(repairs), "affected_clip_count": len({r["clip_id"] for r in repairs.values()}),
                  "repairs": [{"choice_id": key, **value} for key, value in repairs.items()],
                  "retained": retained, "files": [], "errors": []}
        updates = {}
        for path, original in artifacts.items():
            payload = deepcopy(original)
            changed = 0
            for choice in payload.get("choiceHistory", []):
                repair = repairs.get(choice["id"])
                if repair is None:
                    continue
                choice["source"] = repair["source"]
                choice["reason"] = f"unchanged_apply_repaired:previous={repair['previous_id']}"
                if repair["source"] == "unrecorded":
                    choice["stage"] = "observed"
                    choice.pop("appliedAt", None)
                ProductionChoice.model_validate(choice)
                changed += 1
            if not changed:
                continue
            if path in record_paths:
                record = ProductionRecord.model_validate(payload)
                payload["revision"] = record.revision + 1
                payload["updatedAt"] = max(datetime.now(UTC), record.updatedAt, record.createdAt).isoformat().replace("+00:00", "Z")
                ProductionRecord.model_validate(payload)
            updates[path] = payload
            report["files"].append({"path": path.relative_to(paths.root).as_posix(), "choice_count": changed})
        if execute and updates:
            written = []
            try:
                result = db.execute(update(Job).where(Job.id == job_id, Job.status == job.status,
                                                      Job.updated_at == job.updated_at).values(status=Job.status))
                if result.rowcount != 1:
                    raise ValueError("Job state changed; retry after it is idle")
                for path, payload in updates.items():
                    write_json_atomic(path, payload)
                    written.append(path)
            except OSError:
                # Do not leave retained records and working history disagreeing
                # if one replacement fails (e.g. an open Windows file).
                for path in reversed(written):
                    write_json_atomic(path, artifacts[path])
                raise
            finally:
                db.rollback()  # Hold the DB write lock; do not change the job row.
        return report
