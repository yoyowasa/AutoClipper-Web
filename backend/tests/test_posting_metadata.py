import json
from pathlib import Path
from types import SimpleNamespace

from app.posting_metadata import (
    YouTubePostingProfile,
    YouTubeTitleCandidate,
    build_post_metadata_revision_hash,
    build_youtube_posting_copy,
    write_youtube_posting_artifacts,
)


def test_post_metadata_revision_changes_with_text_or_boundary_only() -> None:
    segments = [{"segmentId": "seg_1", "start": 10.0, "end": 11.0, "text": "本文"}]
    first = build_post_metadata_revision_hash(
        clip_id="clip_1",
        clip_type="short",
        start=10.0,
        end=20.0,
        segments=segments,
    )
    same = build_post_metadata_revision_hash(
        clip_id="clip_1",
        clip_type="short",
        start=10,
        end=20,
        segments=segments,
    )
    changed_text = build_post_metadata_revision_hash(
        clip_id="clip_1",
        clip_type="short",
        start=10.0,
        end=20.0,
        segments=[{**segments[0], "text": "修正版"}],
    )
    changed_boundary = build_post_metadata_revision_hash(
        clip_id="clip_1",
        clip_type="short",
        start=10.0,
        end=21.0,
        segments=segments,
    )

    assert first == same
    assert first != changed_text
    assert first != changed_boundary


def test_youtube_posting_artifacts_are_copy_ready(tmp_path: Path) -> None:
    candidates = [
        YouTubeTitleCandidate(
            id="a",
            title="候補A",
            intent="factual",
            reason="根拠A",
            evidenceSegmentIds=["seg_1"],
        ),
        YouTubeTitleCandidate(id="b", title="候補B", intent="engagement", reason="根拠B"),
        YouTubeTitleCandidate(id="c", title="候補C", intent="concise", reason="根拠C"),
    ]
    clip = SimpleNamespace(
        id="short_1",
        type="short",
        title="動画内タイトル",
        publication_title="手編集タイトル",
        title_candidates=candidates,
        recommended_title_id="a",
        selected_title_id=None,
        youtube_description="説明欄本文",
        youtube_hashtags=["#切り抜き", "#Shorts"],
        youtube_tags=["儒烏風亭らでん", "ReGLOSS"],
        description_evidence_segment_ids=["seg_1"],
        post_metadata_source="codex",
        post_metadata_revision_hash="b" * 64,
    )

    json_path, markdown_path = write_youtube_posting_artifacts([clip], tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert payload["clips"][0]["selectedTitle"] == "手編集タイトル"
    assert payload["clips"][0]["titleCandidates"][0]["intent"] == "factual"
    assert payload["clips"][0]["titleCandidates"][0]["evidenceSegmentIds"] == ["seg_1"]
    assert payload["clips"][0]["descriptionEvidenceSegmentIds"] == ["seg_1"]
    assert payload["version"] == 2
    assert payload["clips"][0]["youtubeTags"] == ["儒烏風亭らでん", "ReGLOSS"]
    assert "説明欄本文" in markdown
    assert "#切り抜き #Shorts" in markdown
    assert "儒烏風亭らでん,ReGLOSS" in markdown


def test_youtube_posting_copy_uses_fixed_template_and_short_hashtag() -> None:
    copy = build_youtube_posting_copy(
        clip_type="short",
        source_title="【雑談】たのしい休肝日計画【儒烏風亭らでん #ReGLOSS】",
        source_url="https://www.youtube.com/watch?v=z8eCi7kAEVI",
        profile=YouTubePostingProfile(
            performerName="儒烏風亭らでん",
            affiliation="hololive DEV_IS / ReGLOSS",
            baseHashtags=["#儒烏風亭らでん", "#ReGLOSS", "#ホロライブ切り抜き"],
            shortHashtags=["#shortsfunny"],
            baseTags=["儒烏風亭らでん", "らでん", "ReGLOSS"],
        ),
        fallback_description="AIの自由文は使わない",
        topic_hashtags=["#休肝日", "#スパチャ", "#ReGLOSS"],
    )

    assert copy.description == (
        "元配信：\n"
        "【雑談】たのしい休肝日計画【儒烏風亭らでん #ReGLOSS】\n"
        "https://www.youtube.com/watch?v=z8eCi7kAEVI\n\n"
        "出演：\n"
        "儒烏風亭らでん（hololive DEV_IS / ReGLOSS）"
    )
    assert copy.hashtags == [
        "#儒烏風亭らでん",
        "#ReGLOSS",
        "#ホロライブ切り抜き",
        "#shortsfunny",
    ]
    assert copy.tags == ["儒烏風亭らでん", "らでん", "ReGLOSS", "休肝日", "スパチャ"]


def test_youtube_posting_copy_keeps_legacy_ai_copy_without_profile() -> None:
    copy = build_youtube_posting_copy(
        clip_type="normal",
        fallback_description="clip内容の要約",
        topic_hashtags=["#雑談", "#切り抜き"],
    )

    assert copy.description == "clip内容の要約"
    assert copy.hashtags == ["#雑談", "#切り抜き"]
    assert copy.tags == ["雑談", "切り抜き"]
