import { contentFieldEquals, contentDraftChangedFields, contentDraftForClip, type ClipContentDraft } from "./drafts";
import { remapDraftEvidence } from "./draftEvidence";
import { rebaseUnchangedContent, type StoredReviewDraft } from "./draftStorage";
import type { SubtitleReviewClip, SubtitleReviewDocument } from "../types";

export function editContentDraft(current: ClipContentDraft, saved: ClipContentDraft, update: Partial<ClipContentDraft>): ClipContentDraft {
  const next = { ...current, ...update };
  const edited = new Set(current._editedFields ?? Object.keys(saved).filter(key =>
    !contentFieldEquals(key, current[key as keyof ClipContentDraft], saved[key as keyof ClipContentDraft])));
  for (const key of Object.keys(update).filter(key => key !== "_editedFields")) {
    if (contentFieldEquals(key, next[key as keyof ClipContentDraft], saved[key as keyof ClipContentDraft])) edited.delete(key);
    else edited.add(key);
  }
  return { ...next, _editedFields: [...edited] };
}

export function synchronizeContentDraft(draft: ClipContentDraft, saved: ClipContentDraft): ClipContentDraft {
  const edited = (draft._editedFields ?? []).filter(key => key in saved &&
    !contentFieldEquals(key, draft[key as keyof ClipContentDraft], saved[key as keyof ClipContentDraft]));
  return { ...saved, ...Object.fromEntries(edited.map(key => [key, draft[key as keyof ClipContentDraft]])), _editedFields: edited };
}

export function restoreContentDraft(document: SubtitleReviewDocument, clip: SubtitleReviewClip,
  stored: StoredReviewDraft | null, archive: (draft: StoredReviewDraft) => boolean) {
  const saved = contentDraftForClip(clip);
  const content = remapDraftEvidence(stored ? stored.baseContent
    ? rebaseUnchangedContent(stored.content, stored.baseContent, saved) : stored.content : saved, document, clip);
  if (!document.subtitleOnlyAuto || !clip.confirmed) return { content, blocked: false };
  // Legacy snapshots did not record editing intent, and their base was rewritten
  // during polling. Keep the entire uncertain record before activating server data.
  if (stored && stored.content._editedFields === undefined && contentDraftChangedFields(clip, content).length) {
    if (!archive(stored)) return { content, blocked: true };
    return { content: { ...saved, _editedFields: [] }, blocked: false };
  }
  return { content: synchronizeContentDraft(content, saved), blocked: false };
}
