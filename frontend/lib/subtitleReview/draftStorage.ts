import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewClipFramingUpdateRequest } from "../types";
import { contentDraftForClip, type ClipContentDraft } from "./drafts";

export type StoredReviewDraft = {
  version: 1;
  fingerprint: string;
  content: ClipContentDraft;
  framing: SubtitleReviewClipFramingUpdateRequest | null;
  segments: Record<string, string>;
};
type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export const reviewDraftKey = (jobId: string, clipId: string) => `subtitle-review-draft:v1:${jobId}:${clipId}`;

export function clearJobReviewDrafts(jobId: string, storage: Storage | null = null): void {
  try {
    const target = storage ?? window.localStorage;
    const prefix = reviewDraftKey(jobId, "");
    const keys = Array.from({ length: target.length }, (_, index) => target.key(index));
    for (const key of keys) if (key?.startsWith(prefix)) target.removeItem(key);
  } catch { /* Disabled storage must not block returning to clip review. */ }
}

// Preview completion and polling timestamps must never invalidate text in progress.
export function reviewDraftFingerprint(document: SubtitleReviewDocument, clip: SubtitleReviewClip): string {
  return JSON.stringify({
    revision: document.renderRevision, generation: document.previewGeneration, start: clip.start, end: clip.end, confirmed: clip.confirmed,
    content: contentDraftForClip(clip), framing: [clip.framingOffsetX, clip.framingOffsetY, clip.framingZoom, clip.shortLayout],
    segments: document.segments.filter(segment => clip.segmentIds.includes(segment.id))
      .map(segment => [segment.id, segment.start, segment.end, segment.text, segment.singleLine])
  });
}

export function readReviewDraft(jobId: string, clipId: string, fingerprint: string,
  storage: DraftStorage | null = null): StoredReviewDraft | null {
  try {
    const target = storage ?? window.localStorage;
    const key = reviewDraftKey(jobId, clipId), text = target.getItem(key);
    if (!text) return null;
    const draft = JSON.parse(text) as StoredReviewDraft;
    if (draft.version !== 1 || draft.fingerprint !== fingerprint || !draft.content
      || [draft.content.publicationTitle, draft.content.title, draft.content.hookText, draft.content.youtubeTagsText,
        draft.content.youtubeHashtagsText, draft.content.youtubeDescription].some(value => typeof value !== "string")
      || !Array.isArray(draft.content.subtitleStyles) || !Array.isArray(draft.content.titleCandidates)
      || !Number.isFinite(draft.content.hookDurationSeconds)
      || !draft.segments || Array.isArray(draft.segments)
      || Object.values(draft.segments).some(value => typeof value !== "string")) {
      target.removeItem(key);
      return null;
    }
    return draft;
  } catch { return null; }
}

export function writeReviewDraft(jobId: string, clipId: string, draft: StoredReviewDraft | null,
  storage: DraftStorage | null = null): void {
  try {
    const target = storage ?? window.localStorage;
    if (draft) target.setItem(reviewDraftKey(jobId, clipId), JSON.stringify(draft));
    else target.removeItem(reviewDraftKey(jobId, clipId));
  } catch { /* Storage may be disabled or full; editing and confirmation still work. */ }
}
