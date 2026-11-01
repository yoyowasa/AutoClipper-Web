"use client";

import { canEditManualFraming } from "../manualFraming";
import { segmentDraftKey } from "../sharedSegments";
import { useEffect, useRef } from "react";
import { contentDraftForClip, isClipContentDirty } from "../drafts";
import { remapDraftEvidence } from "../draftEvidence";
import { readReviewDraft, reviewDraftFingerprint, writeReviewDraft, rebaseUnchangedContent } from "../draftStorage";
import type { SubtitleReviewState } from "./useSubtitleReviewState";

export function usePersistedReviewDrafts(state: SubtitleReviewState) {
  const { jobId, review, drafts, dirtySegmentIds, clipContentDrafts, shortFramingDrafts,
    setDrafts, setDirtySegmentIds, setClipContentDrafts, setShortFramingDrafts, locallyUpdatedReviewRef } = state;
  const fingerprints = useRef<Record<string, string>>({});
  const previousContent = useRef<Record<string, ReturnType<typeof contentDraftForClip>>>({});
  const activeJob = useRef("");
  const restoring = useRef(false);
  useEffect(() => {
    if (!review || review.jobId !== jobId) return;
    if (activeJob.current !== jobId) { activeJob.current = jobId; fingerprints.current = {}; previousContent.current = {}; }
    const ownedUpdate = locallyUpdatedReviewRef.current === review;
    locallyUpdatedReviewRef.current = null;
    const restoredSegments: Record<string, string> = {};
    const resetIds = new Set<string>();
    for (const clip of review.clips) {
      const saved = contentDraftForClip(clip), oldContent = previousContent.current[clip.id];
      previousContent.current[clip.id] = saved;
      // A caption response can also remap title/description evidence IDs (COW).
      // Own responses need the same content rebase as background decisions;
      // only caption restoration below must be skipped for an owned response.
      if (review.subtitleOnlyAuto && clip.confirmed && oldContent && JSON.stringify(oldContent) !== JSON.stringify(saved)) {
        setClipContentDrafts(current => ({ ...current, [clip.id]: remapDraftEvidence(rebaseUnchangedContent(current[clip.id] ?? oldContent, oldContent, saved), review, clip) }));
      }
      const fingerprint = reviewDraftFingerprint(review, clip);
      const previous = fingerprints.current[clip.id];
      fingerprints.current[clip.id] = fingerprint;
      if (review.state !== "awaiting_review" && !(review.subtitleOnlyAuto && clip.confirmed)) { writeReviewDraft(jobId, clip.id, null); continue; }
      if (ownedUpdate || previous === fingerprint) continue;
      const stored = readReviewDraft(jobId, clip.id, fingerprint);
      restoring.current = true;
      setClipContentDrafts(current => ({ ...current, [clip.id]: remapDraftEvidence(stored ? stored.baseContent ? rebaseUnchangedContent(stored.content, stored.baseContent, saved) : stored.content : saved, review, clip) }));
      setShortFramingDrafts(current => {
        const next = { ...current };
        if (stored?.framing && canEditManualFraming(review, clip)) next[clip.id] = stored.framing; else delete next[clip.id];
        return next;
      });
      for (const id of clip.segmentIds) {
        const key = segmentDraftKey(clip, id);
        resetIds.add(key);
        restoredSegments[key] = stored?.segments[id] ?? review.segments.find(segment => segment.id === id)?.text ?? "";
      }

    }
    if (resetIds.size > 0) {
      setDrafts(current => ({ ...current, ...restoredSegments }));
      setDirtySegmentIds(current => {
        const next = new Set(current);
        for (const id of resetIds) {
          const saved = review.segments.find(segment => id === segment.id || id.endsWith(`::${segment.id}`));
          if (saved && restoredSegments[id] !== saved.text) next.add(id); else next.delete(id);
        }
        return next;
      });
    }
  }, [jobId, review, locallyUpdatedReviewRef, setClipContentDrafts, setShortFramingDrafts, setDrafts, setDirtySegmentIds]);

  useEffect(() => {
    if (!review || review.jobId !== jobId || review.state !== "awaiting_review" && !review.subtitleOnlyAuto) return;
    if (restoring.current) { restoring.current = false; return; }
    for (const clip of review.clips) {
      const segments = Object.fromEntries(clip.segmentIds.filter(id => dirtySegmentIds.has(segmentDraftKey(clip, id)))
        .map(id => [id, drafts[segmentDraftKey(clip, id)] ?? ""]));
      const content = clipContentDrafts[clip.id] ?? contentDraftForClip(clip);
      const framing = shortFramingDrafts[clip.id] ?? null;
      const dirty = isClipContentDirty(clip, clipContentDrafts) || Boolean(framing) || Object.keys(segments).length > 0;
      writeReviewDraft(jobId, clip.id, dirty ? {
        version: 1, fingerprint: reviewDraftFingerprint(review, clip), content, baseContent: contentDraftForClip(clip), framing, segments
      } : null);
    }
  }, [jobId, review, drafts, dirtySegmentIds, clipContentDrafts, shortFramingDrafts]);
}
