import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


PostTitleIntent = Literal["factual", "engagement", "concise"]
PostMetadataSource = Literal["codex", "manual", "existing"]
YOUTUBE_POSTING_PACKAGES_FILENAME = "youtube_posting_packages.json"
YOUTUBE_POSTS_FILENAME = "youtube_posts.md"


class YouTubeTitleCandidate(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=100)
    intent: PostTitleIntent
    reason: str = Field(default="", max_length=300)
    evidence_segment_ids: list[str] = Field(
        default_factory=list,
        max_length=64,
        alias="evidenceSegmentIds",
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    @field_validator("evidence_segment_ids")
    @classmethod
    def validate_unique_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate evidence segment id")
        return value


def _segment_value(segment: Mapping[str, Any] | BaseModel, *names: str) -> Any:
    if isinstance(segment, BaseModel):
        for name in names:
            if hasattr(segment, name):
                return getattr(segment, name)
        return None
    for name in names:
        if name in segment:
            return segment[name]
    return None


def build_post_metadata_revision_hash(
    *,
    clip_id: str,
    clip_type: str,
    start: float,
    end: float,
    segments: Sequence[Mapping[str, Any] | BaseModel],
) -> str:
    """Hash only the clip boundary and reviewed subtitle evidence.

    Provider/model/prompt changes deliberately do not alter this revision. The value
    is used to reject posting copy generated from an older subtitle draft.
    """

    payload = {
        "clipId": clip_id,
        "clipType": clip_type,
        "start": round(float(start), 3),
        "end": round(float(end), 3),
        "segments": [
            {
                "segmentId": str(_segment_value(segment, "segment_id", "segmentId", "id") or ""),
                "start": round(float(_segment_value(segment, "start") or 0.0), 3),
                "end": round(float(_segment_value(segment, "end") or 0.0), 3),
                "text": str(_segment_value(segment, "text") or "").strip(),
            }
            for segment in segments
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def youtube_posting_packages_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / YOUTUBE_POSTING_PACKAGES_FILENAME


def youtube_posts_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / YOUTUBE_POSTS_FILENAME


def _write_text_atomic(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(path)
    return path


def write_youtube_posting_artifacts(clips: Sequence[Any], output_dir: str | Path) -> list[Path]:
    packages: list[dict[str, Any]] = []
    markdown_sections: list[str] = []
    for clip in clips:
        title_candidates = list(getattr(clip, "title_candidates", []) or [])
        publication_title = str(getattr(clip, "publication_title", "") or "").strip()
        youtube_description = str(getattr(clip, "youtube_description", "") or "").strip()
        hashtags = list(getattr(clip, "youtube_hashtags", []) or [])
        description_evidence_segment_ids = list(
            getattr(clip, "description_evidence_segment_ids", []) or []
        )
        if (
            not title_candidates
            and not publication_title
            and not youtube_description
            and not hashtags
        ):
            continue

        selected_title_id = getattr(clip, "selected_title_id", None)
        recommended_title_id = getattr(clip, "recommended_title_id", None)
        selected_candidate = next(
            (candidate for candidate in title_candidates if candidate.id == selected_title_id),
            None,
        )
        recommended_candidate = next(
            (candidate for candidate in title_candidates if candidate.id == recommended_title_id),
            None,
        )
        selected_title = str(
            selected_candidate.title
            if selected_candidate is not None
            else (
                publication_title
                or (recommended_candidate.title if recommended_candidate is not None else "")
                or getattr(clip, "title", "")
            )
        )
        package = {
            "clipId": str(getattr(clip, "id")),
            "clipType": str(getattr(clip, "type")),
            "selectedTitle": selected_title,
            "selectedTitleId": selected_title_id,
            "recommendedTitleId": recommended_title_id,
            "titleCandidates": [
                candidate.model_dump(by_alias=True, mode="json") for candidate in title_candidates
            ],
            "youtubeDescription": youtube_description,
            "youtubeHashtags": hashtags,
            "descriptionEvidenceSegmentIds": description_evidence_segment_ids,
            "postMetadataSource": getattr(clip, "post_metadata_source", None),
            "postMetadataRevisionHash": getattr(clip, "post_metadata_revision_hash", None),
        }
        packages.append(package)
        markdown_sections.append(
            "\n".join(
                [
                    f"## {package['clipType']} / {package['clipId']}",
                    "",
                    "### 選択タイトル",
                    selected_title,
                    "",
                    "### タイトル候補",
                    *[
                        f"- [{candidate.intent}] {candidate.title}"
                        for candidate in title_candidates
                    ],
                    "",
                    "### 説明欄",
                    youtube_description,
                    "",
                    "### ハッシュタグ",
                    " ".join(hashtags),
                ]
            ).rstrip()
        )

    json_path = youtube_posting_packages_path(output_dir)
    markdown_path = youtube_posts_path(output_dir)
    _write_text_atomic(
        json_path,
        json.dumps({"version": 1, "clips": packages}, ensure_ascii=False, indent=2) + "\n",
    )
    _write_text_atomic(
        markdown_path,
        ("# YouTube投稿用テキスト\n\n" + "\n\n---\n\n".join(markdown_sections) + "\n")
        if markdown_sections
        else "# YouTube投稿用テキスト\n\n生成済みの投稿用テキストはありません。\n",
    )
    return [json_path, markdown_path]
