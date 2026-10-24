"use client";

import { segmentDraftKey } from "../sharedSegments";
import type { ExportType, SubtitleReviewClip } from "../../types";
import { isPreviewReady } from "../preview";
import type { SubtitleReviewContext } from "./context";

export function useReviewMutations(context: SubtitleReviewContext) {
  function beginReviewMutation(): number {
    const { reviewMutationCountRef, reviewRequestGenerationRef } = context;
    reviewMutationCountRef.current += 1;
    reviewRequestGenerationRef.current += 1;
    return reviewRequestGenerationRef.current;
  }

  function endReviewMutation() {
    const { reviewMutationCountRef } = context;
    reviewMutationCountRef.current = Math.max(
      0,
      reviewMutationCountRef.current - 1
    );
  }

  function isCurrentReviewMutation(generation: number): boolean {
    const { reviewRequestGenerationRef } = context;
    return generation === reviewRequestGenerationRef.current;
  }

  function selectClip(clip: SubtitleReviewClip) {
    const {
      setStyledSegmentId,
      setPausedSubtitleDraft,
      videoRef,
      suggestionPlaybackEndRef,
      setPreviewingSuggestionId,
      setClipTime,
      setIsPlaying,
      setIsBuffering,
      review,
      setIsPlayerReady,
      setVideoLoadSeconds,
      setSelectedClipId,
      setActiveClipType,
      setLastSelectedClipIds,
      setSelectedTextStyleTarget,
      setShowSavedPreview,
      setCopiedPostField,
      setError
    } = context;
    setStyledSegmentId(null);
    setPausedSubtitleDraft(null);
    videoRef.current?.pause();
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
    setClipTime(0);
    setIsPlaying(false);
    setIsBuffering(
      Boolean(clip.livePreviewVideoUrl) || isPreviewReady(clip, review?.state)
    );
    setIsPlayerReady(false);
    setVideoLoadSeconds(0);
    setSelectedClipId(clip.id);
    setActiveClipType(clip.type);
    setLastSelectedClipIds((current) => ({ ...current, [clip.type]: clip.id }));
    setSelectedTextStyleTarget("title");
    setShowSavedPreview(false);
    setCopiedPostField(null);
    setError(null);
  }

  function selectClipType(clipType: ExportType) {
    const { normalClips, shortClips, lastSelectedClipIds, selectClip } = context;
    const candidates = clipType === "normal" ? normalClips : shortClips;
    if (candidates.length === 0) {
      return;
    }
    const remembered = candidates.find(
      (clip) => clip.id === lastSelectedClipIds[clipType]
    );
    selectClip(remembered ?? candidates[0]);
  }

  function updateDraft(segmentId: string, text: string) {
    const { setShowSavedPreview, setDrafts, setDirtySegmentIds, review, selectedClip } = context;
    if (!selectedClip) return;
    const key = segmentDraftKey(selectedClip, segmentId);
    setShowSavedPreview(false);
    setDrafts((current) => ({ ...current, [key]: text }));
    setDirtySegmentIds((current) => {
      const next = new Set(current);
      if (review?.segments.find(segment => segment.id === segmentId)?.text === text) next.delete(key);
      else next.add(key);
      return next;
    });
  }
  return { beginReviewMutation, endReviewMutation, isCurrentReviewMutation, selectClip, selectClipType, updateDraft };
}
