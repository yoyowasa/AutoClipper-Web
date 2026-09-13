import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.codex_initial_selection import (
    CODEX_INITIAL_SELECTION_PROMPT_VERSION,
    MAX_REFINEMENT_PROMPT_CHARS,
    MAX_REFINEMENT_TRANSCRIPT_CHARS,
    MAX_TOPIC_SELECTION_PROMPT_CHARS,
    CodexClipProposal,
    CodexInitialSelectionError,
    CodexInitialSelectionResponse,
    CodexInitialSelectionSharedFileBridge,
    CodexTopicBlockInput,
    CodexTopicChoice,
    CodexTopicSelectionRequest,
    CodexTopicSelectionResponse,
    _validate_topic_selection_response,
    _bridge_envelope,
    _topic_bridge_envelope,
    build_local_topic_blocks,
    build_codex_boundary_refinement_request,
    build_codex_initial_selection_request,
    build_codex_topic_selection_request,
    codex_initial_selection_response_schema,
    codex_initial_selection_response_schema_sha256,
    codex_initial_selection_summary_output_path,
    codex_topic_selection_response_schema_sha256,
    compute_codex_initial_selection_input_hash,
    compute_codex_topic_selection_input_hash,
    convert_codex_initial_selection_response,
    request_codex_initial_selection,
    write_codex_initial_selection_summary,
)
from app.schemas import JobSettings
from app.video.heatmap import HeatmapSegment


def _transcript() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=0, end=30, text="最初の話題を説明します。"),
        TranscriptSegment(start=30, end=60, text="具体例を紹介します。"),
        TranscriptSegment(start=60, end=90, text="最初の話題の結論です。"),
        TranscriptSegment(start=90, end=110, text="次の話題で驚いた場面です。"),
        TranscriptSegment(start=110, end=130, text="短い反応と結論です。"),
        TranscriptSegment(start=130, end=160, text="最後の説明です。"),
    ]


def _settings(**overrides: object) -> dict[str, object]:
    settings: dict[str, object] = {
        "normalClipCount": 1,
        "shortCount": 1,
        "normalMinDuration": 90,
        "normalMaxDuration": 120,
        "shortMinDuration": 20,
        "shortMaxDuration": 40,
        "heatmapIntervalMode": False,
        "maxOverlapRatio": 0.8,
        "crossTypeOverlapDedupe": False,
    }
    settings.update(overrides)
    return settings


def _request(
    *,
    settings: dict[str, object] | None = None,
    heatmap: list[HeatmapSegment] | None = None,
):
    return build_codex_initial_selection_request(
        job_id="job_codex",
        transcript_segments=_transcript(),
        heatmap_segments=heatmap or [],
        video_duration=200,
        settings=settings or _settings(),
    )


def _response(request, *, short_start: float = 100, short_end: float = 120):
    return CodexInitialSelectionResponse(
        version=1,
        promptVersion=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        jobId=request.job_id,
        requestId=request.request_id,
        inputHash=request.input_hash,
        threadId="thread_local",
        selectedClips=[
            CodexClipProposal(
                proposalId="normal_1",
                type="normal",
                topicKey="main_explanation",
                start=0,
                end=90,
                momentKey=None,
                parentStart=None,
                parentEnd=None,
                evidenceSegmentIds=["seg_000001", "seg_000003"],
                heatmapSegmentIds=[],
                reason="話題が完結しています。",
                confidence=0.91,
                riskFlags=[],
            ),
            CodexClipProposal(
                proposalId="short_1",
                type="short",
                topicKey="reaction_topic",
                start=short_start,
                end=short_end,
                momentKey="surprise_reaction",
                parentStart=max(0, short_start - (short_end - short_start)),
                parentEnd=short_end + (short_end - short_start),
                evidenceSegmentIds=["seg_000004", "seg_000005"],
                heatmapSegmentIds=[],
                reason="短い反応と結論があります。",
                confidence=0.87,
                riskFlags=[],
            ),
        ],
        warnings=[],
    )


def _topic_response(request):
    return CodexTopicSelectionResponse(
        version=1,
        promptVersion=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        jobId=request.job_id,
        requestId=request.request_id,
        inputHash=request.input_hash,
        threadId="thread_local",
        selectedTopics=[
            CodexTopicChoice(
                selectionId="topic_normal_1",
                type="normal",
                topicKey="main_explanation",
                topicBlockIds=[request.topic_blocks[0].id],
                reason="主要テーマが完結しています。",
                confidence=0.91,
            ),
            CodexTopicChoice(
                selectionId="topic_short_1",
                type="short",
                topicKey="reaction_topic",
                topicBlockIds=[request.topic_blocks[-1].id],
                reason="短い反応と結論があります。",
                confidence=0.87,
            ),
        ],
        warnings=[],
    )


class _FakeClock:
    def __init__(self) -> None:
        self.monotonic_value = 0.0
        self.wall_time_value = 1_800_000_000.0

    def monotonic(self) -> float:
        return self.monotonic_value

    def wall_time(self) -> float:
        return self.wall_time_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_time_value += seconds

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)


def _write_bridge_status(
    bridge: CodexInitialSelectionSharedFileBridge,
    clock: _FakeClock,
    *,
    state: str = "ready",
    request_id: str | None = None,
    request_state: str | None = None,
    updated_at: float | None = None,
    error_code: str | None = None,
) -> None:
    path = bridge.status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 1,
        "state": state,
        "pid": 123,
        "updatedAt": datetime.fromtimestamp(
            clock.wall_time() if updated_at is None else updated_at,
            UTC,
        )
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if request_id is not None:
        payload["requestId"] = request_id
    if request_state is not None:
        payload["requestState"] = request_state
    if error_code is not None:
        payload["errorCode"] = error_code
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_host_response(
    bridge: CodexInitialSelectionSharedFileBridge,
    request,
) -> None:
    response_path = bridge.response_path(request.request_id)
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "requestId": request.request_id,
                "state": "completed",
                "threadId": "thread_local",
                "output": _response(request).model_dump(by_alias=True, mode="json"),
                "error": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_request_hash_is_stable_and_covers_transcript() -> None:
    request = _request()
    assert request.input_hash == compute_codex_initial_selection_input_hash(request)
    assert request.constraints.normal_candidate_count == 1
    assert request.constraints.short_candidate_count == 3

    changed = build_codex_initial_selection_request(
        job_id="job_codex",
        transcript_segments=[*_transcript()[:-1], TranscriptSegment(start=130, end=160, text="変更後")],
        heatmap_segments=[],
        video_duration=200,
        settings=_settings(),
    )
    changed_with_same_request_id = changed.model_copy(
        update={
            "request_id": request.request_id,
            "input_hash": "0" * 64,
        }
    )
    assert compute_codex_initial_selection_input_hash(changed_with_same_request_id) != request.input_hash

    schema = codex_initial_selection_response_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    proposal_schema = schema["$defs"]["CodexClipProposal"]
    assert proposal_schema["additionalProperties"] is False
    assert set(proposal_schema["required"]) == set(proposal_schema["properties"])
    assert {
        "momentKey",
        "parentStart",
        "parentEnd",
    }.issubset(proposal_schema["required"])


def test_short_candidate_count_is_tripled_and_capped() -> None:
    assert _request(settings=_settings(shortCount=3)).constraints.short_candidate_count == 9
    assert _request(settings=_settings(shortCount=24)).constraints.short_candidate_count == 24


def test_normal_candidate_count_covers_active_duration_bands_and_is_capped() -> None:
    assert (
        _request(
            settings=_settings(
                normalClipCount=2,
                normalMaxDuration=600,
            )
        ).constraints.normal_candidate_count
        == 6
    )
    assert (
        _request(
            settings=_settings(
                normalClipCount=24,
                normalMaxDuration=600,
            )
        ).constraints.normal_candidate_count
        == 24
    )


def test_duration_bands_are_constraints_not_single_target_lengths() -> None:
    request = _request(
        settings=_settings(
            normalMinDuration=90,
            normalMaxDuration=600,
            shortMinDuration=20,
            shortMaxDuration=75,
        )
    )

    assert [
        (band.minimum, band.maximum)
        for band in request.constraints.normal.duration_bands
    ] == [(90, 180), (180, 300), (300, 600)]
    assert [
        (band.minimum, band.maximum)
        for band in request.constraints.short.duration_bands
    ] == [(20, 35), (35, 50), (50, 75)]


def test_local_topic_blocks_split_at_semantic_boundary() -> None:
    source_request = build_codex_initial_selection_request(
        job_id="job_semantic_blocks",
        transcript_segments=[
            TranscriptSegment(start=0, end=30, text="前提を説明します。"),
            TranscriptSegment(start=30, end=60, text="まとめると、最初の話題はここまでです。"),
            TranscriptSegment(start=60, end=90, text="次の疑問はなぜ起きるのでしょう？"),
            TranscriptSegment(start=90, end=120, text="次の話題の答えを説明します。"),
        ],
        heatmap_segments=[],
        video_duration=120,
        settings=_settings(),
    )

    blocks = build_local_topic_blocks(source_request)

    assert len(blocks) == 2
    assert (blocks[0].start, blocks[0].end) == (0, 60)
    assert (blocks[1].start, blocks[1].end) == (60, 120)
    assert blocks[1].question_cue is True


def test_topic_selection_requires_contiguous_blocks_and_drops_normal_overlap() -> None:
    source_request = _request(
        settings=_settings(
            normalClipCount=3,
            shortCount=0,
        )
    )
    topic_request = CodexTopicSelectionRequest(
        jobId=source_request.job_id,
        requestId="a" * 32,
        inputHash="0" * 64,
        sourceDuration=300,
        constraints=source_request.constraints,
        topicBlocks=[
            CodexTopicBlockInput(
                id="topic_000001",
                start=0,
                end=100,
                summary="最初の主要話題",
                segmentCount=1,
                questionCue=True,
                silenceBefore=0,
                silenceAfter=0,
                popularity=None,
            ),
            CodexTopicBlockInput(
                id="topic_000002",
                start=50,
                end=150,
                summary="半分以上重なる別話題",
                segmentCount=1,
                questionCue=True,
                silenceBefore=0,
                silenceAfter=0,
                popularity=None,
            ),
            CodexTopicBlockInput(
                id="topic_000003",
                start=160,
                end=260,
                summary="重ならない主要話題",
                segmentCount=1,
                questionCue=True,
                silenceBefore=0,
                silenceAfter=0,
                popularity=None,
            ),
        ],
    )
    topic_request = topic_request.model_copy(
        update={
            "input_hash": compute_codex_topic_selection_input_hash(topic_request)
        }
    )
    topic_response = CodexTopicSelectionResponse(
        version=1,
        promptVersion=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        jobId=topic_request.job_id,
        requestId=topic_request.request_id,
        inputHash=topic_request.input_hash,
        threadId="thread_topics",
        selectedTopics=[
            CodexTopicChoice(
                selectionId="normal_first",
                type="normal",
                topicKey="first_topic",
                topicBlockIds=["topic_000001"],
                reason="主要話題です。",
                confidence=0.95,
            ),
            CodexTopicChoice(
                selectionId="normal_reused",
                type="normal",
                topicKey="reused_topic",
                topicBlockIds=["topic_000001"],
                reason="同じブロックの再利用です。",
                confidence=0.94,
            ),
            CodexTopicChoice(
                selectionId="normal_overlapping",
                type="normal",
                topicKey="overlapping_topic",
                topicBlockIds=["topic_000002"],
                reason="範囲が半分以上重なります。",
                confidence=0.93,
            ),
            CodexTopicChoice(
                selectionId="normal_distinct",
                type="normal",
                topicKey="distinct_topic",
                topicBlockIds=["topic_000003"],
                reason="独立した主要話題です。",
                confidence=0.92,
            ),
        ],
        warnings=[],
    )

    selected = _validate_topic_selection_response(topic_request, topic_response)

    assert [item.selection_id for item in selected] == [
        "normal_first",
        "normal_distinct",
    ]

    non_contiguous = topic_response.model_copy(
        update={
            "selected_topics": [
                CodexTopicChoice(
                    selectionId="normal_non_contiguous",
                    type="normal",
                    topicKey="non_contiguous_topic",
                    topicBlockIds=["topic_000001", "topic_000003"],
                    reason="離れたブロックをまとめた不正候補です。",
                    confidence=0.95,
                )
            ]
        }
    )
    with pytest.raises(CodexInitialSelectionError) as error:
        _validate_topic_selection_response(topic_request, non_contiguous)
    assert error.value.code == "codex_topic_selection_block_not_contiguous"


def test_normal_selection_drops_duplicate_topic_keys_without_backfill() -> None:
    request = _request(
        settings=_settings(
            normalClipCount=2,
            shortCount=0,
            normalMinDuration=20,
            normalMaxDuration=120,
        )
    )
    response = _response(request)
    first = response.selected_clips[0]
    duplicate_topic = first.model_copy(
        update={
            "proposal_id": "normal_2",
            "start": 90,
            "end": 160,
            "evidence_segment_ids": ["seg_000004", "seg_000006"],
            "confidence": 0.89,
        }
    )
    only_duplicate_normals = response.model_copy(
        update={"selected_clips": [first, duplicate_topic]}
    )

    result = convert_codex_initial_selection_response(
        request,
        only_duplicate_normals,
    )

    assert len(result.selection.normal_clips) == 1
    assert result.selection.normal_clips[0].topic_key == "main_explanation"
    assert result.summary["selectedNormalCount"] == 1


def test_normal_selection_caps_time_overlap_at_half_even_when_setting_is_looser() -> None:
    request = _request(
        settings=_settings(
            normalClipCount=2,
            shortCount=0,
            normalMinDuration=20,
            normalMaxDuration=120,
            maxOverlapRatio=0.8,
        )
    )
    response = _response(request)
    first = response.selected_clips[0]
    overlapping_topic = first.model_copy(
        update={
            "proposal_id": "normal_2",
            "topic_key": "different_explanation",
            "start": 40,
            "end": 130,
            "evidence_segment_ids": ["seg_000002", "seg_000005"],
            "confidence": 0.89,
        }
    )

    result = convert_codex_initial_selection_response(
        request,
        response.model_copy(
            update={"selected_clips": [first, overlapping_topic]}
        ),
    )

    assert len(result.selection.normal_clips) == 1
    assert result.selection.normal_clips[0].topic_key == "main_explanation"


def test_two_stage_contract_bounds_dense_transcript_and_keeps_source_ids() -> None:
    transcript = [
        TranscriptSegment(
            start=index * 10.0,
            end=(index + 1) * 10.0,
            text=(f"話題{index}の質問、説明、具体例、結論。" + "字" * 1760),
        )
        for index in range(300)
    ]
    source_request = build_codex_initial_selection_request(
        job_id="job_dense",
        transcript_segments=transcript,
        heatmap_segments=[],
        video_duration=3000,
        settings=_settings(
            normalClipCount=1,
            shortCount=1,
            normalMaxDuration=600,
            shortMaxDuration=75,
        ),
    )
    assert sum(len(item.text) for item in source_request.transcript) > 510_000

    topic_request = build_codex_topic_selection_request(source_request)
    topic_envelope = _topic_bridge_envelope(topic_request, thread_id=None)
    assert len(topic_request.topic_blocks) <= 180
    assert sum(len(item.summary) for item in topic_request.topic_blocks) <= 180 * 600
    assert len(topic_envelope.prompt) <= MAX_TOPIC_SELECTION_PROMPT_CHARS
    assert '"transcript"' not in topic_envelope.prompt

    topic_response = CodexTopicSelectionResponse(
        version=1,
        promptVersion=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        jobId=topic_request.job_id,
        requestId=topic_request.request_id,
        inputHash=topic_request.input_hash,
        threadId="thread_dense",
        selectedTopics=[
            CodexTopicChoice(
                selectionId="dense_normal",
                type="normal",
                topicKey="dense_main_topic",
                topicBlockIds=[item.id for item in topic_request.topic_blocks[:3]],
                reason="主要な説明話題です。",
                confidence=0.9,
            ),
            CodexTopicChoice(
                selectionId="dense_short",
                type="short",
                topicKey="dense_reaction",
                topicBlockIds=[topic_request.topic_blocks[-1].id],
                reason="短い反応があります。",
                confidence=0.8,
            ),
        ],
        warnings=[],
    )
    refinement = build_codex_boundary_refinement_request(
        source_request,
        topic_request,
        topic_response,
    )
    assert refinement is not None
    assert sum(len(item.text) for item in refinement.transcript) <= MAX_REFINEMENT_TRANSCRIPT_CHARS
    assert {item.id for item in refinement.transcript}.issubset(
        {item.id for item in source_request.transcript}
    )
    assert len(_bridge_envelope(refinement, thread_id="thread_dense").prompt) <= (
        MAX_REFINEMENT_PROMPT_CHARS
    )


def test_single_normal_topic_refinement_window_can_cover_max_duration() -> None:
    source_request = build_codex_initial_selection_request(
        job_id="job_wide_window",
        transcript_segments=[
            TranscriptSegment(
                start=index * 10,
                end=(index + 1) * 10,
                text=f"元字幕{index}の説明です。",
            )
            for index in range(100)
        ],
        heatmap_segments=[],
        video_duration=1000,
        settings=_settings(
            normalClipCount=1,
            shortCount=0,
            normalMinDuration=90,
            normalMaxDuration=600,
        ),
    )
    topic_request = build_codex_topic_selection_request(source_request)
    selected_block = topic_request.topic_blocks[len(topic_request.topic_blocks) // 2]
    topic_response = CodexTopicSelectionResponse(
        version=1,
        promptVersion=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        jobId=topic_request.job_id,
        requestId=topic_request.request_id,
        inputHash=topic_request.input_hash,
        threadId="thread_wide",
        selectedTopics=[
            CodexTopicChoice(
                selectionId="wide_normal",
                type="normal",
                topicKey="wide_explanation",
                topicBlockIds=[selected_block.id],
                reason="長い説明を自然な境界まで確認します。",
                confidence=0.9,
            )
        ],
        warnings=[],
    )

    refinement = build_codex_boundary_refinement_request(
        source_request,
        topic_request,
        topic_response,
    )

    assert refinement is not None
    selected_topic = refinement.selected_topics[0]
    assert selected_topic.window_end - selected_topic.window_start == 600
    assert refinement.transcript[0].start <= selected_topic.window_start
    assert refinement.transcript[-1].end >= selected_topic.window_end
    assert all(
        item.end > selected_topic.window_start
        and item.start < selected_topic.window_end
        for item in refinement.transcript
    )

    proposal_response = CodexInitialSelectionResponse(
        version=1,
        promptVersion=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        jobId=refinement.job_id,
        requestId=refinement.request_id,
        inputHash=refinement.input_hash,
        threadId="thread_wide",
        selectedClips=[
            CodexClipProposal(
                proposalId="wide_normal_1",
                type="normal",
                topicKey="wide_explanation",
                start=selected_topic.window_start,
                end=selected_topic.window_end,
                momentKey=None,
                parentStart=None,
                parentEnd=None,
                evidenceSegmentIds=[refinement.transcript[0].id],
                heatmapSegmentIds=[],
                reason="最大尺でも元字幕範囲内です。",
                confidence=0.9,
                riskFlags=[],
            )
        ],
        warnings=[],
    )
    result = convert_codex_initial_selection_response(
        refinement,
        proposal_response,
    )
    assert len(result.selection.normal_clips) == 1
    assert result.selection.normal_clips[0].duration == 600


def test_valid_response_converts_to_existing_candidate_selection() -> None:
    request = _request()
    result = convert_codex_initial_selection_response(request, _response(request))

    assert len(result.selection.normal_clips) == 1
    assert len(result.selection.shorts) == 1
    assert result.selection.normal_clips[0].selection_reason == "codex_direct"
    assert result.selection.normal_clips[0].final_score == 91
    assert result.selection.shorts[0].transcript_text
    assert result.selection.shorts[0].moment_key == "surprise_reaction"
    assert result.selection.shorts[0].parent_start == 80
    assert result.selection.shorts[0].parent_end == 140
    assert result.selection.shorts[0].evidence_segment_ids == [
        "seg_000004",
        "seg_000005",
    ]
    assert result.summary == {
        "provider": "codex",
        "phase": "initial",
        "status": "completed",
        "fallbackUsed": False,
        "error": None,
        "requestedNormalCount": 1,
        "requestedShortCount": 1,
        "selectedNormalCount": 1,
        "selectedShortCount": 1,
        "droppedNormalCandidates": [],
        "droppedShortCandidates": [],
        "threadId": "thread_local",
        "promptVersion": CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        "requestId": request.request_id,
        "attemptCount": 1,
        "hostErrorCode": None,
        "topicBlockCount": 0,
        "topicSummaryCharCount": 0,
        "refinementTranscriptSegmentCount": 6,
        "refinementTranscriptCharCount": sum(len(item.text) for item in request.transcript),
        "selectionStage": None,
    }


def test_response_allows_quality_shortfall_but_rejects_hash_and_unknown_evidence() -> None:
    request = _request()
    wrong_count = _response(request).model_copy(update={"selected_clips": _response(request).selected_clips[1:]})
    shortfall = convert_codex_initial_selection_response(request, wrong_count)
    assert shortfall.selection.normal_clips == []
    assert len(shortfall.selection.shorts) == 1

    wrong_hash = _response(request).model_copy(update={"input_hash": "f" * 64})
    with pytest.raises(CodexInitialSelectionError, match="更新") as hash_error:
        convert_codex_initial_selection_response(request, wrong_hash)
    assert hash_error.value.code == "codex_initial_selection_hash_mismatch"

    bad_clips = list(_response(request).selected_clips)
    bad_clips[0] = bad_clips[0].model_copy(
        update={"evidence_segment_ids": ["seg_999999"]}
    )
    partially_valid = convert_codex_initial_selection_response(
        request,
        _response(request).model_copy(update={"selected_clips": bad_clips}),
    )
    assert partially_valid.selection.normal_clips == []
    assert len(partially_valid.selection.shorts) == 1
    assert partially_valid.summary["droppedNormalCandidates"] == [
        {
            "proposalId": "normal_1",
            "code": "codex_initial_selection_evidence_unknown",
            "message": "Codex初期選定の字幕根拠が入力に存在しません。",
        }
    ]


def test_invalid_normal_proposal_is_dropped_while_valid_normal_is_retained() -> None:
    request = _request(
        settings=_settings(
            normalClipCount=1,
            shortCount=0,
            normalMinDuration=20,
            normalMaxDuration=120,
        )
    )
    response = _response(request)
    invalid_normal = response.selected_clips[0].model_copy(
        update={
            "evidence_segment_ids": ["seg_999999"],
            "confidence": 0.99,
        }
    )
    valid_normal = response.selected_clips[0].model_copy(
        update={
            "proposal_id": "normal_valid_alternate",
            "topic_key": "closing_explanation",
            "start": 90,
            "end": 160,
            "evidence_segment_ids": ["seg_000004", "seg_000006"],
            "confidence": 0.85,
        }
    )

    result = convert_codex_initial_selection_response(
        request,
        response.model_copy(
            update={"selected_clips": [invalid_normal, valid_normal]}
        ),
    )

    assert [item.topic_key for item in result.selection.normal_clips] == [
        "closing_explanation"
    ]
    assert [item.proposal_id for item in result.proposals] == [
        "normal_valid_alternate"
    ]
    assert result.dropped_normal_candidates[0].code == (
        "codex_initial_selection_evidence_unknown"
    )


def test_strict_quality_allows_fewer_clips_and_filters_low_confidence() -> None:
    request = _request(settings=_settings(selectionPolicy="strict_quality"))
    response = _response(request)
    normal = response.selected_clips[0]

    fewer = convert_codex_initial_selection_response(
        request,
        response.model_copy(update={"selected_clips": [normal]}),
    )
    assert len(fewer.selection.normal_clips) == 1
    assert fewer.selection.shorts == []

    filtered = convert_codex_initial_selection_response(
        request,
        response.model_copy(update={"selected_clips": [normal.model_copy(update={"confidence": 0.59})]}),
    )
    assert filtered.selection.normal_clips == []
    assert filtered.selection.shorts == []


def test_duration_band_candidates_remain_in_pool_without_forcing_final_spread() -> None:
    request = build_codex_initial_selection_request(
        job_id="job_duration_band_pool",
        transcript_segments=[
            TranscriptSegment(
                start=index * 5,
                end=(index + 1) * 5,
                text=f"区間{index}の発話です。",
            )
            for index in range(200)
        ],
        heatmap_segments=[],
        video_duration=1000,
        settings=_settings(
            normalClipCount=1,
            shortCount=1,
            normalMinDuration=90,
            normalMaxDuration=600,
            shortMinDuration=20,
            shortMaxDuration=75,
        ),
    )
    proposals = [
        CodexClipProposal(
            proposalId="normal_band_1a",
            type="normal",
            topicKey="normal_topic_1a",
            start=0,
            end=100,
            momentKey=None,
            parentStart=None,
            parentEnd=None,
            evidenceSegmentIds=["seg_000001"],
            heatmapSegmentIds=[],
            reason="短い尺帯の高品質候補です。",
            confidence=0.99,
            riskFlags=[],
        ),
        CodexClipProposal(
            proposalId="normal_band_1b",
            type="normal",
            topicKey="normal_topic_1b",
            start=100,
            end=200,
            momentKey=None,
            parentStart=None,
            parentEnd=None,
            evidenceSegmentIds=["seg_000021"],
            heatmapSegmentIds=[],
            reason="同じ尺帯の別の高品質候補です。",
            confidence=0.98,
            riskFlags=[],
        ),
        CodexClipProposal(
            proposalId="normal_band_2",
            type="normal",
            topicKey="normal_topic_2",
            start=200,
            end=400,
            momentKey=None,
            parentStart=None,
            parentEnd=None,
            evidenceSegmentIds=["seg_000041"],
            heatmapSegmentIds=[],
            reason="中間尺帯の候補です。",
            confidence=0.9,
            riskFlags=[],
        ),
        CodexClipProposal(
            proposalId="normal_band_3",
            type="normal",
            topicKey="normal_topic_3",
            start=400,
            end=800,
            momentKey=None,
            parentStart=None,
            parentEnd=None,
            evidenceSegmentIds=["seg_000081"],
            heatmapSegmentIds=[],
            reason="長い尺帯の候補です。",
            confidence=0.8,
            riskFlags=[],
        ),
        CodexClipProposal(
            proposalId="short_band_1a",
            type="short",
            topicKey="short_topic_1a",
            start=800,
            end=825,
            momentKey="short_moment_1a",
            parentStart=795,
            parentEnd=832.5,
            evidenceSegmentIds=["seg_000161"],
            heatmapSegmentIds=[],
            reason="短い尺帯の高品質Shortです。",
            confidence=0.99,
            riskFlags=[],
        ),
        CodexClipProposal(
            proposalId="short_band_1b",
            type="short",
            topicKey="short_topic_1b",
            start=830,
            end=860,
            momentKey="short_moment_1b",
            parentStart=825,
            parentEnd=870,
            evidenceSegmentIds=["seg_000167"],
            heatmapSegmentIds=[],
            reason="同じ尺帯の別の高品質Shortです。",
            confidence=0.98,
            riskFlags=[],
        ),
        CodexClipProposal(
            proposalId="short_band_2",
            type="short",
            topicKey="short_topic_2",
            start=870,
            end=910,
            momentKey="short_moment_2",
            parentStart=860,
            parentEnd=920,
            evidenceSegmentIds=["seg_000175"],
            heatmapSegmentIds=[],
            reason="中間尺帯のShortです。",
            confidence=0.9,
            riskFlags=[],
        ),
        CodexClipProposal(
            proposalId="short_band_3",
            type="short",
            topicKey="short_topic_3",
            start=920,
            end=980,
            momentKey="short_moment_3",
            parentStart=910,
            parentEnd=1000,
            evidenceSegmentIds=["seg_000185"],
            heatmapSegmentIds=[],
            reason="長い尺帯のShortです。",
            confidence=0.8,
            riskFlags=[],
        ),
    ]
    response = CodexInitialSelectionResponse(
        version=1,
        promptVersion=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        jobId=request.job_id,
        requestId=request.request_id,
        inputHash=request.input_hash,
        threadId="thread_duration_band_pool",
        selectedClips=proposals,
        warnings=[],
    )

    result = convert_codex_initial_selection_response(request, response)

    assert sorted(
        item.duration for item in result.candidates if item.type == "normal"
    ) == [100, 200, 400]
    assert sorted(
        item.duration for item in result.candidates if item.type == "short"
    ) == [25, 40, 60]
    assert [item.duration for item in result.selection.normal_clips] == [100]
    assert [item.duration for item in result.selection.shorts] == [25]


def test_job_settings_reject_clip_counts_above_ui_limits() -> None:
    with pytest.raises(ValidationError):
        JobSettings(normalClipCount=13, shortCount=0)
    with pytest.raises(ValidationError):
        JobSettings(normalClipCount=0, shortCount=25)


def test_heatmap_reference_does_not_require_positive_overlap_or_data() -> None:
    heatmap = [HeatmapSegment(start_time=40, end_time=55, value=0.9)]
    request = _request(
        settings=_settings(heatmapIntervalMode=True),
        heatmap=heatmap,
    )
    response = _response(request, short_start=100, short_end=120)
    proposals = list(response.selected_clips)
    proposals[0] = proposals[0].model_copy(update={"heatmap_segment_ids": ["heat_000001"]})
    proposals[1] = proposals[1].model_copy(update={"heatmap_segment_ids": ["heat_000001"]})

    result = convert_codex_initial_selection_response(
        request,
        response.model_copy(update={"selected_clips": proposals}),
    )
    assert len(result.selection.shorts) == 1
    assert result.summary["droppedShortCandidates"] == []
    assert _request(
        settings=_settings(heatmapIntervalMode=True),
        heatmap=[],
    ).heatmap == []


def test_heatmap_reference_annotates_without_owning_candidate_boundaries() -> None:
    request = _request(
        settings=_settings(heatmapIntervalMode=True),
        heatmap=[
            HeatmapSegment(start_time=40, end_time=55, value=0.9),
            HeatmapSegment(start_time=105, end_time=115, value=0.8),
        ],
    )
    response = _response(request)
    proposals = list(response.selected_clips)
    proposals[0] = proposals[0].model_copy(update={"heatmap_segment_ids": ["heat_000001"]})
    proposals[1] = proposals[1].model_copy(update={"heatmap_segment_ids": ["heat_000002"]})

    result = convert_codex_initial_selection_response(
        request,
        response.model_copy(update={"selected_clips": proposals}),
    )

    assert all(item.generation_source is None for item in result.candidates)
    assert all(item.heatmap_direct_score is None for item in result.candidates)
    assert all(item.heatmap_seed_value is None for item in result.candidates)
    assert result.candidates[0].heatmap_score == 9
    assert result.candidates[1].heatmap_score == 8


def test_heatmap_reference_is_opt_in_clamped_and_drops_outside_ranges() -> None:
    heatmap = [
        HeatmapSegment(start_time=190, end_time=201, value=0.9),
        HeatmapSegment(start_time=210, end_time=220, value=0.8),
    ]

    disabled = _request(
        settings=_settings(heatmapIntervalMode=False),
        heatmap=heatmap,
    )
    enabled = _request(
        settings=_settings(heatmapIntervalMode=True),
        heatmap=heatmap,
    )

    assert disabled.heatmap == []
    assert len(enabled.heatmap) == 1
    assert enabled.heatmap[0].start == 190
    assert enabled.heatmap[0].end == 200


def test_cross_type_overlap_only_applies_when_enabled() -> None:
    request = _request()
    overlapping = _response(request, short_start=50, short_end=70)
    proposals = list(overlapping.selected_clips)
    proposals[1] = proposals[1].model_copy(update={"evidence_segment_ids": ["seg_000002", "seg_000003"]})
    overlapping = overlapping.model_copy(update={"selected_clips": proposals})
    assert convert_codex_initial_selection_response(request, overlapping).candidates

    strict_request = _request(settings=_settings(crossTypeOverlapDedupe=True))
    strict_response = overlapping.model_copy(
        update={
            "request_id": strict_request.request_id,
            "input_hash": strict_request.input_hash,
        }
    )
    strict_result = convert_codex_initial_selection_response(strict_request, strict_response)
    assert strict_result.selection.shorts == []
    assert len(strict_result.candidates) == 2


def test_short_pool_keeps_all_candidates_and_initial_selection_dedupes_moment_key() -> None:
    request = _request()
    response = _response(request)
    first_short = response.selected_clips[1]
    duplicate_moment = CodexClipProposal(
        proposalId="short_2",
        type="short",
        topicKey="reaction_topic",
        start=105,
        end=125,
        momentKey="surprise_reaction",
        parentStart=95,
        parentEnd=135,
        evidenceSegmentIds=["seg_000004", "seg_000005"],
        heatmapSegmentIds=[],
        reason="同じ見せ場の時刻違い候補です。",
        confidence=0.95,
        riskFlags=[],
    )
    distinct_moment = CodexClipProposal(
        proposalId="short_3",
        type="short",
        topicKey="closing_topic",
        start=130,
        end=150,
        momentKey="closing_explanation",
        parentStart=120,
        parentEnd=160,
        evidenceSegmentIds=["seg_000006"],
        heatmapSegmentIds=[],
        reason="別の話題の結論です。",
        confidence=0.9,
        riskFlags=[],
    )
    pooled_response = response.model_copy(
        update={
            "selected_clips": [
                response.selected_clips[0],
                first_short,
                duplicate_moment,
                distinct_moment,
            ]
        }
    )

    result = convert_codex_initial_selection_response(request, pooled_response)

    assert len(result.candidates) == 4
    assert len(result.proposals) == 4
    assert result.duplicate_short_moment_keys == ["surprise_reaction"]
    assert len(result.selection.shorts) == 1
    assert result.selection.shorts[0].start == 105
    assert result.summary["selectedShortCount"] == 1


def test_invalid_short_alternate_is_dropped_and_remaining_pool_fills_selection() -> None:
    request = _request(settings=_settings(shortCount=2))
    response = _response(request)
    invalid_alternate = CodexClipProposal(
        proposalId="short_invalid_evidence",
        type="short",
        topicKey="invalid_topic",
        start=90,
        end=110,
        momentKey="invalid_alternate",
        parentStart=80,
        parentEnd=120,
        evidenceSegmentIds=["seg_999999"],
        heatmapSegmentIds=[],
        reason="存在しない字幕を参照した不正候補です。",
        confidence=0.99,
        riskFlags=[],
    )
    valid_alternate = CodexClipProposal(
        proposalId="short_valid_alternate",
        type="short",
        topicKey="closing_topic",
        start=130,
        end=150,
        momentKey="closing_explanation",
        parentStart=120,
        parentEnd=160,
        evidenceSegmentIds=["seg_000006"],
        heatmapSegmentIds=[],
        reason="別の話題の結論です。",
        confidence=0.85,
        riskFlags=[],
    )
    pooled_response = response.model_copy(
        update={
            "selected_clips": [
                response.selected_clips[0],
                response.selected_clips[1],
                invalid_alternate,
                valid_alternate,
            ]
        }
    )

    result = convert_codex_initial_selection_response(request, pooled_response)

    assert [item.proposal_id for item in result.proposals] == [
        "normal_1",
        "short_1",
        "short_valid_alternate",
    ]
    assert len(result.candidates) == 3
    assert len(result.selection.shorts) == 2
    assert result.summary["selectedShortCount"] == 2
    assert result.summary["droppedShortCandidates"] == [
        {
            "proposalId": "short_invalid_evidence",
            "code": "codex_initial_selection_evidence_unknown",
            "message": "Codex初期選定の字幕根拠が入力に存在しません。",
        }
    ]


def test_short_parent_range_is_required_contains_final_and_stays_in_source() -> None:
    request = _request()
    response = _response(request)
    missing_parent = response.selected_clips[1].model_copy(
        update={"moment_key": None, "parent_start": None, "parent_end": None}
    )
    result = convert_codex_initial_selection_response(
        request,
        response.model_copy(
            update={"selected_clips": [response.selected_clips[0], missing_parent]}
        ),
    )
    assert result.selection.shorts == []
    assert result.dropped_short_candidates[0].code == (
        "codex_initial_selection_short_metadata_missing"
    )

    parent_not_containing = response.selected_clips[1].model_copy(
        update={"parent_start": 90, "parent_end": 115}
    )
    result = convert_codex_initial_selection_response(
        request,
        response.model_copy(
            update={
                "selected_clips": [response.selected_clips[0], parent_not_containing]
            }
        ),
    )
    assert result.dropped_short_candidates[0].code == (
        "codex_initial_selection_parent_not_containing_final"
    )

    outside_source = response.selected_clips[1].model_copy(
        update={
            "start": 150,
            "end": 170,
            "parent_start": 145,
            "parent_end": 205,
            "evidence_segment_ids": ["seg_000006"],
        }
    )
    result = convert_codex_initial_selection_response(
        request,
        response.model_copy(
            update={"selected_clips": [response.selected_clips[0], outside_source]}
        ),
    )
    assert result.dropped_short_candidates[0].code == (
        "codex_initial_selection_parent_outside_source"
    )


def test_shared_file_bridge_success_writes_contract_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_wait_for_topic_response(
        self,
        request,
        *,
        timeout_seconds,
        poll_seconds,
        heartbeat,
    ):
        del self, timeout_seconds, poll_seconds, heartbeat
        return _topic_response(request)

    def fake_wait_for_response(
        self,
        request,
        *,
        timeout_seconds,
        poll_seconds,
        heartbeat,
    ):
        del self, timeout_seconds, poll_seconds, heartbeat
        return _response(request)

    monkeypatch.setattr(
        CodexInitialSelectionSharedFileBridge,
        "wait_for_response",
        fake_wait_for_response,
    )
    monkeypatch.setattr(
        CodexInitialSelectionSharedFileBridge,
        "wait_for_topic_response",
        fake_wait_for_topic_response,
    )
    heartbeat: list[dict[str, object]] = []

    result = request_codex_initial_selection(
        "job_codex",
        tmp_path,
        _transcript(),
        [],
        200,
        _settings(),
        heartbeat=heartbeat.append,
    )

    request_files = list((tmp_path / "codex_bridge" / "requests").glob("*.json"))
    assert len(request_files) == 2
    request_payloads = {
        payload["task"]: payload
        for path in request_files
        for payload in [json.loads(path.read_text(encoding="utf-8"))]
    }
    topic_payload = request_payloads["initial_clip_topic_selection"]
    request_payload = request_payloads["initial_clip_selection"]
    assert request_payload["schemaVersion"] == 1
    assert request_payload["task"] == "initial_clip_selection"
    assert request_payload["images"] == []
    assert request_payload["threadScope"] == "job_codex"
    assert topic_payload["threadId"] is None
    assert request_payload["threadId"] == "thread_local"
    assert request_payload["promptVersion"] == CODEX_INITIAL_SELECTION_PROMPT_VERSION
    assert request_payload["attempt"] == 1
    assert '"jobId":"job_codex"' in request_payload["prompt"]
    assert '"normalCandidateCount":1' in request_payload["prompt"]
    assert '"shortCandidateCount":3' in request_payload["prompt"]
    assert '"selectedTopics"' in request_payload["prompt"]
    assert '"topicBlocks"' in topic_payload["prompt"]
    assert '"transcript"' not in topic_payload["prompt"]
    assert "名前読み、連続お礼、スパチャ読みだけ" in topic_payload["prompt"]
    assert "同じtopicBlockIdを再利用せず" in topic_payload["prompt"]
    assert "候補プール全体に各帯から少なくとも1件" in request_payload["prompt"]
    assert "通常はnormalCandidateCount以下" in request_payload["prompt"]
    assert "人気度は候補の優先順位を考える参考情報にだけ" in request_payload["prompt"]
    assert "人気区間との重なりを必須条件にせず" in request_payload["prompt"]
    assert "momentKey" in request_payload["prompt"]
    assert "parentStart/parentEnd" in request_payload["prompt"]
    assert request_payload["responseSchema"]["additionalProperties"] is False
    assert result.summary["status"] == "completed"
    assert result.summary["topicBlockCount"] > 0
    assert result.summary["topicSummaryCharCount"] > 0
    assert result.summary["refinementTranscriptSegmentCount"] > 0
    assert result.summary["selectionStage"] == "boundary_refinement"
    assert not codex_initial_selection_summary_output_path(tmp_path).exists()
    assert [item["status"] for item in heartbeat] == ["completed"]


def test_shared_file_bridge_retries_once_with_new_request_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_request_ids: list[str] = []

    def fake_wait_for_topic_response(
        self,
        request,
        *,
        timeout_seconds,
        poll_seconds,
        heartbeat,
    ):
        del self, timeout_seconds, poll_seconds, heartbeat
        return _topic_response(request)

    def fake_wait_for_response(
        self,
        request,
        *,
        timeout_seconds,
        poll_seconds,
        heartbeat,
    ):
        del self, timeout_seconds, poll_seconds, heartbeat
        observed_request_ids.append(request.request_id)
        if len(observed_request_ids) == 1:
            raise CodexInitialSelectionError(
                "codex_initial_selection_host_failed",
                "Codex初期選定を実行できませんでした。",
                host_error_code="codex_failed",
            )
        return _response(request)

    monkeypatch.setattr(
        CodexInitialSelectionSharedFileBridge,
        "wait_for_response",
        fake_wait_for_response,
    )
    monkeypatch.setattr(
        CodexInitialSelectionSharedFileBridge,
        "wait_for_topic_response",
        fake_wait_for_topic_response,
    )

    result = request_codex_initial_selection(
        "job_codex",
        tmp_path,
        _transcript(),
        [],
        200,
        _settings(),
    )

    assert len(set(observed_request_ids)) == 2
    assert result.summary["requestId"] == observed_request_ids[1]
    assert result.summary["attemptCount"] == 2
    request_files = sorted((tmp_path / "codex_bridge" / "requests").glob("*.json"))
    assert len(request_files) == 3
    attempts = sorted(
        json.loads(path.read_text(encoding="utf-8"))["attempt"]
        for path in request_files
    )
    assert attempts == [1, 1, 2]


def test_missing_response_times_out_and_exposes_fallback_summary(tmp_path: Path) -> None:
    heartbeat: list[dict[str, object]] = []
    with pytest.raises(CodexInitialSelectionError, match="時間切れ") as error:
        request_codex_initial_selection(
            "job_codex",
            tmp_path,
            _transcript(),
            [],
            200,
            _settings(
                codexSelectionTimeoutSeconds=0.01,
                codexSelectionPollSeconds=0.01,
            ),
            heartbeat=heartbeat.append,
        )

    assert error.value.code == "codex_initial_selection_timeout"
    assert heartbeat[0]["status"] == "running"
    fallback = error.value.fallback_summary(
        requested_normal_count=1,
        requested_short_count=1,
    )
    write_codex_initial_selection_summary(
        fallback.model_dump(by_alias=True, mode="json"),
        codex_initial_selection_summary_output_path(tmp_path),
    )
    summary = json.loads(codex_initial_selection_summary_output_path(tmp_path).read_text(encoding="utf-8"))
    assert summary["provider"] == "codex"
    assert summary["status"] == "fallback"
    assert summary["fallbackUsed"] is True
    assert summary["requestId"] == error.value.request_id
    assert summary["attemptCount"] == 2
    assert summary["error"] == {
        "code": "codex_initial_selection_timeout",
        "message": "Codex初期選定の応答待ちが時間切れになりました。",
    }


def test_bridge_without_status_fails_before_the_full_response_timeout(
    tmp_path: Path,
) -> None:
    clock = _FakeClock()
    request = _request()
    bridge = CodexInitialSelectionSharedFileBridge(
        tmp_path,
        sleep_func=clock.sleep,
        monotonic_func=clock.monotonic,
        wall_time_func=clock.wall_time,
        request_claim_grace_seconds=2,
        status_stale_seconds=3,
        unavailable_confirmation_seconds=1,
    )
    bridge.write_request(request)

    with pytest.raises(CodexInitialSelectionError) as error:
        bridge.wait_for_response(request, timeout_seconds=900, poll_seconds=1)

    assert error.value.code == "codex_initial_selection_bridge_unavailable"
    assert clock.monotonic() == 3


def test_bridge_terminal_status_after_request_fails_immediately(tmp_path: Path) -> None:
    clock = _FakeClock()
    request = _request()
    bridge = CodexInitialSelectionSharedFileBridge(
        tmp_path,
        sleep_func=clock.sleep,
        monotonic_func=clock.monotonic,
        wall_time_func=clock.wall_time,
        request_claim_grace_seconds=10,
        status_stale_seconds=3,
        unavailable_confirmation_seconds=0,
    )
    bridge.write_request(request)
    _write_bridge_status(
        bridge,
        clock,
        state="error",
        error_code="codex_login_missing",
    )

    with pytest.raises(CodexInitialSelectionError) as error:
        bridge.wait_for_response(request, timeout_seconds=900, poll_seconds=1)

    assert error.value.code == "codex_initial_selection_bridge_unavailable"
    assert error.value.host_error_code == "codex_login_missing"
    assert clock.monotonic() == 0


@pytest.mark.parametrize(
    ("task_schema_fingerprints", "host_error_code"),
    [
        ({}, "bridge_contract_metadata_missing"),
        (
            {
                "initial_clip_topic_selection": codex_topic_selection_response_schema_sha256(),
                "initial_clip_selection": "0" * 64,
            },
            "response_schema_contract_mismatch",
        ),
    ],
)
def test_bridge_contract_compatibility_is_checked_before_request(
    tmp_path: Path,
    task_schema_fingerprints: dict[str, str],
    host_error_code: str,
) -> None:
    clock = _FakeClock()
    bridge = CodexInitialSelectionSharedFileBridge(tmp_path)
    _write_bridge_status(bridge, clock)
    status = json.loads(bridge.status_path().read_text(encoding="utf-8"))
    status["taskSchemaFingerprints"] = task_schema_fingerprints
    bridge.status_path().write_text(json.dumps(status), encoding="utf-8")

    with pytest.raises(CodexInitialSelectionError) as error:
        bridge.ensure_contract_compatible()

    assert error.value.code == "codex_initial_selection_bridge_contract_mismatch"
    assert error.value.host_error_code == host_error_code


def test_current_bridge_contract_is_accepted(tmp_path: Path) -> None:
    clock = _FakeClock()
    bridge = CodexInitialSelectionSharedFileBridge(tmp_path)
    _write_bridge_status(bridge, clock)
    status = json.loads(bridge.status_path().read_text(encoding="utf-8"))
    status["taskSchemaFingerprints"] = {
        "initial_clip_topic_selection": codex_topic_selection_response_schema_sha256(),
        "initial_clip_selection": codex_initial_selection_response_schema_sha256()
    }
    bridge.status_path().write_text(json.dumps(status), encoding="utf-8")

    bridge.ensure_contract_compatible()


def test_stale_processing_heartbeat_detects_bridge_crash(tmp_path: Path) -> None:
    clock = _FakeClock()
    request = _request()
    bridge = CodexInitialSelectionSharedFileBridge(
        tmp_path,
        sleep_func=clock.sleep,
        monotonic_func=clock.monotonic,
        wall_time_func=clock.wall_time,
        request_claim_grace_seconds=2,
        status_stale_seconds=3,
        unavailable_confirmation_seconds=1,
    )
    bridge.write_request(request)
    _write_bridge_status(
        bridge,
        clock,
        request_id=request.request_id,
        request_state="processing",
    )

    with pytest.raises(CodexInitialSelectionError) as error:
        bridge.wait_for_response(request, timeout_seconds=900, poll_seconds=1)

    assert error.value.code == "codex_initial_selection_bridge_unavailable"
    assert clock.monotonic() == 5


@pytest.mark.parametrize("active_request", ["own", "different"])
def test_fresh_processing_heartbeat_keeps_long_codex_run_alive(
    tmp_path: Path,
    active_request: str,
) -> None:
    clock = _FakeClock()
    request = _request()
    bridge: CodexInitialSelectionSharedFileBridge

    def sleep_and_heartbeat(seconds: float) -> None:
        clock.advance(seconds)
        _write_bridge_status(
            bridge,
            clock,
            request_id=(request.request_id if active_request == "own" else "different-request"),
            request_state="processing",
        )
        if clock.monotonic() == 20:
            _write_host_response(bridge, request)

    bridge = CodexInitialSelectionSharedFileBridge(
        tmp_path,
        sleep_func=sleep_and_heartbeat,
        monotonic_func=clock.monotonic,
        wall_time_func=clock.wall_time,
        request_claim_grace_seconds=2,
        status_stale_seconds=3,
        unavailable_confirmation_seconds=1,
    )
    bridge.write_request(request)
    _write_bridge_status(
        bridge,
        clock,
        request_id=(request.request_id if active_request == "own" else "different-request"),
        request_state="processing",
    )

    response = bridge.wait_for_response(
        request,
        timeout_seconds=100,
        poll_seconds=1,
    )

    assert response.request_id == request.request_id
    assert clock.monotonic() == 20


def test_bridge_rejects_response_from_another_request(tmp_path: Path) -> None:
    request = _request()
    bridge = CodexInitialSelectionSharedFileBridge(tmp_path)
    bridge.write_request(request)
    wrong_response = _response(request).model_copy(update={"request_id": "f" * 32})
    response_path = bridge.response_path(request.request_id)
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "requestId": request.request_id,
                "state": "completed",
                "threadId": "thread_local",
                "output": wrong_response.model_dump(by_alias=True, mode="json"),
                "error": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodexInitialSelectionError, match="request") as error:
        bridge.wait_for_response(request, timeout_seconds=0.1)
    assert error.value.code == "codex_initial_selection_request_mismatch"


def test_bridge_unwraps_host_response_and_injects_thread_id(tmp_path: Path) -> None:
    request = _request()
    bridge = CodexInitialSelectionSharedFileBridge(tmp_path)
    bridge.write_request(request)
    output = _response(request).model_dump(by_alias=True, mode="json")
    output.pop("threadId")
    response_path = bridge.response_path(request.request_id)
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "requestId": request.request_id,
                "state": "completed",
                "threadId": "thread_from_host",
                "output": output,
                "error": None,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    response = bridge.wait_for_response(request, timeout_seconds=0.1)
    assert response.thread_id == "thread_from_host"


def test_bridge_preserves_host_error_code_and_attempt_metadata(tmp_path: Path) -> None:
    request = _request()
    bridge = CodexInitialSelectionSharedFileBridge(tmp_path)
    bridge.write_request(request, attempt=2)
    response_path = bridge.response_path(request.request_id)
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "requestId": request.request_id,
                "state": "failed",
                "threadId": None,
                "output": None,
                "error": {
                    "code": "response_schema_contract_mismatch",
                    "message": "Response schema contract mismatch.",
                },
                "attempt": 2,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodexInitialSelectionError) as error:
        bridge.wait_for_response(request, timeout_seconds=0.1)

    assert error.value.code == "codex_initial_selection_host_failed"
    assert error.value.host_error_code == "response_schema_contract_mismatch"
    assert error.value.request_id == request.request_id
    assert error.value.attempt_count == 2


def test_response_schema_rejects_extra_fields() -> None:
    request = _request()
    payload = _response(request).model_dump(by_alias=True, mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        CodexInitialSelectionResponse.model_validate(payload)
