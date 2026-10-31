"use client";

import { useEffect, useRef } from "react";
import { segmentDraftKey } from "../sharedSegments";
import type { SubtitleReviewContext } from "./context";

// Confirmed captions save without applying/unconfirming the clip. Insertion
// holds its own draft and submits overlapping edits atomically instead.
export function useConfirmedSubtitleAutosave(context: SubtitleReviewContext) {
  const latest = useRef(context);
  const attempted = useRef("");
  useEffect(() => { latest.current = context; });
  const clip = context.review?.subtitleOnlyAuto ? context.review.clips.find(item => item.confirmed &&
    item.id !== context.pausedSubtitleDraft?.clipId && item.segmentIds.some(id => context.rawDirtySegmentIds.has(segmentDraftKey(item, id)))) : null;
  const clipId = clip?.id;
  const signature = clip ? JSON.stringify([context.jobId, clip.id, clip.segmentIds.filter(id => context.rawDirtySegmentIds.has(segmentDraftKey(clip, id)))
    .map(id => [id, context.rawDrafts[segmentDraftKey(clip, id)]])]) : "";
  const blocked = context.hasReviewMutationInFlight;
  useEffect(() => {
    if (!clipId || blocked || !signature || attempted.current === signature) return;
    const timer = window.setTimeout(() => {
      attempted.current = signature;
      void latest.current.saveConfirmedSubtitles(clipId);
    }, 600);
    return () => window.clearTimeout(timer);
  }, [clipId, signature, blocked]);
}
