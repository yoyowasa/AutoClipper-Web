"use client";

import { useEffect, useRef } from "react";
import { contentDraftForClip, isClipContentDirty } from "../drafts";
import { readReviewDraft, reviewDraftFingerprint, writeReviewDraft } from "../draftStorage";
import type { SubtitleReviewState } from "./useSubtitleReviewState";

export function usePersistedReviewDrafts(state: SubtitleReviewState) {
  const { jobId, review, drafts, dirtySegmentIds, clipContentDrafts, shortFramingDrafts,
    setDrafts, setDirtySegmentIds, setClipContentDrafts, setShortFramingDrafts, locallyUpdatedReviewRef } = state;
  const fingerprints = useRef<Record<string, string>>({});
  const activeJob = useRef("");
  const restoring = useRef(false);
  useEffect(() => {
    if (!review || review.jobId !== jobId) return;
    if (activeJob.current !== jobId) { activeJob.current = jobId; fingerprints.current = {}; }
    const ownedUpdate = locallyUpdatedReviewRef.current === review;
    locallyUpdatedReviewRef.current = null;
    const restoredSegments: Record<string, string> = {};
    const resetIds = new Set<string>();
    for (const clip of review.clips) {
      const fingerprint = reviewDraftFingerprint(review, clip);
      const previous = fingerprints.current[clip.id];
      fingerprints.current[clip.id] = fingerprint;
      if (review.state !== "awaiting_review") { writeReviewDraft(jobId, clip.id, null); continue; }
      if (ownedUpdate || previous === fingerprint) continue;
      const stored = readReviewDraft(jobId, clip.id, fingerprint);
      restoring.current = true;
      setClipContentDrafts(current => ({ ...current, [clip.id]: stored?.content ?? contentDraftForClip(clip) }));
      setShortFramingDrafts(current => {
        const next = { ...current };
        if (stored?.framing) next[clip.id] = stored.framing; else delete next[clip.id];
        return next;
      });
      Object.assign(restoredSegments, stored?.segments ?? {});
      for (const id of clip.segmentIds) resetIds.add(id);

    }
    if (resetIds.size > 0) {
      setDrafts(current => ({ ...current, ...Object.fromEntries(review.segments
        .filter(segment => resetIds.has(segment.id))
        .map(segment => [segment.id, restoredSegments[segment.id] ?? segment.text])) }));
      setDirtySegmentIds(current => {
        const next = new Set(current);
        for (const id of resetIds) { if (id in restoredSegments) next.add(id); else next.delete(id); }
        return next;
      });
    }
  }, [jobId, review, locallyUpdatedReviewRef, setClipContentDrafts, setShortFramingDrafts, setDrafts, setDirtySegmentIds]);

  useEffect(() => {
    if (!review || review.jobId !== jobId || review.state !== "awaiting_review") return;
    if (restoring.current) { restoring.current = false; return; }
    for (const clip of review.clips) {
      const segments = Object.fromEntries(clip.segmentIds.filter(id => dirtySegmentIds.has(id))
        .map(id => [id, drafts[id] ?? ""]));
      const content = clipContentDrafts[clip.id] ?? contentDraftForClip(clip);
      const framing = shortFramingDrafts[clip.id] ?? null;
      const dirty = isClipContentDirty(clip, clipContentDrafts) || Boolean(framing) || Object.keys(segments).length > 0;
      writeReviewDraft(jobId, clip.id, dirty ? {
        version: 1, fingerprint: reviewDraftFingerprint(review, clip), content, framing, segments
      } : null);
    }
  }, [jobId, review, drafts, dirtySegmentIds, clipContentDrafts, shortFramingDrafts]);
}
