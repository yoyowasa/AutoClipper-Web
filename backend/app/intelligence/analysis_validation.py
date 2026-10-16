"""Validate identity strictly and discard invalid individual items with safe diagnostics."""

from collections import Counter
from typing import Any

from pydantic import Field, ValidationError, create_model

from app.intelligence.analysis_input import AnalysisContext
from app.intelligence.analysis_schema import Finding, Proposal, Review
from app.intelligence.recommendation_rules import FRAMEWORK_VERSION

Envelope = create_model("ReviewEnvelope", __config__=Review.model_config,
    **{name: (field.annotation, field) for name, field in Review.model_fields.items() if name not in {"findings", "proposals"}},
    findings=(list[Any], Field(min_length=1, max_length=20)), proposals=(list[Any], Field(max_length=12)))
SAFE_FIELDS = frozenset().union(*(model.model_fields for model in (Review, Finding, Proposal))) | {
    "surface", "viewer_need", "stage", "signal_hypothesis", "evidence_gap", "rule_ids", "start", "end", "action"}


class ReviewValidationError(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__("CODEX_INVALID_OUTPUT")


def validate_review(output, context: AnalysisContext, *, diagnostics: dict | None = None) -> Review:
    report = diagnostics if diagnostics is not None else {}
    report.update(excludedFindings=0, excludedProposals=0, issues=[], reasonCounts={}, fatal=False)

    def issue(code, loc):
        # Unknown extra keys can themselves contain Codex/user text.
        safe = [part if isinstance(part, int) or part in SAFE_FIELDS else "[extra]" for part in loc]
        report["issues"].append({"code": code, "loc": safe})
        report["reasonCounts"] = dict(Counter(item["code"] for item in report["issues"]))

    def schema_errors(error, prefix=()):
        for item in error.errors(include_input=False, include_context=False, include_url=False):
            loc = (*prefix, *item["loc"])
            issue("PRIMARY_METRIC_INVALID" if "primary_metric" in loc else "SCHEMA_INVALID", loc)

    def fail():
        report["fatal"] = True
        raise ReviewValidationError(report)

    try:
        envelope = Envelope.model_validate(output)
    except ValidationError as error:
        schema_errors(error)
        fail()
    payload = context.payload
    for name, expected, code in (
        ("id", payload["review_id"], "REVIEW_ID_MISMATCH"),
        ("channel_id", payload["channel"]["id"], "CHANNEL_MISMATCH"),
        ("batch_run_id", payload["batch"]["run_id"], "BATCH_MISMATCH"),
        ("recommendation_framework_version", FRAMEWORK_VERSION, "FRAMEWORK_MISMATCH"),
    ):
        if getattr(envelope, name) != expected:
            issue(code, [name])
    if report["issues"]:
        fail()
    accepted = {"findings": [], "proposals": []}
    for kind, model in (("findings", Finding), ("proposals", Proposal)):
        seen = set()
        for index, raw in enumerate(getattr(envelope, kind)):
            prefix, initial = (kind, index), len(report["issues"])
            try:
                item = model.model_validate(raw)
            except ValidationError as error:
                schema_errors(error, prefix)
                report["excludedFindings" if kind == "findings" else "excludedProposals"] += 1
                continue
            if item.id in seen:
                issue("DUPLICATE_ITEM", (*prefix, "id"))
            unknown = not set(item.evidence_ids) <= context.evidence.keys()
            if unknown:
                issue("EVIDENCE_UNKNOWN", (*prefix, "evidence_ids"))
            if kind == "proposals":
                baseline = context.videos.get(item.baseline_video_id)
                if not baseline:
                    issue("BASELINE_NOT_FOUND", (*prefix, "baseline_video_id"))
                elif baseline["format"] == "unknown":
                    issue("BASELINE_FORMAT_UNKNOWN", (*prefix, "baseline_video_id"))
                elif baseline["format"] != item.format:
                    issue("BASELINE_FORMAT_MISMATCH", (*prefix, "format"))
                if item.primary_metric != "views":
                    issue("PRIMARY_METRIC_INVALID", (*prefix, "primary_metric"))
                if item.recommendation_link is None:
                    issue("RECOMMENDATION_LINK_REQUIRED", (*prefix, "recommendation_link"))
                if not unknown and not any(context.evidence[id]["video_id"] == item.baseline_video_id
                        and context.evidence[id]["source"] in {"youtube_analytics", "youtube_public"} for id in item.evidence_ids):
                    issue("BASELINE_EVIDENCE_MISSING", (*prefix, "evidence_ids"))
            elif not unknown and item.format != "all" and any(
                evidence["video_id"] and context.videos.get(evidence["video_id"], {}).get("format") != item.format
                for evidence in (context.evidence[id] for id in item.evidence_ids)
            ):
                issue("FINDING_FORMAT_MISMATCH", (*prefix, "format"))
            if len(report["issues"]) > initial:
                report["excludedFindings" if kind == "findings" else "excludedProposals"] += 1
            else:
                seen.add(item.id)
                accepted[kind].append(item)
    if not accepted["findings"]:
        issue("NO_VALID_FINDINGS", ["findings"])
        fail()
    try:
        return Review.model_validate({**envelope.model_dump(), **accepted})
    except ValidationError as error:
        schema_errors(error)
        fail()
