import json
import uuid
from pathlib import Path
import pytest
from app.inspection.content import CONTENT_REVIEW_SCHEMA, ContentReview, CodexOutputInspector
from test_codex_host_bridge import isolate_private_bridge_root as isolate_private_bridge_root
from launcher import codex_bridge as bridge


def result(outcome="pass"):
    return {
        "findings": [
            {
                "kind": kind,
                "outcome": outcome,
                "reason": {"pass": "supported", "fail": "contradicts", "unknown": "insufficient_evidence"}[outcome],
                "evidence_ids": ["subtitle-0", "output-0" if kind == "content" else "thumbnail"],
            }
            for kind in ("content", "thumbnail")
        ]
    }


@pytest.mark.parametrize("outcome", ["pass", "fail", "unknown"])
def test_content_results_are_structured_and_grounded(outcome):
    review = ContentReview.model_validate(result(outcome))
    review.validate_evidence({"subtitles": [{"id": "subtitle-0"}], "imageIds": ["output-0", "thumbnail"]})
    assert [f.outcome for f in review.findings] == [outcome, outcome]


@pytest.mark.parametrize("fault", ["unknown_id", "missing_kind", "inconsistent_outcome", "unstructured_prose"])
def test_invalid_content_result_is_not_treated_as_a_pass(fault):
    payload = result()
    if fault == "unknown_id":
        payload["findings"][0]["evidence_ids"] = ["subtitle-0", "invented"]
    elif fault == "missing_kind":
        payload["findings"][0]["kind"] = "thumbnail"
    elif fault == "inconsistent_outcome":
        payload["findings"][0]["reason"] = "contradicts"
    else:
        payload["findings"][0]["reason"] = "some model text"
    with pytest.raises(ValueError):
        ContentReview.model_validate(payload).validate_evidence(
            {"subtitles": [{"id": "subtitle-0"}], "imageIds": ["output-0", "thumbnail"]}
        )


def test_new_inspection_contract_uses_existing_bridge_and_bounded_host_timeout(tmp_path):
    assert CodexOutputInspector.task == bridge.FINAL_OUTPUT_REVIEW_TASK == "final_output_review"
    assert bridge.EXPECTED_RESPONSE_SCHEMA_SHA256["final_output_review"] == bridge._response_schema_sha256(CONTENT_REVIEW_SCHEMA)
    project = tmp_path / "project"
    paths = bridge.bridge_paths(project)
    bridge.ensure_bridge_directories(paths)
    request_id = uuid.uuid4().hex
    target = paths.processing / f"{request_id}.json"
    bridge.atomic_write_json(
        target,
        {
            "schemaVersion": 1,
            "requestId": request_id,
            "task": "final_output_review",
            "responseSchema": CONTENT_REVIEW_SCHEMA,
            "images": [],
            "prompt": "Inspect a synthetic output",
            "threadScope": "job_test",
        },
    )
    seen = []

    def execute(command, prompt, cwd, timeout, stop_request):
        seen.append(timeout)
        output = Path(command[list(command).index("--output-last-message") + 1])
        output.write_text(json.dumps(result()), encoding="utf-8")
        return bridge.CodexRunResult(0, json.dumps({"type": "thread.started", "thread_id": str(uuid.uuid4())}), "")

    response = bridge.process_request_file(target, project_root=project, codex_executable="synthetic-codex", runner=execute)
    assert response["state"] == "ready" and response["output"] == result()
    assert seen == [120.0]


def test_image_only_evidence_never_invents_a_transcript():
    payload = result()
    for item in payload["findings"]:
        item["evidence_ids"] = ["output-0", "source-0"]
    ContentReview.model_validate(payload).validate_evidence({"subtitles": [], "imageIds": ["output-0", "source-0"]})
