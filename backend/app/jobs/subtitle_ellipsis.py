"""Explicit, preview-deferred cleanup of unedited legacy review captions."""

import re

from app.jobs.subtitle_review_edits import editable_clip_ids, writable_segment

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.audio.transcript_postprocess import parse_transcript_postprocess_settings, strip_transcript_ellipsis
from app.jobs.subtitle_review import _refresh_counts, load_subtitle_review, subtitle_review_output_path, write_subtitle_review
from app.jobs.subtitle_review import subtitle_review_summary_path, write_subtitle_review_summary
from app.jobs.quality_gate import invalidate_quality_gate_decisions
from app.jobs.subtitle_review_preview import subtitle_review_document_lock
from app.models import Job
from app.storage.locking import storage_mutation_lock
from app.storage.lifecycle import _is_reparse_or_symlink
from app.storage.paths import StoragePaths


def strip_subtitle_ellipsis(db: Session, paths: StoragePaths, job_id: str, *, execute: bool = False) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise ValueError("Unsafe job identifier")
    output = paths.outputs / job_id
    path = subtitle_review_output_path(output)
    if (_is_reparse_or_symlink(output) or _is_reparse_or_symlink(path)
            or not output.resolve().is_relative_to(paths.outputs.resolve())):
        raise ValueError("Unsafe subtitle review path")
    if not output.is_dir():
        raise ValueError("字幕確認データがありません。")
    with storage_mutation_lock(paths.root), subtitle_review_document_lock(output):
        job = db.get(Job, job_id, populate_existing=True)
        if job is None or job.status != "awaiting_subtitle_review":
            raise ValueError("字幕確認待ちのジョブだけが対象です。")
        document = load_subtitle_review(path)
        if document.state != "awaiting_review":
            raise ValueError("字幕確認が編集中のときだけ実行できます。")
        settings = parse_transcript_postprocess_settings(job.settings_json or {})
        report = {"command": "strip-subtitle-ellipsis", "job_id": job_id, "dry_run": not execute,
                  "changed_segment_count": 0, "skipped_edited_segment_count": 0, "affected_clip_ids": [], "examples": [], "errors": []}
        if not settings.enabled or not settings.normalize_punctuation:
            report["skipped_reason"] = "punctuation_normalization_disabled"
            return report
        changed = set()
        editable = editable_clip_ids(document)
        for segment in list(document.segments):
            cleaned = strip_transcript_ellipsis(segment.text)
            if cleaned == segment.text:
                continue
            if segment.text != segment.original_text:
                report["skipped_edited_segment_count"] += 1
                continue
            segment = writable_segment(document, segment, editable)
            if segment is None:
                continue
            if len(report["examples"]) < 5:
                report["examples"].append({"segment_id": segment.id, "before": segment.text, "after": cleaned})
            # This is automatic cleanup, not a user edit. Keep future cleanup eligible.
            segment.text = segment.original_text = cleaned
            segment.edited = False
            changed.add(segment.id)
        affected = {clip.id for clip in document.clips if changed.intersection(clip.segment_ids)}
        report["changed_segment_count"] = len(changed)
        report["affected_clip_ids"] = sorted(affected)
        if execute and changed:
            try:
                # Keep concurrent finalize/retry from changing the state during the write.
                result = db.execute(update(Job).where(Job.id == job_id, Job.status == "awaiting_subtitle_review").values(status=Job.status))
                if result.rowcount != 1:
                    raise ValueError("ジョブの状態が変わりました。再確認してください。")
                for clip in document.clips:
                    if clip.id in affected:
                        clip.confirmed = False
                        clip.preview_deferred = True
                        clip.preview_state = "stale"
                        clip.preview_video_url = None
                        clip.preview_error = None
                document.has_saved_review_changes = True
                _refresh_counts(document)
                invalidate_quality_gate_decisions(output, ("content", "post_render"))
                write_subtitle_review(document, path)
                write_subtitle_review_summary(document, subtitle_review_summary_path(output))
            finally:
                db.rollback()  # The conditional no-op UPDATE only holds SQLite's write lock.
        return report
