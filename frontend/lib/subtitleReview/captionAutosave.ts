import { segmentDraftKey } from "./sharedSegments";
import type { SubtitleReviewDocument, SubtitleReviewSegment } from "../types";

export type CaptionSaveFocus = { clipId: string | null; composing: boolean };

export function nextCaptionSave(document: SubtitleReviewDocument | null, dirty: Set<string>, focus: CaptionSaveFocus, insertionClipId?: string) {
  if (!document?.subtitleOnlyAuto || focus.composing) return null;
  return document.clips.find(clip => clip.confirmed && clip.id !== focus.clipId && clip.id !== insertionClipId &&
    clip.segmentIds.some(id => dirty.has(segmentDraftKey(clip, id)))) ?? null;
}

// A text update preserves the clip's ordered segment slots, even when COW gives
// a shared segment a new ID. Keep typing received after this request began.
export function reconcileCaptionSave(before: SubtitleReviewDocument, after: SubtitleReviewDocument, clipId: string,
  sent: { segmentId: string; text: string }[], drafts: Record<string, string>, dirty: Set<string>) {
  const oldClip = before.clips.find(clip => clip.id === clipId), newClip = after.clips.find(clip => clip.id === clipId);
  if (!oldClip || !newClip || oldClip.segmentIds.length !== newClip.segmentIds.length) throw new Error("字幕の構成が更新されました。入力は保持しています。");
  const nextDrafts = { ...drafts }, nextDirty = new Set(dirty);
  for (const update of sent) {
    const slot = oldClip.segmentIds.indexOf(update.segmentId), id = newClip.segmentIds[slot];
    const saved = after.segments.find(segment => segment.id === id);
    if (!saved || saved.text !== update.text) throw new Error("字幕が別の操作で更新されました。入力は保持しています。");
    const oldKey = segmentDraftKey(oldClip, update.segmentId), newKey = segmentDraftKey(newClip, id);
    const current = drafts[oldKey];
    delete nextDrafts[oldKey]; nextDirty.delete(oldKey);
    if (current !== undefined && current !== update.text) {
      nextDrafts[newKey] = current;
      if (current !== saved.text) nextDirty.add(newKey);
    }
  }
  return { drafts: nextDrafts, dirty: nextDirty };
}

// Caption text saves must not remount the focused textarea when COW changes IDs.
export function captionRowKey(clipId: string, segment: Pick<SubtitleReviewSegment, "index" | "start" | "end">) {
  return JSON.stringify([clipId, segment.index, segment.start, segment.end]);
}
