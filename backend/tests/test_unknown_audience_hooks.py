from hashlib import sha256
from types import SimpleNamespace

import pytest

from app.db import get_db
from app.jobs.title_hook_suggestions import (
    MissingTopicHookError,
    TitleHookDraftSegment,
    TitleHookSuggestionInput,
    _generate_acceptable_result,
    build_title_hook_suggestion_input,
    generate_title_hook_suggestions_for_auto,
    load_title_hook_suggestion_input,
    load_title_hook_suggestions,
    queued_title_hook_suggestions,
    run_title_hook_suggestion_generation,
    title_hook_suggestion_input_path,
    title_hook_suggestions_path,
    write_title_hook_suggestion_input,
    write_title_hook_suggestions,
)
from app.main import app
from app.models import Job
from app.scoring.title_hook_suggestions import SYSTEM_PROMPT, has_transcript_topic_word, title_hook_system_prompt
from test_title_hook_suggestions import _short_drafts, _suggestion_result, title_hook_api as title_hook_api


def request_for(case, mode="unknown"):
    drafts = [TitleHookDraftSegment(**item) for item in _short_drafts(case["review"])]
    drafts[0].text = "科学の実験で123の気圧を比べる。コーヒーとAIも紹介します。"
    return build_title_hook_suggestion_input(case["review"], "short_1", drafts, model="codex-default", audience_familiarity=mode)


def result_for(*hooks, recommended="model-a"):
    result = _suggestion_result().model_copy(deep=True)
    for suggestion, hook in zip(result.suggestions, hooks, strict=True):
        suggestion.hook_text = hook
    result.recommended_suggestion_id = recommended
    return result


def test_known_system_prompt_is_exactly_v10():
    # SHA256 of main 7cd64a3's unchanged v10 prompt body (UTF-8).
    assert sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest() == "b721ae51ad968678c89f03063f7256c91836de469b8c7aa18e53c760478f8818"
    assert title_hook_system_prompt() == SYSTEM_PROMPT
    assert title_hook_system_prompt(audience_familiarity="known") == SYSTEM_PROMPT
    assert title_hook_system_prompt(audience_familiarity="unknown", clip_type="normal") == SYSTEM_PROMPT
    prompt = title_hook_system_prompt(audience_familiarity="unknown")
    assert prompt.startswith(SYSTEM_PROMPT)
    assert "【知名度低モード" in prompt
    assert "hookText と publicationTitle の先頭" in prompt


@pytest.mark.parametrize(
    "hook,expected",
    [
        ("科学って面白い", True),
        ("コーヒーはなぜ？", True),
        ("AIは123で変わる", True),
        ("科学入門！", True),
        ("ＮＧです", False),
        ("見知らぬ芸術家", False),
        ("それ！あれ！えー！あの！やばい！すごい！", False),
        ("ヤバイ！スゴイ！エー", False),
        ("A", False),
    ],
)
def test_topic_word_requires_subtitle_overlap_and_excludes_fillers(hook, expected):
    assert has_transcript_topic_word(hook, "科学の実験で123の気圧を比べる。コーヒーとAIも紹介します。") is expected


def test_input_payload_hash_and_legacy_default(title_hook_api):
    known = request_for(title_hook_api, "known")
    unknown = request_for(title_hook_api)
    assert known.prompt_payload()["audienceFamiliarity"] == "known"
    assert unknown.prompt_payload()["audienceFamiliarity"] == "unknown"
    assert known.input_hash != unknown.input_hash
    # Subtitle metadata revisions continue to identify the same text and boundaries.
    assert known.revision_hash == unknown.revision_hash
    old = known.model_dump(by_alias=True)
    del old["audienceFamiliarity"]
    old["promptVersion"] = "title_hook_suggestions_v10"
    assert TitleHookSuggestionInput.model_validate(old).audience_familiarity == "known"


@pytest.mark.parametrize("succeed", [True, False])
def test_all_invalid_retries_once_and_worker_persists_failure_or_ready(title_hook_api, succeed):
    case = title_hook_api
    request = request_for(case)
    output = case["storage"].job_outputs(case["job_id"])
    write_title_hook_suggestion_input(request, title_hook_suggestion_input_path(output, "short_1"))
    write_title_hook_suggestions(queued_title_hook_suggestions(request), title_hook_suggestions_path(output, "short_1"))
    payloads = []

    def generate(payload, _frames):
        payloads.append(payload)
        if succeed and len(payloads) == 2:
            return result_for("科学って面白い", "みんなに会えなかったら", "ヤバイ", recommended="model-b")
        return result_for("みんなに会えなかったら", "それってすごい", "ヤバイ", recommended="model-b")

    outcome = run_title_hook_suggestion_generation(
        case["job_id"],
        "short_1",
        request.input_hash,
        session_factory=case["session_factory"],
        paths=case["storage"],
        generator=SimpleNamespace(generate=generate),
        frame_extractor=lambda *_args, **_kwargs: [],
    )
    artifact = load_title_hook_suggestions(title_hook_suggestions_path(output, "short_1"))
    assert len(payloads) == 2
    assert "題材語" in payloads[1]["retryInstruction"]
    if succeed:
        assert outcome == ["ready"]
        assert [item.id for item in artifact.suggestions] == ["suggestion_1"]
        assert artifact.recommended_suggestion_id == "suggestion_1"
    else:
        assert outcome == ["failed"]
        assert artifact.error and "題材語を含むフック案を生成できませんでした" in artifact.error
        assert artifact.suggestions == []
        assert artifact.recommended_suggestion_id is None
    assert (
        case["client"].get(f"/api/jobs/{case['job_id']}/subtitle-review/clips/short_1/title-hook-suggestions").json()["state"] == outcome[0]
    )


def test_known_and_normal_skip_topic_validation(title_hook_api):
    bad = result_for("みんなに会えなかったら", "それってすごい", "ヤバイ")
    generator = SimpleNamespace(generate=lambda _payload, _frames: bad)
    assert _generate_acceptable_result(generator, request_for(title_hook_api, "known"), []) is bad
    normal = request_for(title_hook_api).model_copy(update={"clip_type": "normal"})
    assert _generate_acceptable_result(generator, normal, []) is bad


def test_fillers_do_not_become_topic_words_when_extended():
    assert not has_transcript_topic_word("ヤバイナ", "ヤバイナ")
    assert not has_transcript_topic_word("ーー", "ーー")


def test_repeated_titles_and_missing_topic_share_one_retry(title_hook_api):
    request = request_for(title_hook_api)
    bad = result_for("みんなに会えなかったら", "それってすごい", "ヤバイ")
    request.avoid_publication_titles = [item.publication_title for item in bad.suggestions]
    payloads = []

    def generate(payload, _frames):
        payloads.append(payload)
        return bad

    with pytest.raises(MissingTopicHookError):
        _generate_acceptable_result(SimpleNamespace(generate=generate), request, [], reject_repeated=True)
    assert len(payloads) == 2
    assert "題材語" in payloads[1]["retryInstruction"]
    assert "公開タイトル" in payloads[1]["retryInstruction"]


@pytest.mark.parametrize("succeed", [False, True])
def test_automatic_generation_persists_topic_result(title_hook_api, succeed):
    case = title_hook_api
    document = case["review"].model_copy(deep=True)
    document.segments[1].text = "科学の実験"
    calls = []

    def generate(payload, _frames):
        calls.append(payload)
        if succeed:
            return result_for("科学って面白い", "それってすごい", "ヤバイ", recommended="model-b")
        return result_for("みんなに会えなかったら", "それってすごい", "ヤバイ")

    def run():
        return generate_title_hook_suggestions_for_auto(
            document=document,
            clip_id="short_1",
            source_path="unused.mp4",
            paths=case["storage"],
            model="codex-default",
            audience_familiarity="unknown",
            generator=SimpleNamespace(generate=generate),
            frame_extractor=lambda *_args, **_kwargs: [],
        )
    if succeed:
        assert run().recommended_suggestion_id == "suggestion_1"
    else:
        with pytest.raises(MissingTopicHookError):
            run()
    artifact = load_title_hook_suggestions(title_hook_suggestions_path(case["storage"].job_outputs(case["job_id"]), "short_1"))
    assert len(calls) == (1 if succeed else 2)
    assert artifact.state == ("ready" if succeed else "failed")
    if not succeed:
        assert artifact.error and "題材語" in artifact.error


def test_api_passes_job_familiarity_and_invalidates_cache(title_hook_api):
    case = title_hook_api
    url = f"/api/jobs/{case['job_id']}/subtitle-review/clips/short_1/title-hook-suggestions"
    drafts = _short_drafts(case["review"])
    assert case["client"].post(url, json={"segments": drafts}).status_code == 200
    first_hash = case["queued"][-1][2]
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, case["job_id"])
        job.settings_json = {**(job.settings_json or {}), "audienceFamiliarity": "unknown"}
        db.commit()
    assert case["client"].post(url, json={"segments": drafts}).status_code == 200
    assert case["queued"][-1][2] != first_hash
    request = load_title_hook_suggestion_input(title_hook_suggestion_input_path(case["storage"].job_outputs(case["job_id"]), "short_1"))
    assert request.audience_familiarity == "unknown"
