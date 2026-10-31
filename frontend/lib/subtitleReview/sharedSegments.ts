import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../types";


// Confirmed clips may be edited explicitly, but never inherit another clip's draft.
export function segmentDraftKey(clip: Pick<SubtitleReviewClip, "id" | "confirmed">, segmentId: string): string {
  return clip.confirmed ? `${clip.id}::${segmentId}` : segmentId;
}

export function clipSegmentDrafts(clip: SubtitleReviewClip | null, segments: SubtitleReviewSegment[], drafts: Record<string, string>) {
  const result = { ...drafts };
  if (clip?.confirmed) for (const segment of segments) {
    if (clip.segmentIds.includes(segment.id)) result[segment.id] = drafts[segmentDraftKey(clip, segment.id)] ?? segment.text;
  }
  return result;
}

export function clipDirtySegmentIds(clip: SubtitleReviewClip | null, dirty: Set<string>): Set<string> {
  return new Set(clip?.segmentIds.filter(id => dirty.has(segmentDraftKey(clip, id))) ?? []);
}

export function subtitleEditTargets(document: SubtitleReviewDocument, segments: Pick<SubtitleReviewSegment, "affectedClipIds">[], clipId?: string) {
  const ids = new Set(segments.flatMap(segment => segment.affectedClipIds));
  if (document.subtitleOnlyAuto && document.clips.some(clip => clip.id === clipId && clip.confirmed)) {
    return document.clips.filter(clip => clip.id === clipId && ids.has(clip.id));
  }
  return document.clips.filter(clip => ids.has(clip.id) && (!clip.confirmed || clip.id === clipId));
}

export function subtitleTargetName(clip: SubtitleReviewClip): string {
  return `${clip.type === "short" ? "ショート" : "通常"}「${clip.title}」`;
}

export function sharedSubtitleNotice(document: SubtitleReviewDocument, segments: Pick<SubtitleReviewSegment, "affectedClipIds">[], clipId: string): string {
  const others = subtitleEditTargets(document, segments, clipId).filter(clip => clip.id !== clipId);
  return others.length ? `次の未確定clipにも反映します：${others.map(subtitleTargetName).join("、")}` : "";
}

export function bulkEditableSegments(document: SubtitleReviewDocument, clipId?: string): SubtitleReviewSegment[] {
  const selected = document.subtitleOnlyAuto ? document.clips.find(clip => clip.id === clipId && clip.confirmed) : null;
  const editable = new Set(selected ? [selected.id] : document.clips.filter(clip => !clip.confirmed).map(clip => clip.id));
  return document.segments.filter(segment => segment.affectedClipIds.some(id => editable.has(id)))
    .map(segment => ({ ...segment, affectedClipIds: segment.affectedClipIds.filter(id => editable.has(id)) }));
}
