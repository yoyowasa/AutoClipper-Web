import type { SubtitleReviewSegment } from "./types";

export type SubtitleBatchUpdate = { segmentId: string; before: string; text: string };
export type SubtitleUndoUpdate = SubtitleBatchUpdate & Pick<SubtitleReviewSegment, "index" | "start" | "end">;
export type CorrectionSelection = { segmentId: string; source: string; replacement: string };

// Text-only copy-on-write can change IDs without changing the subtitle's slot.
export function subtitleUndoUpdates(segments: SubtitleReviewSegment[], undo: SubtitleUndoUpdate[]): SubtitleBatchUpdate[] {
  return undo.flatMap(item => {
    const candidates = segments.filter(segment => segment.id === item.segmentId ||
      segment.index === item.index && segment.start === item.start && segment.end === item.end);
    return candidates.length === 1 ? [{ segmentId: candidates[0].id, before: item.before, text: item.text }] : [];
  });
}

export function matchingSubtitleCorrections(
  segments: SubtitleReviewSegment[], drafts: Record<string, string>, source: string, replacement: string,
) {
  if (!source || source === replacement || !replacement.trim()) return [];
  return segments.flatMap((segment) => {
    const current = drafts[segment.id] ?? segment.text;
    const parts = current.split(source);
    if (parts.length === 1) return [];
    return [{ segmentId: segment.id, before: segment.text, current, text: parts.join(replacement),
      count: parts.length - 1, start: segment.start, clipIds: segment.affectedClipIds }];
  });
}
