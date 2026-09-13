import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import app.jobs.quality_gate as quality_gate_module
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
from app.jobs.subtitle_review import refresh_review_overlay_title_expectations
from app.jobs.title_hook_suggestions import (
    TitleHookDraftSegment,
    TitleHookSuggestionsDocument,
    apply_recommended_title_hook_suggestions,
    build_title_hook_suggestion_input,
)
from app.render.render_normal import NormalRenderFailure
from app.scoring.title_hook_suggestions import TitleHookSuggestion
from app.video.probe import VideoMetadata


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


def _apply_ready_codex_evidence(
    document: SubtitleReviewDocument,
    clip_id: str | None = None,
) -> TitleHookSuggestionsDocument:
    clip = next(
        (
            item
            for item in document.clips
            if clip_id is None or item.id == clip_id
        ),
        None,
    )
    assert clip is not None
    drafts = [
        TitleHookDraftSegment(segmentId=segment.id, text=segment.text)
        for segment in document.segments
        if segment.id in clip.segment_ids
    ]
    request = build_title_hook_suggestion_input(
        document,
        clip.id,
        drafts,
        model="codex-default",
    )
    suggestion = TitleHookSuggestion(
        id="factual",
        publicationTitle="確認できる投稿タイトル",
        overlayTitle="確認できるタイトル",
        hookText="根拠になる字幕です",
        hookDurationSeconds=2.0,
        hookSceneStart=0.0,
        hookSceneEnd=2.0,
        reason="入力字幕を根拠にした案",
        intent="factual",
        evidenceSegmentIds=[draft.segment_id for draft in drafts],
    )
    artifact = TitleHookSuggestionsDocument(
        clipId=clip.id,
        state="ready",
        inputHash=request.input_hash,
        draftHash=request.draft_hash,
        revisionHash=request.revision_hash,
        provider="codex",
        model="codex-default",
        suggestions=[suggestion],
        recommendedSuggestionId=suggestion.id,
        youtubeDescription="字幕で確認できる内容です。",
        hashtags=["#切り抜き"],
        descriptionEvidenceSegmentIds=[draft.segment_id for draft in drafts],
    )
    apply_recommended_title_hook_suggestions(document, artifact)
    refresh_review_overlay_title_expectations(
        document,
        render_mode=document.render_mode,
    )
    return artifact


def test_auto_content_gate_passes_only_with_current_codex_asr_and_layout_evidence() -> None:
    document = _ready_content_document()
    document.segments[0].confidence = 0.9
    artifact = _apply_ready_codex_evidence(document)

    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
        mode="auto",
        title_hook_evidence={document.clips[0].id: artifact},
    )

    assert decision.outcome == "pass"
    assert decision.route == "continue"
    assert _check(decision, "content.title_hook_semantics").outcome == "pass"
    assert _check(decision, "content.subtitle_accuracy").outcome == "pass"
    assert _check(decision, "content.overlay_layout").outcome == "pass"
    framing = _check(decision, "content.actual_framing")
    assert framing.outcome == "pass"
    assert framing.evidence["deferredToPostRender"] is True


def test_auto_content_gate_accepts_one_clip_human_override_without_weakening_others() -> None:
    first = _candidate("normal_human", start=0.0, end=10.0)
    second = _candidate("normal_auto", start=20.0, end=30.0)
    document = build_subtitle_review(
        "job_1",
        _selection(normal=[first, second]),
        _transcript_for(first, second),
        short_max_duration=30.0,
        source_width=1920,
        source_height=1080,
    )
    _mark_previews_ready(document)
    human_clip = next(clip for clip in document.clips if clip.id == first.id)
    human_clip.confirmed = True
    human_clip.resolved_subtitle_style.font_size = 500
    document.confirmed_clip_count = 1
    for segment in document.segments:
        segment.confidence = 0.1 if first.id in segment.affected_clip_ids else 0.9
    auto_artifact = _apply_ready_codex_evidence(document, second.id)

    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
        mode="auto",
        title_hook_evidence={second.id: auto_artifact},
    )

    assert decision.outcome == "pass"
    assert decision.route == "continue"
    for code in (
        "content.title_hook_semantics",
        "content.subtitle_accuracy",
        "content.overlay_layout",
    ):
        check = _check(decision, code)
        assert check.outcome == "pass"
        assert check.evidence["humanAcceptedClipIds"] == [first.id]

    stale_artifact = auto_artifact.model_copy(update={"revision_hash": "0" * 64})
    blocked = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
        mode="auto",
        title_hook_evidence={second.id: stale_artifact},
    )
    assert blocked.route == "subtitle_review"
    assert _check(blocked, "content.title_hook_semantics").outcome == "unknown"


def test_auto_content_overlay_gate_uses_render_events_for_long_shared_segments() -> None:
    normal = _candidate(
        "normal_1",
        clip_type="normal",
        start=0.0,
        end=15.0,
    )
    short = _candidate(
        "short_1",
        clip_type="short",
        start=0.0,
        end=15.0,
    )
    long_text = (
        "あの手を洗ってブロッコリーと一緒に電子レンジへ入れて、"
        "いい感じになったらバジルソースをかけていただきます。"
        "最後にご飯を混ぜるとリゾットの完成です。"
    )
    document = build_subtitle_review(
        "job_1",
        _selection(normal=[normal], shorts=[short]),
        [
            TranscriptSegment(
                start=0.0,
                end=15.0,
                text=long_text,
                confidence=0.9,
            )
        ],
        short_max_duration=30.0,
        source_width=1920,
        source_height=1080,
    )
    _mark_previews_ready(document)

    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
        mode="auto",
    )

    overlay = _check(decision, "content.overlay_layout")
    subtitle_items = [
        item
        for item in overlay.evidence["inspected"]
        if item["role"].startswith("subtitle:")
    ]
    assert overlay.outcome == "pass"
    assert len(subtitle_items) > 2
    assert {item["clipId"] for item in subtitle_items} == {"normal_1", "short_1"}
    assert all(item["fitsWidth"] for item in subtitle_items)
    assert not overlay.evidence["failures"]
    for clip in document.clips:
        events, layout = quality_gate_module._subtitle_events_for_review_clip(
            document,
            clip,
            width=clip.preview_width,
            height=clip.preview_height,
        )
        assert "".join(event.text for event in events) == long_text
        assert all(
            len(event.text) <= layout.max_chars_per_line * layout.max_lines
            for event in events
        )
        assert all(
            0 < event.end - event.start <= layout.max_subtitle_duration
            for event in events
        )


def test_auto_content_overlay_gate_rejects_unfit_single_render_event() -> None:
    short = _candidate(
        "short_1",
        clip_type="short",
        start=0.0,
        end=1.0,
    )
    document = build_subtitle_review(
        "job_1",
        _selection(shorts=[short]),
        [
            TranscriptSegment(
                start=0.0,
                end=1.0,
                text="長文" * 120,
                confidence=0.9,
            )
        ],
        short_max_duration=30.0,
        source_width=1920,
        source_height=1080,
    )
    _mark_previews_ready(document)

    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
        mode="auto",
    )

    overlay = _check(decision, "content.overlay_layout")
    assert overlay.outcome == "fail"
    assert any(
        failure["reason"] == "horizontal_text_overflow"
        and failure["role"] == "subtitle:event_00001"
        for failure in overlay.evidence["failures"]
    )


def test_auto_content_gate_fails_closed_when_asr_or_codex_evidence_is_missing() -> None:
    document = _ready_content_document()

    decision = evaluate_content_quality_gate(
        job_id="job_1",
        document=document,
        settings={"burnSubtitles": True},
        mode="auto",
    )

    assert decision.outcome == "unknown"
    assert decision.route == "subtitle_review"
    assert _check(decision, "content.title_hook_semantics").reason_code == (
        "title_hook_evidence_unavailable_or_stale"
    )
    assert _check(decision, "content.subtitle_accuracy").reason_code == (
        "asr_alignment_evidence_insufficient"
    )


def test_auto_post_render_requires_media_and_crop_containment_or_human_preview(
    tmp_path,
    monkeypatch,
) -> None:
    document = _ready_content_document()
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: VideoMetadata(
            duration=10.0,
            width=1080,
            height=1920,
            fps=30.0,
            has_audio=True,
            video_stream_duration=10.0,
            audio_stream_duration=10.0,
            container_duration=10.0,
        ),
    )
    video_path = tmp_path / "short.mp4"
    subtitle_path = tmp_path / "short.ass"
    metadata_path = tmp_path / "short.json"
    video_path.write_bytes(b"video")
    subtitle_path.write_text("subtitle", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "candidate_id": "short_1",
                "type": "short",
                "title": document.clips[0].publication_title
                or document.clips[0].title,
                "overlay_title": document.clips[0].title,
                "hook_text": document.clips[0].hook_text,
                "post_metadata_revision_hash": document.clips[
                    0
                ].post_metadata_revision_hash,
                "duration": document.clips[0].duration,
                "crop_strategy": "face_tracking_crop",
                "crop_confidence": 0.99,
                "crop_detection_count": 10,
                "top_banner_rendered": False,
                "bottom_banner_rendered": False,
                "overlay_title_expected": document.clips[
                    0
                ].overlay_title_expected,
                "overlay_title_rendered": document.clips[
                    0
                ].overlay_title_expected,
                "hook_rendered": False,
                "hook_scene_rendered": False,
            }
        ),
        encoding="utf-8",
    )
    export = {
        "id": "export_1",
        "candidate_id": "short_1",
        "type": "short",
        "video_path": str(video_path),
        "subtitle_path": str(subtitle_path),
        "metadata_path": str(metadata_path),
    }

    unconfirmed = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )
    assert unconfirmed.outcome == "unknown"
    assert _check(unconfirmed, "post_render.media_artifacts").outcome == "pass"
    assert _check(unconfirmed, "post_render.visual_framing_layout").reason_code == (
        "post_render_visual_evidence_insufficient"
    )

    document.clips[0].confirmed = True
    document.confirmed_clip_count = 1
    confirmed = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )
    assert confirmed.outcome == "pass"
    assert confirmed.route == "continue"


def _post_render_document() -> SubtitleReviewDocument:
    normal = _candidate("normal_1", start=1.0, end=11.0)
    short = _candidate(
        "short_1",
        clip_type="short",
        start=15.0,
        end=25.0,
    )
    document = build_subtitle_review(
        "job_1",
        _selection(normal=[normal], shorts=[short]),
        _transcript_for(normal, short),
        short_max_duration=30.0,
        source_width=1920,
        source_height=1080,
    )
    return _mark_previews_ready(document)


def _post_render_export(
    tmp_path,
    *,
    export_id: str,
    candidate_id: str,
    clip_type: str,
) -> dict[str, str]:
    output_dir = tmp_path / export_id
    output_dir.mkdir(parents=True, exist_ok=True)
    video_path = output_dir / "clip.mp4"
    subtitle_path = output_dir / "clip.ass"
    metadata_path = output_dir / "clip.json"
    video_path.write_bytes(b"not-a-real-mp4")
    subtitle_path.write_text("subtitle", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "duration": 10.0,
                "crop_strategy": "blur_background",
                "top_banner_rendered": False,
                "bottom_banner_rendered": False,
                "overlay_title_expected": False,
                "overlay_title_rendered": False,
                "hook_rendered": False,
                "hook_scene_rendered": False,
            }
        ),
        encoding="utf-8",
    )
    return {
        "id": export_id,
        "candidate_id": candidate_id,
        "type": clip_type,
        "video_path": str(video_path),
        "subtitle_path": str(subtitle_path),
        "metadata_path": str(metadata_path),
    }


def _matching_short_render_metadata(
    document: SubtitleReviewDocument,
    *,
    duration: float,
) -> dict[str, object]:
    clip = next(item for item in document.clips if item.type == "short")
    hook_scene_rendered = (
        clip.hook_scene_start is not None and clip.hook_scene_end is not None
    )
    hook_scene_duration = (
        float(clip.hook_scene_end) - float(clip.hook_scene_start)
        if hook_scene_rendered
        else 0.0
    )
    return {
        "candidate_id": clip.id,
        "type": clip.type,
        "title": clip.publication_title or clip.title,
        "overlay_title": clip.title,
        "overlay_title_expected": clip.overlay_title_expected,
        "overlay_title_rendered": clip.overlay_title_expected,
        "hook_text": clip.hook_text,
        "hook_rendered": bool(clip.hook_text),
        "hook_scene_start": clip.hook_scene_start,
        "hook_scene_end": clip.hook_scene_end,
        "hook_scene_duration": hook_scene_duration,
        "hook_scene_rendered": hook_scene_rendered,
        "post_metadata_revision_hash": clip.post_metadata_revision_hash,
        "start": clip.start,
        "end": clip.end,
        "body_duration": clip.duration,
        "duration": duration,
        "crop_strategy": "blur_background",
        "top_banner_rendered": document.short_top_banner_enabled,
        "bottom_banner_rendered": document.short_bottom_banner_enabled,
    }


def _write_export_metadata(
    export: dict[str, str],
    metadata: dict[str, object],
) -> None:
    Path(export["metadata_path"]).write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )


def _rendered_video_metadata(
    *,
    duration: float | None,
    video_stream_duration: float | None,
    audio_stream_duration: float | None,
) -> VideoMetadata:
    return VideoMetadata(
        duration=duration,
        width=1080,
        height=1920,
        fps=30.0,
        has_audio=True,
        video_stream_duration=video_stream_duration,
        audio_stream_duration=audio_stream_duration,
        container_duration=duration,
    )


def test_auto_post_render_rejects_export_identity_mismatches(
    tmp_path,
    monkeypatch,
) -> None:
    document = _post_render_document()
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: VideoMetadata(
            duration=10.0,
            width=1080,
            height=1920,
            fps=30.0,
            has_audio=True,
            video_stream_duration=10.0,
            audio_stream_duration=10.0,
            container_duration=10.0,
        ),
        raising=False,
    )
    normal = _post_render_export(
        tmp_path,
        export_id="normal",
        candidate_id="normal_1",
        clip_type="normal",
    )
    short = _post_render_export(
        tmp_path,
        export_id="short",
        candidate_id="short_1",
        clip_type="short",
    )
    cases = {
        "missing": [normal],
        "unexpected": [
            normal,
            _post_render_export(
                tmp_path,
                export_id="unexpected",
                candidate_id="short_unexpected",
                clip_type="short",
            ),
        ],
        "duplicates": [
            short,
            _post_render_export(
                tmp_path,
                export_id="short_duplicate",
                candidate_id="short_1",
                clip_type="short",
            ),
        ],
        "typeMismatches": [
            normal,
            _post_render_export(
                tmp_path,
                export_id="short_wrong_type",
                candidate_id="short_1",
                clip_type="normal",
            ),
        ],
    }

    for evidence_key, exports in cases.items():
        decision = evaluate_post_render_quality_gate(
            job_id="job_1",
            expected_export_count=2,
            exports=exports,
            render_failures=[],
            mode="auto",
            document=document,
        )

        identity = _check(decision, "post_render.export_identity")
        assert identity.outcome == "fail", evidence_key
        assert identity.reason_code == "rendered_export_identity_mismatch"
        assert identity.evidence[evidence_key]
        assert decision.outcome == "fail"
        assert decision.route == "subtitle_review"


@pytest.mark.parametrize("missing_input", ["document", "exports"])
def test_auto_post_render_keeps_uninspected_export_identity_unknown(
    missing_input: str,
) -> None:
    document = None if missing_input == "document" else _post_render_document()
    exports = [] if missing_input == "document" else None
    decision = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=0 if exports == [] else 2,
        exports=exports,
        render_failures=[],
        mode="auto",
        document=document,
    )

    assert _check(decision, "post_render.export_identity").outcome == "unknown"
    assert decision.outcome == "unknown"
    assert decision.route == "subtitle_review"


def test_auto_post_render_does_not_accept_nonempty_but_invalid_mp4(tmp_path) -> None:
    document = _ready_content_document()
    export = _post_render_export(
        tmp_path,
        export_id="invalid_mp4",
        candidate_id="short_1",
        clip_type="short",
    )

    decision = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )

    assert _check(decision, "post_render.media_artifacts").outcome != "pass"
    assert decision.outcome != "pass"
    assert decision.route == "subtitle_review"


def test_auto_post_render_keeps_ffprobe_failure_nonpassing(
    tmp_path,
    monkeypatch,
) -> None:
    document = _ready_content_document()
    export = _post_render_export(
        tmp_path,
        export_id="probe_failure",
        candidate_id="short_1",
        clip_type="short",
    )

    def fail_probe(_path):
        raise OSError("ffprobe unavailable")

    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        fail_probe,
        raising=False,
    )
    decision = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )

    assert _check(decision, "post_render.media_artifacts").outcome != "pass"
    assert decision.outcome != "pass"
    assert decision.route == "subtitle_review"


@pytest.mark.parametrize(
    "probe_result",
    [
        VideoMetadata(
            duration=10.0,
            width=None,
            height=None,
            fps=None,
            has_audio=True,
            audio_stream_duration=10.0,
            container_duration=10.0,
        ),
        VideoMetadata(
            duration=10.0,
            width=1080,
            height=1920,
            fps=30.0,
            has_audio=False,
            video_stream_duration=10.0,
            container_duration=10.0,
        ),
        VideoMetadata(
            duration=None,
            width=1080,
            height=1920,
            fps=30.0,
            has_audio=True,
            audio_stream_duration=10.0,
        ),
    ],
    ids=["video_stream_missing", "audio_stream_missing", "duration_missing"],
)
def test_auto_post_render_keeps_incomplete_probe_metadata_nonpassing(
    tmp_path,
    monkeypatch,
    probe_result: VideoMetadata,
) -> None:
    document = _ready_content_document()
    export = _post_render_export(
        tmp_path,
        export_id="incomplete_probe",
        candidate_id="short_1",
        clip_type="short",
    )
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: probe_result,
        raising=False,
    )

    decision = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )

    assert _check(decision, "post_render.media_artifacts").outcome != "pass"
    assert decision.outcome != "pass"
    assert decision.route == "subtitle_review"


@pytest.mark.parametrize(
    ("metadata_override", "expected_outcome"),
    [
        ({}, "pass"),
        ({"hook_scene_rendered": False}, "fail"),
        ({"hook_scene_start": 6.1}, "fail"),
        ({"hook_scene_end": 7.9}, "fail"),
    ],
    ids=["matching", "not_rendered", "start_mismatch", "end_mismatch"],
)
def test_auto_post_render_requires_exact_hook_scene_metadata(
    tmp_path,
    monkeypatch,
    metadata_override: dict[str, object],
    expected_outcome: str,
) -> None:
    document = _ready_content_document()
    clip = document.clips[0]
    clip.hook_text = "冒頭フック"
    clip.hook_scene_start = 6.0
    clip.hook_scene_end = 8.0
    output_duration = clip.duration + 2.0
    export = _post_render_export(
        tmp_path,
        export_id="hook_scene",
        candidate_id=clip.id,
        clip_type=clip.type,
    )
    metadata = _matching_short_render_metadata(
        document,
        duration=output_duration,
    )
    metadata.update(metadata_override)
    _write_export_metadata(export, metadata)
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: _rendered_video_metadata(
            duration=output_duration,
            video_stream_duration=output_duration,
            audio_stream_duration=output_duration,
        ),
    )

    decision = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )

    assert _check(decision, "post_render.content_contract").outcome == expected_outcome
    assert decision.outcome == expected_outcome
    assert decision.route == (
        "continue" if expected_outcome == "pass" else "subtitle_review"
    )


def test_auto_post_render_content_contract_requires_exact_curated_title(
    tmp_path,
    monkeypatch,
) -> None:
    document = _ready_content_document()
    clip = document.clips[0]
    publication_title = "箸が止まらない！バジルソースで食べるブロッコリー"
    clip.title = "箸が止まらない！\nめちゃうまブロッコリー"
    clip.publication_title = publication_title
    clip.confirmed = True
    clip.post_metadata_revision_hash = "a" * 64
    document.confirmed_clip_count = 1
    export = _post_render_export(
        tmp_path,
        export_id="curated_title_contract",
        candidate_id=clip.id,
        clip_type=clip.type,
    )
    metadata = _matching_short_render_metadata(
        document,
        duration=clip.duration,
    )
    _write_export_metadata(export, metadata)
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: _rendered_video_metadata(
            duration=clip.duration,
            video_stream_duration=clip.duration,
            audio_stream_duration=clip.duration,
        ),
    )

    matching = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )
    assert _check(matching, "post_render.content_contract").outcome == "pass"
    assert matching.outcome == "pass"
    assert matching.route == "continue"

    metadata["title"] = publication_title.removesuffix("ー")
    _write_export_metadata(export, metadata)
    missing_prolonged_sound_mark = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )
    contract = _check(
        missing_prolonged_sound_mark,
        "post_render.content_contract",
    )
    assert contract.outcome == "fail"
    assert contract.evidence["failures"] == [
        {
            "clipId": clip.id,
            "type": "short",
            "mismatches": ["title"],
        }
    ]
    assert missing_prolonged_sound_mark.route == "subtitle_review"


def test_auto_post_render_rejects_rendered_hook_scene_when_none_is_configured(
    tmp_path,
    monkeypatch,
) -> None:
    document = _ready_content_document()
    clip = document.clips[0]
    export = _post_render_export(
        tmp_path,
        export_id="hook_scene_unset",
        candidate_id=clip.id,
        clip_type=clip.type,
    )
    metadata = _matching_short_render_metadata(
        document,
        duration=clip.duration,
    )
    _write_export_metadata(export, metadata)
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: _rendered_video_metadata(
            duration=clip.duration,
            video_stream_duration=clip.duration,
            audio_stream_duration=clip.duration,
        ),
    )
    not_rendered = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )
    assert not_rendered.outcome == "pass"

    metadata["hook_scene_rendered"] = True
    _write_export_metadata(export, metadata)
    rendered = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )

    assert _check(rendered, "post_render.content_contract").outcome == "fail"
    assert rendered.outcome == "fail"
    assert rendered.route == "subtitle_review"


@pytest.mark.parametrize(
    ("metadata_duration", "probe_result"),
    [
        (
            11.0,
            _rendered_video_metadata(
                duration=12.0,
                video_stream_duration=12.0,
                audio_stream_duration=12.0,
            ),
        ),
        (
            12.0,
            _rendered_video_metadata(
                duration=11.0,
                video_stream_duration=11.0,
                audio_stream_duration=11.0,
            ),
        ),
        (
            12.0,
            _rendered_video_metadata(
                duration=12.0,
                video_stream_duration=None,
                audio_stream_duration=12.0,
            ),
        ),
        (
            12.0,
            _rendered_video_metadata(
                duration=12.0,
                video_stream_duration=12.0,
                audio_stream_duration=None,
            ),
        ),
        (
            12.0,
            _rendered_video_metadata(
                duration=12.0,
                video_stream_duration=9.0,
                audio_stream_duration=12.0,
            ),
        ),
        (
            12.0,
            _rendered_video_metadata(
                duration=12.0,
                video_stream_duration=12.0,
                audio_stream_duration=9.0,
            ),
        ),
    ],
    ids=[
        "metadata_truncated_one_second",
        "probe_truncated_one_second",
        "video_stream_duration_missing",
        "audio_stream_duration_missing",
        "video_stream_duration_mismatch",
        "audio_stream_duration_mismatch",
    ],
)
def test_auto_post_render_requires_full_hook_augmented_media_duration(
    tmp_path,
    monkeypatch,
    metadata_duration: float,
    probe_result: VideoMetadata,
) -> None:
    document = _ready_content_document()
    clip = document.clips[0]
    clip.hook_text = "冒頭フック"
    clip.hook_scene_start = 6.0
    clip.hook_scene_end = 8.0
    export = _post_render_export(
        tmp_path,
        export_id="duration_contract",
        candidate_id=clip.id,
        clip_type=clip.type,
    )
    _write_export_metadata(
        export,
        _matching_short_render_metadata(
            document,
            duration=metadata_duration,
        ),
    )
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: probe_result,
    )

    decision = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )

    assert _check(decision, "post_render.media_artifacts").outcome != "pass"
    assert decision.outcome != "pass"
    assert decision.route == "subtitle_review"


@pytest.mark.parametrize(
    ("strategy", "evidence_case", "expected_outcome"),
    [
        ("face_tracking_crop", "inside", "pass"),
        ("face_tracking_crop", "outside", "fail"),
        ("face_tracking_crop", "samples_empty", "unknown"),
        ("face_tracking_crop", "crop_missing", "unknown"),
        ("face_tracking_crop", "insufficient_samples", "unknown"),
        ("speaker_tracking_crop", "inside", "pass"),
        ("speaker_tracking_crop", "outside", "fail"),
        ("speaker_tracking_crop", "samples_empty", "unknown"),
        ("speaker_tracking_crop", "crop_missing", "unknown"),
        ("speaker_tracking_crop", "low_confidence", "unknown"),
        ("person_tracking_crop", "inside", "pass"),
        ("person_tracking_crop", "outside", "fail"),
        ("person_tracking_crop", "samples_empty", "unknown"),
        ("person_tracking_crop", "crop_missing", "unknown"),
        ("person_tracking_crop", "low_stability", "unknown"),
        ("subject_tracking_crop", "samples_empty", "unknown"),
    ],
)
def test_auto_post_render_tracking_evidence_controls_visual_gate(
    tmp_path,
    monkeypatch,
    strategy: str,
    evidence_case: str,
    expected_outcome: str,
) -> None:
    document = _ready_content_document()
    clip = document.clips[0]
    export = _post_render_export(
        tmp_path,
        export_id=f"{strategy}_{evidence_case}",
        candidate_id=clip.id,
        clip_type=clip.type,
    )
    samples: list[dict[str, object]] = [
        {
            "start": 0.0,
            "end": 1.0,
            "box": [0.30, 0.20, 0.50, 0.60],
            "confidence": 0.92,
            "source": strategy.removesuffix("_tracking_crop"),
        },
        {
            "start": 1.0,
            "end": 2.0,
            "box": [0.40, 0.30, 0.60, 0.70],
            "confidence": 0.89,
            "source": strategy.removesuffix("_tracking_crop"),
        },
        {
            "start": 2.0,
            "end": 3.0,
            "box": [0.35, 0.25, 0.55, 0.65],
            "confidence": 0.91,
            "source": strategy.removesuffix("_tracking_crop"),
        },
    ]
    if evidence_case == "outside":
        samples[1]["box"] = [0.10, 0.30, 0.30, 0.70]
    elif evidence_case == "samples_empty":
        samples = []
    elif evidence_case == "insufficient_samples":
        samples = samples[:2]
    tracking_evidence: dict[str, object] = {
        "schema_version": 1,
        "strategy": strategy,
        "source": {"width": 1000, "height": 1000},
        "scaled": {"width": 2000, "height": 2000},
        "crop": {"x": 400, "y": 0, "width": 1080, "height": 1920},
        "safe_area": {"x": 500, "y": 100, "width": 880, "height": 1600},
        "samples": samples,
    }
    if evidence_case == "crop_missing":
        tracking_evidence.pop("crop")
    metadata = _matching_short_render_metadata(
        document,
        duration=clip.duration,
    )
    metadata.update(
        {
            "crop_strategy": strategy,
            "crop_confidence": 0.90,
            "tracking_evidence": tracking_evidence,
        }
    )
    if strategy == "face_tracking_crop":
        metadata["crop_detection_count"] = len(samples)
    elif strategy == "speaker_tracking_crop":
        metadata["speaker_window_count"] = len(samples)
        metadata["speaker_region_confidence"] = (
            0.70 if evidence_case == "low_confidence" else 0.90
        )
        metadata["crop_stability_score"] = 0.80
    elif strategy == "person_tracking_crop":
        metadata["person_detection_count"] = len(samples)
        metadata["person_detection_confidence"] = 0.90
        metadata["crop_sampled_frames"] = len(samples)
        metadata["crop_stability_score"] = (
            0.50 if evidence_case == "low_stability" else 0.80
        )
    _write_export_metadata(export, metadata)
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: _rendered_video_metadata(
            duration=clip.duration,
            video_stream_duration=clip.duration,
            audio_stream_duration=clip.duration,
        ),
    )

    decision = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )

    visual = _check(decision, "post_render.visual_framing_layout")
    assert visual.outcome == expected_outcome
    assert decision.outcome == expected_outcome
    assert decision.route == (
        "continue" if expected_outcome == "pass" else "subtitle_review"
    )


@pytest.mark.parametrize(
    ("mismatch_field", "mismatch_value", "expected_outcome"),
    [
        (None, None, "pass"),
        ("title", "不一致の投稿タイトル", "fail"),
        ("overlay_title", "不一致の帯タイトル", "fail"),
        ("hook_text", "不一致のフック", "fail"),
        ("hook_scene_start", 2.25, "fail"),
        ("post_metadata_revision_hash", "b" * 64, "fail"),
    ],
    ids=[
        "matching",
        "title_mismatch",
        "overlay_mismatch",
        "hook_mismatch",
        "hook_scene_mismatch",
        "revision_mismatch",
    ],
)
def test_auto_post_render_normal_export_content_contract_is_exact(
    tmp_path,
    monkeypatch,
    mismatch_field: str | None,
    mismatch_value: object,
    expected_outcome: str,
) -> None:
    normal = _candidate("normal_1", start=1.0, end=11.0)
    document = build_subtitle_review(
        "job_1",
        _selection(normal=[normal]),
        _transcript_for(normal),
        short_max_duration=30.0,
        source_width=1920,
        source_height=1080,
    )
    _mark_previews_ready(document)
    clip = document.clips[0]
    clip.hook_text = "冒頭フック"
    clip.hook_scene_start = 2.0
    clip.hook_scene_end = 4.0
    clip.post_metadata_revision_hash = "a" * 64
    output_duration = clip.duration + 2.0
    export = _post_render_export(
        tmp_path,
        export_id="normal_content_contract",
        candidate_id=clip.id,
        clip_type=clip.type,
    )
    metadata: dict[str, object] = {
        "candidate_id": clip.id,
        "type": clip.type,
        "title": clip.publication_title or clip.title,
        "overlay_title": clip.title,
        "overlay_title_expected": clip.overlay_title_expected,
        "overlay_title_rendered": clip.overlay_title_expected,
        "title_rendered": True,
        "hook_text": clip.hook_text,
        "hook_rendered": True,
        "hook_scene_start": clip.hook_scene_start,
        "hook_scene_end": clip.hook_scene_end,
        "hook_scene_duration": 2.0,
        "hook_scene_rendered": True,
        "post_metadata_revision_hash": clip.post_metadata_revision_hash,
        "body_duration": clip.duration,
        "duration": output_duration,
    }
    if mismatch_field is not None:
        metadata[mismatch_field] = mismatch_value
    _write_export_metadata(export, metadata)
    monkeypatch.setattr(
        quality_gate_module,
        "probe_metadata",
        lambda _path: VideoMetadata(
            duration=output_duration,
            width=1920,
            height=1080,
            fps=30.0,
            has_audio=True,
            video_stream_duration=output_duration,
            audio_stream_duration=output_duration,
            container_duration=output_duration,
        ),
    )

    decision = evaluate_post_render_quality_gate(
        job_id="job_1",
        expected_export_count=1,
        exports=[export],
        render_failures=[],
        mode="auto",
        document=document,
    )

    contract = _check(decision, "post_render.content_contract")
    assert contract.outcome == expected_outcome
    assert decision.outcome == expected_outcome
    assert decision.route == (
        "continue" if expected_outcome == "pass" else "subtitle_review"
    )


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
