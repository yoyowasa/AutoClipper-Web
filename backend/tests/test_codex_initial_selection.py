import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.codex_initial_selection import (
    CODEX_INITIAL_SELECTION_PROMPT_VERSION,
    CodexClipProposal,
    CodexInitialSelectionError,
    CodexInitialSelectionResponse,
    CodexInitialSelectionSharedFileBridge,
    build_codex_initial_selection_request,
    codex_initial_selection_response_schema,
    codex_initial_selection_summary_output_path,
    compute_codex_initial_selection_input_hash,
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
        "status": "completed",
        "fallbackUsed": False,
        "error": None,
        "requestedNormalCount": 1,
        "requestedShortCount": 1,
        "selectedNormalCount": 1,
        "selectedShortCount": 1,
        "droppedShortCandidates": [],
        "threadId": "thread_local",
    }


def test_response_rejects_wrong_count_hash_and_unknown_evidence() -> None:
    request = _request()
    wrong_count = _response(request).model_copy(update={"selected_clips": _response(request).selected_clips[1:]})
    with pytest.raises(CodexInitialSelectionError, match="本数") as count_error:
        convert_codex_initial_selection_response(request, wrong_count)
    assert count_error.value.code == "codex_initial_selection_count_mismatch"

    wrong_hash = _response(request).model_copy(update={"input_hash": "f" * 64})
    with pytest.raises(CodexInitialSelectionError, match="更新") as hash_error:
        convert_codex_initial_selection_response(request, wrong_hash)
    assert hash_error.value.code == "codex_initial_selection_hash_mismatch"

    bad_clips = list(_response(request).selected_clips)
    bad_clips[0] = bad_clips[0].model_copy(update={"evidence_segment_ids": ["seg_999999"]})
    with pytest.raises(CodexInitialSelectionError, match="存在") as evidence_error:
        convert_codex_initial_selection_response(
            request,
            _response(request).model_copy(update={"selected_clips": bad_clips}),
        )
    assert evidence_error.value.code == "codex_initial_selection_evidence_unknown"


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


def test_job_settings_reject_clip_counts_above_ui_limits() -> None:
    with pytest.raises(ValidationError):
        JobSettings(normalClipCount=13, shortCount=0)
    with pytest.raises(ValidationError):
        JobSettings(normalClipCount=0, shortCount=25)


def test_heatmap_interval_mode_requires_positive_actual_overlap() -> None:
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
    assert result.selection.shorts == []
    assert result.summary["droppedShortCandidates"] == [
        {
            "proposalId": "short_1",
            "code": "codex_initial_selection_heatmap_required",
            "message": "JSON区間モードの選定が人気区間と重なっていません。",
        }
    ]

    with pytest.raises(ValidationError, match="positive heatmap"):
        _request(settings=_settings(heatmapIntervalMode=True), heatmap=[])


def test_heatmap_interval_mode_maps_valid_seeds_to_candidates() -> None:
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

    assert all(item.generation_source == "heatmap_interval" for item in result.candidates)
    assert result.candidates[0].heatmap_seed_value == 0.9
    assert result.candidates[1].heatmap_seed_value == 0.8


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
    assert len(request_files) == 1
    request_payload = json.loads(request_files[0].read_text(encoding="utf-8"))
    assert request_files[0].stem == request_payload["requestId"]
    assert request_payload["schemaVersion"] == 1
    assert request_payload["task"] == "initial_clip_selection"
    assert request_payload["images"] == []
    assert request_payload["threadScope"] == "job_codex"
    assert '"jobId":"job_codex"' in request_payload["prompt"]
    assert '"shortCandidateCount":3' in request_payload["prompt"]
    assert "同じheatmapピーク" in request_payload["prompt"]
    assert "momentKey" in request_payload["prompt"]
    assert "parentStart/parentEnd" in request_payload["prompt"]
    assert request_payload["responseSchema"]["additionalProperties"] is False
    assert result.summary["status"] == "completed"
    assert not codex_initial_selection_summary_output_path(tmp_path).exists()
    assert [item["status"] for item in heartbeat] == ["completed"]


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
    assert clock.monotonic() == 0


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


def test_response_schema_rejects_extra_fields() -> None:
    request = _request()
    payload = _response(request).model_dump(by_alias=True, mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        CodexInitialSelectionResponse.model_validate(payload)
