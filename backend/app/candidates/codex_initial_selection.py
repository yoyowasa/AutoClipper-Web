from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.candidates.deduplicate import time_overlap_ratio
from app.candidates.merge_boundaries import Candidate, CandidateType, build_candidate
from app.candidates.select_candidates import CandidateSelection, SelectionPolicy
from app.scoring.clip_preferences import ClipSelectionPreset
from app.scoring.heatmap import candidate_heatmap_features
from app.video.heatmap import HeatmapSegment


CODEX_INITIAL_SELECTION_PROMPT_VERSION = "codex_initial_selection_v4"
CODEX_INITIAL_SELECTION_SUMMARY_FILENAME = "codex_initial_selection_summary.json"
CODEX_RESELECTION_SUMMARY_FILENAME = "codex_reselection_summary.json"
CODEX_INITIAL_SELECTION_BRIDGE_DIRNAME = "codex_bridge"
CODEX_INITIAL_SELECTION_REQUESTS_DIRNAME = "requests"
CODEX_INITIAL_SELECTION_RESPONSES_DIRNAME = "responses"
CODEX_INITIAL_SELECTION_BRIDGE_STATUS_FILENAME = "status.json"
MAX_RESPONSE_SIZE_BYTES = 2 * 1024 * 1024
MAX_BRIDGE_STATUS_SIZE_BYTES = 64 * 1024
SOURCE_TIME_TOLERANCE_SECONDS = 0.5
DEFAULT_RESPONSE_TIMEOUT_SECONDS = 900.0
DEFAULT_RESPONSE_POLL_SECONDS = 0.25
HEARTBEAT_INTERVAL_SECONDS = 5.0
BRIDGE_REQUEST_CLAIM_GRACE_SECONDS = 10.0
BRIDGE_STATUS_STALE_SECONDS = 15.0
BRIDGE_UNAVAILABLE_CONFIRMATION_SECONDS = 2.0
BRIDGE_STATUS_FUTURE_TOLERANCE_SECONDS = 30.0
CODEX_STRICT_QUALITY_MIN_CONFIDENCE = 0.6
SHORT_CANDIDATE_MULTIPLIER = 3
MAX_SHORT_CANDIDATE_COUNT = 24

CODEX_INITIAL_SELECTION_PROMPT = """あなたは日本語動画の切り抜き編集者です。
入力の時刻付き全文字幕、任意の人気度参考情報、通常・ショート別の制約だけを根拠に、公開に値する区間を選んでください。
- timestampSemantics は source_absolute_seconds です。start/end は元動画の絶対秒で返してください。
- まず全文字幕から話題の開始・展開・結論を把握してください。
  通常は一つの話題が自立して完結する区間、ショートはその話題から短時間でフック・反応・結論が成立する区間を選びます。
- 挨拶、宣伝、長い前置き、文の途中で切れる区間は優先しません。
- evidenceSegmentIds は選定理由を直接裏付け、選択範囲と重なる字幕IDだけを返してください。
- 人気区間値は動画内の相対値0〜1で、再生数でも切り抜き境界でもありません。
- heatmapIntervalMode=true の場合も、人気度は候補の優先順位を考える参考情報にだけ使ってください。
  字幕上の話題のまとまりを優先し、人気区間との重なりを必須条件にせず、開始・終了を人気区間の端へ合わせないでください。
- heatmapIntervalMode=false または人気区間が空の場合は、字幕内容だけで選んでください。
- heatmapSegmentIds は実際に参考にした人気区間IDだけを返し、参考にしなかった場合は空配列にしてください。
- requestedShortCountではなくshortCandidateCountまでショート候補を多めに返し、後段で独立したrequestedCount本を選べるようにしてください。
- selectionPolicy=fill_requested の場合、通常はrequestedCountと同数を返してください。
  ショートはshortCandidateCountを目標に多めに返し、独立候補が不足する場合は
  水増しせずshortCandidateCount未満で返してください。
- selectionPolicy=strict_quality の場合はconfidence>=0.6の公開に値する区間だけを、
  通常はrequestedCount以下、ショートはshortCandidateCount以下で返してください。良い場面が不足する場合は水増しせず本数を減らしてください。
- 同じ話題、同じ出来事、同じオチを時刻だけ数秒ずらして複数候補にしないでください。
- ショートのmomentKeyは、時刻や候補番号ではなく、同じ見せ場なら常に同じになる
  簡潔な意味キーにしてください。異なる見せ場には異なるキーを付けてください。
- ショートのstart/endは完成区間、parentStart/parentEndはそれを含む文脈区間です。
  親区間は完成区間の1.5〜3倍程度とし、元動画の範囲内に収めてください。
- 通常clipのmomentKey、parentStart、parentEndはnullにしてください。
- 入力にない発言、人物名、出来事を創作しないでください。
指定されたJSON schema以外を返さないでください。"""


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class CodexInitialSelectionError(RuntimeError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message

    def build_summary(
        self,
        *,
        requested_normal_count: int,
        requested_short_count: int,
        thread_id: str | None = None,
        fallback_used: bool = False,
    ) -> CodexInitialSelectionSummary:
        return CodexInitialSelectionSummary(
            status="fallback" if fallback_used else "failed",
            fallbackUsed=fallback_used,
            error=CodexInitialSelectionSummaryError(
                code=self.code,
                message=self.safe_message,
            ),
            requestedNormalCount=requested_normal_count,
            requestedShortCount=requested_short_count,
            selectedNormalCount=0,
            selectedShortCount=0,
            threadId=thread_id,
        )

    def fallback_summary(
        self,
        *,
        requested_normal_count: int,
        requested_short_count: int,
        thread_id: str | None = None,
    ) -> CodexInitialSelectionSummary:
        return self.build_summary(
            requested_normal_count=requested_normal_count,
            requested_short_count=requested_short_count,
            thread_id=thread_id,
            fallback_used=True,
        )


class CodexTranscriptInput(_StrictModel):
    id: str = Field(pattern=r"^seg_\d{6}$")
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=4000)
    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def validate_range(self) -> CodexTranscriptInput:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class CodexHeatmapInput(_StrictModel):
    id: str = Field(pattern=r"^heat_\d{6}$")
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    value: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_range(self) -> CodexHeatmapInput:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class CodexClipTypeConstraints(_StrictModel):
    requested_count: int = Field(ge=0, le=24, alias="requestedCount")
    min_duration: float = Field(gt=0, allow_inf_nan=False, alias="minDuration")
    max_duration: float = Field(gt=0, allow_inf_nan=False, alias="maxDuration")
    preset: ClipSelectionPreset = "auto"
    guidance: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_duration_range(self) -> CodexClipTypeConstraints:
        if self.max_duration < self.min_duration:
            raise ValueError("maxDuration must be >= minDuration")
        return self


class CodexSelectionConstraints(_StrictModel):
    normal: CodexClipTypeConstraints
    short: CodexClipTypeConstraints
    selection_policy: SelectionPolicy = Field(
        default="fill_requested",
        alias="selectionPolicy",
    )
    short_candidate_count: int = Field(
        ge=0,
        le=MAX_SHORT_CANDIDATE_COUNT,
        alias="shortCandidateCount",
    )
    heatmap_interval_mode: bool = Field(default=False, alias="heatmapIntervalMode")
    max_overlap_ratio: float = Field(
        default=0.8,
        ge=0,
        le=1,
        allow_inf_nan=False,
        alias="maxOverlapRatio",
    )
    cross_type_overlap_dedupe: bool = Field(
        default=False,
        alias="crossTypeOverlapDedupe",
    )
    exclude_intro_outro: bool = Field(default=True, alias="excludeIntroOutro")
    exclude_promotional_content: bool = Field(
        default=False,
        alias="excludePromotionalContent",
    )

    @model_validator(mode="after")
    def validate_requested_count(self) -> CodexSelectionConstraints:
        if self.normal.requested_count + self.short.requested_count <= 0:
            raise ValueError("at least one normal clip or short must be requested")
        expected_short_candidate_count = min(
            self.short.requested_count * SHORT_CANDIDATE_MULTIPLIER,
            MAX_SHORT_CANDIDATE_COUNT,
        )
        if self.short_candidate_count != expected_short_candidate_count:
            raise ValueError("shortCandidateCount must equal min(short requestedCount * 3, 24)")
        return self


class CodexInitialSelectionRequest(_StrictModel):
    version: Literal[1] = 1
    prompt_version: Literal[CODEX_INITIAL_SELECTION_PROMPT_VERSION] = Field(
        default=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        alias="promptVersion",
    )
    job_id: str = Field(min_length=1, max_length=128, alias="jobId")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$", alias="inputHash")
    timestamp_semantics: Literal["source_absolute_seconds"] = Field(
        default="source_absolute_seconds",
        alias="timestampSemantics",
    )
    source_duration: float = Field(
        gt=0,
        allow_inf_nan=False,
        alias="sourceDuration",
    )
    constraints: CodexSelectionConstraints
    transcript: list[CodexTranscriptInput] = Field(min_length=1)
    heatmap: list[CodexHeatmapInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_input_contract(self) -> CodexInitialSelectionRequest:
        transcript_ids = [item.id for item in self.transcript]
        heatmap_ids = [item.id for item in self.heatmap]
        if len(transcript_ids) != len(set(transcript_ids)):
            raise ValueError("transcript IDs must be unique")
        if len(heatmap_ids) != len(set(heatmap_ids)):
            raise ValueError("heatmap IDs must be unique")
        if [(item.start, item.end) for item in self.transcript] != sorted((item.start, item.end) for item in self.transcript):
            raise ValueError("transcript segments must be ordered")
        if [(item.start, item.end) for item in self.heatmap] != sorted((item.start, item.end) for item in self.heatmap):
            raise ValueError("heatmap segments must be ordered")
        if any(item.end > self.source_duration + SOURCE_TIME_TOLERANCE_SECONDS for item in [*self.transcript, *self.heatmap]):
            raise ValueError("input segment exceeds source duration")
        return self

    def prompt_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class CodexClipProposal(_StrictModel):
    proposal_id: str = Field(min_length=1, max_length=40, alias="proposalId")
    type: CandidateType
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    moment_key: str | None = Field(
        min_length=1,
        max_length=80,
        alias="momentKey",
    )
    parent_start: float | None = Field(
        ge=0,
        allow_inf_nan=False,
        alias="parentStart",
    )
    parent_end: float | None = Field(
        gt=0,
        allow_inf_nan=False,
        alias="parentEnd",
    )
    evidence_segment_ids: list[str] = Field(
        min_length=1,
        max_length=128,
        alias="evidenceSegmentIds",
    )
    heatmap_segment_ids: list[str] = Field(
        max_length=16,
        alias="heatmapSegmentIds",
    )
    reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    risk_flags: list[str] = Field(
        max_length=20,
        alias="riskFlags",
    )

class CodexInitialSelectionResponse(_StrictModel):
    version: Literal[1]
    prompt_version: Literal[CODEX_INITIAL_SELECTION_PROMPT_VERSION] = Field(
        alias="promptVersion",
    )
    job_id: str = Field(min_length=1, max_length=128, alias="jobId")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$", alias="inputHash")
    thread_id: str | None = Field(min_length=1, max_length=128, alias="threadId")
    selected_clips: list[CodexClipProposal] = Field(
        max_length=48,
        alias="selectedClips",
    )
    warnings: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_unique_proposals(self) -> CodexInitialSelectionResponse:
        proposal_ids = [item.proposal_id for item in self.selected_clips]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise ValueError("proposal IDs must be unique")
        return self


class CodexInitialSelectionBridgeEnvelope(_StrictModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    task: Literal["initial_clip_selection"] = "initial_clip_selection"
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    prompt: str = Field(min_length=1)
    response_schema: dict[str, Any] = Field(alias="responseSchema")
    images: list[str] = Field(default_factory=list, max_length=0)
    thread_scope: str = Field(min_length=1, max_length=128, alias="threadScope")
    thread_id: str | None = Field(default=None, alias="threadId")


class CodexInitialSelectionSummaryError(_StrictModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=300)


class CodexDroppedShortCandidate(_StrictModel):
    proposal_id: str = Field(min_length=1, max_length=40, alias="proposalId")
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=300)


class CodexInitialSelectionHostResponse(_StrictModel):
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    state: Literal["queued", "running", "completed", "failed"]
    thread_id: str | None = Field(default=None, min_length=1, max_length=128, alias="threadId")
    output: dict[str, Any] | None = None
    error: CodexInitialSelectionSummaryError | None = None

    @model_validator(mode="after")
    def validate_state_payload(self) -> CodexInitialSelectionHostResponse:
        if self.state == "completed" and self.output is None:
            raise ValueError("completed host response requires output")
        if self.state == "failed" and self.error is None:
            raise ValueError("failed host response requires error")
        return self


class CodexInitialSelectionBridgeStatus(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    schema_version: Literal[1] = Field(alias="schemaVersion")
    state: Literal["ready", "error", "stopped"]
    updated_at: datetime = Field(alias="updatedAt")
    request_id: str | None = Field(default=None, max_length=100, alias="requestId")
    request_state: Literal["idle", "processing"] | None = Field(
        default=None,
        alias="requestState",
    )
    error_code: str | None = Field(default=None, max_length=100, alias="errorCode")

    @model_validator(mode="after")
    def validate_status(self) -> CodexInitialSelectionBridgeStatus:
        if self.updated_at.tzinfo is None:
            raise ValueError("updatedAt must include a timezone")
        if self.request_state == "processing" and not self.request_id:
            raise ValueError("processing bridge status requires requestId")
        return self


CodexInitialSelectionSummaryStatus = Literal[
    "queued",
    "running",
    "completed",
    "fallback",
    "failed",
]


class CodexInitialSelectionSummary(_StrictModel):
    provider: Literal["codex"] = "codex"
    phase: Literal["initial", "reselection"] = "initial"
    status: CodexInitialSelectionSummaryStatus
    fallback_used: bool = Field(alias="fallbackUsed")
    error: CodexInitialSelectionSummaryError | None = None
    requested_normal_count: int = Field(ge=0, alias="requestedNormalCount")
    requested_short_count: int = Field(ge=0, alias="requestedShortCount")
    selected_normal_count: int = Field(ge=0, alias="selectedNormalCount")
    selected_short_count: int = Field(ge=0, alias="selectedShortCount")
    dropped_short_candidates: list[CodexDroppedShortCandidate] = Field(
        default_factory=list,
        alias="droppedShortCandidates",
    )
    thread_id: str | None = Field(default=None, alias="threadId")


@dataclass(frozen=True)
class CodexInitialSelectionResult:
    selection: CandidateSelection
    candidates: list[Candidate]
    summary: dict[str, Any]
    proposals: list[CodexClipProposal] = field(default_factory=list)
    duplicate_short_moment_keys: list[str] = field(default_factory=list)
    dropped_short_candidates: list[CodexDroppedShortCandidate] = field(
        default_factory=list
    )


def codex_initial_selection_request_output_path(
    storage_root: str | Path,
    request_id: str,
) -> Path:
    return Path(storage_root) / CODEX_INITIAL_SELECTION_BRIDGE_DIRNAME / CODEX_INITIAL_SELECTION_REQUESTS_DIRNAME / f"{request_id}.json"


def codex_initial_selection_response_output_path(
    storage_root: str | Path,
    request_id: str,
) -> Path:
    return Path(storage_root) / CODEX_INITIAL_SELECTION_BRIDGE_DIRNAME / CODEX_INITIAL_SELECTION_RESPONSES_DIRNAME / f"{request_id}.json"


def codex_initial_selection_summary_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / CODEX_INITIAL_SELECTION_SUMMARY_FILENAME


def codex_reselection_summary_output_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / CODEX_RESELECTION_SUMMARY_FILENAME


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def write_codex_initial_selection_summary(
    summary: CodexInitialSelectionSummary | dict[str, Any],
    path: str | Path,
) -> Path:
    validated = CodexInitialSelectionSummary.model_validate(summary)
    return _write_json_atomic(
        Path(path),
        validated.model_dump(by_alias=True, mode="json"),
    )


def codex_initial_selection_response_schema() -> dict[str, Any]:
    return CodexInitialSelectionResponse.model_json_schema(by_alias=True)


def compute_codex_initial_selection_input_hash(
    request: CodexInitialSelectionRequest,
) -> str:
    payload = request.model_dump(
        by_alias=True,
        mode="json",
        exclude={"input_hash"},
    )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _int_setting(settings: dict[str, Any], key: str, default: int) -> int:
    try:
        return max(0, int(settings.get(key, default)))
    except (TypeError, ValueError):
        return default


def _float_setting(settings: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError):
        return default


def _bool_setting(settings: dict[str, Any], key: str, default: bool) -> bool:
    value = settings.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _text_setting(settings: dict[str, Any], key: str, default: str = "") -> str:
    value = settings.get(key, default)
    return str(value).strip() if value is not None else default


def _preset_setting(settings: dict[str, Any], key: str) -> ClipSelectionPreset:
    value = _text_setting(settings, key, "auto")
    if value in {"auto", "highlights", "funny", "important", "emotional", "informative"}:
        return value  # type: ignore[return-value]
    return "auto"


def _selection_policy_setting(settings: dict[str, Any]) -> SelectionPolicy:
    value = _text_setting(settings, "selectionPolicy", "fill_requested")
    return "strict_quality" if value == "strict_quality" else "fill_requested"


def _build_constraints(settings: dict[str, Any]) -> CodexSelectionConstraints:
    return CodexSelectionConstraints(
        normal=CodexClipTypeConstraints(
            requestedCount=_int_setting(settings, "normalClipCount", 2),
            minDuration=_float_setting(settings, "normalMinDuration", 90.0),
            maxDuration=_float_setting(settings, "normalMaxDuration", 600.0),
            preset=_preset_setting(settings, "normalClipSelectionPreset"),
            guidance=_text_setting(settings, "normalClipGuidance"),
        ),
        short=CodexClipTypeConstraints(
            requestedCount=_int_setting(settings, "shortCount", 3),
            minDuration=_float_setting(settings, "shortMinDuration", 20.0),
            maxDuration=_float_setting(settings, "shortMaxDuration", 75.0),
            preset=_preset_setting(settings, "shortClipSelectionPreset"),
            guidance=_text_setting(settings, "shortClipGuidance"),
        ),
        shortCandidateCount=min(
            _int_setting(settings, "shortCount", 3) * SHORT_CANDIDATE_MULTIPLIER,
            MAX_SHORT_CANDIDATE_COUNT,
        ),
        selectionPolicy=_selection_policy_setting(settings),
        heatmapIntervalMode=_bool_setting(settings, "heatmapIntervalMode", False),
        maxOverlapRatio=_float_setting(settings, "maxOverlapRatio", 0.8),
        crossTypeOverlapDedupe=_bool_setting(settings, "crossTypeOverlapDedupe", False),
        excludeIntroOutro=_bool_setting(settings, "excludeIntroOutro", True),
        excludePromotionalContent=_bool_setting(settings, "excludePromotionalContent", False),
    )


def build_codex_initial_selection_request(
    *,
    job_id: str,
    transcript_segments: Sequence[TranscriptSegment],
    heatmap_segments: Sequence[HeatmapSegment],
    video_duration: float,
    settings: dict[str, Any],
) -> CodexInitialSelectionRequest:
    clean_transcript = sorted(
        (segment for segment in transcript_segments if segment.text.strip()),
        key=lambda item: (item.start, item.end),
    )
    reference_heatmap = (
        heatmap_segments
        if _bool_setting(settings, "heatmapIntervalMode", False)
        else ()
    )
    clean_heatmap: list[HeatmapSegment] = []
    for segment in sorted(
        reference_heatmap,
        key=lambda item: (item.start_time, item.end_time),
    ):
        start = max(0.0, min(float(segment.start_time), video_duration))
        end = max(0.0, min(float(segment.end_time), video_duration))
        if end <= start:
            continue
        clean_heatmap.append(
            HeatmapSegment(
                start_time=round(start, 3),
                end_time=round(end, 3),
                value=float(segment.value),
            )
        )
    request = CodexInitialSelectionRequest(
        jobId=job_id,
        requestId=uuid4().hex,
        inputHash="0" * 64,
        sourceDuration=video_duration,
        constraints=_build_constraints(settings),
        transcript=[
            CodexTranscriptInput(
                id=f"seg_{index:06d}",
                start=round(float(segment.start), 3),
                end=round(float(segment.end), 3),
                text=segment.text.strip(),
                confidence=segment.confidence,
            )
            for index, segment in enumerate(clean_transcript, start=1)
        ],
        heatmap=[
            CodexHeatmapInput(
                id=f"heat_{index:06d}",
                start=round(float(segment.start_time), 3),
                end=round(float(segment.end_time), 3),
                value=float(segment.value),
            )
            for index, segment in enumerate(clean_heatmap, start=1)
        ],
    )
    return request.model_copy(update={"input_hash": compute_codex_initial_selection_input_hash(request)})


def _bridge_envelope(
    request: CodexInitialSelectionRequest,
    *,
    thread_id: str | None,
) -> CodexInitialSelectionBridgeEnvelope:
    request_json = json.dumps(
        request.prompt_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return CodexInitialSelectionBridgeEnvelope(
        requestId=request.request_id,
        prompt=f"{CODEX_INITIAL_SELECTION_PROMPT}\n\n入力JSON:\n{request_json}",
        responseSchema=codex_initial_selection_response_schema(),
        images=[],
        threadScope=request.job_id,
        threadId=thread_id,
    )


class CodexInitialSelectionSharedFileBridge:
    def __init__(
        self,
        storage_root: str | Path,
        *,
        sleep_func: Callable[[float], None] = time.sleep,
        monotonic_func: Callable[[], float] = time.monotonic,
        wall_time_func: Callable[[], float] = time.time,
        request_claim_grace_seconds: float = BRIDGE_REQUEST_CLAIM_GRACE_SECONDS,
        status_stale_seconds: float = BRIDGE_STATUS_STALE_SECONDS,
        unavailable_confirmation_seconds: float = BRIDGE_UNAVAILABLE_CONFIRMATION_SECONDS,
    ) -> None:
        self.storage_root = Path(storage_root)
        self.sleep_func = sleep_func
        self.monotonic_func = monotonic_func
        self.wall_time_func = wall_time_func
        self.request_claim_grace_seconds = max(0.0, float(request_claim_grace_seconds))
        self.status_stale_seconds = max(0.1, float(status_stale_seconds))
        self.unavailable_confirmation_seconds = max(
            0.0,
            float(unavailable_confirmation_seconds),
        )
        self._request_created_at: dict[str, float] = {}

    def request_path(self, request_id: str) -> Path:
        return codex_initial_selection_request_output_path(
            self.storage_root,
            request_id,
        )

    def response_path(self, request_id: str) -> Path:
        return codex_initial_selection_response_output_path(
            self.storage_root,
            request_id,
        )

    def status_path(self) -> Path:
        return self.storage_root / CODEX_INITIAL_SELECTION_BRIDGE_DIRNAME / CODEX_INITIAL_SELECTION_BRIDGE_STATUS_FILENAME

    def write_request(
        self,
        request: CodexInitialSelectionRequest,
        *,
        thread_id: str | None = None,
    ) -> Path:
        path = _write_json_atomic(
            self.request_path(request.request_id),
            _bridge_envelope(request, thread_id=thread_id).model_dump(
                by_alias=True,
                mode="json",
            ),
        )
        self._request_created_at[request.request_id] = self.wall_time_func()
        return path

    def _read_bridge_status(self) -> CodexInitialSelectionBridgeStatus | None:
        status_path = self.status_path()
        try:
            if not status_path.is_file():
                return None
            if status_path.stat().st_size > MAX_BRIDGE_STATUS_SIZE_BYTES:
                return None
            return CodexInitialSelectionBridgeStatus.model_validate_json(status_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            return None

    def _bridge_unavailable_reason(
        self,
        request: CodexInitialSelectionRequest,
        *,
        elapsed_seconds: float,
        wall_time: float,
    ) -> str | None:
        request_created_at = self._request_created_at.get(
            request.request_id,
            wall_time - elapsed_seconds,
        )
        status = self._read_bridge_status()
        if status is None:
            return "status_missing" if elapsed_seconds >= self.request_claim_grace_seconds else None

        status_updated_at = status.updated_at.timestamp()
        if status_updated_at > wall_time + BRIDGE_STATUS_FUTURE_TOLERANCE_SECONDS:
            return "status_clock_invalid" if elapsed_seconds >= self.request_claim_grace_seconds else None
        if status.state in {"error", "stopped"}:
            if status_updated_at >= request_created_at - 1.0 or elapsed_seconds >= self.request_claim_grace_seconds:
                return f"status_{status.state}"
            return None

        if status.request_state == "processing":
            if wall_time - status_updated_at > self.status_stale_seconds:
                return "status_stale"
            return None

        idle_reference = max(request_created_at, status_updated_at)
        if wall_time - idle_reference >= self.request_claim_grace_seconds:
            return "request_unclaimed"
        return None

    def _read_response_file(
        self,
        request: CodexInitialSelectionRequest,
    ) -> CodexInitialSelectionResponse | None:
        response_path = self.response_path(request.request_id)
        if not response_path.is_file():
            raise CodexInitialSelectionError(
                "codex_initial_selection_response_missing",
                "Codex初期選定の応答ファイルがありません。",
            )
        try:
            if response_path.stat().st_size > MAX_RESPONSE_SIZE_BYTES:
                raise CodexInitialSelectionError(
                    "codex_initial_selection_response_too_large",
                    "Codex初期選定の応答ファイルが上限を超えています。",
                )
            host_response = CodexInitialSelectionHostResponse.model_validate_json(response_path.read_text(encoding="utf-8"))
        except CodexInitialSelectionError:
            raise
        except (OSError, ValidationError, ValueError) as exc:
            raise CodexInitialSelectionError(
                "codex_initial_selection_response_invalid",
                "Codex初期選定の応答形式が不正です。",
            ) from exc
        if host_response.request_id != request.request_id:
            raise CodexInitialSelectionError(
                "codex_initial_selection_request_mismatch",
                "Codex初期選定のrequestが一致しません。",
            )
        if host_response.state in {"queued", "running"}:
            return None
        if host_response.state == "failed":
            raise CodexInitialSelectionError(
                "codex_initial_selection_host_failed",
                "Codex初期選定を実行できませんでした。",
            )
        output_payload = dict(host_response.output or {})
        output_thread_id = output_payload.get("threadId")
        if output_thread_id is not None and host_response.thread_id is not None and output_thread_id != host_response.thread_id:
            raise CodexInitialSelectionError(
                "codex_initial_selection_thread_mismatch",
                "Codex初期選定のthreadが一致しません。",
            )
        if output_thread_id is None and host_response.thread_id is not None:
            output_payload["threadId"] = host_response.thread_id
        try:
            response = CodexInitialSelectionResponse.model_validate(output_payload)
        except ValidationError as exc:
            raise CodexInitialSelectionError(
                "codex_initial_selection_output_invalid",
                "Codex初期選定の出力形式が不正です。",
            ) from exc
        if response.job_id != request.job_id:
            raise CodexInitialSelectionError(
                "codex_initial_selection_job_mismatch",
                "Codex初期選定のjobが一致しません。",
            )
        if response.request_id != request.request_id:
            raise CodexInitialSelectionError(
                "codex_initial_selection_request_mismatch",
                "Codex初期選定のrequestが一致しません。",
            )
        if response.input_hash != request.input_hash:
            raise CodexInitialSelectionError(
                "codex_initial_selection_hash_mismatch",
                "Codex初期選定の入力が更新されています。",
            )
        return response

    def wait_for_response(
        self,
        request: CodexInitialSelectionRequest,
        *,
        timeout_seconds: float = DEFAULT_RESPONSE_TIMEOUT_SECONDS,
        poll_seconds: float = DEFAULT_RESPONSE_POLL_SECONDS,
        heartbeat: Callable[[dict[str, Any]], None] | None = None,
    ) -> CodexInitialSelectionResponse:
        timeout = max(0.01, float(timeout_seconds))
        poll = min(max(0.01, float(poll_seconds)), 5.0)
        started_at = self.monotonic_func()
        next_heartbeat = started_at
        unavailable_since: float | None = None
        while True:
            if self.response_path(request.request_id).is_file():
                response = self._read_response_file(request)
                if response is not None:
                    return response
            now = self.monotonic_func()
            if now - started_at >= timeout:
                raise CodexInitialSelectionError(
                    "codex_initial_selection_timeout",
                    "Codex初期選定の応答待ちが時間切れになりました。",
                )
            unavailable_reason = self._bridge_unavailable_reason(
                request,
                elapsed_seconds=now - started_at,
                wall_time=self.wall_time_func(),
            )
            if unavailable_reason is None:
                unavailable_since = None
            else:
                if unavailable_since is None:
                    unavailable_since = now
                if now - unavailable_since >= self.unavailable_confirmation_seconds:
                    raise CodexInitialSelectionError(
                        "codex_initial_selection_bridge_unavailable",
                        "Codex bridgeを利用できないため、従来選定へ切り替えます。",
                    )
            if heartbeat is not None and now >= next_heartbeat:
                heartbeat(
                    {
                        "provider": "codex",
                        "status": "running",
                        "fallbackUsed": False,
                        "error": None,
                        "requestedNormalCount": request.constraints.normal.requested_count,
                        "requestedShortCount": request.constraints.short.requested_count,
                        "selectedNormalCount": 0,
                        "selectedShortCount": 0,
                        "threadId": None,
                    }
                )
                next_heartbeat = now + HEARTBEAT_INTERVAL_SECONDS
            self.sleep_func(min(poll, max(0.01, timeout - (now - started_at))))


def _overlaps(start: float, end: float, other_start: float, other_end: float) -> bool:
    return other_end > start and other_start < end


def _validate_proposal_moment_metadata(proposal: CodexClipProposal) -> None:
    if proposal.end <= proposal.start:
        raise CodexInitialSelectionError(
            "codex_initial_selection_range_invalid",
            "Codex初期選定の区間が不正です。",
        )
    if len(proposal.evidence_segment_ids) != len(set(proposal.evidence_segment_ids)):
        raise CodexInitialSelectionError(
            "codex_initial_selection_evidence_duplicate",
            "Codex初期選定の字幕根拠IDが重複しています。",
        )
    if len(proposal.heatmap_segment_ids) != len(set(proposal.heatmap_segment_ids)):
        raise CodexInitialSelectionError(
            "codex_initial_selection_heatmap_duplicate",
            "Codex初期選定の人気区間IDが重複しています。",
        )
    parent_values = (proposal.parent_start, proposal.parent_end)
    if proposal.type == "normal":
        if proposal.moment_key is not None or any(
            value is not None for value in parent_values
        ):
            raise CodexInitialSelectionError(
                "codex_initial_selection_normal_metadata_invalid",
                "Codex初期選定の通常clipにショート用親区間が含まれています。",
            )
        return
    if proposal.moment_key is None or any(value is None for value in parent_values):
        raise CodexInitialSelectionError(
            "codex_initial_selection_short_metadata_missing",
            "Codex初期選定のショート候補に見せ場キーまたは親区間がありません。",
        )
    assert proposal.parent_start is not None
    assert proposal.parent_end is not None
    if proposal.parent_end <= proposal.parent_start:
        raise CodexInitialSelectionError(
            "codex_initial_selection_parent_range_invalid",
            "Codex初期選定のショート親区間が不正です。",
        )
    if proposal.parent_start > proposal.start or proposal.parent_end < proposal.end:
        raise CodexInitialSelectionError(
            "codex_initial_selection_parent_not_containing_final",
            "Codex初期選定のショート親区間が完成区間を含んでいません。",
        )
    final_duration = proposal.end - proposal.start
    parent_ratio = (proposal.parent_end - proposal.parent_start) / final_duration
    if parent_ratio < 1.5 - 0.001 or parent_ratio > 3.0 + 0.001:
        raise CodexInitialSelectionError(
            "codex_initial_selection_parent_ratio_invalid",
            "Codex初期選定のショート親区間が完成区間の1.5〜3倍ではありません。",
        )


def _proposal_candidate(
    proposal: CodexClipProposal,
    *,
    request: CodexInitialSelectionRequest,
) -> Candidate:
    _validate_proposal_moment_metadata(proposal)
    if proposal.end > request.source_duration + 0.001:
        raise CodexInitialSelectionError(
            "codex_initial_selection_range_outside_source",
            "Codex初期選定の範囲が元動画を超えています。",
        )
    if proposal.type == "short" and proposal.parent_end is not None and proposal.parent_end > request.source_duration + 0.001:
        raise CodexInitialSelectionError(
            "codex_initial_selection_parent_outside_source",
            "Codex初期選定の親区間が元動画を超えています。",
        )
    type_constraints = request.constraints.normal if proposal.type == "normal" else request.constraints.short
    duration = proposal.end - proposal.start
    if duration < type_constraints.min_duration - 0.001 or duration > type_constraints.max_duration + 0.001:
        raise CodexInitialSelectionError(
            "codex_initial_selection_duration_invalid",
            "Codex初期選定の長さが設定範囲外です。",
        )

    transcript_by_id = {item.id: item for item in request.transcript}
    try:
        evidence = [transcript_by_id[item_id] for item_id in proposal.evidence_segment_ids]
    except KeyError as exc:
        raise CodexInitialSelectionError(
            "codex_initial_selection_evidence_unknown",
            "Codex初期選定の字幕根拠が入力に存在しません。",
        ) from exc
    if any(not _overlaps(proposal.start, proposal.end, item.start, item.end) for item in evidence):
        raise CodexInitialSelectionError(
            "codex_initial_selection_evidence_outside_range",
            "Codex初期選定の字幕根拠が選択範囲外です。",
        )

    heatmap_by_id = {item.id: item for item in request.heatmap}
    unknown_heatmap_ids = [
        item_id
        for item_id in proposal.heatmap_segment_ids
        if item_id not in heatmap_by_id
    ]
    if unknown_heatmap_ids:
        raise CodexInitialSelectionError(
            "codex_initial_selection_heatmap_unknown",
            "Codex初期選定の人気区間根拠が入力に存在しません。",
        )
    transcript_segments = [
        TranscriptSegment(
            start=item.start,
            end=item.end,
            text=item.text,
            confidence=item.confidence,
        )
        for item in request.transcript
    ]
    candidate = build_candidate(
        proposal.type,
        proposal.start,
        proposal.end,
        transcript_segments,
    )
    if candidate is None:
        raise CodexInitialSelectionError(
            "codex_initial_selection_no_transcript",
            "Codex初期選定の範囲に字幕がありません。",
        )

    heatmap_segments = [HeatmapSegment(start_time=item.start, end_time=item.end, value=item.value) for item in request.heatmap]
    heatmap_value: float | None = None
    heatmap_overlap: float | None = None
    heatmap_score: float | None = None
    if heatmap_segments:
        heatmap_value, heatmap_overlap = candidate_heatmap_features(candidate, heatmap_segments)
        heatmap_score = round(heatmap_value * 10.0, 6)
    score = round(proposal.confidence * 100.0, 6)
    return candidate.model_copy(
        update={
            "generation_source": None,
            "heatmap_value": heatmap_value,
            "heatmap_overlap_seconds": heatmap_overlap,
            "heatmap_score": heatmap_score,
            "heatmap_direct_score": None,
            "heatmap_seed_start": None,
            "heatmap_seed_end": None,
            "heatmap_seed_value": None,
            "ai_score": score,
            "final_score": score,
            "should_use": True,
            "reason": proposal.reason,
            "risk_flags": proposal.risk_flags,
            "moment_key": proposal.moment_key,
            "parent_start": proposal.parent_start,
            "parent_end": proposal.parent_end,
            "evidence_segment_ids": list(proposal.evidence_segment_ids),
            "heatmap_segment_ids": list(proposal.heatmap_segment_ids),
            "selection_reason": "codex_direct",
            "used_ai_score": True,
            "openai_scored": False,
            "openai_not_scored_reason": "codex_direct_selection",
        }
    )


def _validate_overlap(
    candidates: Sequence[Candidate],
    *,
    max_overlap_ratio: float,
    cross_type_overlap_dedupe: bool,
) -> None:
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if left.type != right.type and not cross_type_overlap_dedupe:
                continue
            if time_overlap_ratio(left, right) >= max_overlap_ratio:
                raise CodexInitialSelectionError(
                    "codex_initial_selection_high_overlap",
                    "Codex初期選定の区間が重複上限を超えています。",
                )


def find_duplicate_short_moment_keys(
    proposals: Sequence[CodexClipProposal],
) -> list[str]:
    counts: dict[str, int] = {}
    for proposal in proposals:
        if proposal.type != "short" or proposal.moment_key is None:
            continue
        key = proposal.moment_key.casefold()
        counts[key] = counts.get(key, 0) + 1
    return sorted(key for key, count in counts.items() if count > 1)


def _select_initial_short_pairs(
    pairs: Sequence[tuple[CodexClipProposal, Candidate]],
    *,
    requested_count: int,
    normal_candidates: Sequence[Candidate],
    max_overlap_ratio: float,
    cross_type_overlap_dedupe: bool,
) -> list[tuple[CodexClipProposal, Candidate]]:
    selected: list[tuple[CodexClipProposal, Candidate]] = []
    used_moment_keys: set[str] = set()
    ranked_pairs = sorted(
        pairs,
        key=lambda item: (-item[0].confidence, item[0].proposal_id),
    )
    for proposal, candidate in ranked_pairs:
        if len(selected) >= requested_count:
            break
        assert proposal.moment_key is not None
        moment_key = proposal.moment_key.casefold()
        if moment_key in used_moment_keys:
            continue
        if any(time_overlap_ratio(candidate, selected_candidate) >= max_overlap_ratio for _, selected_candidate in selected):
            continue
        if cross_type_overlap_dedupe and any(
            time_overlap_ratio(candidate, normal_candidate) >= max_overlap_ratio for normal_candidate in normal_candidates
        ):
            continue
        selected.append((proposal, candidate))
        used_moment_keys.add(moment_key)
    return selected


def convert_codex_initial_selection_response(
    request: CodexInitialSelectionRequest,
    response: CodexInitialSelectionResponse,
) -> CodexInitialSelectionResult:
    if response.job_id != request.job_id:
        raise CodexInitialSelectionError(
            "codex_initial_selection_job_mismatch",
            "Codex初期選定のjobが一致しません。",
        )
    if response.request_id != request.request_id:
        raise CodexInitialSelectionError(
            "codex_initial_selection_request_mismatch",
            "Codex初期選定のrequestが一致しません。",
        )
    if response.input_hash != request.input_hash:
        raise CodexInitialSelectionError(
            "codex_initial_selection_hash_mismatch",
            "Codex初期選定の入力が更新されています。",
        )

    normal_proposals = [item for item in response.selected_clips if item.type == "normal"]
    short_proposals = [item for item in response.selected_clips if item.type == "short"]
    requested_normal = request.constraints.normal.requested_count
    requested_short = request.constraints.short.requested_count
    short_candidate_count = request.constraints.short_candidate_count
    if request.constraints.selection_policy == "fill_requested":
        if len(normal_proposals) != requested_normal:
            raise CodexInitialSelectionError(
                "codex_initial_selection_count_mismatch",
                "Codex初期選定の本数が要求と一致しません。",
            )
        if len(short_proposals) > short_candidate_count:
            raise CodexInitialSelectionError(
                "codex_initial_selection_count_exceeded",
                "Codex初期選定のショート候補が上限を超えています。",
            )
    else:
        if len(normal_proposals) > requested_normal or len(short_proposals) > short_candidate_count:
            raise CodexInitialSelectionError(
                "codex_initial_selection_count_exceeded",
                "Codex初期選定の本数が要求上限を超えています。",
            )
        response = response.model_copy(
            update={"selected_clips": [item for item in response.selected_clips if item.confidence >= CODEX_STRICT_QUALITY_MIN_CONFIDENCE]}
        )

    proposals: list[CodexClipProposal] = []
    candidates: list[Candidate] = []
    dropped_short_candidates: list[CodexDroppedShortCandidate] = []
    for proposal in response.selected_clips:
        try:
            candidate = _proposal_candidate(proposal, request=request)
        except CodexInitialSelectionError as exc:
            if proposal.type == "normal":
                raise
            dropped_short_candidates.append(
                CodexDroppedShortCandidate(
                    proposalId=proposal.proposal_id,
                    code=exc.code,
                    message=exc.safe_message,
                )
            )
            continue
        proposals.append(proposal)
        candidates.append(candidate)
    proposal_candidate_pairs = list(zip(proposals, candidates, strict=True))
    normal_pairs = [item for item in proposal_candidate_pairs if item[0].type == "normal"]
    short_pairs = [item for item in proposal_candidate_pairs if item[0].type == "short"]
    normal_candidates = [item[1] for item in normal_pairs]
    _validate_overlap(
        normal_candidates,
        max_overlap_ratio=request.constraints.max_overlap_ratio,
        cross_type_overlap_dedupe=False,
    )
    selected_short_pairs = _select_initial_short_pairs(
        short_pairs,
        requested_count=requested_short,
        normal_candidates=normal_candidates,
        max_overlap_ratio=request.constraints.max_overlap_ratio,
        cross_type_overlap_dedupe=request.constraints.cross_type_overlap_dedupe,
    )
    short_candidates = [item[1] for item in selected_short_pairs]
    selection = CandidateSelection(
        normalClips=normal_candidates,
        shorts=short_candidates,
        selectionPolicy=request.constraints.selection_policy,
        requestedNormalCount=request.constraints.normal.requested_count,
        requestedShortCount=request.constraints.short.requested_count,
    )
    summary_model = CodexInitialSelectionSummary(
        status="completed",
        fallbackUsed=False,
        error=None,
        requestedNormalCount=request.constraints.normal.requested_count,
        requestedShortCount=request.constraints.short.requested_count,
        selectedNormalCount=len(normal_candidates),
        selectedShortCount=len(short_candidates),
        droppedShortCandidates=dropped_short_candidates,
        threadId=response.thread_id,
    )
    return CodexInitialSelectionResult(
        selection=selection,
        candidates=candidates,
        summary=summary_model.model_dump(by_alias=True, mode="json"),
        proposals=proposals,
        duplicate_short_moment_keys=find_duplicate_short_moment_keys(proposals),
        dropped_short_candidates=dropped_short_candidates,
    )


def request_codex_initial_selection(
    job_id: str,
    storage_root: str | Path,
    transcript_segments: Sequence[TranscriptSegment],
    heatmap_segments: Sequence[HeatmapSegment],
    video_duration: float,
    settings: dict[str, Any],
    heartbeat: Callable[[dict[str, Any]], None] | None = None,
) -> CodexInitialSelectionResult:
    timeout_seconds = _float_setting(
        settings,
        "codexSelectionTimeoutSeconds",
        DEFAULT_RESPONSE_TIMEOUT_SECONDS,
    )
    poll_seconds = _float_setting(
        settings,
        "codexSelectionPollSeconds",
        DEFAULT_RESPONSE_POLL_SECONDS,
    )
    try:
        request = build_codex_initial_selection_request(
            job_id=job_id,
            transcript_segments=transcript_segments,
            heatmap_segments=heatmap_segments,
            video_duration=video_duration,
            settings=settings,
        )
        bridge = CodexInitialSelectionSharedFileBridge(storage_root)
        thread_id = _text_setting(settings, "codexSelectionThreadId") or None
        bridge.write_request(request, thread_id=thread_id)
        response = bridge.wait_for_response(
            request,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
            heartbeat=heartbeat,
        )
        result = convert_codex_initial_selection_response(request, response)
        if heartbeat is not None:
            heartbeat(result.summary)
        return result
    except CodexInitialSelectionError:
        raise
    except (OSError, ValidationError, ValueError) as exc:
        wrapped = CodexInitialSelectionError(
            "codex_initial_selection_request_invalid",
            "Codex初期選定の入力を作成できませんでした。",
        )
        raise wrapped from exc
