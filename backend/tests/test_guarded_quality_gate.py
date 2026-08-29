import json

import pytest
from pydantic import ValidationError

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.quality_gate import (
    QualityGateDecision,
    aggregate_quality_gate_outcomes,
    evaluate_content_quality_gate,
    evaluate_post_render_quality_gate,
    evaluate_selection_quality_gate,
    load_quality_gate_decision,
    quality_gate_decision_path,
    quality_gate_input_hash,
    unknown_quality_gate_decision,
    write_quality_gate_decision,
)
from app.jobs.subtitle_review import SubtitleReviewDocument, build_subtitle_review
from app.render.render_normal import NormalRenderFailure


def _candidate(
    candidate_id: str,
    *,
    clip_type: str = "normal",
    start: float = 1.0,
    end: float = 11.0,
    title: str | None = "確認できるタイトル",
    hard_gate_passed: bool | None = True,
    risk_flags: list[str] | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=clip_type,
        start=start,
        end=end,
        duration=end - start,
        transcript_text="根拠になる字幕です",
        title=title,
        hard_gate_passed=hard_gate_passed,
        risk_flags=risk_flags or [],
    )


def _selection(
    *,
    normal: list[Candidate] | None = None,
    shorts: list[Candidate] | None = None,
) -> CandidateSelection:
    normal_clips = normal or []
    short_clips = shorts or []
    return CandidateSelection(
        normalClips=normal_clips,
        shorts=short_clips,
        requestedNormalCount=len(normal_clips),
        requestedShortCount=len(short_clips),
    )


def _transcript_for(*candidates: Candidate) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start=candidate.start,
            end=candidate.end,
            text=candidate.transcript_text,
        )
        for candidate in candidates
    ]


def _selection_settings(*, normal_count: int, short_count: int) -> dict[str, object]:
    return {
        "normalClipCount": normal_count,
        "shortCount": short_count,
        "normalMinDuration": 1.0,
        "normalMaxDuration": 30.0,
        "shortMinDuration": 1.0,
        "shortMaxDuration": 30.0,
        "heatmapIntervalMode": False,
    }


def _mark_previews_ready(document: SubtitleReviewDocument) -> SubtitleReviewDocument:
    for index, clip in enumerate(document.clips, start=1):
        clip.preview_state = "ready"
        clip.preview_spec_hash = f"{index:064x}"
        clip.preview_video_url = f"/exact-preview-{clip.id}.mp4"
        clip.live_preview_spec_hash = f"{index + 100:064x}"
        clip.live_preview_video_url = f"/live-preview-{clip.id}.mp4"
    return document


def _ready_content_document() -> SubtitleReviewDocument:
    short = _candidate(
        "short_1",
        clip_type="short",
        start=5.0,
        end=15.0,
    )
    document = build_subtitle_review(
        "job_1",
        _selection(shorts=[short]),
        _transcript_for(short),
        short_max_duration=30.0,
        source_width=1920,
        source_height=1080,
    )
    return _mark_previews_ready(document)


def _check(decision: QualityGateDecision, code: str):
    return next(check for check in decision.checks if check.code == code)


def test_aggregate_quality_gate_outcomes_is_fail_closed() -> None:
    assert aggregate_quality_gate_outcomes(["pass", "pass"]) == "pass"
    assert aggregate_quality_gate_outcomes(["pass", "unknown"]) == "unknown"
    assert aggregate_quality_gate_outcomes(["unknown", "fail"]) == "fail"
    with pytest.raises(ValueError, match="at least one"):
        aggregate_quality_gate_outcomes([])


def test_quality_gate_input_hash_is_canonical_stage_scoped_and_sensitive() -> None:
    first = quality_gate_input_hash(
        "selection",
        {"settings": {"shortCount": 2, "normalClipCount": 1}},
    )
    reordered = quality_gate_input_hash(
        "selection",
        {"settings": {"normalClipCount": 1, "shortCount": 2}},
    )
    changed = quality_gate_input_hash(
        "selection",
        {"settings": {"normalClipCount": 1, "shortCount": 1}},
    )
    other_stage = quality_gate_input_hash(
        "content",
        {"settings": {"normalClipCount": 1, "shortCount": 2}},
    )

    assert first == reordered
    assert first != changed
    assert first != other_stage
    assert len(first) == 64
    with pytest.raises(ValueError, match="finite"):
        quality_gate_input_hash("selection", {"invalid": float("nan")})


def test_selection_gate_passes_only_when_all_recorded_checks_pass() -> None:
    normal = _candidate("normal_1")
    decision = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(normal=[normal]),
        transcript_segments=_transcript_for(normal),
        settings=_selection_settings(normal_count=1, short_count=0),
        source_duration=30.0,
    )

    assert decision.outcome == "pass"
    assert decision.route == "continue"
    assert all(check.outcome == "pass" for check in decision.checks)


def test_selection_gate_hash_ignores_subtitle_style_but_tracks_selection_settings() -> None:
    normal = _candidate("normal_1")
    settings = _selection_settings(normal_count=1, short_count=0)
    original = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(normal=[normal]),
        transcript_segments=_transcript_for(normal),
        settings={**settings, "subtitleFontSize": 52},
        source_duration=30.0,
    )
    style_changed = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(normal=[normal]),
        transcript_segments=_transcript_for(normal),
        settings={**settings, "subtitleFontSize": 76},
        source_duration=30.0,
    )
    count_changed = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(normal=[normal]),
        transcript_segments=_transcript_for(normal),
        settings={**settings, "normalClipCount": 2},
        source_duration=30.0,
    )

    assert original.input_hash == style_changed.input_hash
    assert original.input_hash != count_changed.input_hash


def test_selection_gate_fail_wins_over_unknown() -> None:
    candidate = _candidate(
        "normal_1",
        start=20.0,
        end=30.0,
        title=None,
        hard_gate_passed=None,
        risk_flags=["abrupt_start"],
    )
    decision = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(normal=[candidate]),
        transcript_segments=_transcript_for(candidate),
        settings=_selection_settings(normal_count=1, short_count=0),
        source_duration=25.0,
    )

    assert decision.outcome == "fail"
    assert decision.route == "clip_review"
    assert _check(decision, "selection.range_duration").outcome == "fail"
    assert _check(decision, "selection.candidate_hard_gate").outcome == "unknown"
    assert _check(decision, "selection.risk_flags").outcome == "unknown"


def test_shadow_gate_records_failure_without_enforcement() -> None:
    candidate = _candidate("normal_1", title=None)
    decision = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(normal=[candidate]),
        transcript_segments=_transcript_for(candidate),
        settings=_selection_settings(normal_count=1, short_count=0),
        source_duration=30.0,
        mode="shadow",
    )

    assert decision.mode == "shadow"
    assert decision.enforced is False
    assert decision.outcome == "fail"
    assert decision.route == "observe"


def test_selection_gate_rejects_requested_shortfall_and_duplicate_shorts() -> None:
    first = _candidate(
        "short_1",
        clip_type="short",
        start=1.0,
        end=11.0,
    )
    second = _candidate(
        "short_2",
        clip_type="short",
        start=9.0,
        end=19.0,
    )
    decision = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(shorts=[first, second]),
        transcript_segments=_transcript_for(first, second),
        settings=_selection_settings(normal_count=0, short_count=3),
        source_duration=30.0,
    )

    assert decision.outcome == "fail"
    assert _check(decision, "selection.requested_counts").outcome == "fail"
    assert _check(decision, "selection.short_diversity").outcome == "fail"


def test_content_gate_keeps_unconfirmed_semantic_checks_unknown() -> None:
    document = _ready_content_document()
    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
    )

    assert decision.outcome == "unknown"
    assert decision.route == "subtitle_review"
    assert _check(decision, "content.subtitle_structure").outcome == "pass"
    assert _check(decision, "content.preview_ready").outcome == "pass"
    assert _check(decision, "content.title_hook_semantics").outcome == "unknown"
    assert _check(decision, "content.subtitle_accuracy").outcome == "unknown"
    assert _check(decision, "content.actual_framing").outcome == "unknown"
    assert (
        _check(decision, "content.title_hook_semantics").evidence["provider"]
        == "human_review_confirmation"
    )
    assert _check(decision, "content.title_hook_semantics").evidence[
        "incompleteClipIds"
    ] == ["short_1"]


def test_content_gate_passes_after_confirmation_and_current_preview_are_ready() -> None:
    document = _ready_content_document()
    document.clips[0].confirmed = True
    document.confirmed_clip_count = 1

    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
    )

    assert decision.outcome == "pass"
    assert decision.route == "continue"
    assert all(check.outcome == "pass" for check in decision.checks)
    for code in (
        "content.title_hook_semantics",
        "content.subtitle_accuracy",
        "content.actual_framing",
    ):
        evidence = _check(decision, code).evidence
        assert evidence["provider"] == "human_review_confirmation"
        assert evidence["acceptedReadyClipIds"] == ["short_1"]
        assert evidence["previewSpecHashes"] == {"short_1": f"{1:064x}"}


def test_content_gate_short_framing_uses_only_confirmed_ready_shorts() -> None:
    normal = _candidate("normal_1")
    short = _candidate(
        "short_1",
        clip_type="short",
        start=12.0,
        end=22.0,
    )
    document = build_subtitle_review(
        "job_1",
        _selection(normal=[normal], shorts=[short]),
        _transcript_for(normal, short),
        short_max_duration=30.0,
        source_width=1920,
        source_height=1080,
    )
    _mark_previews_ready(document)
    next(clip for clip in document.clips if clip.id == "short_1").confirmed = True
    document.confirmed_clip_count = 1

    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={},
    )

    assert decision.outcome == "unknown"
    assert _check(decision, "content.title_hook_semantics").outcome == "unknown"
    framing = _check(decision, "content.actual_framing")
    assert framing.outcome == "pass"
    assert framing.evidence["scope"] == "short_clips"
    assert framing.evidence["acceptedReadyClipIds"] == ["short_1"]


def test_content_gate_normal_only_framing_is_non_applicable_pass() -> None:
    normal = _candidate("normal_1")
    document = build_subtitle_review(
        "job_1",
        _selection(normal=[normal]),
        _transcript_for(normal),
        short_max_duration=30.0,
        source_width=1920,
        source_height=1080,
    )
    _mark_previews_ready(document)

    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={},
    )

    framing = _check(decision, "content.actual_framing")
    assert framing.outcome == "pass"
    assert framing.reason_code is None
    assert framing.evidence["applicable"] is False
    assert framing.evidence["clipCount"] == 0


def test_content_gate_structure_failure_wins_over_unknown() -> None:
    document = _ready_content_document()
    document.segments[0].text = ""
    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
    )

    assert decision.outcome == "fail"
    assert decision.route == "subtitle_review"
    assert _check(decision, "content.subtitle_structure").outcome == "fail"


def test_content_gate_treats_unready_preview_as_unknown_and_failed_preview_as_fail() -> None:
    queued_document = _ready_content_document()
    queued_document.clips[0].preview_state = "queued"
    queued_document.clips[0].confirmed = True
    queued_document.confirmed_clip_count = 1
    queued = evaluate_content_quality_gate(
        job_id="job_1",
        document=queued_document,
        settings={},
    )
    assert _check(queued, "content.preview_ready").outcome == "unknown"
    assert _check(queued, "content.title_hook_semantics").outcome == "unknown"
    assert _check(queued, "content.subtitle_accuracy").outcome == "unknown"
    assert _check(queued, "content.actual_framing").outcome == "unknown"

    failed_document = _ready_content_document()
    failed_document.clips[0].preview_state = "failed"
    failed = evaluate_content_quality_gate(
        job_id="job_1",
        document=failed_document,
        settings={},
    )
    assert failed.outcome == "fail"
    assert _check(failed, "content.preview_ready").outcome == "fail"


def test_post_render_gate_requires_exact_count_and_empty_failure_evidence() -> None:
    exports = [
        {"id": "exp_1", "candidate_id": "normal_1", "type": "normal"},
        {"id": "exp_2", "candidate_id": "short_1", "type": "short"},
    ]
    passed = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=2,
        exports=exports,
        render_failures=[],
    )
    reordered = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=2,
        exports=list(reversed(exports)),
        render_failures=[],
    )
    failed = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=2,
        exports=exports[:1],
        render_failures=[
            NormalRenderFailure(candidate_id="short_1", error="render failed")
        ],
    )
    unknown = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=2,
        exports=None,
        render_failures=None,
    )

    assert passed.outcome == "pass"
    assert passed.route == "continue"
    assert passed.input_hash == reordered.input_hash
    assert failed.outcome == "fail"
    assert failed.route == "failed"
    assert unknown.outcome == "unknown"
    assert unknown.route == "failed"


def test_quality_gate_decision_atomic_round_trip_and_strict_schema(tmp_path) -> None:
    normal = _candidate("normal_1")
    decision = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(normal=[normal]),
        transcript_segments=_transcript_for(normal),
        settings=_selection_settings(normal_count=1, short_count=0),
        source_duration=30.0,
    )
    path = quality_gate_decision_path(tmp_path, "selection")

    written = write_quality_gate_decision(decision, path)
    loaded = load_quality_gate_decision(written)

    assert loaded == decision
    assert not list(path.parent.glob("*.tmp"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        QualityGateDecision.model_validate(payload)


def test_quality_gate_decision_rejects_forged_aggregate() -> None:
    normal = _candidate("normal_1")
    decision = evaluate_selection_quality_gate(
        job_id="job_1",
        selection=_selection(normal=[normal]),
        transcript_segments=_transcript_for(normal),
        settings=_selection_settings(normal_count=1, short_count=0),
        source_duration=30.0,
    )
    payload = decision.model_dump(by_alias=True, mode="json")
    payload["outcome"] = "unknown"
    payload["route"] = "clip_review"

    with pytest.raises(ValidationError, match="outcome must match"):
        QualityGateDecision.model_validate(payload)


@pytest.mark.parametrize(
    ("stage", "route"),
    [
        ("selection", "clip_review"),
        ("content", "subtitle_review"),
        ("post_render", "failed"),
    ],
)
def test_unknown_quality_gate_decision_fails_closed(stage: str, route: str) -> None:
    decision = unknown_quality_gate_decision(
        job_id="job_1",
        stage=stage,
        reason_code="evaluator_unavailable",
        evidence={"errorType": "RuntimeError"},
    )

    assert decision.outcome == "unknown"
    assert decision.route == route
    assert decision.checks[0].reason_code == "evaluator_unavailable"
    assert decision.checks[0].evidence == {"errorType": "RuntimeError"}
