import json
import sys
from collections.abc import Generator
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.db import Base, get_db
from app.jobs.queue import (
    get_enqueue_subtitle_review_preview,
    get_enqueue_title_hook_suggestions,
)
from app.jobs.subtitle_review import (
    apply_reviewed_clip_content,
    build_subtitle_review,
    load_subtitle_review,
    subtitle_review_output_path,
    write_subtitle_review,
)
from app.jobs.title_hook_suggestions import (
    TITLE_HOOK_GENERATION_CANCELLED_ERROR,
    TitleHookDraftSegment,
    TitleHookSuggestionsDocument,
    build_title_hook_suggestion_input,
    generate_title_hook_suggestions_for_auto,
    load_title_hook_suggestions,
    queued_title_hook_suggestions,
    run_title_hook_suggestion_generation,
    title_hook_suggestion_input_path,
    title_hook_suggestions_path,
    write_title_hook_suggestion_input,
    write_title_hook_suggestions,
)
from app.audio.transcribe_faster_whisper import TranscriptSegment
from app.main import app
from app.models import Job, Video
from app.posting_metadata import (
    NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX,
    write_youtube_posting_artifacts,
)
from app.scoring.title_hook_suggestions import (
    OPENAI_REQUEST_TIMEOUT_SECONDS,
    SYSTEM_PROMPT,
    TITLE_HOOK_GENERATION_SCHEMA,
    TITLE_HOOK_PROMPT_VERSION,
    OpenAITitleHookSuggestionGenerator,
    TitleHookSuggestionResult,
    extract_representative_frames,
    normalize_title_hook_suggestions,
)
from app.storage.paths import StoragePaths, get_storage_paths


def _candidate(
    candidate_id: str,
    candidate_type: str,
    start: float,
    end: float,
    *,
    title: str,
    overlay_title: str | None = None,
) -> Candidate:
    return Candidate(
        id=candidate_id,
        type=candidate_type,
        start=start,
        end=end,
        duration=end - start,
        transcript_text="字幕",
        title=title,
        overlay_title=overlay_title,
    )


def _suggestion_result() -> TitleHookSuggestionResult:
    return TitleHookSuggestionResult.model_validate(
        {
            "suggestions": [
                {
                    "id": "model-a",
                    "intent": "factual",
                    "publicationTitle": "会話の意外な展開を振り返る",
                    "overlayTitle": "まさかの展開",
                    "hookText": "その一言で流れが変わった",
                    "hookDurationSeconds": 2.0,
                    "hookSceneStart": 0.2,
                    "hookSceneEnd": 2.2,
                    "thumbnailKicker": "美学を考える",
                    "thumbnailLine1": "美しいものって",
                    "thumbnailLine2": "なんだろう？",
                    "thumbnailFrameSeconds": 8.5,
                    "reason": "発言直後の反応が伝わる",
                    "evidenceSegmentIds": [],
                },
                {
                    "id": "model-b",
                    "intent": "engagement",
                    "publicationTitle": "思わず聞き返した会話",
                    "overlayTitle": "聞き間違い？",
                    "hookText": "今、なんて言った？",
                    "hookDurationSeconds": 2.5,
                    "hookSceneStart": 28.0,
                    "hookSceneEnd": 31.0,
                    "reason": "clip終端付近のやり取りを使う",
                    "evidenceSegmentIds": [],
                },
                {
                    "id": "model-c",
                    "intent": "concise",
                    "publicationTitle": "予想外の返答に笑ってしまう",
                    "overlayTitle": "予想外の返答",
                    "hookText": "答えが想像と違いすぎた",
                    "hookDurationSeconds": 1.5,
                    "hookSceneStart": 4.0,
                    "hookSceneEnd": 4.4,
                    "reason": "短すぎる提案は正規化対象",
                    "evidenceSegmentIds": [],
                },
            ],
            "recommendedSuggestionId": "model-a",
            "youtubeDescription": "会話中に起きた意外な展開を振り返る切り抜きです。",
            "hashtags": ["#会話", "#切り抜き", "#動画"],
            "descriptionEvidenceSegmentIds": [],
        }
    )


def test_short_prompt_requires_scroll_stop_package_ranking() -> None:
    assert TITLE_HOOK_PROMPT_VERSION == "title_hook_suggestions_v9"
    assert "【ショート専用のタイトル・フック基準】" in SYSTEM_PROMPT
    assert "最初の0.3〜1秒" in SYSTEM_PROMPT
    assert "少なくとも6つの異なる切り口" in SYSTEM_PROMPT
    assert "publicationTitle、hookText、hookSceneStart / hookSceneEndの組み合わせ全体" in SYSTEM_PROMPT
    assert "スクロール停止力、具体性、一読理解、情報ギャップ" in SYSTEM_PROMPT
    assert "感想・指示語・疑問だけのフックを1案も返さない" in SYSTEM_PROMPT
    assert "対象を示さず期待だけを要求する文言は使用禁止" in SYSTEM_PROMPT
    assert "必須条件を満たさない案を3案へ含めず" in SYSTEM_PROMPT
    assert "無難さを優先しない" in SYSTEM_PROMPT


@pytest.fixture()
def title_hook_api(tmp_path: Path) -> Generator[dict[str, Any], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()
    source_path = storage.uploads / "source.mp4"
    source_path.write_bytes(b"test video")
    job_id = "job_title_hook"
    video_id = "vid_title_hook"
    with testing_session() as db:
        db.add(
            Video(
                id=video_id,
                original_filename="source.mp4",
                stored_path=str(source_path),
                duration=40,
                width=1280,
                height=720,
                fps=30,
                has_audio=True,
            )
        )
        db.add(
            Job(
                id=job_id,
                video_id=video_id,
                status="awaiting_subtitle_review",
                progress=88,
                current_step="字幕確認",
                settings_json={"openaiModel": "gpt-test-title-hook"},
            )
        )
        db.commit()

    selection = CandidateSelection(
        normalClips=[
            _candidate("normal_1", "normal", 0, 10, title="通常公開タイトル")
        ],
        shorts=[
            _candidate(
                "short_1",
                "short",
                10,
                30,
                title="ショート公開タイトル",
                overlay_title="ショート表示タイトル",
            )
        ],
    )
    transcript = [
        TranscriptSegment(start=1, end=5, text="通常字幕"),
        TranscriptSegment(start=11, end=15, text="最初のショート字幕"),
        TranscriptSegment(start=16, end=22, text="次のショート字幕"),
    ]
    review = build_subtitle_review(job_id, selection, transcript)
    write_subtitle_review(
        review,
        subtitle_review_output_path(storage.job_outputs(job_id)),
    )
    queued: list[tuple[str, str, str]] = []

    def override_get_db() -> Generator[Session, None, None]:
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_paths] = lambda: storage
    app.dependency_overrides[get_enqueue_subtitle_review_preview] = (
        lambda: lambda _job_id, _clip_id, _spec_hash: None
    )
    app.dependency_overrides[get_enqueue_title_hook_suggestions] = (
        lambda: lambda queued_job_id, queued_clip_id, input_hash: queued.append(
            (queued_job_id, queued_clip_id, input_hash)
        )
    )
    try:
        yield {
            "client": TestClient(app),
            "storage": storage,
            "session_factory": testing_session,
            "job_id": job_id,
            "review": review,
            "selection": selection,
            "queued": queued,
        }
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _short_drafts(review: Any) -> list[dict[str, str]]:
    clip = next(item for item in review.clips if item.id == "short_1")
    segment_by_id = {segment.id: segment for segment in review.segments}
    return [
        {
            "segmentId": segment_id,
            "text": f"修正: {segment_by_id[segment_id].text}",
        }
        for segment_id in clip.segment_ids
    ]


def test_title_hook_api_queues_caches_force_regenerates_and_gets(
    title_hook_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    client: TestClient = title_hook_api["client"]
    job_id = title_hook_api["job_id"]
    drafts = _short_drafts(title_hook_api["review"])
    url = f"/api/jobs/{job_id}/subtitle-review/clips/short_1/title-hook-suggestions"

    first = client.post(url, json={"segments": drafts, "forceRegenerate": False})
    cached = client.post(url, json={"segments": list(reversed(drafts)), "forceRegenerate": False})
    state_path = title_hook_suggestions_path(
        title_hook_api["storage"].job_outputs(job_id),
        "short_1",
    )
    previous = load_title_hook_suggestions(state_path).model_copy(
        update={"thread_id": "thread-existing"}
    )
    write_title_hook_suggestions(previous, state_path)
    forced = client.post(url, json={"segments": drafts, "forceRegenerate": True})
    fetched = client.get(url)

    assert first.status_code == 200
    assert first.json()["state"] == "queued"
    assert first.json()["model"] == "codex-default"
    assert first.json()["provider"] == "codex"
    assert len(first.json()["inputHash"]) == 64
    assert len(first.json()["draftHash"]) == 64
    assert cached.json()["inputHash"] == first.json()["inputHash"]
    assert cached.json()["draftHash"] == first.json()["draftHash"]
    assert forced.json()["inputHash"] == first.json()["inputHash"]
    assert forced.json()["threadId"] == "thread-existing"
    assert fetched.json() == forced.json()
    assert len(title_hook_api["queued"]) == 4


def test_ready_cache_requires_matching_raw_draft_hash(
    title_hook_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    client: TestClient = title_hook_api["client"]
    job_id = title_hook_api["job_id"]
    drafts = _short_drafts(title_hook_api["review"])
    url = f"/api/jobs/{job_id}/subtitle-review/clips/short_1/title-hook-suggestions"

    first = client.post(url, json={"segments": drafts, "forceRegenerate": False})
    output_dir = title_hook_api["storage"].job_outputs(job_id)
    state_path = title_hook_suggestions_path(output_dir, "short_1")
    pending = load_title_hook_suggestions(state_path)
    ready = pending.model_copy(
        update={
            "state": "ready",
            "suggestions": normalize_title_hook_suggestions(
                _suggestion_result(),
                clip_duration=20,
            ),
        }
    )
    write_title_hook_suggestions(ready, state_path)
    title_hook_api["queued"].clear()

    same = client.post(url, json={"segments": drafts, "forceRegenerate": False})
    changed_drafts = [dict(item) for item in drafts]
    changed_drafts[0]["text"] += "  "
    changed = client.post(
        url,
        json={"segments": changed_drafts, "forceRegenerate": False},
    )

    assert same.json()["state"] == "ready"
    assert changed.json()["state"] == "queued"
    assert changed.json()["inputHash"] == first.json()["inputHash"]
    assert changed.json()["draftHash"] != first.json()["draftHash"]
    assert len(title_hook_api["queued"]) == 1


@pytest.mark.parametrize("pending_state", ["queued", "generating"])
def test_get_reenqueues_pending_artifact_for_automatic_recovery(
    title_hook_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    pending_state: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    client: TestClient = title_hook_api["client"]
    job_id = title_hook_api["job_id"]
    url = f"/api/jobs/{job_id}/subtitle-review/clips/short_1/title-hook-suggestions"
    client.post(
        url,
        json={
            "segments": _short_drafts(title_hook_api["review"]),
            "forceRegenerate": False,
        },
    )
    state_path = title_hook_suggestions_path(
        title_hook_api["storage"].job_outputs(job_id),
        "short_1",
    )
    pending = load_title_hook_suggestions(state_path).model_copy(
        update={"state": pending_state}
    )
    write_title_hook_suggestions(pending, state_path)
    title_hook_api["queued"].clear()

    response = client.get(url)

    assert response.status_code == 200, response.text
    assert response.json()["state"] == pending_state
    assert title_hook_api["queued"] == [(job_id, "short_1", pending.input_hash)]


def test_get_does_not_reenqueue_pending_artifact_after_review_ends(
    title_hook_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    client: TestClient = title_hook_api["client"]
    job_id = title_hook_api["job_id"]
    url = f"/api/jobs/{job_id}/subtitle-review/clips/short_1/title-hook-suggestions"
    client.post(
        url,
        json={
            "segments": _short_drafts(title_hook_api["review"]),
            "forceRegenerate": False,
        },
    )
    with title_hook_api["session_factory"]() as db:
        job = db.get(Job, job_id)
        assert job is not None
        job.status = "completed"
        db.commit()
    title_hook_api["queued"].clear()

    response = client.get(url)

    assert response.status_code == 200
    assert response.json()["state"] == "queued"
    assert title_hook_api["queued"] == []


def test_draft_hash_preserves_raw_text_while_prompt_text_is_stripped(
    title_hook_api: dict[str, Any],
) -> None:
    review = title_hook_api["review"]
    clip = next(item for item in review.clips if item.id == "short_1")
    raw_text_by_id = {
        clip.segment_ids[0]: "\ufeff先頭BOMを保持 ",
        clip.segment_ids[1]: "末尾空白を保持  ",
    }
    drafts = [
        TitleHookDraftSegment(segmentId=segment_id, text=raw_text_by_id[segment_id])
        for segment_id in reversed(clip.segment_ids)
    ]

    suggestion_input = build_title_hook_suggestion_input(
        review,
        clip.id,
        drafts,
        model="gpt-5.5",
    )
    canonical_draft = json.dumps(
        [
            {"segmentId": segment_id, "text": raw_text_by_id[segment_id]}
            for segment_id in clip.segment_ids
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    assert suggestion_input.draft_hash == sha256(canonical_draft.encode("utf-8")).hexdigest()
    assert [segment.text for segment in suggestion_input.segments] == [
        raw_text_by_id[segment_id].strip() for segment_id in clip.segment_ids
    ]


def test_revision_hash_tracks_reviewed_content_not_provider_or_model(
    title_hook_api: dict[str, Any],
) -> None:
    review = title_hook_api["review"]
    drafts = [
        TitleHookDraftSegment.model_validate(item)
        for item in _short_drafts(review)
    ]
    codex_input = build_title_hook_suggestion_input(
        review,
        "short_1",
        drafts,
        model="codex-default",
        provider="codex",
    )
    openai_input = build_title_hook_suggestion_input(
        review,
        "short_1",
        drafts,
        model="gpt-test",
        provider="openai",
    )
    changed_drafts = [item.model_copy(deep=True) for item in drafts]
    changed_drafts[0].text += "変更"
    changed_input = build_title_hook_suggestion_input(
        review,
        "short_1",
        changed_drafts,
        model="codex-default",
        provider="codex",
    )

    assert codex_input.revision_hash == openai_input.revision_hash
    assert codex_input.input_hash != openai_input.input_hash
    assert changed_input.revision_hash != codex_input.revision_hash


def test_queued_document_can_preserve_codex_thread_for_regeneration(
    title_hook_api: dict[str, Any],
) -> None:
    review = title_hook_api["review"]
    request = build_title_hook_suggestion_input(
        review,
        "short_1",
        [
            TitleHookDraftSegment.model_validate(item)
            for item in _short_drafts(review)
        ],
        model="codex-default",
    )

    queued = queued_title_hook_suggestions(
        request,
        thread_id="a" * 32,
    )

    assert queued.thread_id == "a" * 32


def test_title_hook_api_rejects_incomplete_or_foreign_draft_snapshot(
    title_hook_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    client: TestClient = title_hook_api["client"]
    job_id = title_hook_api["job_id"]
    drafts = _short_drafts(title_hook_api["review"])
    url = f"/api/jobs/{job_id}/subtitle-review/clips/short_1/title-hook-suggestions"

    incomplete = client.post(url, json={"segments": drafts[:1], "forceRegenerate": False})
    foreign = client.post(
        url,
        json={
            "segments": [*drafts, {"segmentId": "segment_00000", "text": "別clip"}],
            "forceRegenerate": False,
        },
    )

    assert incomplete.status_code == 422
    assert incomplete.json()["detail"] == "all subtitle segments for the selected clip are required"
    assert foreign.status_code == 422
    assert foreign.json()["detail"] == "subtitle segment does not belong to the selected clip"


def test_title_hook_api_codex_default_does_not_require_openai_key(
    title_hook_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client: TestClient = title_hook_api["client"]
    job_id = title_hook_api["job_id"]
    response = client.post(
        f"/api/jobs/{job_id}/subtitle-review/clips/short_1/title-hook-suggestions",
        json={"segments": _short_drafts(title_hook_api["review"]), "forceRegenerate": False},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "queued"
    assert response.json()["provider"] == "codex"
    assert title_hook_api["queued"]


def test_subtitleless_clip_allows_empty_snapshot_and_generates_from_frame(
    title_hook_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "configured-for-test")
    storage: StoragePaths = title_hook_api["storage"]
    job_id = title_hook_api["job_id"]
    empty_review = build_subtitle_review(
        job_id,
        CandidateSelection(
            normalClips=[],
            shorts=[
                _candidate(
                    "short_empty",
                    "short",
                    10,
                    20,
                    title="字幕なしclip",
                )
            ],
        ),
        [],
    )
    write_subtitle_review(
        empty_review,
        subtitle_review_output_path(storage.job_outputs(job_id)),
    )
    response = title_hook_api["client"].post(
        f"/api/jobs/{job_id}/subtitle-review/clips/short_empty/title-hook-suggestions",
        json={"segments": [], "forceRegenerate": False},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "queued"

    class FrameGenerator:
        def generate(
            self,
            payload: dict[str, Any],
            frame_paths: list[Path],
        ) -> TitleHookSuggestionResult:
            assert payload["subtitleStatus"] == "unavailable"
            assert len(frame_paths) == 1
            return _suggestion_result()

    def one_frame(
        _source_path: Path,
        *,
        clip_start: float,
        clip_end: float,
        output_dir: Path,
    ) -> list[Path]:
        assert (clip_start, clip_end) == (10, 20)
        frame = output_dir / "frame.jpg"
        frame.write_bytes(b"frame")
        return [frame]

    worker_result = run_title_hook_suggestion_generation(
        job_id,
        "short_empty",
        response.json()["inputHash"],
        session_factory=title_hook_api["session_factory"],
        paths=storage,
        generator=FrameGenerator(),
        frame_extractor=one_frame,
    )

    assert worker_result == ["ready"]


def test_apply_persists_publication_title_and_absolute_hook_scene(
    title_hook_api: dict[str, Any],
) -> None:
    client: TestClient = title_hook_api["client"]
    job_id = title_hook_api["job_id"]
    response = client.post(
        f"/api/jobs/{job_id}/subtitle-review/clips/short_1/apply",
        json={
            "title": "動画内表示タイトル",
            "publicationTitle": "公開用タイトル",
            "hookText": "冒頭フック",
            "hookDurationSeconds": 2,
            "hookSceneStart": 12,
            "hookSceneEnd": 14,
            "segments": _short_drafts(title_hook_api["review"]),
        },
    )

    assert response.status_code == 200
    clip = next(item for item in response.json()["clips"] if item["id"] == "short_1")
    assert clip["publicationTitle"] == "公開用タイトル"
    assert clip["title"] == "動画内表示タイトル"
    assert clip["hookSceneStart"] == 12
    assert clip["hookSceneEnd"] == 14

    cleared = client.post(
        f"/api/jobs/{job_id}/subtitle-review/clips/short_1/apply",
        json={
            "title": "動画内表示タイトル",
            "publicationTitle": "公開用タイトル",
            "hookText": "",
            "hookDurationSeconds": 2,
            "hookSceneStart": None,
            "hookSceneEnd": None,
            "segments": _short_drafts(title_hook_api["review"]),
        },
    )
    cleared_clip = next(
        item for item in cleared.json()["clips"] if item["id"] == "short_1"
    )
    assert cleared.status_code == 200
    assert cleared_clip["hookSceneStart"] is None
    assert cleared_clip["hookSceneEnd"] is None

    incomplete_hook = client.post(
        f"/api/jobs/{job_id}/subtitle-review/clips/short_1/apply",
        json={
            "title": "動画内表示タイトル",
            "hookText": "",
            "hookDurationSeconds": 2,
            "hookSceneStart": 12,
            "segments": [],
        },
    )
    assert incomplete_hook.status_code == 422


def test_review_selection_separates_publication_and_overlay_titles(
    title_hook_api: dict[str, Any],
) -> None:
    review = title_hook_api["review"].model_copy(deep=True)
    short = next(item for item in review.clips if item.id == "short_1")
    short.publication_title = "新しい公開タイトル"
    short.title = "新しい表示タイトル"
    short.hook_text = "フック"
    short.hook_duration_seconds = 2
    short.hook_scene_start = 12
    short.hook_scene_end = 14

    applied = apply_reviewed_clip_content(title_hook_api["selection"], review)

    assert applied.shorts[0].title == "新しい公開タイトル"
    assert applied.shorts[0].overlay_title == "新しい表示タイトル"
    assert applied.shorts[0].hook_scene_start == 12
    assert applied.shorts[0].hook_scene_end == 14


@pytest.mark.parametrize("post_metadata_source", ["codex", "manual"])
def test_apply_keeps_copy_and_clears_stale_ai_metadata_when_subtitles_change(
    title_hook_api: dict[str, Any],
    post_metadata_source: str,
) -> None:
    review = title_hook_api["review"]
    drafts = _short_drafts(review)
    generation_input = build_title_hook_suggestion_input(
        review,
        "short_1",
        [TitleHookDraftSegment.model_validate(item) for item in drafts],
        model="codex-default",
    )
    changed_drafts = [dict(item) for item in drafts]
    changed_drafts[0]["text"] += " 修正"

    response = title_hook_api["client"].post(
        f"/api/jobs/{title_hook_api['job_id']}/subtitle-review/clips/short_1/apply",
        json={
            "title": "動画内表示タイトル",
            "publicationTitle": "公開用タイトル",
            "hookText": "冒頭フック",
            "hookDurationSeconds": 2,
            "segments": changed_drafts,
            "titleCandidates": [
                {
                    "id": "candidate-a",
                    "title": "公開用タイトル",
                    "intent": "factual",
                    "reason": "字幕に基づく",
                }
            ],
            "recommendedTitleId": "candidate-a",
            "selectedTitleId": "candidate-a",
            "youtubeDescription": "説明欄",
            "youtubeHashtags": ["#切り抜き"],
            "postMetadataSource": post_metadata_source,
            "postMetadataRevisionHash": generation_input.revision_hash,
        },
    )

    assert response.status_code == 200
    saved = next(item for item in response.json()["clips"] if item["id"] == "short_1")
    assert saved["publicationTitle"] == "公開用タイトル"
    assert saved["titleCandidates"] == []
    assert saved["recommendedTitleId"] is None
    assert saved["selectedTitleId"] is None
    assert saved["youtubeDescription"] == "説明欄"
    assert saved["youtubeHashtags"] == ["#切り抜き"]
    assert saved["descriptionEvidenceSegmentIds"] == []
    assert saved["postMetadataSource"] == "manual"
    assert saved["postMetadataRevisionHash"] is None


@pytest.mark.parametrize("clip_id", ["normal_1", "short_1"])
@pytest.mark.parametrize("source", ["codex", "manual"])
def test_posting_set_generated_from_unsaved_subtitles_survives_confirmation_and_export(
    title_hook_api: dict[str, Any], clip_id: str, source: str,
) -> None:
    review = title_hook_api["review"]
    clip = next(item for item in review.clips if item.id == clip_id)
    segments = {segment.id: segment for segment in review.segments}
    drafts = [{"segmentId": sid, "text": segments[sid].text + " 訂正済み"} for sid in clip.segment_ids]
    generation_input = build_title_hook_suggestion_input(
        review, clip_id, [TitleHookDraftSegment.model_validate(item) for item in drafts], model="codex-default",
    )
    result = _suggestion_result()
    suggestions = normalize_title_hook_suggestions(result, clip_duration=clip.duration)
    artifact = queued_title_hook_suggestions(generation_input).model_copy(update={
        "state": "ready", "suggestions": suggestions, "recommended_suggestion_id": suggestions[0].id,
        "youtube_description": result.youtube_description, "hashtags": result.hashtags,
    })
    job_id = title_hook_api["job_id"]
    output_dir = title_hook_api["storage"].job_outputs(job_id)
    write_title_hook_suggestions(artifact, title_hook_suggestions_path(output_dir, clip_id))
    source_url = "https://www.youtube.com/watch?v=gUgiNlCT8GM"
    with title_hook_api["session_factory"]() as db:
        job = db.get(Job, job_id)
        job.settings_json = {
            **job.settings_json, "youtubeSourceTitle": "元の配信", "youtubeSourceUrl": source_url,
            "youtubePostingProfile": {"performerName": "儒烏風亭らでん", "baseTags": ["らでん"], "baseHashtags": ["#ReGLOSS"]},
        }
        db.commit()
    description = "手で整えた説明文" if source == "manual" else result.youtube_description
    payload = {
        "title": suggestions[0].overlay_title,
        "publicationTitle": "手で整えた公開タイトル" if source == "manual" else suggestions[0].publication_title,
        "hookText": "", "hookDurationSeconds": 2, "segments": drafts,
        "titleCandidates": [
            {"id": s.id, "title": s.publication_title, "intent": s.intent, "reason": s.reason}
            for s in suggestions
        ],
        "recommendedTitleId": suggestions[0].id,
        "selectedTitleId": None if source == "manual" else suggestions[0].id,
        "youtubeDescription": description, "youtubeHashtags": result.hashtags, "youtubeTags": [],
        "postMetadataSource": source, "postMetadataRevisionHash": generation_input.revision_hash,
    }
    url = f"/api/jobs/{job_id}/subtitle-review/clips/{clip_id}/apply"
    response = title_hook_api["client"].post(url, json=payload)
    assert response.status_code == 200, response.text
    saved = next(item for item in response.json()["clips"] if item["id"] == clip_id)
    assert len(saved["titleCandidates"]) == 3
    assert saved["selectedTitleId"] == payload["selectedTitleId"]
    assert saved["postMetadataSource"] == source
    assert saved["postMetadataRevisionHash"] == generation_input.revision_hash
    assert saved["youtubeDescription"].startswith(description)
    assert source_url in saved["youtubeDescription"]
    assert "出演：" in saved["youtubeDescription"]
    assert "らでん" in saved["youtubeTags"]
    if source == "codex" and clip.type == "short":
        assert "#shortsfunny" in saved["youtubeHashtags"]

    # A second save must preserve edited text/tags and not duplicate credits.
    payload.update({key: saved[key] for key in ("youtubeDescription", "youtubeHashtags", "youtubeTags")})
    again = title_hook_api["client"].post(url, json=payload)
    assert again.status_code == 200, again.text
    again_clip = next(item for item in again.json()["clips"] if item["id"] == clip_id)
    assert again_clip["youtubeDescription"] == saved["youtubeDescription"]
    assert again_clip["youtubeTags"] == saved["youtubeTags"]
    restored = load_subtitle_review(subtitle_review_output_path(output_dir))
    selection = apply_reviewed_clip_content(title_hook_api["selection"], restored)
    exported = next(item for item in [*selection.normal_clips, *selection.shorts] if item.id == clip_id)
    json_path, markdown_path = write_youtube_posting_artifacts([exported], output_dir / "posting-assertion")
    posting = json.loads(json_path.read_text(encoding="utf-8"))["clips"][0]
    assert len(posting["titleCandidates"]) == 3
    assert posting["selectedTitleId"] == payload["selectedTitleId"]
    assert source_url in markdown_path.read_text(encoding="utf-8")
    assert posting["youtubeTags"] == saved["youtubeTags"]


@pytest.mark.parametrize("change_subtitle", [False, True])
def test_apply_preserves_stale_codex_copy_as_manual_without_blocking_save(
    title_hook_api: dict[str, Any],
    change_subtitle: bool,
) -> None:
    review = title_hook_api["review"]
    short = next(item for item in review.clips if item.id == "short_1")
    segment_by_id = {segment.id: segment for segment in review.segments}
    unchanged_drafts = [
        {"segmentId": segment_id, "text": segment_by_id[segment_id].text}
        for segment_id in short.segment_ids
    ]
    if change_subtitle:
        unchanged_drafts[0]["text"] = "修正した字幕"

    response = title_hook_api["client"].post(
        f"/api/jobs/{title_hook_api['job_id']}/subtitle-review/clips/short_1/apply",
        json={
            "title": "動画内表示タイトル",
            "publicationTitle": "公開用タイトル",
            "hookText": "冒頭フック",
            "hookDurationSeconds": 2,
            "segments": unchanged_drafts,
            "titleCandidates": [],
            "youtubeDescription": "説明欄",
            "youtubeHashtags": ["#切り抜き"],
            "youtubeTags": ["保存するタグ"],
            "postMetadataSource": "codex",
            "postMetadataRevisionHash": "f" * 64,
        },
    )

    assert response.status_code == 200, response.text
    saved = next(item for item in response.json()["clips"] if item["id"] == "short_1")
    assert saved["publicationTitle"] == "公開用タイトル"
    assert saved["hookText"] == "冒頭フック"
    assert saved["youtubeDescription"].startswith("説明欄")
    assert saved["youtubeTags"] == ["保存するタグ"]
    assert saved["postMetadataSource"] == "manual"
    assert saved["postMetadataRevisionHash"] is None
    assert saved["titleCandidates"] == []
    assert saved["descriptionEvidenceSegmentIds"] == []
    if change_subtitle:
        segment = next(item for item in response.json()["segments"] if item["id"] == unchanged_drafts[0]["segmentId"])
        assert segment["text"] == "修正した字幕"


def test_apply_rehydrates_evidence_ids_from_ready_codex_artifact(
    title_hook_api: dict[str, Any],
) -> None:
    review = title_hook_api["review"]
    short = next(item for item in review.clips if item.id == "short_1")
    segment_by_id = {segment.id: segment for segment in review.segments}
    segment_id = short.segment_ids[0]
    drafts = [
        {"segmentId": item_id, "text": segment_by_id[item_id].text}
        for item_id in short.segment_ids
    ]
    generation_input = build_title_hook_suggestion_input(
        review,
        "short_1",
        [TitleHookDraftSegment.model_validate(item) for item in drafts],
        model="codex-default",
    )
    result_payload = _suggestion_result().model_dump(by_alias=True, mode="json")
    for suggestion in result_payload["suggestions"]:
        suggestion["evidenceSegmentIds"] = [segment_id]
    result_payload["descriptionEvidenceSegmentIds"] = [segment_id]
    result = TitleHookSuggestionResult.model_validate(result_payload)
    suggestions = normalize_title_hook_suggestions(result, clip_duration=short.duration)
    ready = queued_title_hook_suggestions(generation_input).model_copy(
        update={
            "state": "ready",
            "suggestions": suggestions,
            "recommended_suggestion_id": "suggestion_1",
            "youtube_description": result.youtube_description,
            "hashtags": result.hashtags,
            "description_evidence_segment_ids": result.description_evidence_segment_ids,
        }
    )
    output_dir = title_hook_api["storage"].job_outputs(title_hook_api["job_id"])
    write_title_hook_suggestions(
        ready,
        title_hook_suggestions_path(output_dir, "short_1"),
    )

    response = title_hook_api["client"].post(
        f"/api/jobs/{title_hook_api['job_id']}/subtitle-review/clips/short_1/apply",
        json={
            "title": suggestions[0].overlay_title,
            "publicationTitle": suggestions[0].publication_title,
            "hookText": suggestions[0].hook_text,
            "hookDurationSeconds": suggestions[0].hook_duration_seconds,
            "hookSceneStart": short.start + (suggestions[0].hook_scene_start or 0),
            "hookSceneEnd": short.start + (suggestions[0].hook_scene_end or 0),
            "segments": drafts,
            "titleCandidates": [
                {
                    "id": suggestion.id,
                    "title": suggestion.publication_title,
                    "intent": suggestion.intent,
                    "reason": suggestion.reason,
                }
                for suggestion in suggestions
            ],
            "recommendedTitleId": "suggestion_1",
            "selectedTitleId": None,
            "youtubeDescription": result.youtube_description,
            "youtubeHashtags": result.hashtags,
            "postMetadataSource": "codex",
            "postMetadataRevisionHash": generation_input.revision_hash,
        },
    )

    assert response.status_code == 200, response.text
    saved = next(item for item in response.json()["clips"] if item["id"] == "short_1")
    assert saved["titleCandidates"][0]["evidenceSegmentIds"] == [segment_id]
    assert saved["descriptionEvidenceSegmentIds"] == [segment_id]

    restored = load_subtitle_review(subtitle_review_output_path(output_dir))
    applied = apply_reviewed_clip_content(title_hook_api["selection"], restored).shorts[0]
    assert applied.title_candidates[0].evidence_segment_ids == [segment_id]
    assert applied.description_evidence_segment_ids == [segment_id]
    json_path, _markdown_path = write_youtube_posting_artifacts(
        [applied],
        output_dir / "posting_assertion",
    )
    posting = json.loads(json_path.read_text(encoding="utf-8"))["clips"][0]
    assert posting["titleCandidates"][0]["evidenceSegmentIds"] == [segment_id]
    assert posting["descriptionEvidenceSegmentIds"] == [segment_id]


def test_legacy_review_without_publication_title_falls_back_to_display_title(
    title_hook_api: dict[str, Any],
) -> None:
    review = title_hook_api["review"]
    payload = review.model_dump(by_alias=True, mode="json")
    for clip in payload["clips"]:
        clip.pop("publicationTitle")
    legacy_short = next(clip for clip in payload["clips"] if clip["id"] == "short_1")
    legacy_short["title"] = "ショート公開タイトル"
    legacy = type(review).model_validate(payload)

    applied = apply_reviewed_clip_content(title_hook_api["selection"], legacy)

    legacy_normal = next(clip for clip in legacy.clips if clip.type == "normal")
    legacy_short_clip = next(clip for clip in legacy.clips if clip.type == "short")
    assert legacy_normal.publication_title is not None
    assert legacy_normal.publication_title.endswith(NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX)
    assert legacy_short_clip.publication_title is None
    assert applied.shorts[0].title == "ショート公開タイトル"
    assert applied.shorts[0].overlay_title == "ショート表示タイトル"
    assert applied.shorts[0].title_source == title_hook_api["selection"].shorts[0].title_source


def test_legacy_review_applies_manually_edited_short_title_to_overlay(
    title_hook_api: dict[str, Any],
) -> None:
    review = title_hook_api["review"]
    payload = review.model_dump(by_alias=True, mode="json")
    for clip in payload["clips"]:
        clip.pop("publicationTitle")
    legacy_short = next(clip for clip in payload["clips"] if clip["id"] == "short_1")
    legacy_short["title"] = "旧画面で手動編集した表示タイトル"
    legacy_short["titleEdited"] = True
    legacy = type(review).model_validate(payload)

    applied = apply_reviewed_clip_content(title_hook_api["selection"], legacy)

    assert applied.shorts[0].title == "旧画面で手動編集した表示タイトル"
    assert applied.shorts[0].overlay_title == "旧画面で手動編集した表示タイトル"
    assert applied.shorts[0].title_source == "manual_review"


def test_legacy_normal_uses_review_title_even_when_candidate_overlay_differs(
    title_hook_api: dict[str, Any],
) -> None:
    review = title_hook_api["review"]
    payload = review.model_dump(by_alias=True, mode="json")
    for clip in payload["clips"]:
        clip.pop("publicationTitle")
    legacy_normal = next(clip for clip in payload["clips"] if clip["id"] == "normal_1")
    legacy_normal["title"] = "旧通常reviewタイトル"
    legacy = type(review).model_validate(payload)
    selection = title_hook_api["selection"].model_copy(
        update={
            "normal_clips": [
                title_hook_api["selection"].normal_clips[0].model_copy(
                    update={"overlay_title": "候補側の異なる通常overlay"}
                )
            ]
        }
    )

    applied = apply_reviewed_clip_content(selection, legacy)

    assert applied.normal_clips[0].title == (
        f"旧通常reviewタイトル{NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX}"
    )
    assert applied.normal_clips[0].overlay_title == "旧通常reviewタイトル"
    assert applied.normal_clips[0].title_source == "manual_review"


def test_default_openai_client_disables_sdk_retries_and_sets_bounded_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_client = object()

    def fake_openai(**kwargs: Any) -> object:
        captured.update(kwargs)
        return fake_client

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=fake_openai))
    import app.scoring.title_hook_suggestions as title_hook_module

    loaded = title_hook_module._load_default_client()

    assert loaded is fake_client
    assert captured == {
        "max_retries": 0,
        "timeout": OPENAI_REQUEST_TIMEOUT_SECONDS,
    }
    assert OPENAI_REQUEST_TIMEOUT_SECONDS < 900 / 4


def _prepare_worker_case(title_hook_api: dict[str, Any]) -> dict[str, Any]:
    storage: StoragePaths = title_hook_api["storage"]
    job_id = title_hook_api["job_id"]
    review = title_hook_api["review"]
    request = build_title_hook_suggestion_input(
        review,
        "short_1",
        [TitleHookDraftSegment.model_validate(item) for item in _short_drafts(review)],
        model="gpt-test-title-hook",
    )
    output_dir = storage.job_outputs(job_id)
    state_path = title_hook_suggestions_path(output_dir, "short_1")
    write_title_hook_suggestion_input(
        request,
        title_hook_suggestion_input_path(output_dir, "short_1"),
    )
    write_title_hook_suggestions(queued_title_hook_suggestions(request), state_path)
    return {
        "storage": storage,
        "job_id": job_id,
        "review": review,
        "request": request,
        "output_dir": output_dir,
        "state_path": state_path,
    }


def test_worker_cancels_before_frames_when_job_left_subtitle_review(
    title_hook_api: dict[str, Any],
) -> None:
    case = _prepare_worker_case(title_hook_api)
    with title_hook_api["session_factory"]() as db:
        job = db.get(Job, case["job_id"])
        assert job is not None
        job.status = "completed"
        db.commit()

    class UnexpectedGenerator:
        def generate(
            self,
            _payload: dict[str, Any],
            _frame_paths: list[Path],
        ) -> TitleHookSuggestionResult:
            raise AssertionError("provider must not be called")

    def unexpected_frames(*_args: Any, **_kwargs: Any) -> list[Path]:
        raise AssertionError("frame extraction must not be called")

    result = run_title_hook_suggestion_generation(
        case["job_id"],
        "short_1",
        case["request"].input_hash,
        session_factory=title_hook_api["session_factory"],
        paths=case["storage"],
        generator=UnexpectedGenerator(),
        frame_extractor=unexpected_frames,
    )
    artifact = load_title_hook_suggestions(case["state_path"])

    assert result == ["cancelled"]
    assert artifact.state == "failed"
    assert artifact.error == TITLE_HOOK_GENERATION_CANCELLED_ERROR


def test_worker_rechecks_review_state_before_provider_call(
    title_hook_api: dict[str, Any],
) -> None:
    case = _prepare_worker_case(title_hook_api)
    review_path = subtitle_review_output_path(case["output_dir"])

    def end_review_before_provider(*_args: Any, **_kwargs: Any) -> list[Path]:
        ended = case["review"].model_copy(update={"state": "render_queued"})
        write_subtitle_review(ended, review_path)
        return []

    class UnexpectedGenerator:
        def generate(
            self,
            _payload: dict[str, Any],
            _frame_paths: list[Path],
        ) -> TitleHookSuggestionResult:
            raise AssertionError("provider must not be called")

    result = run_title_hook_suggestion_generation(
        case["job_id"],
        "short_1",
        case["request"].input_hash,
        session_factory=title_hook_api["session_factory"],
        paths=case["storage"],
        generator=UnexpectedGenerator(),
        frame_extractor=end_review_before_provider,
    )
    artifact = load_title_hook_suggestions(case["state_path"])

    assert result == ["cancelled"]
    assert artifact.error == TITLE_HOOK_GENERATION_CANCELLED_ERROR
    assert load_subtitle_review(review_path).state == "render_queued"


def test_worker_discards_provider_result_when_review_ends_before_write(
    title_hook_api: dict[str, Any],
) -> None:
    case = _prepare_worker_case(title_hook_api)
    review_path = subtitle_review_output_path(case["output_dir"])

    class EndingGenerator:
        calls = 0

        def generate(
            self,
            _payload: dict[str, Any],
            _frame_paths: list[Path],
        ) -> TitleHookSuggestionResult:
            self.calls += 1
            ended = case["review"].model_copy(update={"state": "render_queued"})
            write_subtitle_review(ended, review_path)
            return _suggestion_result()

    generator = EndingGenerator()
    result = run_title_hook_suggestion_generation(
        case["job_id"],
        "short_1",
        case["request"].input_hash,
        session_factory=title_hook_api["session_factory"],
        paths=case["storage"],
        generator=generator,
        frame_extractor=lambda *_args, **_kwargs: [],
    )
    artifact = load_title_hook_suggestions(case["state_path"])

    assert generator.calls == 1
    assert result == ["cancelled"]
    assert artifact.state == "failed"
    assert artifact.suggestions == []
    assert artifact.error == TITLE_HOOK_GENERATION_CANCELLED_ERROR


def test_worker_uses_text_only_fallback_and_normalizes_clip_relative_scene(
    title_hook_api: dict[str, Any],
) -> None:
    storage: StoragePaths = title_hook_api["storage"]
    job_id = title_hook_api["job_id"]
    review = title_hook_api["review"]
    request = build_title_hook_suggestion_input(
        review,
        "short_1",
        [TitleHookDraftSegment.model_validate(item) for item in _short_drafts(review)],
        model="gpt-test-title-hook",
    )
    output_dir = storage.job_outputs(job_id)
    write_title_hook_suggestion_input(
        request,
        title_hook_suggestion_input_path(output_dir, "short_1"),
    )
    write_title_hook_suggestions(
        queued_title_hook_suggestions(request),
        title_hook_suggestions_path(output_dir, "short_1"),
    )

    class FakeGenerator:
        def __init__(self) -> None:
            self.payload: dict[str, Any] | None = None
            self.frames: list[Path] | None = None

        def generate(
            self,
            payload: dict[str, Any],
            frame_paths: list[Path],
        ) -> TitleHookSuggestionResult:
            self.payload = payload
            self.frames = list(frame_paths)
            return _suggestion_result()

    generator = FakeGenerator()

    def failed_frames(*_args: Any, **_kwargs: Any) -> list[Path]:
        raise RuntimeError("ffmpeg unavailable")

    result = run_title_hook_suggestion_generation(
        job_id,
        "short_1",
        request.input_hash,
        session_factory=title_hook_api["session_factory"],
        paths=storage,
        generator=generator,
        frame_extractor=failed_frames,
    )
    artifact = load_title_hook_suggestions(
        title_hook_suggestions_path(output_dir, "short_1")
    )

    assert result == ["ready"]
    assert artifact.state == "ready"
    assert generator.frames == []
    assert generator.payload is not None
    assert set(generator.payload) == {
        "normalTitleSuffix",
        "clipType",
        "clipDurationSeconds",
        "timestampSemantics",
        "subtitleStatus",
        "segments",
    }
    assert artifact.suggestions[1].hook_scene_start == 17
    assert artifact.suggestions[1].hook_scene_end == 20
    assert artifact.suggestions[2].hook_scene_end - artifact.suggestions[2].hook_scene_start == 1.5
    assert artifact.recommended_suggestion_id == "suggestion_1"
    assert artifact.youtube_description == _suggestion_result().youtube_description
    assert artifact.hashtags == ["#会話", "#切り抜き", "#動画"]
    assert artifact.provider == "codex"
    assert artifact.revision_hash == request.revision_hash


def test_worker_rejects_unknown_evidence_segment_id(
    title_hook_api: dict[str, Any],
) -> None:
    case = _prepare_worker_case(title_hook_api)

    class UnknownEvidenceGenerator:
        def generate(
            self,
            _payload: dict[str, Any],
            _frame_paths: list[Path],
        ) -> TitleHookSuggestionResult:
            payload = _suggestion_result().model_dump(by_alias=True, mode="json")
            payload["suggestions"][0]["evidenceSegmentIds"] = ["segment_unknown"]
            return TitleHookSuggestionResult.model_validate(payload)

    result = run_title_hook_suggestion_generation(
        case["job_id"],
        "short_1",
        case["request"].input_hash,
        session_factory=title_hook_api["session_factory"],
        paths=case["storage"],
        generator=UnknownEvidenceGenerator(),
        frame_extractor=lambda *_args, **_kwargs: [],
    )
    artifact = load_title_hook_suggestions(case["state_path"])

    assert result == ["failed"]
    assert artifact.state == "failed"
    assert artifact.error == "title/hook generation failed (ValueError)"
    assert artifact.suggestions == []


def test_worker_does_not_overwrite_newer_input_hash(
    title_hook_api: dict[str, Any],
) -> None:
    storage: StoragePaths = title_hook_api["storage"]
    job_id = title_hook_api["job_id"]
    review = title_hook_api["review"]
    request = build_title_hook_suggestion_input(
        review,
        "short_1",
        [TitleHookDraftSegment.model_validate(item) for item in _short_drafts(review)],
        model="gpt-test-title-hook",
    )
    output_dir = storage.job_outputs(job_id)
    state_path = title_hook_suggestions_path(output_dir, "short_1")
    write_title_hook_suggestion_input(
        request,
        title_hook_suggestion_input_path(output_dir, "short_1"),
    )
    write_title_hook_suggestions(queued_title_hook_suggestions(request), state_path)

    class RacingGenerator:
        def generate(
            self,
            _payload: dict[str, Any],
            _frame_paths: list[Path],
        ) -> TitleHookSuggestionResult:
            write_title_hook_suggestions(
                queued_title_hook_suggestions(
                    request.model_copy(update={"input_hash": "b" * 64})
                ),
                state_path,
            )
            return _suggestion_result()

    result = run_title_hook_suggestion_generation(
        job_id,
        "short_1",
        request.input_hash,
        session_factory=title_hook_api["session_factory"],
        paths=storage,
        generator=RacingGenerator(),
        frame_extractor=lambda *_args, **_kwargs: [],
    )

    assert result == ["superseded"]
    assert load_title_hook_suggestions(state_path).input_hash == "b" * 64


def test_worker_preserves_main_job_after_provider_retries_are_exhausted(
    title_hook_api: dict[str, Any],
) -> None:
    case = _prepare_worker_case(title_hook_api)

    class RateLimitError(Exception):
        status_code = 429

    class ExhaustedResponses:
        calls = 0

        def create(self, **_kwargs: Any) -> Any:
            self.calls += 1
            raise RateLimitError("provider body containing secret-token-value")

    responses = ExhaustedResponses()
    generator = OpenAITitleHookSuggestionGenerator(
        model="gpt-test-title-hook",
        client=SimpleNamespace(responses=responses),
        max_retries=1,
        sleep_func=lambda _seconds: None,
    )

    result = run_title_hook_suggestion_generation(
        case["job_id"],
        "short_1",
        case["request"].input_hash,
        session_factory=title_hook_api["session_factory"],
        paths=case["storage"],
        generator=generator,
        frame_extractor=lambda *_args, **_kwargs: [],
    )
    artifact = load_title_hook_suggestions(case["state_path"])
    with title_hook_api["session_factory"]() as db:
        job = db.get(Job, case["job_id"])
        assert job is not None
        job_status = job.status

    assert responses.calls == 2
    assert result == ["failed"]
    assert artifact.error == "title/hook generation failed (RateLimitError)"
    assert "secret-token-value" not in artifact.model_dump_json()
    assert job_status == "awaiting_subtitle_review"
    assert load_subtitle_review(
        subtitle_review_output_path(case["output_dir"])
    ).state == "awaiting_review"


def test_openai_generator_retries_transient_error_and_disables_storage(
    tmp_path: Path,
) -> None:
    class RateLimitError(Exception):
        status_code = 429

    class FakeResponses:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise RateLimitError("sensitive provider response")
            return SimpleNamespace(
                output_text=json.dumps(
                    _suggestion_result().model_dump(by_alias=True, mode="json"),
                    ensure_ascii=False,
                )
            )

    image_path = tmp_path / "frame.jpg"
    image_path.write_bytes(b"jpeg")
    responses = FakeResponses()
    sleeps: list[float] = []
    generator = OpenAITitleHookSuggestionGenerator(
        model="gpt-test",
        client=SimpleNamespace(responses=responses),
        max_retries=1,
        sleep_func=sleeps.append,
    )

    generated = generator.generate(
        {"clipType": "short", "clipDurationSeconds": 20, "segments": []},
        [image_path],
    )

    assert len(generated.suggestions) == 3
    assert len(responses.calls) == 2
    assert sleeps == [0.25]
    assert responses.calls[-1]["store"] is False
    user_content = responses.calls[-1]["input"][1]["content"]
    assert user_content[0]["type"] == "input_text"
    assert user_content[1]["text"] == "次の代表フレームはclip相対10.000秒です。"
    assert user_content[2]["image_url"].startswith("data:image/jpeg;base64,")


def test_openai_image_labels_preserve_original_timestamp_when_frame_is_missing(
    tmp_path: Path,
) -> None:
    class FakeResponses:
        def __init__(self) -> None:
            self.call: dict[str, Any] | None = None

        def create(self, **kwargs: Any) -> Any:
            self.call = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    _suggestion_result().model_dump(by_alias=True, mode="json"),
                    ensure_ascii=False,
                )
            )

    frame_1 = tmp_path / "frame_1.jpg"
    frame_3 = tmp_path / "frame_3.jpg"
    frame_1.write_bytes(b"first")
    frame_3.write_bytes(b"third")
    responses = FakeResponses()
    generator = OpenAITitleHookSuggestionGenerator(
        model="gpt-test",
        client=SimpleNamespace(responses=responses),
        max_retries=0,
    )

    generator.generate(
        {"clipType": "short", "clipDurationSeconds": 20, "segments": []},
        [frame_1, frame_3],
    )

    assert responses.call is not None
    content = responses.call["input"][1]["content"]
    assert [item["type"] for item in content] == [
        "input_text",
        "input_text",
        "input_image",
        "input_text",
        "input_image",
    ]
    assert content[1]["text"] == "次の代表フレームはclip相対2.400秒です。"
    assert content[3]["text"] == "次の代表フレームはclip相対12.400秒です。"


def test_frame_extraction_continues_after_one_failed_frame(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: Any) -> Any:
        calls.append(command)
        if len(calls) == 2:
            raise RuntimeError("one frame failed")
        Path(command[-1]).write_bytes(b"frame")
        return SimpleNamespace(returncode=0)

    frames = extract_representative_frames(
        tmp_path / "input.mp4",
        clip_start=10,
        clip_end=30,
        output_dir=tmp_path / "frames",
        runner=runner,
    )

    assert len(calls) == 4
    assert [path.name for path in frames] == ["frame_1.jpg", "frame_3.jpg", "frame_4.jpg"]


def test_normalization_clamps_scenes_to_clip_range() -> None:
    suggestions = normalize_title_hook_suggestions(
        _suggestion_result(),
        clip_duration=20,
    )

    assert [item.id for item in suggestions] == [
        "suggestion_1",
        "suggestion_2",
        "suggestion_3",
    ]
    assert all(0 <= item.hook_scene_start < item.hook_scene_end <= 20 for item in suggestions)
    assert all(1.5 <= item.hook_scene_end - item.hook_scene_start <= 3 for item in suggestions)


def test_normalization_suffixes_only_normal_publication_titles() -> None:
    normal = normalize_title_hook_suggestions(
        _suggestion_result(),
        clip_duration=20,
        clip_type="normal",
    )
    short = normalize_title_hook_suggestions(
        _suggestion_result(),
        clip_duration=20,
        clip_type="short",
    )

    assert all(
        item.publication_title.endswith(NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX)
        for item in normal
    )
    assert all(
        not item.publication_title.endswith(NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX)
        for item in short
    )
    assert normal[0].overlay_title == short[0].overlay_title
    assert normal[0].thumbnail_kicker == "美学を考える"
    assert normal[0].thumbnail_line1 == "美しいものって"
    assert normal[0].thumbnail_line2 == "なんだろう？"
    assert normal[0].thumbnail_frame_seconds == 8.5
    assert normal[1].thumbnail_kicker
    assert normal[1].thumbnail_line1
    assert normal[1].thumbnail_frame_seconds == 20
    assert all(item.thumbnail_kicker == "" for item in short)
    assert all(item.thumbnail_line1 == "" for item in short)
    assert all(item.thumbnail_line2 == "" for item in short)
    assert all(item.thumbnail_frame_seconds is None for item in short)


def test_generation_schema_requires_thumbnail_contract_in_same_suggestion() -> None:
    suggestion_schema = TITLE_HOOK_GENERATION_SCHEMA["properties"]["suggestions"]["items"]

    assert {
        "thumbnailKicker",
        "thumbnailLine1",
        "thumbnailLine2",
        "thumbnailFrameSeconds",
    }.issubset(set(suggestion_schema["required"]))


def test_auto_generation_maps_recommended_source_id_to_normalized_id(
    tmp_path: Path,
) -> None:
    short = _candidate(
        "short_auto",
        "short",
        0,
        20,
        title="自動生成前",
    )
    document = build_subtitle_review(
        "job_auto_title_hook",
        CandidateSelection(normalClips=[], shorts=[short]),
        [],
    )
    result_payload = _suggestion_result().model_dump(by_alias=True, mode="json")
    result_payload["recommendedSuggestionId"] = "model-b"
    result = TitleHookSuggestionResult.model_validate(result_payload)
    generator = SimpleNamespace(generate=lambda _payload, _frames: result)
    storage = StoragePaths(tmp_path / "storage")
    storage.ensure()

    artifact = generate_title_hook_suggestions_for_auto(
        document=document,
        clip_id=short.id,
        source_path=tmp_path / "source.mp4",
        paths=storage,
        model="codex-default",
        generator=generator,
        frame_extractor=lambda *_args, **_kwargs: [tmp_path / "frame.jpg"],
    )

    assert [item.id for item in artifact.suggestions] == [
        "suggestion_1",
        "suggestion_2",
        "suggestion_3",
    ]
    assert artifact.recommended_suggestion_id == "suggestion_2"
    persisted = load_title_hook_suggestions(
        title_hook_suggestions_path(
            storage.job_outputs(document.job_id),
            short.id,
        )
    )
    assert persisted.recommended_suggestion_id == "suggestion_2"


def test_suggestion_contract_accepts_explicit_no_hook() -> None:
    payload = _suggestion_result().model_dump(by_alias=True, mode="json")
    payload["suggestions"][0].update(
        {
            "hookText": "",
            "hookDurationSeconds": 2,
            "hookSceneStart": None,
            "hookSceneEnd": None,
        }
    )

    result = TitleHookSuggestionResult.model_validate(payload)
    normalized = normalize_title_hook_suggestions(result, clip_duration=20)

    assert normalized[0].hook_text == ""
    assert normalized[0].hook_scene_start is None
    assert normalized[0].hook_scene_end is None


def test_legacy_suggestion_artifact_without_draft_hash_is_accepted() -> None:
    payload = queued_title_hook_suggestions(
        build_title_hook_suggestion_input(
            build_subtitle_review(
                "job_legacy",
                CandidateSelection(
                    normalClips=[],
                    shorts=[
                        _candidate(
                            "short_legacy",
                            "short",
                            0,
                            10,
                            title="旧clip",
                        )
                    ],
                ),
                [],
            ),
            "short_legacy",
            [],
            model="gpt-5.5",
        )
    ).model_dump(by_alias=True, mode="json")
    for key in (
        "draftHash",
        "revisionHash",
        "provider",
        "threadId",
        "recommendedSuggestionId",
        "youtubeDescription",
        "hashtags",
        "descriptionEvidenceSegmentIds",
    ):
        payload.pop(key)

    restored = TitleHookSuggestionsDocument.model_validate(payload)
    assert restored.draft_hash is None
    assert restored.revision_hash is None
    assert restored.provider == "openai"
    assert restored.youtube_description == ""


def test_legacy_suggestion_result_fills_intents_and_recommendation() -> None:
    payload = _suggestion_result().model_dump(by_alias=True, mode="json")
    for suggestion in payload["suggestions"]:
        suggestion.pop("intent")
        suggestion.pop("evidenceSegmentIds")
        suggestion.pop("thumbnailKicker")
        suggestion.pop("thumbnailLine1")
        suggestion.pop("thumbnailLine2")
        suggestion.pop("thumbnailFrameSeconds")
    for key in (
        "recommendedSuggestionId",
        "youtubeDescription",
        "hashtags",
        "descriptionEvidenceSegmentIds",
    ):
        payload.pop(key)

    restored = TitleHookSuggestionResult.model_validate(payload)

    assert [item.intent for item in restored.suggestions] == [
        "factual",
        "engagement",
        "concise",
    ]
    assert restored.recommended_suggestion_id == "model-a"
    assert restored.suggestions[0].thumbnail_kicker == ""
    assert restored.suggestions[0].thumbnail_frame_seconds is None
