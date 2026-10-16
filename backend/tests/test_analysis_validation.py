from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from app.intelligence.analysis_bridge import ChannelAnalysisGenerator
from app.intelligence.analysis_validation import ReviewValidationError, validate_review
from app.intelligence.analysis_errors import AnalysisError
from app.intelligence.analysis_input import build_analysis_input
from app.intelligence.models import AnalysisRun
from test_api_routes import client as client
from test_intelligence import environment as environment, VIDEO_ID
from test_channel_analysis import CLOCK, URL, FixedGenerator, execute, prepared as prepared, valid_review


def context():
    return SimpleNamespace(payload={"review_id": "analysis_test", "channel": {"id": 1}, "batch": {"run_id": "sync_test"}},
        evidence={"r:1:views": {"video_id": VIDEO_ID, "source": "youtube_analytics"}}, videos={VIDEO_ID: {"format": "shorts"}})


@pytest.mark.parametrize("kind,problem,code", [
    ("findings", "evidence", "EVIDENCE_UNKNOWN"), ("proposals", "evidence", "EVIDENCE_UNKNOWN"),
    ("proposals", "format", "BASELINE_FORMAT_MISMATCH"), ("proposals", "unknown", "BASELINE_FORMAT_UNKNOWN"),
    ("proposals", "baseline", "BASELINE_NOT_FOUND"), ("proposals", "metric", "PRIMARY_METRIC_INVALID"),
    ("proposals", "metric_schema", "PRIMARY_METRIC_INVALID"), ("findings", "schema", "SCHEMA_INVALID"),
    ("proposals", "schema", "SCHEMA_INVALID"), ("proposals", "link", "RECOMMENDATION_LINK_REQUIRED"),
    ("findings", "format", "FINDING_FORMAT_MISMATCH"), ("proposals", "duplicate", "DUPLICATE_ITEM"),
    ("findings", "duplicate", "DUPLICATE_ITEM"), ("proposals", "baseline_evidence", "BASELINE_EVIDENCE_MISSING"),
])
def test_only_invalid_item_discarded(kind, problem, code):
    ctx = context()
    output = valid_review(ctx)
    bad = deepcopy(output[kind][0])
    if problem != "duplicate":
        bad["id"] = "bad_item"
    if problem == "evidence":
        bad["evidence_ids"] = ["invented-private-content"]
    elif problem == "format":
        bad["format"] = "videoondemand"
        if kind == "proposals":
            bad["recommendation_link"]["surface"] = "home"
            bad["recommendation_link"]["rule_ids"] = ["surface_context"]
    elif problem == "unknown":
        ctx.videos["video000002"] = {"format": "unknown"}
        bad["baseline_video_id"] = "video000002"
    elif problem == "baseline":
        bad["baseline_video_id"] = "video000009"
    elif problem in {"metric", "metric_schema"}:
        bad["primary_metric"] = "averageViewPercentage" if problem == "metric" else "private-unrecognized-metric"
    elif problem == "schema":
        bad["private-extra-name"] = "private-text-value"
        bad["title"] = []
    elif problem == "link":
        bad["recommendation_link"] = None
    elif problem == "baseline_evidence":
        ctx.evidence["r:2:views"] = {"video_id": None, "source": "youtube_analytics"}
        bad["evidence_ids"] = ["r:2:views"]
    output[kind].append(bad)
    report = {}
    result = validate_review(ChannelAnalysisGenerator.parse_output(None, output), ctx, diagnostics=report)
    assert len(result.findings) == len(result.proposals) == 1
    assert report["excludedFindings" if kind == "findings" else "excludedProposals"] == 1
    assert code in report["reasonCounts"] and report["fatal"] is False
    assert "private" not in json.dumps(report)


@pytest.mark.parametrize("field,value", [("id", "wrong_review"), ("channel_id", 2), ("batch_run_id", "wrong_batch"),
                                         ("recommendation_framework_version", None), ("recommendation_framework_version", "other")])
def test_wrong_envelope_always_fails(field, value):
    ctx = context()
    output = valid_review(ctx)
    output[field] = value
    with pytest.raises(ReviewValidationError) as error:
        validate_review(output, ctx)
    assert error.value.report["fatal"] is True and error.value.report["issues"]


def test_all_findings_invalid_fails_with_only_safe_locations():
    ctx = context()
    output = valid_review(ctx)
    output["findings"][0]["alternatives"] = []
    with pytest.raises(ReviewValidationError) as error:
        validate_review(output, ctx)
    report = error.value.report
    assert report["excludedFindings"] == 1 and report["reasonCounts"]["NO_VALID_FINDINGS"] == 1
    assert {"code": "SCHEMA_INVALID", "loc": ["findings", 0, "alternatives"]} in report["issues"]


@pytest.mark.parametrize("fatal", [False, True])
def test_diagnostics_persist_and_reach_api(client, prepared, fatal, caplog):
    id = client.post(URL, json={"syncBefore": "never"}).json()["id"]

    class Invalid(FixedGenerator):
        def analyze(self, ctx):
            output = valid_review(ctx)
            output["proposals"][0]["primary_metric"] = "private-invalid-value"
            if fatal:
                output["findings"][0]["alternatives"] = []
            return output

    if fatal:
        with pytest.raises(AnalysisError):
            execute(prepared, id, Invalid)
    else:
        execute(prepared, id, Invalid)
    prepared.db.expire_all()
    saved = prepared.db.get(AnalysisRun, id)
    assert saved.validation.report["excludedProposals"] == 1
    data = client.get(URL).json()
    report = data["latestRun"]["validation"]
    assert report["fatal"] is fatal and "PRIMARY_METRIC_INVALID" in report["reasonCounts"]
    assert "private-invalid-value" not in json.dumps(data) + caplog.text
    if not fatal:
        assert data["latestResult"]["review"]["findings"] and data["latestResult"]["review"]["proposals"] == []


def test_no_bad_items_matches_original_contract(prepared):
    ctx = build_analysis_input(prepared.db, prepared.paths, prepared.config, 1, "analysis_test", CLOCK)
    from app.intelligence.analysis_schema import Review
    output = valid_review(ctx)
    assert validate_review(output, ctx) == Review.model_validate(output)
