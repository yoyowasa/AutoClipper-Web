from datetime import UTC, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.production_choices import ProductionChoice

POLICY_SETTING = "_publicationPolicy"


class PublicationPolicy(BaseModel):
    """Unvalidated operational thresholds, snapshotted only when creating a job."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)
    version: Literal["weak-material-v1"] = "weak-material-v1"
    min_score: float = Field(default=65, ge=0, le=100, alias="minScore")
    min_characters_per_second: float = Field(default=0.5, ge=0, alias="minCharactersPerSecond")
    validated: Literal[False] = False


class HintReference(BaseModel):
    analysis_id: str = Field(alias="analysisId")
    generated_at: str = Field(alias="generatedAt")
    expires_at: str = Field(alias="expiresAt")


class PublicationEvidence(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", allow_inf_nan=False)
    score: float | None = None
    score_source: str | None = Field(default=None, alias="scoreSource")
    selection_reason: str | None = Field(default=None, alias="selectionReason")
    selection_rationale: str | None = Field(default=None, alias="selectionRationale")
    hard_gate_passed: bool | None = Field(default=None, alias="hardGatePassed")
    hard_gate_hash: str | None = Field(default=None, alias="hardGateHash")
    hard_gate_reasons: list[str] = Field(default_factory=list, alias="hardGateReasons")
    transcript_characters: int | None = Field(default=None, alias="transcriptCharacters")
    characters_per_second: float | None = Field(default=None, alias="charactersPerSecond")
    transcript_hash: str | None = Field(default=None, alias="transcriptHash")
    hint_references: list[HintReference] = Field(default_factory=list, alias="hintReferences")


class PublicationDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", allow_inf_nan=False)
    candidate_id: str = Field(alias="candidateId")
    type: Literal["normal", "short"]
    start: float
    end: float
    title: str
    decision: Literal["publish", "skip", "unknown"]
    source: Literal["automatic", "manual"] = "automatic"
    policy_version: str = Field(alias="policyVersion")
    reasons: list[str]
    evidence: PublicationEvidence
    original_decision: Literal["publish", "skip", "unknown"] | None = Field(default=None, alias="originalDecision")


class PublicationRevision(BaseModel):
    revision: int
    decisions: list[PublicationDecision]


class PublicationReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    schema_version: Literal[1] = Field(default=1, alias="schemaVersion")
    job_id: str = Field(alias="jobId")
    revision: int = 1
    previous_decisions: list[PublicationRevision] = Field(default_factory=list, alias="previousDecisions", exclude_if=lambda v: not v)
    policy: PublicationPolicy
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="createdAt")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="updatedAt")
    outcome: Literal["publish", "partial", "no_publication", "needs_review"]
    selected_count: int = Field(alias="selectedCount")
    decisions: list[PublicationDecision]
    choice_history: list[ProductionChoice] = Field(default_factory=list, alias="choiceHistory")


REASONS = {
    "WEAK_SCORE": "内容の強さの採点が見送り基準を下回っています",
    "LOW_CONTENT_DENSITY": "字幕から確認できる内容が尺に対して少ないため見送ります",
    "MODEL_REJECTED": "既存の選定で採用に適さないと判定されています",
    "QUALITY_EVIDENCE_MISSING": "必須条件の検査記録が足りず、投稿可否を判定できません",
    "EXISTING_GATE_REJECTED": "既存の必須条件を満たしていません。範囲・内容の確認が必要です",
    "SCORE_MISSING": "採点が記録されていないため、投稿可否を判定できません",
    "TRANSCRIPT_MISSING": "内容の根拠となる字幕が足りず、投稿可否を判定できません",
    "RANGE_INVALID": "元動画の範囲・尺の条件に合っていません",
    "SELECTION_REASON_MISSING": "選定理由が記録されていないため、投稿可否を判定できません",
    "CRITERIA_MET": "既存の必須条件と投稿可否の基準を満たしています",
    "MANUAL_SELECTION": "人のキープ・範囲指定による採用です",
    "MANUAL_OVERRIDE": "人が見送り・判定不能を取り消して採用しました",
}
