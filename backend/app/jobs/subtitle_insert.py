"""Insert within existing captions without dropping saved or atomic draft text."""
from uuid import uuid4

from app.jobs.subtitle_review import SubtitleReviewSegment, _refresh_counts
from app.candidates.merge_boundaries import SubtitleStyleOverride

MIN_PART_SECONDS = 0.1


def insert_preserving_text(document, request, overlapping):
    clip = next(c for c in document.clips if c.id == request.clip_id)
    affected = {c.id for c in document.clips if c.start < request.end and c.end > request.start}
    nearest = min(overlapping, key=lambda s: (s.start, s.end))
    source_indices = sorted({i for s in overlapping for i in (s.source_indices or [s.index])})
    rows, contained, origins = [], [], {}
    for segment in overlapping:
        left = (segment.start, min(segment.end, request.start))
        right = (max(segment.start, request.end), segment.end)
        parts = [part for part in (left, right) if part[1] - part[0] >= MIN_PART_SECONDS - 0.000001]
        if segment.text.strip():
            if not parts:
                contained.append(segment)
                continue
            # Keep all prior text once, preferably before the new caption.
            parts = parts[:1]
        for start, end in parts:
            targets = [c.id for c in document.clips if c.id in segment.affected_clip_ids and c.start < end and c.end > start]
            if targets:
                replacement = segment.model_copy(deep=True, update={"id": f"seg_{uuid4().hex}", "start": start, "end": end,
                    "affected_clip_ids": targets, "words": None, "preserve_segmentation": True, "edited": True,
                    "source_indices": segment.source_indices or [segment.index]})
                rows.append(replacement)
                origins[replacement.id] = segment
    duration = request.end - request.start
    content = (request.text or "").strip()
    pieces = [(content, None), *[(s.text, s) for s in contained]]
    if duration < len(pieces) * MIN_PART_SECONDS - 0.000001:
        # A sub-0.2s slot cannot hold two nonoverlapping captions. Preserve both
        # literal texts in one cue rather than dropping text or creating overlap.
        pieces = [("\n".join(text for text, _ in pieces), None)]
    step = duration / len(pieces)
    for index, (text, source) in enumerate(pieces):
        if len(text) > 4000:
            raise ValueError("１区間の字幕は4000文字以内にしてください。")
        start, end = request.start + index * step, request.start + (index + 1) * step
        targets = [c.id for c in document.clips if c.id in affected and c.start < end and c.end > start]
        replacement = SubtitleReviewSegment(id=f"seg_{uuid4().hex}", index=source.index if source else nearest.index,
            start=start, end=end, text=text, originalText=source.original_text if source else "", edited=True,
            affectedClipIds=targets, sourceIndices=source_indices, preserveSegmentation=True)
        rows.append(replacement)
        origins[replacement.id] = source or nearest
    removed = {s.id for s in overlapping}
    document.segments = sorted([s for s in document.segments if s.id not in removed] + rows, key=lambda s: (s.start, s.end))
    for item in document.clips:
        if item.id not in affected:
            continue
        item.confirmed = False
        item.segment_ids = [s.id for s in document.segments if item.id in s.affected_clip_ids]
        old_styles = {(s.start, s.end): s.style for s in item.subtitle_styles}
        item.subtitle_styles = [s for s in item.subtitle_styles if (s.start, s.end) not in {(old.start, old.end) for old in overlapping}]
        for row in rows:
            origin = origins[row.id]
            style = old_styles.get((origin.start, origin.end))
            if style is not None and item.id in row.affected_clip_ids:
                item.subtitle_styles.append(SubtitleStyleOverride(start=row.start, end=row.end, style=style))
    _refresh_counts(document)
    return affected | {clip.id}
