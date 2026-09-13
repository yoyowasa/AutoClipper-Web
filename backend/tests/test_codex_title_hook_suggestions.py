from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.scoring.codex_title_hook_suggestions import (
    CodexTitleHookSuggestionGenerator,
)
from app.scoring.title_hook_suggestions import TITLE_HOOK_GENERATION_SCHEMA


def _generated_output() -> dict[str, Any]:
    intents = ("factual", "engagement", "concise")
    return {
        "suggestions": [
            {
                "id": f"candidate-{index}",
                "intent": intent,
                "publicationTitle": f"公開タイトル{index}",
                "overlayTitle": f"表示タイトル{index}",
                "hookText": f"フック{index}",
                "hookDurationSeconds": 2.0,
                "hookSceneStart": 0.0,
                "hookSceneEnd": 2.0,
                "reason": f"字幕segment_1が根拠{index}",
                "evidenceSegmentIds": ["segment_1"],
            }
            for index, intent in enumerate(intents, start=1)
        ],
        "recommendedSuggestionId": "candidate-1",
        "youtubeDescription": "字幕で確認できる会話を紹介します。",
        "hashtags": ["#会話", "#切り抜き", "#動画"],
        "descriptionEvidenceSegmentIds": ["segment_1"],
    }


def test_codex_generator_writes_fixed_bridge_request_and_reads_response(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    frame_path = storage_root / "temp" / "job_1" / "frame.jpg"
    frame_path.parent.mkdir(parents=True)
    frame_path.write_bytes(b"frame")
    captured: dict[str, Any] = {}
    thread_id = str(uuid4())

    def respond(_seconds: float) -> None:
        request_paths = list((storage_root / "codex_bridge" / "requests").glob("*.json"))
        assert len(request_paths) == 1
        request_payload = json.loads(request_paths[0].read_text(encoding="utf-8"))
        captured.update(request_payload)
        response_path = (
            storage_root
            / "codex_bridge"
            / "responses"
            / f"{request_payload['requestId']}.json"
        )
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "requestId": request_payload["requestId"],
                    "state": "ready",
                    "threadId": thread_id,
                    "output": _generated_output(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    generator = CodexTitleHookSuggestionGenerator(
        storage_root=storage_root,
        job_id="job_1",
        clip_id="short_1",
        model="codex-default",
        thread_id=thread_id,
        timeout_seconds=1,
        poll_seconds=0.01,
        sleep_func=respond,
    )

    result = generator.generate(
        {
            "clipType": "short",
            "clipDurationSeconds": 10,
            "segments": [
                {"segmentId": "segment_1", "start": 0, "end": 2, "text": "会話"}
            ],
        },
        [frame_path],
    )

    assert captured["task"] == "title_hook_suggestions"
    assert captured["responseSchema"] == TITLE_HOOK_GENERATION_SCHEMA
    assert captured["images"] == ["temp/job_1/frame.jpg"]
    assert captured["threadScope"] == "job_1:short_1"
    assert captured["threadId"] == thread_id
    assert "model" not in captured
    assert "segment_1" in captured["prompt"]
    assert result.recommended_suggestion_id == "candidate-1"
    assert result.youtube_description
    assert result.hashtags == ["#会話", "#切り抜き", "#動画"]
    assert generator.last_thread_id == thread_id
