"""Copy-on-write boundaries for shared review subtitles."""

from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from app.jobs.subtitle_review import SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment


def editable_clip_ids(document: "SubtitleReviewDocument", clip_id: str | None = None) -> set[str]:
    if clip_id is not None and not any(clip.id == clip_id for clip in document.clips):
        raise KeyError("対象動画が見つかりません。")
    return {clip.id for clip in document.clips if not clip.confirmed or clip.id == clip_id}


def remap_clip_segment_ids(clip: "SubtitleReviewClip", mapping: dict[str, str]) -> None:
    clip.segment_ids = [mapping.get(item, item) for item in clip.segment_ids]
    clip.description_evidence_segment_ids = [mapping.get(item, item) for item in clip.description_evidence_segment_ids]
    for candidate in clip.title_candidates:
        candidate.evidence_segment_ids = [mapping.get(item, item) for item in candidate.evidence_segment_ids]


def writable_segment(
    document: "SubtitleReviewDocument", segment: "SubtitleReviewSegment", editable: set[str],
) -> "SubtitleReviewSegment | None":
    targets = [item for item in segment.affected_clip_ids if item in editable]
    if not targets:
        return None
    if len(targets) == len(segment.affected_clip_ids):
        return segment
    segment.clip_scoped = True
    replacement = segment.model_copy(deep=True, update={"id": f"seg_{uuid4().hex}", "affected_clip_ids": targets})
    segment.affected_clip_ids = [item for item in segment.affected_clip_ids if item not in editable]
    document.segments.append(replacement)
    for clip in document.clips:
        if clip.id in targets:
            remap_clip_segment_ids(clip, {segment.id: replacement.id})
    return replacement


def editable_document(document: "SubtitleReviewDocument", editable: set[str]) -> "SubtitleReviewDocument":
    """Structure operations see only editable rows, including adjacency/overlap checks."""
    working = document.model_copy(deep=True)
    working.clips = [clip for clip in working.clips if clip.id in editable]
    working.segments = [segment for segment in working.segments if editable.intersection(segment.affected_clip_ids)]
    for segment in working.segments:
        segment.affected_clip_ids = [item for item in segment.affected_clip_ids if item in editable]
    return working


def commit_structure_edit(document: "SubtitleReviewDocument", working: "SubtitleReviewDocument", editable: set[str]) -> None:
    """Keep protected IDs/content intact; only changed editable versions get new IDs."""
    replacements = {segment.id: segment for segment in working.segments}
    mapping: dict[str, str] = {}
    result = []
    for original in document.segments:
        if not editable.intersection(original.affected_clip_ids):
            result.append(original)
            continue
        replacement = replacements.pop(original.id, None)
        if replacement is not None and original.model_dump(exclude={"affected_clip_ids"}) == replacement.model_dump(
            exclude={"affected_clip_ids"}
        ):
            result.append(original)
            continue
        protected = [item for item in original.affected_clip_ids if item not in editable]
        if protected:
            original.affected_clip_ids = protected
            original.clip_scoped = True
            result.append(original)
            if replacement is not None:
                mapping[original.id] = f"seg_{uuid4().hex}"
                replacement.id = mapping[original.id]
        if replacement is not None:
            result.append(replacement)
    for segment in replacements.values():
        if any(clip.id not in editable and clip.start < segment.end and clip.end > segment.start for clip in document.clips):
            segment.clip_scoped = True
        result.append(segment)
    scoped = {index for segment in result if segment.clip_scoped for index in (segment.source_indices or [segment.index])}
    for segment in result:
        if scoped.intersection(segment.source_indices or [segment.index]):
            segment.clip_scoped = True
    document.segments = sorted(result, key=lambda segment: (segment.start, segment.end))
    for clip in working.clips:
        remap_clip_segment_ids(clip, mapping)
    by_id = {clip.id: clip for clip in working.clips}
    document.clips = [by_id.get(clip.id, clip) for clip in document.clips]


def scoped_source_indices(document: "SubtitleReviewDocument") -> set[int]:
    return {
        index for segment in document.segments if segment.clip_scoped
        for index in (segment.source_indices or [segment.index])
    }
