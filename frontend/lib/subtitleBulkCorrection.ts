import type { SubtitleReviewSegment } from "./types";

export type SubtitleBatchUpdate = { segmentId: string; before: string; text: string };
export type CorrectionSelection = { segmentId: string; source: string; replacement: string };

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
