"""Review contract ported from Clip Intelligence; YouTube IDs are strings here."""

from copy import deepcopy
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.intelligence.recommendation_rules import FRAMEWORK_VERSION, RULES
from app.intelligence.performance_schema import PerformanceHint

Format = Literal["all", "shorts", "videoondemand"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnalysisGoals(Strict):
    normal_views: Literal[100000] = 100000
    short_views: Literal[1000000] = 1000000
    window_days: Literal[30] = 30
    interim_days: Literal[7] = 7


class Finding(Strict):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,50}$")
    format: Format
    title: str = Field(min_length=1, max_length=150)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    observation: str = Field(min_length=1, max_length=1600)
    hypothesis: str = Field(min_length=1, max_length=1200)
    alternatives: list[str] = Field(min_length=2, max_length=5)
    counter_evidence: str = Field(min_length=1, max_length=1200)
    next_check: str = Field(min_length=1, max_length=1200)
    confidence: Literal["low", "medium"] = "low"


class StructureStep(Strict):
    start: float = Field(ge=0, le=600)
    end: float = Field(gt=0, le=600)
    action: str = Field(min_length=1, max_length=600)

    @model_validator(mode="after")
    def valid(self):
        if self.end <= self.start:
            raise ValueError("INVALID_PLANNED_TIMELINE")
        return self


class RecommendationLink(Strict):
    surface: Literal["shorts_feed", "home", "up_next", "search", "multi_surface"]
    viewer_need: str = Field(min_length=1, max_length=800)
    stage: Literal["viewer_fit", "appeal", "engagement", "satisfaction", "topic_demand"]
    signal_hypothesis: str = Field(min_length=1, max_length=1000)
    evidence_gap: str = Field(min_length=1, max_length=1000)
    rule_ids: list[Literal[*tuple(RULES)]] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def relevant_source(self):
        required = {"shorts_feed": "shorts_response", "home": "surface_context", "up_next": "surface_context", "search": "search_relevance"}
        if self.surface in required and required[self.surface] not in self.rule_ids:
            raise ValueError("RECOMMENDATION_SURFACE_RULE_REQUIRED")
        return self


class Proposal(Strict):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,50}$")
    format: Literal["shorts", "videoondemand"]
    priority: int = Field(ge=1, le=3)
    title: str = Field(min_length=1, max_length=150)
    baseline_video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=1200)
    goal_path: str = Field(min_length=1, max_length=1200)
    material_to_find: str = Field(min_length=1, max_length=1200)
    title_candidates: list[str] = Field(min_length=1, max_length=4)
    hook: str = Field(min_length=1, max_length=300)
    structure: list[StructureStep] = Field(min_length=2, max_length=8)
    change_one: str = Field(min_length=1, max_length=1000)
    keep_fixed: str = Field(min_length=1, max_length=1000)
    primary_metric: Literal["engagedViews", "views", "averageViewPercentage", "averageViewDuration", "subscribersGained"]
    result_check: str = Field(min_length=1, max_length=1200)
    rejection_condition: str = Field(min_length=1, max_length=1000)
    recommendation_link: RecommendationLink | None = None

    @model_validator(mode="after")
    def timeline(self):
        if self.structure[0].start != 0 or any(b.start < a.end for a, b in zip(self.structure, self.structure[1:])):
            raise ValueError("INVALID_PLANNED_TIMELINE")
        if self.recommendation_link and self.recommendation_link.surface == "shorts_feed" and self.format != "shorts":
            raise ValueError("RECOMMENDATION_SURFACE_FORMAT_MISMATCH")
        return self


class Review(Strict):
    performance_hints: list[PerformanceHint] = Field(default_factory=list, max_length=50)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")
    channel_id: int = Field(ge=1)
    batch_run_id: str = Field(min_length=8, max_length=64)
    title: str = Field(min_length=1, max_length=150)
    summary: str = Field(min_length=1, max_length=2000)
    goals: AnalysisGoals | None = None
    goal_views: Literal[1000000] | None = None  # Read-only compatibility for older saved reviews.
    recommendation_framework_version: Literal[FRAMEWORK_VERSION] | None = None
    reviewed_material: Literal["statistics_and_titles"] = "statistics_and_titles"
    limitations: list[str] = Field(min_length=1, max_length=10)
    findings: list[Finding] = Field(min_length=1, max_length=20)
    proposals: list[Proposal] = Field(max_length=12)

    @model_validator(mode="after")
    def unique_ids(self):
        for items in (self.findings, self.proposals):
            if len({x.id for x in items}) != len(items):
                raise ValueError("DUPLICATE_ITEM")
        if self.recommendation_framework_version and any(p.recommendation_link is None for p in self.proposals):
            raise ValueError("RECOMMENDATION_LINK_REQUIRED")
        return self


def analysis_response_schema() -> dict:
    schema = deepcopy(Review.model_json_schema())
    schema["properties"].pop("goal_views")
    schema["properties"]["goals"] = {"$ref": "#/$defs/AnalysisGoals"}

    def strict(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return schema
