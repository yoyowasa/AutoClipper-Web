from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

import pytest

from app.audio.transcribe_faster_whisper import TranscriptSegment
import app.candidates.codex_initial_selection as selection
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.subtitle_review import build_subtitle_review
from app.jobs.title_hook_suggestions import TitleHookDraftSegment, build_title_hook_suggestion_input, title_hook_suggestion_input_path
from app.scoring.title_hook_suggestions import title_hook_system_prompt
from app.storage.json_io import write_json_atomic
from test_production_records import example as example
from test_codex_initial_selection import _response


def hint(target="selection", expires=None):
    stamp = datetime.now(UTC)
    return {"analysisId": "analysis_verified", "generatedAt": stamp.isoformat().replace("+00:00", "Z"),
            "expiresAt": (expires or stamp + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "target": target, "text": "過去の投稿実績から題材が分かる場面を参考にしてください。効果は未検証です。", "format": "short"}


def requests(monkeypatch, hints=None, enabled=True):
    monkeypatch.setattr(selection, "uuid4", lambda: UUID(int=1))
    settings = {"normalClipCount": 1, "shortCount": 1, "normalMinDuration": 90, "normalMaxDuration": 120,
        "shortMinDuration": 20, "shortMaxDuration": 40, "heatmapIntervalMode": False, "maxOverlapRatio": 0.8,
        "crossTypeOverlapDedupe": False, "usePerformanceHints": enabled, "_performanceHints": hints or []}
    transcript = [TranscriptSegment(start=0, end=30, text="科学の題材を説明します。"),
                  TranscriptSegment(start=30, end=160, text="具体例と結論です。")]
    request = selection.build_codex_initial_selection_request(job_id="job_hint_contract", transcript_segments=transcript,
        heatmap_segments=[], video_duration=200, settings=settings)
    topic = selection.build_codex_topic_selection_request(request)
    candidate = Candidate(id="short_one", type="short", start=0, end=30, duration=30, title="題材", transcript_text=transcript[0].text)
    review = build_subtitle_review("job_hint_contract", CandidateSelection(normalClips=[], shorts=[candidate]), transcript)
    title = build_title_hook_suggestion_input(review, "short_one",
        [TitleHookDraftSegment(segmentId=segment.id, text=segment.text) for segment in review.segments], model="codex-default",
        performance_hints=[item for item in hints or [] if enabled])
    return request, topic, title


@pytest.mark.parametrize("mode", ["none", "off", "expired"])
def test_empty_off_and_expired_prompts_are_byte_identical_to_main_before_task217(monkeypatch, mode):
    hints = [] if mode == "none" else [hint(), hint("title_hook")]
    if mode == "expired":
        hints = [hint(expires=datetime(2020, 1, 1, tzinfo=UTC)), hint("title_hook", datetime(2020, 1, 1, tzinfo=UTC))]
    request, topic, title = requests(monkeypatch, hints, enabled=mode != "off")
    prompts = {"selection": selection._bridge_envelope(request, thread_id=None).prompt,
               "topic": selection._topic_bridge_envelope(topic, thread_id=None).prompt,
               "title_hook": title_hook_system_prompt() + "\n\n入力JSON:\n" + json.dumps(title.prompt_payload(),
                   ensure_ascii=False, separators=(",", ":"), allow_nan=False)}
    expected = json.loads((Path(__file__).parent / "fixtures/performance_hint_prompts_before_task217.json").read_text())
    assert {key: sha256(value.encode()).hexdigest() for key, value in prompts.items()} == expected
    assert "performanceHints" not in request.prompt_payload() and "performanceHints" not in title.prompt_payload()


def test_active_hints_reach_both_selection_stages_title_input_hash_and_summary(monkeypatch):
    used = [hint(), hint("title_hook")]
    request, topic, title = requests(monkeypatch, used)
    assert request.performance_hints == topic.performance_hints == [used[0]]
    assert "過去の投稿実績からの参考情報（決まりではない）" in selection._topic_bridge_envelope(topic, thread_id=None).prompt
    assert "本数・尺の上下限" in selection._bridge_envelope(request, thread_id=None).prompt
    assert title.prompt_payload()["performanceHints"] == [used[1]]
    assert title.input_hash != requests(monkeypatch)[2].input_hash
    result = selection.convert_codex_initial_selection_response(request, _response(request))
    assert result.summary["performanceHints"] == [used[0]]


def test_record_projects_exact_used_hints_and_legacy_record_has_no_required_new_field(example):
    import app.production_records as records

    db, job, export, paths = example
    output = paths.job_outputs(job.id)
    selected, title = hint(), hint("title_hook")
    write_json_atomic(output / "codex_initial_selection_summary.json", {"performanceHints": [selected]})
    write_json_atomic(title_hook_suggestion_input_path(output, export.candidate_id), {"performanceHints": [title]})
    path = records.write_production_record(job, export, paths)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["performanceHints"] == [selected, title]
    del saved["performanceHints"]
    assert records.ProductionRecord.model_validate(saved).performanceHints == []
