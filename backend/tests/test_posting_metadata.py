import json
from pathlib import Path
from types import SimpleNamespace

from app.posting_metadata import (
    YouTubeTitleCandidate,
    build_post_metadata_revision_hash,
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
    assert "説明欄本文" in markdown
    assert "#切り抜き #Shorts" in markdown
