import json
from pathlib import Path
from types import SimpleNamespace

from app.posting_metadata import (
    NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX,
    YouTubePostingProfile,
    YouTubeTitleCandidate,
    build_post_metadata_revision_hash,
    build_youtube_posting_copy,
    ensure_publication_title_suffix,
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
        thumbnail_kicker="見どころ",
        thumbnail_line1="長すぎる名前が",
        thumbnail_line2="まさかの結末へ",
        thumbnail_frame_seconds=4.25,
    )
    thumbnail = tmp_path / "thumbnails" / "shorts" / "short_01.jpg"
    thumbnail.parent.mkdir(parents=True)
    thumbnail.write_bytes(b"thumbnail")

    json_path, markdown_path = write_youtube_posting_artifacts(
        [clip],
        tmp_path,
        thumbnail_metadata_by_clip_id={
            clip.id: {
                "thumbnail_status": "ready",
                "thumbnail_filename": thumbnail.name,
                "thumbnail_path": str(thumbnail),
            }
        },
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")

    assert payload["clips"][0]["selectedTitle"] == "手編集タイトル"
    assert payload["clips"][0]["titleCandidates"][0]["intent"] == "factual"
    assert payload["clips"][0]["titleCandidates"][0]["evidenceSegmentIds"] == ["seg_1"]
    assert payload["clips"][0]["descriptionEvidenceSegmentIds"] == ["seg_1"]
    assert payload["version"] == 2
    assert payload["clips"][0]["youtubeTags"] == ["儒烏風亭らでん", "ReGLOSS"]
    assert payload["clips"][0]["thumbnailKicker"] == "見どころ"
    assert payload["clips"][0]["thumbnailFrameSeconds"] == 4.25
    assert payload["clips"][0]["thumbnailStatus"] == "ready"
    assert payload["clips"][0]["thumbnailFilename"] == "short_01.jpg"
    assert payload["clips"][0]["thumbnailPath"] == "thumbnails/shorts/short_01.jpg"
    assert "説明欄本文" in markdown
    assert "#切り抜き #Shorts" in markdown
    assert "儒烏風亭らでん,ReGLOSS" in markdown


def test_posting_artifact_uses_failed_metadata_instead_of_stale_thumbnail(
    tmp_path: Path,
) -> None:
    clip = SimpleNamespace(
        id="short_failed",
        type="short",
        title="動画内タイトル",
        publication_title="公開タイトル",
        title_candidates=[],
        recommended_title_id=None,
        selected_title_id=None,
        youtube_description="説明欄本文",
        youtube_hashtags=[],
        youtube_tags=[],
        description_evidence_segment_ids=[],
        post_metadata_source="manual",
        post_metadata_revision_hash=None,
    )
    stale_thumbnail = tmp_path / "thumbnails" / "shorts" / "short_01.jpg"
    stale_thumbnail.parent.mkdir(parents=True)
    stale_thumbnail.write_bytes(b"stale-thumbnail")

    json_path, _markdown_path = write_youtube_posting_artifacts(
        [clip],
        tmp_path,
        thumbnail_metadata_by_clip_id={
            clip.id: {
                "thumbnail_status": "failed",
                "thumbnail_filename": stale_thumbnail.name,
                "thumbnail_path": None,
            }
        },
    )
    package = json.loads(json_path.read_text(encoding="utf-8"))["clips"][0]

    assert stale_thumbnail.is_file()
    assert package["thumbnailStatus"] == "failed"
    assert package["thumbnailPath"] is None


def test_normal_publication_title_suffix_is_fixed_once_within_youtube_limit() -> None:
    title = ensure_publication_title_suffix("通常タイトル", clip_type="normal")
    duplicate = ensure_publication_title_suffix(
        title + NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX,
        clip_type="normal",
    )
    long_title = ensure_publication_title_suffix("長" * 100, clip_type="normal")

    assert title == f"通常タイトル{NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX}"
    assert duplicate == title
    assert len(long_title) == 100
    assert long_title.endswith(NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX)
    assert ensure_publication_title_suffix("ショートタイトル", clip_type="short") == (
        "ショートタイトル"
    )


def test_normal_posting_artifact_suffixes_selected_title_and_candidates(
    tmp_path: Path,
) -> None:
    clip = SimpleNamespace(
        id="normal_1",
        type="normal",
        title="動画内タイトル",
        publication_title="公開タイトル",
        title_candidates=[
            YouTubeTitleCandidate(
                id="a",
                title="候補A",
                intent="factual",
                reason="根拠A",
            )
        ],
        recommended_title_id="a",
        selected_title_id="a",
        youtube_description="説明欄本文",
        youtube_hashtags=[],
        youtube_tags=[],
        description_evidence_segment_ids=[],
        post_metadata_source="manual",
        post_metadata_revision_hash=None,
    )

    json_path, _markdown_path = write_youtube_posting_artifacts([clip], tmp_path)
    package = json.loads(json_path.read_text(encoding="utf-8"))["clips"][0]

    assert package["selectedTitle"] == f"候補A{NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX}"
    assert package["titleCandidates"][0]["title"] == (
        f"候補A{NORMAL_CLIP_PUBLICATION_TITLE_SUFFIX}"
    )


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
        fallback_description=(
            "長すぎる名前を読み進めると、思わぬ名フレーズが誕生。\n\n"
            "00:00 長すぎて切れる名前\n"
            "01:28 痛風オールバック"
        ),
        topic_hashtags=["#休肝日", "#スパチャ", "#ReGLOSS"],
    )

    assert copy.description == (
        "長すぎる名前を読み進めると、思わぬ名フレーズが誕生。\n\n"
        "00:00 長すぎて切れる名前\n"
        "01:28 痛風オールバック\n\n"
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


def test_youtube_posting_copy_does_not_duplicate_existing_source_or_performer() -> None:
    kwargs = {
        "clip_type": "normal", "source_title": "元配信", "source_url": "https://www.youtube.com/watch?v=gUgiNlCT8GM",
        "profile": {"performerName": "儒烏風亭らでん"},
    }
    first = build_youtube_posting_copy(**kwargs, fallback_description="手入力の説明")
    second = build_youtube_posting_copy(**kwargs, fallback_description=first.description)
    assert second.description == first.description
    partial = build_youtube_posting_copy(**kwargs, fallback_description="手入力の説明\n\n出演：\n儒烏風亭らでん")
    assert partial.description.count("出演：") == 1
    assert partial.description.count("元配信：") == 1
