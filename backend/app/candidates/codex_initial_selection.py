from __future__ import annotations

import json
import os
import re
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
from app.candidates.used_ranges import overlaps_used, unused_items, used_ranges
from app.candidates.select_candidates import CandidateSelection, SelectionPolicy
from app.scoring.clip_preferences import ClipSelectionPreset
from app.scoring.heatmap import candidate_heatmap_features
from app.video.heatmap import HeatmapSegment


CODEX_INITIAL_SELECTION_PROMPT_VERSION = "codex_initial_selection_v5"
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
MAX_NORMAL_CANDIDATE_COUNT = 24
SHORT_CANDIDATE_MULTIPLIER = 3
MAX_SHORT_CANDIDATE_COUNT = 24
MAX_CODEX_INITIAL_SELECTION_ATTEMPTS = 2
CODEX_TOPIC_SELECTION_TASK = "initial_clip_topic_selection"
MAX_LOCAL_TOPIC_BLOCKS = 180
LOCAL_TOPIC_BLOCK_TARGET_SECONDS = 120.0
LOCAL_TOPIC_BLOCK_MIN_SECONDS = 20.0
LOCAL_TOPIC_SILENCE_SPLIT_SECONDS = 4.0
MAX_TOPIC_SUMMARY_CHARS = 600
MAX_TOPIC_SELECTION_PROMPT_CHARS = 160_000
MAX_REFINEMENT_TRANSCRIPT_CHARS = 240_000
MAX_REFINEMENT_PROMPT_CHARS = 300_000
NORMAL_REFINEMENT_CONTEXT_SECONDS = 45.0
SHORT_REFINEMENT_CONTEXT_SECONDS = 15.0
RETRYABLE_BRIDGE_ERROR_CODES = frozenset(
    {
        "codex_failed",
        "codex_timeout",
        "request_read_failed",
        "response_schema_contract_mismatch",
    }
)

CODEX_TOPIC_SELECTION_PROMPT = """あなたは日本語動画の構成編集者です。
入力はローカルで作成した時刻付き話題ブロックの抽出要約です。動画全体の中から公開価値の高い話題を選び、重要度順に返してください。
- 通常clipとShortは別基準で評価してください。
- 通常clip: 配信の主要テーマ、質問→説明→具体例→結論があり、単独で内容を理解できる話題を優先します。
  名前読み、連続お礼、スパチャ読みだけの話題は減点します。通常候補は異なるtopicKeyにしてください。
- Short: 冒頭の反応、驚き、オチ、短い完結を優先し、スパチャ・コメント由来も許可します。
- この段階では完成動画の区間を決めません。topicBlockIdsは次段階で精査する文脈範囲です。
- minDuration/maxDurationは次段階で切り出す完成動画だけの制約です。話題ブロック全体の長さには適用しないでください。
  例: 120秒のブロックに30秒の見せ場が含まれるなら、Short上限75秒でもそのブロックを選んでください。
- 長いブロック内の一部分を切り出せます。部分の開始終了をこの段階で指定できなくても、ブロックを選べば次段階が元字幕から特定します。
  ブロックの長さがmaxDurationを超えることだけを理由に落とさないでください。
- minDuration/maxDurationは制約であり目標尺ではありません。特定の尺へ寄せないでください。
- durationBandsは長さの異なる良質話題を見落とさないための探索枠です。
  自然に各尺帯へ収まる良質話題があれば、各帯から少なくとも1件を候補プールに残してください。
- 通常はnormalCandidateCount以下、ShortはshortCandidateCount以下で返してください。各枠を埋める目的で話題を伸縮・水増ししないでください。
- topicBlockIdsは入力に存在するIDだけを、飛び番のない連続した時系列順で返してください。
- 通常候補間で同じtopicBlockIdを再利用せず、選択範囲を50%以上重複させないでください。
- topicKeyは時刻や候補番号ではなく、話題の意味を表す安定した簡潔なキーにしてください。
- 公開価値の高い話題が不足する場合は、requestedCountを無理に埋めず少ない件数で返してください。
- 入力にない発言、人物名、出来事を創作しないでください。
指定されたJSON schema以外を返さないでください。"""

CODEX_INITIAL_SELECTION_PROMPT = """あなたは日本語動画の切り抜き編集者です。
入力には、第1段階で選定済みの重要話題と、その周辺の時刻付き元字幕だけが含まれます。元字幕を根拠に開始・終了を精密化してください。
- timestampSemantics は source_absolute_seconds です。start/end は元動画の絶対秒で返してください。
- 開始は話題開始または質問の開始、終了は回答・具体例・結論の完了後の文節または無音に合わせてください。
- 通常clip: 配信の主要テーマ、質問→説明→具体例→結論、単独での理解を重視します。名前読み、連続お礼、スパチャ読みだけは減点します。
- Short: 冒頭の反応、驚き、オチ、短い完結を重視し、スパチャ・コメント由来も許可します。
- minDuration/maxDurationは制約であり目標尺ではありません。特定の尺へ寄せないでください。
- durationBandsは探索元の尺帯です。自然に各尺帯へ収まる良質候補があれば、候補プール全体に各帯から少なくとも1件を残してください。
- 境界は尺帯の中心ではなく、発話内容の自然な開始・完了へ合わせ、各帯を埋めるための伸縮・水増しはしないでください。
- selectedTopicsと同じtype/topicKeyの候補だけを返し、通常候補はtopicKeyを重複させないでください。
- selectedTopicsのwindowStart/windowEndが、その話題に使用できる元字幕範囲です。
- selectedTopicsのstart/endは文脈範囲であり完成区間ではありません。
  長い話題から、その一部分の完結した見せ場をminDuration/maxDuration内で切り出してください。
- 挨拶、宣伝、長い前置き、文の途中で切れる区間は優先しません。
- evidenceSegmentIds は選定理由を直接裏付け、選択範囲と重なる字幕IDだけを返してください。
- 人気区間値は動画内の相対値0〜1で、再生数でも切り抜き境界でもありません。
- heatmapIntervalMode=true の場合も、人気度は候補の優先順位を考える参考情報にだけ使ってください。
  字幕上の話題のまとまりを優先し、人気区間との重なりを必須条件にせず、開始・終了を人気区間の端へ合わせないでください。
- heatmapIntervalMode=false または人気区間が空の場合は、字幕内容だけで選んでください。
- heatmapSegmentIds は実際に参考にした人気区間IDだけを返し、参考にしなかった場合は空配列にしてください。
- requestedCountではなく、通常はnormalCandidateCount、ShortはshortCandidateCountまで候補を返してください。
  後段で自然な境界と尺帯の異なる良質候補からrequestedCount本を選べる候補プールにしてください。
- selectionPolicyにかかわらずconfidence>=0.6の公開に値する区間だけを、
  通常はnormalCandidateCount以下、ShortはshortCandidateCount以下で返してください。良い場面が不足する場合は水増ししないでください。
- 同じ話題、同じ出来事、同じオチを時刻だけ数秒ずらして複数候補にしないでください。
- ショートのmomentKeyは、時刻や候補番号ではなく、同じ見せ場なら常に同じになる
  簡潔な意味キーにしてください。異なる見せ場には異なるキーを付けてください。
- ショートのstart/endは完成区間、parentStart/parentEndはそれを含む文脈区間です。
  親区間は完成区間の1.5〜3倍程度とし、元動画の範囲内に収めてください。
- topicKeyは第1段階で選ばれたtopicKeyをそのまま返してください。
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
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        host_error_code: str | None = None,
        request_id: str | None = None,
        attempt_count: int = 1,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.host_error_code = host_error_code
        self.request_id = request_id
        self.attempt_count = max(1, int(attempt_count))

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
            promptVersion=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
            requestId=self.request_id,
            attemptCount=self.attempt_count,
            hostErrorCode=self.host_error_code,
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


class CodexDurationBand(_StrictModel):
    minimum: float = Field(gt=0, allow_inf_nan=False, alias="minDuration")
    maximum: float = Field(gt=0, allow_inf_nan=False, alias="maxDuration")

    @model_validator(mode="after")
    def validate_duration_range(self) -> CodexDurationBand:
        if self.maximum < self.minimum:
            raise ValueError("maxDuration must be >= minDuration")
        return self


class CodexClipTypeConstraints(_StrictModel):
    requested_count: int = Field(ge=0, le=24, alias="requestedCount")
    min_duration: float = Field(gt=0, allow_inf_nan=False, alias="minDuration")
    max_duration: float = Field(gt=0, allow_inf_nan=False, alias="maxDuration")
    preset: ClipSelectionPreset = "auto"
    guidance: str = Field(default="", max_length=1000)
    duration_bands: list[CodexDurationBand] = Field(
        min_length=1,
        max_length=3,
        alias="durationBands",
    )

    @model_validator(mode="after")
    def validate_duration_range(self) -> CodexClipTypeConstraints:
        if self.max_duration < self.min_duration:
            raise ValueError("maxDuration must be >= minDuration")
        if any(
            band.minimum < self.min_duration - 0.001
            or band.maximum > self.max_duration + 0.001
            for band in self.duration_bands
        ):
            raise ValueError("durationBands must stay inside minDuration/maxDuration")
        return self


class CodexSelectionConstraints(_StrictModel):
    normal: CodexClipTypeConstraints
    short: CodexClipTypeConstraints
    selection_policy: SelectionPolicy = Field(
        default="strict_quality",
        alias="selectionPolicy",
    )
    normal_candidate_count: int = Field(
        ge=0,
        le=MAX_NORMAL_CANDIDATE_COUNT,
        alias="normalCandidateCount",
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
        expected_normal_candidate_count = min(
            self.normal.requested_count * len(self.normal.duration_bands),
            MAX_NORMAL_CANDIDATE_COUNT,
        )
        if self.normal_candidate_count != expected_normal_candidate_count:
            raise ValueError(
                "normalCandidateCount must equal "
                "min(normal requestedCount * durationBands count, 24)"
            )
        expected_short_candidate_count = min(
            self.short.requested_count * SHORT_CANDIDATE_MULTIPLIER,
            MAX_SHORT_CANDIDATE_COUNT,
        )
        if self.short_candidate_count != expected_short_candidate_count:
            raise ValueError("shortCandidateCount must equal min(short requestedCount * 3, 24)")
        return self


class CodexTopicBlockInput(_StrictModel):
    id: str = Field(pattern=r"^topic_\d{6}$")
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    summary: str = Field(min_length=1, max_length=MAX_TOPIC_SUMMARY_CHARS)
    segment_count: int = Field(ge=1, alias="segmentCount")
    question_cue: bool = Field(alias="questionCue")
    silence_before: float = Field(ge=0, allow_inf_nan=False, alias="silenceBefore")
    silence_after: float = Field(ge=0, allow_inf_nan=False, alias="silenceAfter")
    popularity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_range(self) -> CodexTopicBlockInput:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class CodexTopicSelectionRequest(_StrictModel):
    version: Literal[1] = 1
    prompt_version: Literal[CODEX_INITIAL_SELECTION_PROMPT_VERSION] = Field(
        default=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        alias="promptVersion",
    )
    phase: Literal["topic_selection"] = "topic_selection"
    job_id: str = Field(min_length=1, max_length=128, alias="jobId")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$", alias="inputHash")
    timestamp_semantics: Literal["source_absolute_seconds"] = Field(
        default="source_absolute_seconds",
        alias="timestampSemantics",
    )
    source_duration: float = Field(gt=0, allow_inf_nan=False, alias="sourceDuration")
    constraints: CodexSelectionConstraints
    topic_blocks: list[CodexTopicBlockInput] = Field(
        min_length=1,
        max_length=MAX_LOCAL_TOPIC_BLOCKS,
        alias="topicBlocks",
    )

    @model_validator(mode="after")
    def validate_topic_blocks(self) -> CodexTopicSelectionRequest:
        ids = [item.id for item in self.topic_blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("topic block IDs must be unique")
        if [(item.start, item.end) for item in self.topic_blocks] != sorted(
            (item.start, item.end) for item in self.topic_blocks
        ):
            raise ValueError("topic blocks must be ordered")
        if any(item.end > self.source_duration + SOURCE_TIME_TOLERANCE_SECONDS for item in self.topic_blocks):
            raise ValueError("topic block exceeds source duration")
        return self

    def prompt_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class CodexTopicChoice(_StrictModel):
    selection_id: str = Field(min_length=1, max_length=40, alias="selectionId")
    type: CandidateType
    topic_key: str = Field(min_length=1, max_length=80, alias="topicKey")
    topic_block_ids: list[str] = Field(
        min_length=1,
        max_length=8,
        alias="topicBlockIds",
    )
    reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class CodexTopicSelectionResponse(_StrictModel):
    version: Literal[1]
    prompt_version: Literal[CODEX_INITIAL_SELECTION_PROMPT_VERSION] = Field(
        alias="promptVersion",
    )
    job_id: str = Field(min_length=1, max_length=128, alias="jobId")
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$", alias="inputHash")
    thread_id: str | None = Field(min_length=1, max_length=128, alias="threadId")
    selected_topics: list[CodexTopicChoice] = Field(
        max_length=48,
        alias="selectedTopics",
    )
    warnings: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_unique_selections(self) -> CodexTopicSelectionResponse:
        ids = [item.selection_id for item in self.selected_topics]
        if len(ids) != len(set(ids)):
            raise ValueError("topic selection IDs must be unique")
        return self


class CodexSelectedTopicInput(_StrictModel):
    selection_id: str = Field(min_length=1, max_length=40, alias="selectionId")
    type: CandidateType
    topic_key: str = Field(min_length=1, max_length=80, alias="topicKey")
    topic_block_ids: list[str] = Field(
        min_length=1,
        max_length=8,
        alias="topicBlockIds",
    )
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    window_start: float = Field(ge=0, allow_inf_nan=False, alias="windowStart")
    window_end: float = Field(gt=0, allow_inf_nan=False, alias="windowEnd")
    reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_range(self) -> CodexSelectedTopicInput:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if self.window_end <= self.window_start:
            raise ValueError("windowEnd must be greater than windowStart")
        if self.window_start > self.start or self.window_end < self.end:
            raise ValueError("refinement window must contain the selected topic")
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
    phase: Literal["boundary_refinement"] = "boundary_refinement"
    selected_topics: list[CodexSelectedTopicInput] = Field(
        default_factory=list,
        max_length=48,
        alias="selectedTopics",
    )
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
    topic_key: str = Field(min_length=1, max_length=80, alias="topicKey")
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
    task: Literal["initial_clip_topic_selection", "initial_clip_selection"]
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$", alias="requestId")
    prompt: str = Field(min_length=1)
    response_schema: dict[str, Any] = Field(alias="responseSchema")
    images: list[str] = Field(default_factory=list, max_length=0)
    thread_scope: str = Field(min_length=1, max_length=128, alias="threadScope")
    thread_id: str | None = Field(default=None, alias="threadId")
    prompt_version: Literal[CODEX_INITIAL_SELECTION_PROMPT_VERSION] = Field(
        default=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        alias="promptVersion",
    )
    attempt: int = Field(default=1, ge=1, le=MAX_CODEX_INITIAL_SELECTION_ATTEMPTS)


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
    prompt_version: str | None = Field(
        default=None,
        max_length=100,
        alias="promptVersion",
    )
    attempt: int = Field(default=1, ge=1, le=10)
    bridge_build_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        alias="bridgeBuildFingerprint",
    )
    contract_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        alias="contractFingerprint",
    )
    task_schema_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        alias="taskSchemaFingerprint",
    )

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
    bridge_build_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        alias="bridgeBuildFingerprint",
    )
    contract_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        alias="contractFingerprint",
    )
    task_schema_fingerprints: dict[str, str] = Field(
        default_factory=dict,
        alias="taskSchemaFingerprints",
    )

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
    dropped_normal_candidates: list[CodexDroppedShortCandidate] = Field(
        default_factory=list,
        alias="droppedNormalCandidates",
    )
    dropped_short_candidates: list[CodexDroppedShortCandidate] = Field(
        default_factory=list,
        alias="droppedShortCandidates",
    )
    thread_id: str | None = Field(default=None, alias="threadId")
    prompt_version: str = Field(
        default=CODEX_INITIAL_SELECTION_PROMPT_VERSION,
        max_length=100,
        alias="promptVersion",
    )
    request_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",
        alias="requestId",
    )
    attempt_count: int = Field(default=1, ge=1, le=MAX_CODEX_INITIAL_SELECTION_ATTEMPTS, alias="attemptCount")
    host_error_code: str | None = Field(
        default=None,
        max_length=100,
        alias="hostErrorCode",
    )
    topic_block_count: int = Field(default=0, ge=0, alias="topicBlockCount")
    topic_summary_char_count: int = Field(
        default=0,
        ge=0,
        alias="topicSummaryCharCount",
    )
    refinement_transcript_segment_count: int = Field(
        default=0,
        ge=0,
        alias="refinementTranscriptSegmentCount",
    )
    refinement_transcript_char_count: int = Field(
        default=0,
        ge=0,
        alias="refinementTranscriptCharCount",
    )
    selection_stage: Literal["topic_selection", "boundary_refinement"] | None = Field(
        default=None,
        alias="selectionStage",
    )


@dataclass(frozen=True)
class CodexInitialSelectionResult:
    selection: CandidateSelection
    candidates: list[Candidate]
    summary: dict[str, Any]
    proposals: list[CodexClipProposal] = field(default_factory=list)
    duplicate_short_moment_keys: list[str] = field(default_factory=list)
    dropped_normal_candidates: list[CodexDroppedShortCandidate] = field(
        default_factory=list
    )
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


def codex_initial_selection_response_schema_sha256() -> str:
    encoded = json.dumps(
        codex_initial_selection_response_schema(),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def codex_topic_selection_response_schema() -> dict[str, Any]:
    return CodexTopicSelectionResponse.model_json_schema(by_alias=True)


def codex_topic_selection_response_schema_sha256() -> str:
    encoded = json.dumps(
        codex_topic_selection_response_schema(),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _compute_input_hash(request: BaseModel) -> str:
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


def compute_codex_initial_selection_input_hash(
    request: CodexInitialSelectionRequest,
) -> str:
    return _compute_input_hash(request)


def compute_codex_topic_selection_input_hash(
    request: CodexTopicSelectionRequest,
) -> str:
    return _compute_input_hash(request)


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
    value = _text_setting(settings, "selectionPolicy", "strict_quality")
    return "strict_quality" if value == "strict_quality" else "fill_requested"


def _duration_bands(
    minimum: float,
    maximum: float,
    bands: Sequence[tuple[float, float]],
) -> list[CodexDurationBand]:
    intersected = [
        CodexDurationBand(
            minDuration=max(minimum, band_minimum),
            maxDuration=min(maximum, band_maximum),
        )
        for band_minimum, band_maximum in bands
        if min(maximum, band_maximum) > max(minimum, band_minimum)
    ]
    if intersected:
        return intersected
    return [CodexDurationBand(minDuration=minimum, maxDuration=maximum)]


def _build_constraints(settings: dict[str, Any]) -> CodexSelectionConstraints:
    normal_minimum = _float_setting(settings, "normalMinDuration", 90.0)
    normal_maximum = _float_setting(settings, "normalMaxDuration", 600.0)
    short_minimum = _float_setting(settings, "shortMinDuration", 20.0)
    short_maximum = _float_setting(settings, "shortMaxDuration", 75.0)
    normal_requested_count = _int_setting(settings, "normalClipCount", 2)
    short_requested_count = _int_setting(settings, "shortCount", 3)
    normal_duration_bands = _duration_bands(
        normal_minimum,
        normal_maximum,
        ((90.0, 180.0), (180.0, 300.0), (300.0, 600.0)),
    )
    short_duration_bands = _duration_bands(
        short_minimum,
        short_maximum,
        ((20.0, 35.0), (35.0, 50.0), (50.0, 75.0)),
    )
    return CodexSelectionConstraints(
        normal=CodexClipTypeConstraints(
            requestedCount=normal_requested_count,
            minDuration=normal_minimum,
            maxDuration=normal_maximum,
            preset=_preset_setting(settings, "normalClipSelectionPreset"),
            guidance=_text_setting(settings, "normalClipGuidance"),
            durationBands=normal_duration_bands,
        ),
        short=CodexClipTypeConstraints(
            requestedCount=short_requested_count,
            minDuration=short_minimum,
            maxDuration=short_maximum,
            preset=_preset_setting(settings, "shortClipSelectionPreset"),
            guidance=_text_setting(settings, "shortClipGuidance"),
            durationBands=short_duration_bands,
        ),
        normalCandidateCount=min(
            normal_requested_count * len(normal_duration_bands),
            MAX_NORMAL_CANDIDATE_COUNT,
        ),
        shortCandidateCount=min(
            short_requested_count * SHORT_CANDIDATE_MULTIPLIER,
            MAX_SHORT_CANDIDATE_COUNT,
        ),
        selectionPolicy=_selection_policy_setting(settings),
        heatmapIntervalMode=_bool_setting(settings, "heatmapIntervalMode", False),
        maxOverlapRatio=_float_setting(settings, "maxOverlapRatio", 0.8),
        crossTypeOverlapDedupe=_bool_setting(settings, "crossTypeOverlapDedupe", False),
        excludeIntroOutro=_bool_setting(settings, "excludeIntroOutro", True),
        excludePromotionalContent=_bool_setting(settings, "excludePromotionalContent", False),
    )


def _selection_time_range(start: float, end: float) -> dict[str, float]:
    rounded_start, rounded_end = round(float(start), 3), round(float(end), 3)
    # Keep the source precision when millisecond rounding would erase a valid interval.
    if end > start and rounded_end <= rounded_start:
        return {"start": float(start), "end": float(end)}
    return {"start": rounded_start, "end": rounded_end}


def build_codex_initial_selection_request(
    *,
    job_id: str,
    transcript_segments: Sequence[TranscriptSegment],
    heatmap_segments: Sequence[HeatmapSegment],
    video_duration: float,
    settings: dict[str, Any],
) -> CodexInitialSelectionRequest:
    clean_transcript = sorted(
        (segment for segment in unused_items(transcript_segments, settings) if segment.text.strip()),
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
        if end <= start or overlaps_used(start, end, used_ranges(settings)):
            continue
        clean_heatmap.append(
            HeatmapSegment(
                start_time=start,
                end_time=end,
                value=float(segment.value),
            )
        )
    constraints = _build_constraints(settings)
    if used_ranges(settings):
        guidance = "過去に使用した場面は入力から除外済みです。欠落した時間帯をまたがず、未使用の連続した区間だけを選んでください。"
        constraints = constraints.model_copy(update={
            clip_type: getattr(constraints, clip_type).model_copy(update={
                "guidance": (guidance + "\n" + getattr(constraints, clip_type).guidance)[:1000],
            })
            for clip_type in ("normal", "short")
        })
    request = CodexInitialSelectionRequest(
        jobId=job_id,
        requestId=uuid4().hex,
        inputHash="0" * 64,
        sourceDuration=video_duration,
        constraints=constraints,
        transcript=[
            CodexTranscriptInput(
                id=f"seg_{index:06d}",
                **_selection_time_range(segment.start, segment.end),
                text=segment.text.strip(),
                confidence=segment.confidence,
            )
            for index, segment in enumerate(clean_transcript, start=1)
        ],
        heatmap=[
            CodexHeatmapInput(
                id=f"heat_{index:06d}",
                **_selection_time_range(segment.start_time, segment.end_time),
                value=float(segment.value),
            )
            for index, segment in enumerate(clean_heatmap, start=1)
        ],
    )
    return request.model_copy(update={"input_hash": compute_codex_initial_selection_input_hash(request)})


def _has_question_cue(text: str) -> bool:
    return any(cue in text for cue in ("?", "？", "なぜ", "どうして", "って何", "とは"))


def _has_completion_cue(text: str) -> bool:
    return any(
        cue in text
        for cue in ("まとめると", "結論", "ということです", "という話でした", "答えは")
    )


def _topic_summary(segments: Sequence[CodexTranscriptInput]) -> str:
    texts = [" ".join(item.text.split()) for item in segments if item.text.strip()]
    joined = " ".join(texts)
    if len(joined) <= MAX_TOPIC_SUMMARY_CHARS:
        return joined

    sample_indices = [0, len(texts) // 4, len(texts) // 2, (len(texts) * 3) // 4, len(texts) - 1]
    question_index = next(
        (
            index
            for index, text in enumerate(texts)
            if _has_question_cue(text)
        ),
        None,
    )
    if question_index is not None:
        sample_indices.insert(1, question_index)
    ordered_indices = list(dict.fromkeys(sample_indices))
    separator = " / "
    per_piece = max(
        20,
        (MAX_TOPIC_SUMMARY_CHARS - len(separator) * (len(ordered_indices) - 1))
        // len(ordered_indices),
    )
    pieces: list[str] = []
    for index in ordered_indices:
        text = texts[index]
        if index == len(texts) - 1 and len(text) > per_piece:
            pieces.append(text[-per_piece:])
        else:
            pieces.append(text[:per_piece])
    return separator.join(pieces)[:MAX_TOPIC_SUMMARY_CHARS]


def _topic_popularity(
    start: float,
    end: float,
    heatmap: Sequence[CodexHeatmapInput],
) -> float | None:
    overlaps = [
        (max(0.0, min(end, item.end) - max(start, item.start)), item.value)
        for item in heatmap
        if _overlaps(start, end, item.start, item.end)
    ]
    overlap_seconds = sum(seconds for seconds, _ in overlaps)
    if overlap_seconds <= 0:
        return None
    return round(
        sum(seconds * value for seconds, value in overlaps) / overlap_seconds,
        6,
    )


def build_local_topic_blocks(
    request: CodexInitialSelectionRequest,
) -> list[CodexTopicBlockInput]:
    target_seconds = max(
        LOCAL_TOPIC_BLOCK_TARGET_SECONDS,
        request.source_duration / max(1, MAX_LOCAL_TOPIC_BLOCKS - 10),
    )
    groups: list[list[CodexTranscriptInput]] = []
    current: list[CodexTranscriptInput] = []
    for segment in request.transcript:
        if current:
            previous = current[-1]
            gap = max(0.0, segment.start - previous.end)
            current_duration = previous.end - current[0].start
            next_duration = segment.end - current[0].start
            punctuation_boundary = previous.text.rstrip().endswith(("。", "！", "!", "？", "?"))
            semantic_boundary = (
                _has_question_cue(segment.text)
                or _has_completion_cue(previous.text)
            ) and current_duration >= max(
                LOCAL_TOPIC_BLOCK_MIN_SECONDS,
                target_seconds * 0.5,
            )
            should_split = (
                gap >= LOCAL_TOPIC_SILENCE_SPLIT_SECONDS
                and current_duration >= LOCAL_TOPIC_BLOCK_MIN_SECONDS
            ) or (
                next_duration >= target_seconds
                and current_duration >= LOCAL_TOPIC_BLOCK_MIN_SECONDS
                and (gap >= 0.8 or punctuation_boundary)
            ) or next_duration >= target_seconds * 1.5 or semantic_boundary
            if should_split:
                groups.append(current)
                current = []
        current.append(segment)
    if current:
        groups.append(current)

    while len(groups) > MAX_LOCAL_TOPIC_BLOCKS:
        compacted: list[list[CodexTranscriptInput]] = []
        for index in range(0, len(groups), 2):
            combined = list(groups[index])
            if index + 1 < len(groups):
                combined.extend(groups[index + 1])
            compacted.append(combined)
        groups = compacted

    blocks: list[CodexTopicBlockInput] = []
    for index, group in enumerate(groups, start=1):
        start = group[0].start
        end = group[-1].end
        previous_end = groups[index - 2][-1].end if index > 1 else start
        next_start = groups[index][0].start if index < len(groups) else end
        summary = _topic_summary(group)
        blocks.append(
            CodexTopicBlockInput(
                id=f"topic_{index:06d}",
                start=start,
                end=end,
                summary=summary,
                segmentCount=len(group),
                questionCue=any(
                    _has_question_cue(item.text) for item in group
                ),
                silenceBefore=round(max(0.0, start - previous_end), 3),
                silenceAfter=round(max(0.0, next_start - end), 3),
                popularity=_topic_popularity(start, end, request.heatmap),
            )
        )
    return blocks


def build_codex_topic_selection_request(
    request: CodexInitialSelectionRequest,
) -> CodexTopicSelectionRequest:
    topic_request = CodexTopicSelectionRequest(
        jobId=request.job_id,
        requestId=uuid4().hex,
        inputHash="0" * 64,
        sourceDuration=request.source_duration,
        constraints=request.constraints,
        topicBlocks=build_local_topic_blocks(request),
    )
    return topic_request.model_copy(
        update={"input_hash": compute_codex_topic_selection_input_hash(topic_request)}
    )


def _time_range_overlap_ratio(
    start: float,
    end: float,
    other_start: float,
    other_end: float,
) -> float:
    overlap = max(0.0, min(end, other_end) - max(start, other_start))
    shortest = min(end - start, other_end - other_start)
    if shortest <= 0:
        return 0.0
    return overlap / shortest


def _resolve_topic_block_ids(
    ids: list[str],
    block_order: dict[str, int],
) -> list[str]:
    resolved: list[str] = []
    for raw_id in ids:
        if raw_id in block_order:
            resolved.append(raw_id)
            continue
        # A model can append its own prose to an otherwise exact block ID.
        # Only recover the unambiguous ID from this request; never invent one.
        match = re.fullmatch(r"(topic_[0-9]{6})\s+(.+)", raw_id, flags=re.DOTALL)
        if (
            match is None
            or match.group(1) not in block_order
            or not match.group(2).strip()
            or re.search(r"\btopic_[0-9]{6}\b", match.group(2))
        ):
            raise CodexInitialSelectionError(
                "codex_topic_selection_block_unknown",
                "Codex話題選定のブロックが入力に存在しません。",
            )
        resolved.append(match.group(1))
    if len(resolved) != len(set(resolved)):
        raise CodexInitialSelectionError(
            "codex_topic_selection_duplicate_block",
            "Codex話題選定に重複した話題ブロックがあります。",
        )
    indices = [block_order[item_id] for item_id in resolved]
    if indices != sorted(indices):
        raise CodexInitialSelectionError(
            "codex_topic_selection_block_order_invalid",
            "Codex話題選定のブロック順が不正です。",
        )
    if indices != list(range(indices[0], indices[0] + len(indices))):
        raise CodexInitialSelectionError(
            "codex_topic_selection_block_not_contiguous",
            "Codex話題選定のブロックが連続していません。",
        )
    return resolved


def _validate_topic_selection_response(
    request: CodexTopicSelectionRequest,
    response: CodexTopicSelectionResponse,
) -> list[CodexTopicChoice]:
    if response.job_id != request.job_id:
        raise CodexInitialSelectionError(
            "codex_topic_selection_job_mismatch",
            "Codex話題選定のjobが一致しません。",
        )
    if response.request_id != request.request_id:
        raise CodexInitialSelectionError(
            "codex_topic_selection_request_mismatch",
            "Codex話題選定のrequestが一致しません。",
        )
    if response.input_hash != request.input_hash:
        raise CodexInitialSelectionError(
            "codex_topic_selection_hash_mismatch",
            "Codex話題選定の入力が更新されています。",
        )

    block_order = {item.id: index for index, item in enumerate(request.topic_blocks)}
    block_by_id = {item.id: item for item in request.topic_blocks}
    selected: list[CodexTopicChoice] = []
    first_invalid_choice: CodexInitialSelectionError | None = None
    used_normal_topic_keys: set[str] = set()
    used_normal_block_ids: set[str] = set()
    used_normal_ranges: list[tuple[float, float]] = []
    counts: dict[CandidateType, int] = {"normal": 0, "short": 0}
    limits: dict[CandidateType, int] = {
        "normal": request.constraints.normal_candidate_count,
        "short": request.constraints.short_candidate_count,
    }
    for choice in response.selected_topics:
        if choice.confidence < CODEX_STRICT_QUALITY_MIN_CONFIDENCE:
            continue
        if counts[choice.type] >= limits[choice.type]:
            continue
        try:
            resolved_ids = _resolve_topic_block_ids(choice.topic_block_ids, block_order)
        except CodexInitialSelectionError as exc:
            first_invalid_choice = first_invalid_choice or exc
            continue
        choice = choice.model_copy(update={"topic_block_ids": resolved_ids})
        topic_key = choice.topic_key.casefold()
        if choice.type == "normal":
            blocks = [block_by_id[item_id] for item_id in choice.topic_block_ids]
            topic_start = min(item.start for item in blocks)
            topic_end = max(item.end for item in blocks)
            if topic_key in used_normal_topic_keys:
                continue
            if used_normal_block_ids.intersection(choice.topic_block_ids):
                continue
            if any(
                _time_range_overlap_ratio(topic_start, topic_end, start, end) >= 0.5
                for start, end in used_normal_ranges
            ):
                continue
        selected.append(choice)
        counts[choice.type] += 1
        if choice.type == "normal":
            used_normal_topic_keys.add(topic_key)
            used_normal_block_ids.update(choice.topic_block_ids)
            used_normal_ranges.append((topic_start, topic_end))
    if not selected and first_invalid_choice is not None:
        raise first_invalid_choice
    return selected


def _trim_transcript_to_budget(
    segments: Sequence[CodexTranscriptInput],
    budget: int,
) -> list[CodexTranscriptInput]:
    total = sum(len(item.text) for item in segments)
    if total <= budget:
        return list(segments)
    head_budget = budget // 2
    tail_budget = budget - head_budget
    head: list[CodexTranscriptInput] = []
    used = 0
    for item in segments:
        if head and used + len(item.text) > head_budget:
            break
        head.append(item)
        used += len(item.text)
    tail: list[CodexTranscriptInput] = []
    used = 0
    head_ids = {item.id for item in head}
    for item in reversed(segments):
        if item.id in head_ids:
            continue
        if tail and used + len(item.text) > tail_budget:
            break
        tail.append(item)
        used += len(item.text)
    return sorted([*head, *tail], key=lambda item: (item.start, item.end))


def _refinement_window(
    *,
    topic_start: float,
    topic_end: float,
    source_duration: float,
    type_constraints: CodexClipTypeConstraints,
    candidate_type: CandidateType,
) -> tuple[float, float]:
    context = (
        NORMAL_REFINEMENT_CONTEXT_SECONDS
        if candidate_type == "normal"
        else SHORT_REFINEMENT_CONTEXT_SECONDS
    )
    window_start = max(0.0, topic_start - context)
    window_end = min(source_duration, topic_end + context)
    if candidate_type != "normal":
        return window_start, window_end

    desired_duration = min(
        source_duration,
        max(type_constraints.max_duration, window_end - window_start),
    )
    missing = max(0.0, desired_duration - (window_end - window_start))
    left_extra = min(window_start, missing / 2)
    window_start -= left_extra
    missing -= left_extra
    right_extra = min(source_duration - window_end, missing)
    window_end += right_extra
    missing -= right_extra
    if missing > 0:
        window_start -= min(window_start, missing)
    return window_start, window_end


def build_codex_boundary_refinement_request(
    source_request: CodexInitialSelectionRequest,
    topic_request: CodexTopicSelectionRequest,
    topic_response: CodexTopicSelectionResponse,
) -> CodexInitialSelectionRequest | None:
    choices = _validate_topic_selection_response(topic_request, topic_response)
    if not choices:
        return None
    block_by_id = {item.id: item for item in topic_request.topic_blocks}
    selected_topics: list[CodexSelectedTopicInput] = []
    transcript_ids: set[str] = set()
    windows: list[tuple[float, float]] = []
    per_topic_budget = max(1, MAX_REFINEMENT_TRANSCRIPT_CHARS // len(choices))
    for choice in choices:
        blocks = [block_by_id[item_id] for item_id in choice.topic_block_ids]
        topic_start = min(item.start for item in blocks)
        topic_end = max(item.end for item in blocks)
        type_constraints = (
            source_request.constraints.normal
            if choice.type == "normal"
            else source_request.constraints.short
        )
        window = _refinement_window(
            topic_start=topic_start,
            topic_end=topic_end,
            source_duration=source_request.source_duration,
            type_constraints=type_constraints,
            candidate_type=choice.type,
        )
        selected_topics.append(
            CodexSelectedTopicInput(
                selectionId=choice.selection_id,
                type=choice.type,
                topicKey=choice.topic_key,
                topicBlockIds=choice.topic_block_ids,
                start=topic_start,
                end=topic_end,
                windowStart=window[0],
                windowEnd=window[1],
                reason=choice.reason,
                confidence=choice.confidence,
            )
        )
        windows.append(window)
        topic_segments = [
            item
            for item in source_request.transcript
            if _overlaps(window[0], window[1], item.start, item.end)
        ]
        transcript_ids.update(
            item.id
            for item in _trim_transcript_to_budget(topic_segments, per_topic_budget)
        )

    transcript = [
        item for item in source_request.transcript if item.id in transcript_ids
    ]
    transcript = _trim_transcript_to_budget(
        transcript,
        MAX_REFINEMENT_TRANSCRIPT_CHARS,
    )
    retained_ids = {item.id for item in transcript}
    if not retained_ids:
        raise CodexInitialSelectionError(
            "codex_boundary_refinement_transcript_empty",
            "選定話題の周辺に境界調整用字幕がありません。",
        )
    heatmap = [
        item
        for item in source_request.heatmap
        if any(_overlaps(start, end, item.start, item.end) for start, end in windows)
    ][:256]
    refinement_request = CodexInitialSelectionRequest(
        jobId=source_request.job_id,
        requestId=uuid4().hex,
        inputHash="0" * 64,
        sourceDuration=source_request.source_duration,
        constraints=source_request.constraints,
        selectedTopics=selected_topics,
        transcript=transcript,
        heatmap=heatmap,
    )
    return refinement_request.model_copy(
        update={
            "input_hash": compute_codex_initial_selection_input_hash(
                refinement_request
            )
        }
    )


def _prompt_with_payload(
    prompt: str,
    payload: dict[str, Any],
    *,
    max_chars: int,
) -> str:
    request_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    value = f"{prompt}\n\n入力JSON:\n{request_json}"
    if len(value) > max_chars:
        raise CodexInitialSelectionError(
            "codex_initial_selection_prompt_too_large",
            "Codex選定入力が段階別の文字数上限を超えています。",
        )
    return value


def _topic_bridge_envelope(
    request: CodexTopicSelectionRequest,
    *,
    thread_id: str | None,
    attempt: int = 1,
) -> CodexInitialSelectionBridgeEnvelope:
    return CodexInitialSelectionBridgeEnvelope(
        task=CODEX_TOPIC_SELECTION_TASK,
        requestId=request.request_id,
        prompt=_prompt_with_payload(
            CODEX_TOPIC_SELECTION_PROMPT,
            request.prompt_payload(),
            max_chars=MAX_TOPIC_SELECTION_PROMPT_CHARS,
        ),
        responseSchema=codex_topic_selection_response_schema(),
        images=[],
        threadScope=request.job_id,
        threadId=thread_id,
        promptVersion=request.prompt_version,
        attempt=attempt,
    )


def _bridge_envelope(
    request: CodexInitialSelectionRequest,
    *,
    thread_id: str | None,
    attempt: int = 1,
) -> CodexInitialSelectionBridgeEnvelope:
    return CodexInitialSelectionBridgeEnvelope(
        task="initial_clip_selection",
        requestId=request.request_id,
        prompt=_prompt_with_payload(
            CODEX_INITIAL_SELECTION_PROMPT,
            request.prompt_payload(),
            max_chars=MAX_REFINEMENT_PROMPT_CHARS,
        ),
        responseSchema=codex_initial_selection_response_schema(),
        images=[],
        threadScope=request.job_id,
        threadId=thread_id,
        promptVersion=request.prompt_version,
        attempt=attempt,
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
        self._request_attempts: dict[str, int] = {}

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
        attempt: int = 1,
    ) -> Path:
        path = _write_json_atomic(
            self.request_path(request.request_id),
            _bridge_envelope(
                request,
                thread_id=thread_id,
                attempt=attempt,
            ).model_dump(
                by_alias=True,
                mode="json",
            ),
        )
        self._request_created_at[request.request_id] = self.wall_time_func()
        self._request_attempts[request.request_id] = attempt
        return path

    def write_topic_request(
        self,
        request: CodexTopicSelectionRequest,
        *,
        thread_id: str | None = None,
        attempt: int = 1,
    ) -> Path:
        path = _write_json_atomic(
            self.request_path(request.request_id),
            _topic_bridge_envelope(
                request,
                thread_id=thread_id,
                attempt=attempt,
            ).model_dump(by_alias=True, mode="json"),
        )
        self._request_created_at[request.request_id] = self.wall_time_func()
        self._request_attempts[request.request_id] = attempt
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

    def ensure_contract_compatible(self) -> None:
        status = self._read_bridge_status()
        if status is None or status.state != "ready":
            return
        expected_schemas = {
            CODEX_TOPIC_SELECTION_TASK: codex_topic_selection_response_schema_sha256(),
            "initial_clip_selection": codex_initial_selection_response_schema_sha256(),
        }
        for task, expected in expected_schemas.items():
            actual = status.task_schema_fingerprints.get(task)
            if actual is None:
                raise CodexInitialSelectionError(
                    "codex_initial_selection_bridge_contract_mismatch",
                    "Codex bridgeの契約情報が古いため再起動が必要です。",
                    host_error_code="bridge_contract_metadata_missing",
                )
            if actual != expected:
                raise CodexInitialSelectionError(
                    "codex_initial_selection_bridge_contract_mismatch",
                    "Codex bridgeのschemaが現在の選定処理と一致しません。",
                    host_error_code="response_schema_contract_mismatch",
                )

    def _bridge_unavailable_reason(
        self,
        request: CodexInitialSelectionRequest | CodexTopicSelectionRequest,
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

    def _read_host_output(
        self,
        request: CodexInitialSelectionRequest | CodexTopicSelectionRequest,
    ) -> tuple[dict[str, Any], str | None] | None:
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
                host_error_code=(
                    host_response.error.code if host_response.error is not None else None
                ),
                request_id=request.request_id,
                attempt_count=host_response.attempt,
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
        return output_payload, host_response.thread_id

    def _read_response_file(
        self,
        request: CodexInitialSelectionRequest,
    ) -> CodexInitialSelectionResponse | None:
        host_output = self._read_host_output(request)
        if host_output is None:
            return None
        output_payload, _ = host_output
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

    def _read_topic_response_file(
        self,
        request: CodexTopicSelectionRequest,
    ) -> CodexTopicSelectionResponse | None:
        host_output = self._read_host_output(request)
        if host_output is None:
            return None
        output_payload, _ = host_output
        try:
            response = CodexTopicSelectionResponse.model_validate(output_payload)
        except ValidationError as exc:
            raise CodexInitialSelectionError(
                "codex_topic_selection_output_invalid",
                "Codex話題選定の出力形式が不正です。",
            ) from exc
        _validate_topic_selection_response(request, response)
        return response

    def _wait_for_selection_response(
        self,
        request: CodexInitialSelectionRequest | CodexTopicSelectionRequest,
        *,
        response_reader: Callable[
            [CodexInitialSelectionRequest | CodexTopicSelectionRequest],
            CodexInitialSelectionResponse | CodexTopicSelectionResponse | None,
        ],
        selection_stage: Literal["topic_selection", "boundary_refinement"],
        timeout_seconds: float,
        poll_seconds: float,
        heartbeat: Callable[[dict[str, Any]], None] | None,
    ) -> CodexInitialSelectionResponse | CodexTopicSelectionResponse:
        timeout = max(0.01, float(timeout_seconds))
        poll = min(max(0.01, float(poll_seconds)), 5.0)
        started_at = self.monotonic_func()
        next_heartbeat = started_at
        unavailable_since: float | None = None
        while True:
            if self.response_path(request.request_id).is_file():
                response = response_reader(request)
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
                    bridge_status = self._read_bridge_status()
                    raise CodexInitialSelectionError(
                        "codex_initial_selection_bridge_unavailable",
                        "Codex bridgeを利用できないため、従来選定へ切り替えます。",
                        host_error_code=(
                            bridge_status.error_code
                            if bridge_status is not None
                            and bridge_status.error_code is not None
                            else unavailable_reason
                        ),
                        request_id=request.request_id,
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
                        "promptVersion": request.prompt_version,
                        "requestId": request.request_id,
                        "attemptCount": self._request_attempts.get(request.request_id, 1),
                        "hostErrorCode": None,
                        "selectionStage": selection_stage,
                    }
                )
                next_heartbeat = now + HEARTBEAT_INTERVAL_SECONDS
            self.sleep_func(min(poll, max(0.01, timeout - (now - started_at))))

    def wait_for_response(
        self,
        request: CodexInitialSelectionRequest,
        *,
        timeout_seconds: float = DEFAULT_RESPONSE_TIMEOUT_SECONDS,
        poll_seconds: float = DEFAULT_RESPONSE_POLL_SECONDS,
        heartbeat: Callable[[dict[str, Any]], None] | None = None,
    ) -> CodexInitialSelectionResponse:
        response = self._wait_for_selection_response(
            request,
            response_reader=self._read_response_file,  # type: ignore[arg-type]
            selection_stage="boundary_refinement",
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
            heartbeat=heartbeat,
        )
        assert isinstance(response, CodexInitialSelectionResponse)
        return response

    def wait_for_topic_response(
        self,
        request: CodexTopicSelectionRequest,
        *,
        timeout_seconds: float = DEFAULT_RESPONSE_TIMEOUT_SECONDS,
        poll_seconds: float = DEFAULT_RESPONSE_POLL_SECONDS,
        heartbeat: Callable[[dict[str, Any]], None] | None = None,
    ) -> CodexTopicSelectionResponse:
        response = self._wait_for_selection_response(
            request,
            response_reader=self._read_topic_response_file,  # type: ignore[arg-type]
            selection_stage="topic_selection",
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
            heartbeat=heartbeat,
        )
        assert isinstance(response, CodexTopicSelectionResponse)
        return response


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


def _validate_proposal_topic_metadata(
    proposal: CodexClipProposal,
    request: CodexInitialSelectionRequest,
) -> None:
    if not request.selected_topics:
        return
    matching_topics = [
        item
        for item in request.selected_topics
        if item.type == proposal.type
        and item.topic_key.casefold() == proposal.topic_key.casefold()
    ]
    if not matching_topics:
        raise CodexInitialSelectionError(
            "codex_initial_selection_topic_unknown",
            "Codex初期選定のtopicKeyが第1段階の選定結果に存在しません。",
        )
    if not any(
        proposal.start >= item.window_start - 0.001
        and proposal.end <= item.window_end + 0.001
        for item in matching_topics
    ):
        raise CodexInitialSelectionError(
            "codex_initial_selection_topic_range_invalid",
            "Codex初期選定の範囲が選定話題の周辺を超えています。",
        )


def _proposal_candidate(
    proposal: CodexClipProposal,
    *,
    request: CodexInitialSelectionRequest,
) -> Candidate:
    _validate_proposal_moment_metadata(proposal)
    _validate_proposal_topic_metadata(proposal, request)
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
            "topic_key": proposal.topic_key,
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


def _select_initial_normal_pairs(
    pairs: Sequence[tuple[CodexClipProposal, Candidate]],
    *,
    requested_count: int,
    max_overlap_ratio: float,
) -> list[tuple[CodexClipProposal, Candidate]]:
    selected: list[tuple[CodexClipProposal, Candidate]] = []
    used_topic_keys: set[str] = set()
    effective_overlap_ratio = min(max_overlap_ratio, 0.5)
    for proposal, candidate in sorted(
        pairs,
        key=lambda item: (-item[0].confidence, item[0].proposal_id),
    ):
        if len(selected) >= requested_count:
            break
        topic_key = proposal.topic_key.casefold()
        if topic_key in used_topic_keys:
            continue
        if any(
            time_overlap_ratio(candidate, selected_candidate)
            >= effective_overlap_ratio
            for _, selected_candidate in selected
        ):
            continue
        selected.append((proposal, candidate))
        used_topic_keys.add(topic_key)
    return selected


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


def _duration_band_index(
    duration: float,
    bands: Sequence[CodexDurationBand],
) -> int | None:
    for index, band in enumerate(bands):
        is_last = index == len(bands) - 1
        if duration >= band.minimum - 0.001 and (
            duration < band.maximum
            or (is_last and duration <= band.maximum + 0.001)
        ):
            return index
    return None


def _retain_duration_band_candidate_pool(
    pairs: Sequence[tuple[CodexClipProposal, Candidate]],
    *,
    selected_pairs: Sequence[tuple[CodexClipProposal, Candidate]],
    candidate_limit: int,
    duration_bands: Sequence[CodexDurationBand],
) -> list[tuple[CodexClipProposal, Candidate]]:
    if candidate_limit <= 0:
        return []
    ranked = sorted(
        pairs,
        key=lambda item: (-item[0].confidence, item[0].proposal_id),
    )
    pair_by_id = {proposal.proposal_id: (proposal, candidate) for proposal, candidate in ranked}
    retained: list[tuple[CodexClipProposal, Candidate]] = []
    retained_ids: set[str] = set()
    represented_bands: set[int] = set()

    def retain(pair: tuple[CodexClipProposal, Candidate]) -> None:
        proposal, candidate = pair
        if proposal.proposal_id in retained_ids or len(retained) >= candidate_limit:
            return
        retained.append(pair)
        retained_ids.add(proposal.proposal_id)
        band_index = _duration_band_index(candidate.duration, duration_bands)
        if band_index is not None:
            represented_bands.add(band_index)

    for proposal, _ in selected_pairs:
        pair = pair_by_id.get(proposal.proposal_id)
        if pair is not None:
            retain(pair)

    for band_index in range(len(duration_bands)):
        if band_index in represented_bands:
            continue
        representative = next(
            (
                pair
                for pair in ranked
                if pair[0].proposal_id not in retained_ids
                and _duration_band_index(pair[1].duration, duration_bands)
                == band_index
            ),
            None,
        )
        if representative is not None:
            retain(representative)

    for pair in ranked:
        retain(pair)
    return retained


def convert_codex_initial_selection_response(
    request: CodexInitialSelectionRequest,
    response: CodexInitialSelectionResponse,
    *,
    attempt_count: int = 1,
    topic_block_count: int = 0,
    topic_summary_char_count: int = 0,
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

    requested_normal = request.constraints.normal.requested_count
    requested_short = request.constraints.short.requested_count
    response = response.model_copy(
        update={
            "selected_clips": [
                item
                for item in response.selected_clips
                if item.confidence >= CODEX_STRICT_QUALITY_MIN_CONFIDENCE
            ]
        }
    )

    proposals: list[CodexClipProposal] = []
    candidates: list[Candidate] = []
    dropped_normal_candidates: list[CodexDroppedShortCandidate] = []
    dropped_short_candidates: list[CodexDroppedShortCandidate] = []
    for proposal in response.selected_clips:
        try:
            candidate = _proposal_candidate(proposal, request=request)
        except CodexInitialSelectionError as exc:
            dropped_candidates = (
                dropped_normal_candidates
                if proposal.type == "normal"
                else dropped_short_candidates
            )
            dropped_candidates.append(
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
    selected_normal_pairs = _select_initial_normal_pairs(
        normal_pairs,
        requested_count=requested_normal,
        max_overlap_ratio=request.constraints.max_overlap_ratio,
    )
    normal_candidates = [item[1] for item in selected_normal_pairs]
    selected_short_pairs = _select_initial_short_pairs(
        short_pairs,
        requested_count=requested_short,
        normal_candidates=normal_candidates,
        max_overlap_ratio=request.constraints.max_overlap_ratio,
        cross_type_overlap_dedupe=request.constraints.cross_type_overlap_dedupe,
    )
    short_candidates = [item[1] for item in selected_short_pairs]
    retained_normal_pairs = _retain_duration_band_candidate_pool(
        normal_pairs,
        selected_pairs=selected_normal_pairs,
        candidate_limit=request.constraints.normal_candidate_count,
        duration_bands=request.constraints.normal.duration_bands,
    )
    retained_short_pairs = _retain_duration_band_candidate_pool(
        short_pairs,
        selected_pairs=selected_short_pairs,
        candidate_limit=request.constraints.short_candidate_count,
        duration_bands=request.constraints.short.duration_bands,
    )
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
        droppedNormalCandidates=dropped_normal_candidates,
        droppedShortCandidates=dropped_short_candidates,
        threadId=response.thread_id,
        promptVersion=request.prompt_version,
        requestId=request.request_id,
        attemptCount=attempt_count,
        hostErrorCode=None,
        topicBlockCount=topic_block_count,
        topicSummaryCharCount=topic_summary_char_count,
        refinementTranscriptSegmentCount=len(request.transcript),
        refinementTranscriptCharCount=sum(len(item.text) for item in request.transcript),
    )
    retained_pairs = [*retained_normal_pairs, *retained_short_pairs]
    retained_proposals = [item[0] for item in retained_pairs]
    retained_candidates = [item[1] for item in retained_pairs]
    return CodexInitialSelectionResult(
        selection=selection,
        candidates=retained_candidates,
        summary=summary_model.model_dump(by_alias=True, mode="json"),
        proposals=retained_proposals,
        duplicate_short_moment_keys=find_duplicate_short_moment_keys(
            retained_proposals
        ),
        dropped_normal_candidates=dropped_normal_candidates,
        dropped_short_candidates=dropped_short_candidates,
    )


def _retry_request(
    request: CodexInitialSelectionRequest,
) -> CodexInitialSelectionRequest:
    retried = request.model_copy(
        update={
            "request_id": uuid4().hex,
            "input_hash": "0" * 64,
        }
    )
    return retried.model_copy(
        update={
            "input_hash": compute_codex_initial_selection_input_hash(retried),
        }
    )


def _retry_topic_request(
    request: CodexTopicSelectionRequest,
) -> CodexTopicSelectionRequest:
    retried = request.model_copy(
        update={
            "request_id": uuid4().hex,
            "input_hash": "0" * 64,
        }
    )
    return retried.model_copy(
        update={
            "input_hash": compute_codex_topic_selection_input_hash(retried),
        }
    )


def _empty_quality_result(
    source_request: CodexInitialSelectionRequest,
    topic_request: CodexTopicSelectionRequest,
    topic_response: CodexTopicSelectionResponse,
    *,
    attempt_count: int,
) -> CodexInitialSelectionResult:
    selection = CandidateSelection(
        normalClips=[],
        shorts=[],
        selectionPolicy=source_request.constraints.selection_policy,
        requestedNormalCount=source_request.constraints.normal.requested_count,
        requestedShortCount=source_request.constraints.short.requested_count,
    )
    summary = CodexInitialSelectionSummary(
        status="completed",
        fallbackUsed=False,
        error=None,
        requestedNormalCount=source_request.constraints.normal.requested_count,
        requestedShortCount=source_request.constraints.short.requested_count,
        selectedNormalCount=0,
        selectedShortCount=0,
        threadId=topic_response.thread_id,
        promptVersion=source_request.prompt_version,
        requestId=topic_request.request_id,
        attemptCount=attempt_count,
        hostErrorCode=None,
        topicBlockCount=len(topic_request.topic_blocks),
        topicSummaryCharCount=sum(
            len(item.summary) for item in topic_request.topic_blocks
        ),
        refinementTranscriptSegmentCount=0,
        refinementTranscriptCharCount=0,
        selectionStage="topic_selection",
    )
    return CodexInitialSelectionResult(
        selection=selection,
        candidates=[],
        summary=summary.model_dump(by_alias=True, mode="json"),
    )


def _is_retryable_bridge_error(error: CodexInitialSelectionError) -> bool:
    if error.host_error_code in RETRYABLE_BRIDGE_ERROR_CODES:
        return True
    return error.code in {
        "codex_initial_selection_timeout",
        "codex_initial_selection_bridge_unavailable",
        "codex_initial_selection_bridge_contract_mismatch",
    }


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
        source_request = build_codex_initial_selection_request(
            job_id=job_id,
            transcript_segments=transcript_segments,
            heatmap_segments=heatmap_segments,
            video_duration=video_duration,
            settings=settings,
        )
        topic_request = build_codex_topic_selection_request(source_request)
        bridge = CodexInitialSelectionSharedFileBridge(storage_root)
        thread_id = _text_setting(settings, "codexSelectionThreadId") or None
        topic_attempt = 1
        topic_response: CodexTopicSelectionResponse | None = None
        for attempt in range(1, MAX_CODEX_INITIAL_SELECTION_ATTEMPTS + 1):
            try:
                bridge.ensure_contract_compatible()
                bridge.write_topic_request(
                    topic_request,
                    thread_id=thread_id,
                    attempt=attempt,
                )
                topic_response = bridge.wait_for_topic_response(
                    topic_request,
                    timeout_seconds=timeout_seconds,
                    poll_seconds=poll_seconds,
                    heartbeat=heartbeat,
                )
                topic_attempt = attempt
                break
            except CodexInitialSelectionError as exc:
                exc.request_id = topic_request.request_id
                exc.attempt_count = attempt
                if (
                    attempt < MAX_CODEX_INITIAL_SELECTION_ATTEMPTS
                    and _is_retryable_bridge_error(exc)
                ):
                    topic_request = _retry_topic_request(topic_request)
                    continue
                raise
        if topic_response is None:
            raise AssertionError("Codex topic selection attempts exhausted")

        request = build_codex_boundary_refinement_request(
            source_request,
            topic_request,
            topic_response,
        )
        if request is None:
            result = _empty_quality_result(
                source_request,
                topic_request,
                topic_response,
                attempt_count=topic_attempt,
            )
            if heartbeat is not None:
                heartbeat(result.summary)
            return result

        refinement_thread_id = topic_response.thread_id or thread_id
        topic_block_count = len(topic_request.topic_blocks)
        topic_summary_char_count = sum(
            len(item.summary) for item in topic_request.topic_blocks
        )
        for attempt in range(1, MAX_CODEX_INITIAL_SELECTION_ATTEMPTS + 1):
            try:
                bridge.ensure_contract_compatible()
                bridge.write_request(
                    request,
                    thread_id=refinement_thread_id,
                    attempt=attempt,
                )
                response = bridge.wait_for_response(
                    request,
                    timeout_seconds=timeout_seconds,
                    poll_seconds=poll_seconds,
                    heartbeat=heartbeat,
                )
                result = convert_codex_initial_selection_response(
                    request,
                    response,
                    attempt_count=max(topic_attempt, attempt),
                    topic_block_count=topic_block_count,
                    topic_summary_char_count=topic_summary_char_count,
                )
                result.summary["selectionStage"] = "boundary_refinement"
                if heartbeat is not None:
                    heartbeat(result.summary)
                return result
            except CodexInitialSelectionError as exc:
                exc.request_id = request.request_id
                exc.attempt_count = max(topic_attempt, attempt)
                if (
                    attempt < MAX_CODEX_INITIAL_SELECTION_ATTEMPTS
                    and _is_retryable_bridge_error(exc)
                ):
                    request = _retry_request(request)
                    continue
                raise
        raise AssertionError("Codex boundary refinement attempts exhausted")
    except CodexInitialSelectionError:
        raise
    except (OSError, ValidationError, ValueError) as exc:
        wrapped = CodexInitialSelectionError(
            "codex_initial_selection_request_invalid",
            "Codex初期選定の入力を作成できませんでした。",
        )
        raise wrapped from exc
