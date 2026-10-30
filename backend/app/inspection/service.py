"""Persist each pass and bound local repairs; an unknown check never means pass."""

from copy import deepcopy
from datetime import UTC, datetime
from app.inspection.inspect import inspect_export
from app.inspection.models import Attempt, Check, InspectionRecord, MAX_REPAIRS, failures, stop_message
from app.production_choices import value_hash
from app.storage.json_io import write_json_atomic


class FinalInspectionFailed(RuntimeError):
    def __init__(self, records):
        self.records = records
        super().__init__(" ".join(stop_message(r) for r in records if r.outcome != "pass"))


def persist(paths, record):
    record.updated_at = datetime.now(UTC)
    return write_json_atomic(paths.final_output_inspection(record.job_id, record.clip_id), record.model_dump(mode="json"), allow_nan=False)


def protected_snapshot(document, clip):
    if document is None:
        return None
    fields = set(clip.manual_decision_fields)
    if "framing" in fields:
        fields.update(("framing_offset_x", "framing_offset_y", "framing_zoom", "short_layout", "automatic_crop"))
    return deepcopy(document.segments), {name: deepcopy(getattr(clip, name)) for name in fields if hasattr(clip, name)}


def restore_protected(document, clip, snapshot):
    if snapshot is not None:
        segments, fields = snapshot
        document.segments = deepcopy(segments)
        for name, value in fields.items():
            setattr(clip, name, deepcopy(value))


def protected_unchanged(document, clip, snapshot):
    return snapshot is None or (
        document.segments == snapshot[0] and all(getattr(clip, name) == value for name, value in snapshot[1].items())
    )


def repair_action(checks, clip, attempted):
    codes = {c.code for c in checks if c.outcome != "pass"}
    if any(c.outcome == "unknown" for c in checks) or "SUBTITLE_OVERLAP" in codes:
        return None
    manual = set(clip.manual_decision_fields) if clip is not None else set()
    if codes & {"CONTENT_MISMATCH", "THUMBNAIL_MISMATCH"}:
        content_fields = {
            "title",
            "publication_title",
            "hook_text",
            "hook_scene_start",
            "hook_scene_end",
            "youtube_description",
            "youtube_tags",
            "youtube_hashtags",
            "thumbnail_kicker",
            "thumbnail_line1",
            "thumbnail_line2",
            "thumbnail_frame_seconds",
            "title_hook",
            "post_copy",
            "thumbnail",
        }
        action = (
            "regenerate_content" if clip is not None and clip.automatic_decision_state == "ready" and not manual & content_fields else None
        )
    elif codes & {"SUBTITLE_OUT_OF_FRAME", "SUBTITLE_BANNER_COLLISION", "SUBTITLE_REFERENCE_EMPTY"}:
        action = (
            "refit_subtitle"
            if clip is not None and clip.automatic_decision_state == "ready" and not manual & {"subtitle_style", "subtitle_styles"}
            else "rerender_same"
        )
    else:
        action = "rerender_same"
    return action if action not in attempted else None


def inspect_final_outputs(
    *,
    exports,
    selection,
    source,
    segments,
    settings,
    video,
    paths,
    job_id,
    document=None,
    repair=None,
    inspector=inspect_export,
    selector=None,
    progress=None,
    clip_ids=None,
):
    """Caller owns render publication/rollback and the existing review lock."""
    outputs = list(exports)
    records = []
    all_candidates = [*selection.normal_clips, *selection.shorts]
    labels = {
        c.id: ("通常" if c.type == "normal" else "ショート") + str(i)
        for items in (selection.normal_clips, selection.shorts)
        for i, c in enumerate(items, 1)
    }
    for candidate in all_candidates:
        if clip_ids is not None and candidate.id not in clip_ids:
            continue
        export = next((e for e in outputs if e.candidate_id == candidate.id), None)
        clip = next((c for c in document.clips if c.id == candidate.id), None) if document is not None else None
        revision = value_hash(
            {
                "job": job_id,
                "clip": candidate.id,
                "reviewGeneration": document.created_at if document else None,
                "renderRevision": document.render_revision if document else 0,
                "confirmedInput": {
                    "previewSpec": clip.preview_spec_hash,
                    "decisionRevision": clip.automatic_decision_revision,
                    "captions": [(s.id, s.start, s.end, s.text) for s in document.segments if s.id in clip.segment_ids],
                    "manualValues": protected_snapshot(document, clip)[1],
                }
                if clip is not None
                else {"candidate": candidate.model_dump(mode="json"), "settings": settings},
            }
        )
        target = paths.final_output_inspection(job_id, candidate.id)
        record = None
        if target.is_file():
            previous = InspectionRecord.model_validate_json(target.read_text(encoding="utf-8"))
            if previous.input_revision == revision:
                record = previous
        record = record or InspectionRecord(job_id=job_id, clip_id=candidate.id, label=labels[candidate.id], input_revision=revision)
        snapshot = protected_snapshot(document, clip) if clip is not None else None
        record.outcome = "inspecting"
        persist(paths, record)
        while True:
            if progress:
                progress(record.label)
            try:
                digest, checks = (
                    inspector(
                        export,
                        candidate,
                        source=source,
                        segments=segments,
                        settings=settings,
                        video=video,
                        paths=paths,
                        job_id=job_id,
                        **({"selector": selector} if selector is not None else {}),
                    )
                    if export is not None
                    else (None, [Check(code="MEDIA_UNREADABLE", outcome="fail")])
                )
            except Exception:
                digest, checks = None, [Check(code="MEDIA_UNREADABLE", outcome="unknown")]
            if not checks:
                checks = [Check(code="MEDIA_UNREADABLE", outcome="unknown")]
            attempt = Attempt(index=len(record.attempts), output_sha256=digest, checks=checks)
            record.attempts.append(attempt)
            if checks and all(c.outcome == "pass" for c in checks):
                record.outcome = "pass"
                persist(paths, record)
                break
            attempted = {a.repair for a in record.attempts if a.repair}
            action = repair_action(checks, clip, attempted) if len(attempted) < MAX_REPAIRS else None
            if action is None or repair is None:
                record.outcome = "incomplete"
                persist(paths, record)
                break
            attempt.repair, attempt.repair_result = action, "planned"
            persist(paths, record)  # A killed worker cannot silently repeat this repair.
            try:
                replacement, updated = repair(candidate.id, action)
                if clip is not None and not protected_unchanged(document, clip, snapshot):
                    restore_protected(document, clip, snapshot)
                    raise ValueError("protected review values changed")
                export, candidate = replacement, updated
                outputs = [export if e.candidate_id == candidate.id else e for e in outputs]
                if not any(e.candidate_id == candidate.id for e in outputs):
                    outputs.append(export)
                attempt.repair_result = "rendered; reinspection_required"
            except Exception:
                if clip is not None:
                    restore_protected(document, clip, snapshot)
                attempt.repair_result = "failed"
                attempt.checks.append(Check(code="REPAIR_FAILED", outcome="fail"))
                record.outcome = "incomplete"
                persist(paths, record)
                break
            persist(paths, record)
        records.append(record)
    if any(r.outcome != "pass" for r in records):
        raise FinalInspectionFailed(records)
    return outputs


def read_inspection_attention(paths, job_id):
    result = []
    folder = paths.final_output_inspection_dir(job_id)
    if not folder.is_dir():
        return result
    for file in sorted(folder.glob("*.json")):
        try:
            record = InspectionRecord.model_validate_json(file.read_text(encoding="utf-8"))
            if record.outcome != "pass":
                result.append(
                    {
                        "clipLabel": record.label,
                        "reason": stop_message(record) if failures(record) else record.label + "：完成検査が中断しているため未完成です。",
                        "repairCount": sum(bool(a.repair) for a in record.attempts),
                        "seconds": [c.second for c in failures(record) if c.second is not None],
                    }
                )
        except (ValueError, OSError):
            result.append({"clipLabel": "検査記録", "reason": "完成検査の記録を読み取れません。", "repairCount": 0, "seconds": []})
    return result


def production_inspection(paths, export):
    """Permanent, path-free evidence, only for the exact inspected MP4."""
    from app.inspection.media import file_hash

    if not export.candidate_id:
        return None  # Old exports may not have a candidate identity.
    target = paths.final_output_inspection(export.job_id, export.candidate_id)
    if not target.is_file():
        return None
    record = InspectionRecord.model_validate_json(target.read_text(encoding="utf-8"))
    if record.outcome != "pass" or not record.attempts:
        return None
    try:
        if record.attempts[-1].output_sha256 != file_hash(paths.resolve_stored_file(export.video_path)):
            return None
    except OSError:
        return None
    semantic = [c for c in record.attempts[-1].checks if "publicationHash" in c.evidence]
    if semantic:
        import json
        from app.inspection.content import content_binding
        from app.jobs.thumbnails import thumbnail_path_from_export

        try:
            metadata = json.loads(paths.resolve_stored_file(export.metadata_path).read_text(encoding="utf-8"))
            metadata["publication_title"] = export.title
            binding = content_binding(metadata, thumbnail_path_from_export(export))
        except (OSError, ValueError, TypeError):
            return None
        if any(any(c.evidence.get(k) != v for k, v in binding.items()) for c in semantic):
            return None
    return {
        "version": record.version,
        "outcome": record.outcome,
        "updatedAt": record.updated_at.isoformat(),
        "repairCount": sum(bool(a.repair) for a in record.attempts),
        "attempts": [a.model_dump(mode="json") for a in record.attempts],
    }
