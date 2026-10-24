import pytest

from test_api_routes import client as client
from test_subtitle_structure import seed_structure, items
from app.db import get_db
from app.jobs.subtitle_review import apply_reviewed_text, load_subtitle_review, update_review_segment, write_subtitle_review
from app.jobs.subtitle_review_preview import current_subtitle_review_preview_spec
from app.main import app
from app.models import Job, Video
from app.render.subtitles_ass import build_ass_document
from app.storage.paths import get_storage_paths


def prepared(api):
    job_id, path, document, original, normal = seed_structure(api)
    for clip in document.clips:
        clip.confirmed = clip.id != "short"
        clip.preview_state = "ready"
        clip.preview_spec_hash = f"saved-{clip.id}"
        clip.preview_video_url = f"/saved/{clip.id}.mp4"
    write_subtitle_review(document, path)
    return job_id, path, load_subtitle_review(path), original, normal


def normal_preview(document, job_id):
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        return current_subtitle_review_preview_spec(
            job=job, video=db.get(Video, job.video_id), document=document,
            paths=app.dependency_overrides[get_storage_paths](), clip_id="normal",
        )[1]


@pytest.mark.parametrize("route", ["apply", "batch", "split", "merge", "delete", "line", "insert", "insert_at_time"])
def test_other_clip_edit_preserves_confirmed_text_preview_and_render(client, route):  # noqa: F811
    job_id, path, before, original, normal = prepared(client)
    protected = before.clips[0].model_dump()
    preview = normal_preview(before, job_id)
    before_ass = build_ass_document(normal, apply_reviewed_text(original, before))
    first = before.segments[0]
    if route == "apply":
        response = client.post(f"/api/jobs/{job_id}/subtitle-review/clips/short/apply", json={
            "title": "short", "publicationTitle": "short", "segments": [{"segmentId": first.id, "text": "修正"}],
        })
    elif route == "batch":
        response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={
            "segments": [{"segmentId": s.id, "before": s.text, "text": "修正"} for s in before.segments],
        })
    else:
        request = {"action": route, "clipId": "short", "segments": items(first)}
        if route == "line":
            request["segments"][0]["text"] = "改行も本文も修正"
        if route == "split":
            request.update(splitOffset=1, splitTime=1.5)
        elif route == "merge":
            request["segments"] = items(*before.segments[:2])
        elif route == "insert":
            request.update(splitTime=1.5, insertPosition="after")
        elif route == "insert_at_time":
            request.update(segments=[], start=4, end=5, text="追加")
        response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json=request)
    assert response.status_code == 200, response.text
    saved = load_subtitle_review(path)
    assert saved.clips[0].model_dump() == protected
    assert saved.clips[1].model_dump() == before.clips[1].model_dump()
    assert normal_preview(saved, job_id) == preview
    rendered = apply_reviewed_text(original, saved)
    assert build_ass_document(normal, rendered) == before_ass
    short = normal.model_copy(update={"id": "short", "type": "short"})
    assert build_ass_document(short, rendered) != build_ass_document(short, apply_reviewed_text(original, before))
    # The persisted clip-specific rows keep the normal source text and IDs.
    for segment_id in before.clips[0].segment_ids:
        assert next(s for s in saved.segments if s.id == segment_id).text == next(s for s in before.segments if s.id == segment_id).text


def test_edit_confirmed_clip_explicitly_protects_other_confirmed_clip(client):  # noqa: F811
    job_id, path, document, _, _ = prepared(client)
    document.clips[2].confirmed = True
    write_subtitle_review(document, path)
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json={
        "action": "line", "clipId": "short", "segments": [{**items(document.segments[0])[0], "text": "直接修正"}],
    })
    assert response.status_code == 200, response.text
    saved = load_subtitle_review(path)
    assert saved.clips[0].confirmed and not saved.clips[2].confirmed
    assert saved.clips[0].segment_ids == document.clips[0].segment_ids
    assert saved.clips[2].segment_ids != document.clips[2].segment_ids


def test_batch_with_only_confirmed_clips_changes_nothing(client):  # noqa: F811
    job_id, path, document, _, _ = prepared(client)
    for clip in document.clips:
        clip.confirmed = True
    write_subtitle_review(document, path)
    before = path.read_bytes()
    response = client.patch(f"/api/jobs/{job_id}/subtitle-review/segments", json={
        "segments": [{"segmentId": s.id, "before": s.text, "text": "対象外"} for s in document.segments],
    })
    assert response.status_code == 200
    assert path.read_bytes() == before


def test_shared_unconfirmed_copies_stay_shared_and_can_be_edited_again(client):  # noqa: F811
    _, _, document, original, normal = prepared(client)
    short = document.clips[2]
    another = short.model_copy(deep=True, update={"id": "short2"})
    document.clips.append(another)
    for segment in document.segments:
        if short.id in segment.affected_clip_ids:
            segment.affected_clip_ids.append(another.id)
    first = document.segments[0]
    update_review_segment(document, first.id, "新しい本文", clip_id="short")
    assert short.segment_ids == another.segment_ids
    assert short.segment_ids[0] != first.id
    assert first.text == "前半"
    update_review_segment(document, short.segment_ids[0], "さらに修正", clip_id="short2")
    assert len(document.segments) == 4
    assert "さらに修正" in build_ass_document(normal.model_copy(update={"id": "short2"}), apply_reviewed_text(original, document))
    assert "さらに修正" not in build_ass_document(normal, apply_reviewed_text(original, document))


def test_maintenance_bulk_cleanup_also_protects_confirmed_clips(client):  # noqa: F811
    from app.jobs.subtitle_ellipsis import strip_subtitle_ellipsis

    job_id, path, document, _, _ = prepared(client)
    document.segments[0].text = document.segments[0].original_text = "明．．．明治"
    write_subtitle_review(document, path)
    paths = app.dependency_overrides[get_storage_paths]()
    with next(app.dependency_overrides[get_db]()) as db:
        dry = strip_subtitle_ellipsis(db, paths, job_id)
        report = strip_subtitle_ellipsis(db, paths, job_id, execute=True)
    assert dry["changed_segment_count"] == report["changed_segment_count"] == 1
    assert report["affected_clip_ids"] == ["short"]
    saved = load_subtitle_review(path)
    assert saved.clips[0].model_dump() == document.clips[0].model_dump()
    assert next(s for s in saved.segments if s.id == document.segments[0].id).text == "明．．．明治"
    assert next(s for s in saved.segments if s.id == saved.clips[2].segment_ids[0]).text == "明、明治"


def test_forked_rows_keep_source_indices_for_preview_retry_and_boundary_reedit(client):  # noqa: F811
    from app.audio.transcribe_faster_whisper import write_transcript_segments
    from app.jobs.subtitle_review import retain_review_after_boundary_reedit, subtitle_review_source_path

    job_id, path, document, original, normal = prepared(client)
    preview = normal_preview(document, job_id)
    update_review_segment(document, document.segments[0].id, "ショートだけ修正", clip_id="short")
    write_subtitle_review(document, path)
    assert subtitle_review_source_path(path.parent, document).is_file()
    rendered = apply_reviewed_text(original, document)
    # Final rendering replaces the transcript file, while retry must keep its original index space.
    write_transcript_segments(rendered, path.parent / "transcript_segments.json")
    saved = load_subtitle_review(path)
    assert normal_preview(saved, job_id) == preview
    assert "ショートだけ修正" not in build_ass_document(normal, rendered)
    retained = retain_review_after_boundary_reedit(saved, saved.model_copy(deep=True))
    assert retained.clips[0].model_dump() == saved.clips[0].model_dump()
    assert all(s.affected_clip_ids == next(old.affected_clip_ids for old in saved.segments if old.id == s.id)
               for s in retained.segments)


@pytest.mark.parametrize("action", ["merge", "delete"])
def test_explicit_edit_after_fork_uses_clip_adjacency(client, action):  # noqa: F811
    from app.jobs.subtitle_structure import edit_subtitle_structure
    from app.schemas import SubtitleStructureRequest

    _, _, document, original, normal = prepared(client)
    # Short now has its own version; both clips become editable, but their IDs stay separate.
    for segment_id in list(document.clips[2].segment_ids):
        update_review_segment(document, segment_id, "ショート専用", clip_id="short")
    document.clips[0].confirmed = False
    before_short = build_ass_document(normal.model_copy(update={"id": "short"}), apply_reviewed_text(original, document))
    chosen = [s for s in document.segments if "normal" in s.affected_clip_ids]
    edit_subtitle_structure(document, SubtitleStructureRequest.model_validate({
        "action": action, "clipId": "normal", "segments": items(*(chosen if action == "merge" else chosen[:1])),
    }))
    assert build_ass_document(normal.model_copy(update={"id": "short"}), apply_reviewed_text(original, document)) == before_short


def test_production_record_uses_each_clips_review_revision_after_fork(client):  # noqa: F811
    from app.models import ExportItem
    from app.production_records import build_production_record

    job_id, path, document, _, _ = prepared(client)
    paths = app.dependency_overrides[get_storage_paths]()
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)

        def histories():
            result = {}
            for clip in (document.clips[0], document.clips[2]):
                export = ExportItem(id=f"exp_{clip.id}", job_id=job.id, video_id=job.video_id,
                                    candidate_id=clip.id, type=clip.type, title=clip.title, duration=clip.duration,
                                    score=0, video_path=str(path.parent / f"{clip.id}.mp4"))
                record = build_production_record(job, export, paths)
                result[clip.id] = [c.model_dump() for c in record.choiceHistory if c.clipId == clip.id and c.kind != "publication"]
            return result

        before = histories()
        update_review_segment(document, document.segments[0].id, "ショートだけの変更", clip_id="short")
        write_subtitle_review(document, path, choice_source="manual")
        after = histories()
    assert after["normal"] == before["normal"]
    assert len(after["short"]) > len(before["short"])
    assert after["short"][-1]["inputRevision"] != before["short"][-1]["inputRevision"]
