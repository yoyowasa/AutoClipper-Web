import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewClipFramingUpdateRequest } from "../types";
import { contentDraftForClip, type ClipContentDraft } from "./drafts";

export type StoredReviewDraft = {
  version: 1;
  fingerprint: string;
  content: ClipContentDraft;
  baseContent?: ClipContentDraft;
  framing: SubtitleReviewClipFramingUpdateRequest | null;
  segments: Record<string, string>;
};
type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export const reviewDraftKey = (jobId: string, clipId: string) => `subtitle-review-draft:v1:${jobId}:${clipId}`;
export const legacyReviewDraftKey = (jobId: string, clipId: string) => `subtitle-review-legacy:v1:${jobId}:${clipId}`;
const LEGACY_DRAFT_EVENT = "subtitle-review-legacy-updated";

export function subscribeArchivedDrafts(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  window.addEventListener(LEGACY_DRAFT_EVENT, callback);
  return () => { window.removeEventListener("storage", callback); window.removeEventListener(LEGACY_DRAFT_EVENT, callback); };
}

export function archivedDraftSnapshot(jobId: string, clipId: string): string | null {
  try { return window.localStorage.getItem(legacyReviewDraftKey(jobId, clipId)); } catch { return null; }
}

export function parseArchivedDrafts(snapshot: string | null): StoredReviewDraft[] {
  try {
    const value = JSON.parse(snapshot ?? "[]");
    return Array.isArray(value) ? value.filter(item => item?.version === 1 && item.content && Array.isArray(item.content.titleCandidates)) : [];
  } catch { return []; }
}

export function archivedReviewDrafts(jobId: string, clipId: string, storage: DraftStorage | null = null): StoredReviewDraft[] {
  try {
    return parseArchivedDrafts((storage ?? window.localStorage).getItem(legacyReviewDraftKey(jobId, clipId)));
  } catch { return []; }
}

export function archiveReviewDraft(jobId: string, clipId: string, draft: StoredReviewDraft, storage: DraftStorage | null = null): boolean {
  try {
    const target = storage ?? window.localStorage, key = legacyReviewDraftKey(jobId, clipId);
    const previous = target.getItem(key);
    const copies = previous === null ? [] : JSON.parse(previous);
    if (!Array.isArray(copies)) return false; // Never overwrite unknown data.
    if (!copies.some(copy => JSON.stringify([copy.content, copy.segments, copy.framing]) === JSON.stringify([draft.content, draft.segments, draft.framing]))) {
      target.setItem(key, JSON.stringify([...copies, draft]));
      if (!storage) window.dispatchEvent(new Event(LEGACY_DRAFT_EVENT));
    }
    return true;
  } catch { return false; } // Keep the active draft if its backup cannot be written.
}

export function clearJobReviewDrafts(jobId: string, storage: Storage | null = null): void {
  try {
    const target = storage ?? window.localStorage;
    const prefixes = [reviewDraftKey(jobId, ""), legacyReviewDraftKey(jobId, "")];
    const keys = Array.from({ length: target.length }, (_, index) => target.key(index));
    for (const key of keys) if (key && prefixes.some(prefix => key.startsWith(prefix))) target.removeItem(key);
  } catch { /* Disabled storage must not block returning to clip review. */ }
}

// Preview completion and polling timestamps must never invalidate text in progress.
export function reviewDraftFingerprint(document: SubtitleReviewDocument, clip: SubtitleReviewClip): string {
  if (document.subtitleOnlyAuto && clip.confirmed) return JSON.stringify({
    generation: document.previewGeneration, createdAt: document.createdAt, start: clip.start, end: clip.end,
    segments: document.segments.filter(segment => clip.segmentIds.includes(segment.id))
      .map(segment => [segment.id, segment.start, segment.end, segment.text, segment.singleLine])
  });
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
      || draft.content._editedFields !== undefined && (!Array.isArray(draft.content._editedFields) || draft.content._editedFields.some(key => typeof key !== "string"))
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

// A background decision can change title/style while a caption draft is open.
// Rebase only fields that still equal the previous saved value.
export function rebaseUnchangedContent(draft: ClipContentDraft, before: ClipContentDraft, after: ClipContentDraft): ClipContentDraft {
  const rebased = Object.fromEntries(Object.keys(after).map(key => [key,
    JSON.stringify(draft[key as keyof ClipContentDraft]) === JSON.stringify(before[key as keyof ClipContentDraft])
      ? after[key as keyof ClipContentDraft] : draft[key as keyof ClipContentDraft]
  ])) as ClipContentDraft;
  return draft._editedFields ? { ...rebased, _editedFields: draft._editedFields } : rebased;
}
