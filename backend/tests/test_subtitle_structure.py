import json

import pytest

from test_api_routes import client as client
from test_subtitle_bulk_correction import seed_review
from app.audio.transcribe_faster_whisper import TranscriptSegment, write_transcript_segments
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.db import get_db
from app.jobs.subtitle_review import apply_reviewed_text, build_subtitle_review, load_subtitle_review, write_subtitle_review
from app.main import app
from app.models import Job
from app.render.subtitles_ass import SubtitleLayout, build_ass_document, subtitle_events_for_candidate_output
from app.jobs.subtitle_review_preview import load_subtitle_review_preview_inputs
from app.storage.paths import get_storage_paths
from app.models import Video
from app.render.render_exact_review_preview import build_subtitle_review_preview_spec, subtitle_review_preview_spec_hash


def seed_structure(api):
    job_id, path, _ = seed_review(api)
    original = [
        TranscriptSegment(start=a, end=b, text=t)
        for a, b, t in [(1, 2, "前半"), (2, 3, "後半"), (21, 22, "変更しない"), (40, 41, "選定外")]
    ]
    normal = Candidate(id="normal", type="normal", start=0, end=10, duration=10, transcript_text="前半後半")
    short = normal.model_copy(update={"id": "short", "type": "short"})
    other = normal.model_copy(update={"id": "other", "start": 20, "end": 30})
    selection = CandidateSelection(normalClips=[normal, other], shorts=[short])
    document = build_subtitle_review(job_id, selection, original)
    for c in document.clips:
        c.confirmed = True
    write_subtitle_review(document, path)
    write_selected_clips(selection, path.parent / "selected_clips.json")
    write_transcript_segments(original, path.parent / "transcript_segments.json")
    return job_id, path, document, original, normal


def items(*segments):
    return [{"segmentId": s.id, "before": s.text, "text": s.text} for s in segments]


def test_merge_split_persist_and_reach_ass_without_automatic_regrouping(client):  # noqa: F811
    job_id, path, doc, original, candidate = seed_structure(client)
    url = f"/api/jobs/{job_id}/subtitle-review/segment-structure"
    request = {"action": "merge", "segments": items(*doc.segments[:2])}
    response = client.post(url, json=request)
    assert response.status_code == 200, response.text
    merged = load_subtitle_review(path)
    segment = merged.segments[0]
    assert (segment.start, segment.end, segment.text, segment.source_indices) == (1, 3, "前半後半", [0, 1])
    assert segment.single_line and segment.preserve_segmentation
    assert {c.id: c.confirmed for c in merged.clips} == {"normal": False, "other": True, "short": False}
    assert merged.clips[0].segment_ids == merged.clips[2].segment_ids == [segment.id]
    rendered = apply_reviewed_text(original, merged)
    assert [(s.start, s.end, s.text) for s in rendered] == [(1, 3, "前半後半"), (21, 22, "変更しない"), (40, 41, "選定外")]
    assert client.post(url, json=request).status_code == 404
    response = client.post(url, json={"action": "split", "segments": items(segment), "splitOffset": 2, "splitTime": 1.8})
    assert response.status_code == 200, response.text
    split = load_subtitle_review(path)
    rendered = apply_reviewed_text(original, split)
    events, _ = subtitle_events_for_candidate_output(rendered, candidate, SubtitleLayout.normal())
    assert [(e.start, e.end, e.text) for e in events] == [(1, 1.8, "前半"), (1.8, 3, "後半")]
    assert all(e.single_line for e in events)
    ass = build_ass_document(candidate, rendered)
    subtitles = [line for line in ass.splitlines() if line.startswith("Dialogue:") and ",Subtitle," in line]
    assert len(subtitles) == 2
    assert all("\\N" not in line for line in subtitles)
    # Final rendering writes the edited transcript; preview/retry must still use
    # the immutable source index space, rather than apply edits to shifted indices.
    write_transcript_segments(rendered, path.parent / "transcript_segments.json")
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        preview = load_subtitle_review_preview_inputs(
            job=job,
            video=db.get(Video, job.video_id),
            document=split,
            paths=app.dependency_overrides[get_storage_paths](),
            clip_id="normal",
        )
    assert [(s.start, s.end, s.text) for s in preview.transcript_segments] == [(s.start, s.end, s.text) for s in rendered]
    # Subsequent ordinary text corrections still target the split IDs.
    first = split.segments[0]
    assert client.patch(f"/api/jobs/{job_id}/subtitle-review/segments/{first.id}", json={"text": "修正前半"}).status_code == 200
    assert apply_reviewed_text(original, load_subtitle_review(path))[0].text == "修正前半"


@pytest.mark.parametrize(
    "failure,status", [("conflict", 409), ("time", 422), ("empty", 422), ("duplicate", 422), ("completed", 409), ("shared", 422)]
)
def test_structure_rejects_invalid_requests_without_writes(client, failure, status):  # noqa: F811
    job_id, path, doc, _, _ = seed_structure(client)
    request = {"action": "split", "segments": items(doc.segments[0]), "splitOffset": 1, "splitTime": 1.5}
    if failure == "conflict":
        request["segments"][0]["before"] = "古い字幕"
    if failure == "time":
        request["splitTime"] = 4
    if failure == "empty":
        request["splitOffset"] = 2
    if failure == "duplicate":
        request = {"action": "merge", "segments": items(doc.segments[0], doc.segments[0])}
    if failure == "shared":
        doc.segments[1].affected_clip_ids = ["normal"]
        write_subtitle_review(doc, path)
        request = {"action": "merge", "segments": items(*doc.segments[:2])}
    if failure == "completed":
        with next(app.dependency_overrides[get_db]()) as db:
            db.get(Job, job_id).status = "completed"
            db.commit()
    before = path.read_bytes()
    response = client.post(f"/api/jobs/{job_id}/subtitle-review/segment-structure", json=request)
    assert response.status_code == status, response.text
    assert path.read_bytes() == before


def test_one_line_keeps_long_interval_and_hook_shift(client):  # noqa: F811
    job_id, path, doc, original, candidate = seed_structure(client)
    response = client.post(
        f"/api/jobs/{job_id}/subtitle-review/segment-structure",
        json={"action": "line", "segments": items(doc.segments[0]), "singleLine": True},
    )
    assert response.status_code == 200
    rendered = apply_reviewed_text(original, load_subtitle_review(path))
    candidate = candidate.model_copy(update={"type": "short", "hook_scene_start": 4, "hook_scene_end": 5})
    events, _ = subtitle_events_for_candidate_output(rendered, candidate, SubtitleLayout.short())
    assert events[0].single_line
    assert (events[0].start, events[0].end) == (2, 3)
    assert json.loads(path.read_text(encoding="utf-8"))["segments"][0]["singleLine"] is True


def test_one_line_changes_exact_preview_hash_but_defaults_keep_old_contract():
    candidate = Candidate(id="normal", type="normal", start=0, end=10, duration=10, transcript_text="字幕")
    original = TranscriptSegment(start=1, end=2, text="字幕")
    common = dict(candidate=candidate, settings={}, source_fingerprint="source", source_width=1920, source_height=1080)
    ordinary = build_subtitle_review_preview_spec(**common, transcript_segments=[original])
    explicit = build_subtitle_review_preview_spec(
        **common, transcript_segments=[original.model_copy(update={"single_line": True, "preserve_segmentation": True})]
    )
    assert "single_line" not in ordinary["segments"][0]
    assert "preserve_segmentation" not in ordinary["segments"][0]
    assert explicit["segments"][0]["single_line"] is True
    assert subtitle_review_preview_spec_hash(ordinary) != subtitle_review_preview_spec_hash(explicit)
