"use client";

import { useEffect, useRef, useState } from "react";
import { segmentDraftKey } from "../sharedSegments";
import { nextCaptionSave, type CaptionSaveFocus } from "../captionAutosave";
import type { SubtitleReviewContext } from "./context";

function focusedClip(target: EventTarget | null): string | null {
  return target instanceof Element ? target.closest<HTMLElement>("[data-caption-edit-clip]")?.dataset.captionEditClip ?? null : null;
}

export function useConfirmedSubtitleAutosave(context: SubtitleReviewContext) {
  const latest = useRef(context);
  const attempted = useRef("");
  const [focus, setFocus] = useState<CaptionSaveFocus>({ clipId: null, composing: false });
  useEffect(() => { latest.current = context; });
  const enabled = Boolean(context.review?.subtitleOnlyAuto);
  useEffect(() => {
    if (!enabled) return;
    const updateFocus = (event: FocusEvent) => {
      const clipId = focusedClip(event.type === "focusout" ? event.relatedTarget : event.target);
      if (clipId) attempted.current = "";
      setFocus(current => ({ ...current, clipId }));
    };
    const startComposition = (event: CompositionEvent) => {
      if (focusedClip(event.target)) setFocus(current => ({ ...current, composing: true }));
    };
    const endComposition = () => setFocus({ clipId: focusedClip(document.activeElement), composing: false });
    document.addEventListener("focusin", updateFocus);
    document.addEventListener("focusout", updateFocus);
    document.addEventListener("compositionstart", startComposition);
    document.addEventListener("compositionend", endComposition);
    return () => {
      document.removeEventListener("focusin", updateFocus);
      document.removeEventListener("focusout", updateFocus);
      document.removeEventListener("compositionstart", startComposition);
      document.removeEventListener("compositionend", endComposition);
    };
  }, [enabled]);
  const clip = context.review?.jobId === context.jobId
    ? nextCaptionSave(context.review, context.rawDirtySegmentIds, focus, context.pausedSubtitleDraft?.clipId) : null;
  const clipId = clip?.id;
  const signature = clip ? JSON.stringify([context.jobId, clip.id, clip.segmentIds.filter(id => context.rawDirtySegmentIds.has(segmentDraftKey(clip, id)))
    .map(id => [id, context.rawDrafts[segmentDraftKey(clip, id)]])]) : "";
  const blocked = context.hasReviewMutationInFlight;
  useEffect(() => {
    if (!clipId || blocked || !signature || attempted.current === signature || latest.current.reviewMutationCountRef.current > 0) return;
    attempted.current = signature;
    void latest.current.saveConfirmedSubtitles(clipId);
  }, [clipId, signature, blocked]);
}
