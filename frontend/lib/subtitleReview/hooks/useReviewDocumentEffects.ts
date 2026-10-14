"use client";

import { useEffect } from "react";
import { getJobStatus, getSubtitleReview } from "../../api";
import { livePreviewReference } from "../livePlaybackSource";
import { contentDraftForClip } from "../drafts";
import type { SubtitleReviewContext } from "./context";

export function useReviewDocumentLoad(context: Pick<SubtitleReviewContext,
    "jobId"
    | "reviewRequestGenerationRef"
    | "reviewMutationCountRef"
    | "setReview"
    | "setOpenedFromReupload"
    | "setSelectedClipId"
    | "setActiveClipType"
    | "setLastSelectedClipIds"
    | "setSelectedTextStyleTarget"
    | "setDrafts"
    | "setClipContentDrafts"
    | "setError">) {
  const {
    jobId,
    reviewRequestGenerationRef,
    reviewMutationCountRef,
    setReview,
    setOpenedFromReupload,
    setSelectedClipId,
    setActiveClipType,
    setLastSelectedClipIds,
    setSelectedTextStyleTarget,
    setDrafts,
    setClipContentDrafts,
    setError
  } = context;
  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;
    const requestGeneration = reviewRequestGenerationRef.current;
    const search = new URLSearchParams(window.location.search);
    void getSubtitleReview(jobId)
      .then((document) => {
        if (
          !active ||
          requestGeneration !== reviewRequestGenerationRef.current ||
          reviewMutationCountRef.current > 0
        ) {
          return;
        }
        setReview(document);
        setOpenedFromReupload(search.get("source") === "reupload");
        const requestedClipId = search.get("clipId");
        const requestedClip = document.clips.find(
          (clip) => clip.id === requestedClipId
        );
        const firstNormalClip = document.clips.find((clip) => clip.type === "normal");
        const firstShortClip = document.clips.find((clip) => clip.type === "short");
        const initialClip = requestedClip ?? firstNormalClip ?? firstShortClip;
        setSelectedClipId(initialClip?.id ?? "");
        setActiveClipType(initialClip?.type ?? "normal");
        setLastSelectedClipIds({
          normal:
            initialClip?.type === "normal"
              ? initialClip.id
              : (firstNormalClip?.id ?? ""),
          short:
            initialClip?.type === "short"
              ? initialClip.id
              : (firstShortClip?.id ?? "")
        });
        setSelectedTextStyleTarget("title");
        setDrafts(
          Object.fromEntries(document.segments.map((segment) => [segment.id, segment.text]))
        );
        setClipContentDrafts(
          Object.fromEntries(
            document.clips.map((clip) => [clip.id, contentDraftForClip(clip)])
          )
        );
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "字幕確認データを取得できませんでした");
        }
      });
    return () => {
      active = false;
    };
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);
}

export function useReviewSuggestionReset(context: Pick<SubtitleReviewContext, "autoSuggestionAttemptedClipIdsRef" | "setAutoGeneratingSuggestionClipIds" | "jobId">) {
  const { autoSuggestionAttemptedClipIdsRef, setAutoGeneratingSuggestionClipIds, jobId } = context;
  useEffect(() => {
    autoSuggestionAttemptedClipIdsRef.current = new Set();
    setAutoGeneratingSuggestionClipIds(new Set());
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);
}

export function useRetainedLivePreviews(context: Pick<SubtitleReviewContext, "review" | "setRetainedLivePreviews">) {
  const { review, setRetainedLivePreviews } = context;
  useEffect(() => {
    if (!review) {
      return;
    }
    setRetainedLivePreviews((current) => {
      let next = current;
      for (const clip of review.clips) {
        if (!clip.livePreviewVideoUrl || !clip.livePreviewSpecHash) {
          continue;
        }
        const saved = current[clip.id];
        if (
          saved?.url === clip.livePreviewVideoUrl &&
          saved.version === clip.livePreviewSpecHash
        ) {
          continue;
        }
        if (next === current) {
          next = { ...current };
        }
        next[clip.id] = livePreviewReference(clip, review);
      }
      return next;
    });
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review]);
}

export function useHookSceneUpdatePoll(context: Pick<SubtitleReviewContext,
    "isUpdatingHookScene"
    | "jobId"
    | "reviewMutationCountRef"
    | "reviewRequestGenerationRef"
    | "setReview"
    | "setDrafts"
    | "setClipContentDrafts"
    | "setPreviewLoadFailedClipIds"
    | "selectedClipId"
    | "setClipTime"
    | "setIsPlayerReady"
    | "setIsBuffering"
    | "setIsUpdatingHookScene"
    | "setError">) {
  const {
    isUpdatingHookScene,
    jobId,
    reviewMutationCountRef,
    reviewRequestGenerationRef,
    setReview,
    setDrafts,
    setClipContentDrafts,
    setPreviewLoadFailedClipIds,
    selectedClipId,
    setClipTime,
    setIsPlayerReady,
    setIsBuffering,
    setIsUpdatingHookScene,
    setError
  } = context;
  useEffect(() => {
    if (!isUpdatingHookScene || !jobId) {
      return;
    }
    let active = true;
    const intervalId = window.setInterval(() => {
      void getJobStatus(jobId)
        .then(async (status) => {
          if (!active) {
            return;
          }
          if (status.status === "awaiting_subtitle_review") {
            if (reviewMutationCountRef.current > 0) {
              return;
            }
            window.clearInterval(intervalId);
            reviewRequestGenerationRef.current += 1;
            const requestGeneration = reviewRequestGenerationRef.current;
            const document = await getSubtitleReview(jobId);
            if (
              !active ||
              requestGeneration !== reviewRequestGenerationRef.current ||
              reviewMutationCountRef.current > 0
            ) {
              return;
            }
            setReview(document);
            setDrafts(
              Object.fromEntries(
                document.segments.map((segment) => [segment.id, segment.text])
              )
            );
            setClipContentDrafts(
              Object.fromEntries(
                document.clips.map((clip) => [
                  clip.id,
                  contentDraftForClip(clip)
                ])
              )
            );
            setPreviewLoadFailedClipIds((current) => {
              const next = new Set(current);
              next.delete(selectedClipId);
              return next;
            });
            setClipTime(0);
            setIsPlayerReady(false);
            setIsBuffering(true);
            setIsUpdatingHookScene(false);
            if (status.error) {
              setError(status.error.message);
            }
          } else if (status.status === "failed") {
            window.clearInterval(intervalId);
            setIsUpdatingHookScene(false);
            setError(
              status.error?.message ?? "冒頭フック映像の更新に失敗しました"
            );
          }
        })
        .catch((caught) => {
          if (!active) {
            return;
          }
          window.clearInterval(intervalId);
          setIsUpdatingHookScene(false);
          setError(
            caught instanceof Error
              ? caught.message
              : "冒頭フック映像の状態を取得できませんでした"
          );
        });
    }, 1500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isUpdatingHookScene, jobId, selectedClipId]);
}

export function usePendingPreviewPoll(context: Pick<SubtitleReviewContext, "jobId" | "hasPendingPreviews" | "isUpdatingHookScene" | "reviewMutationCountRef" | "reviewRequestGenerationRef" | "setReview">) {
  const { jobId, hasPendingPreviews, isUpdatingHookScene, reviewMutationCountRef, reviewRequestGenerationRef, setReview } = context;
  useEffect(() => {
    if (!jobId || !hasPendingPreviews || isUpdatingHookScene) {
      return;
    }
    let active = true;
    const refreshReview = () => {
      if (reviewMutationCountRef.current > 0) {
        return;
      }
      const requestGeneration = reviewRequestGenerationRef.current;
      void getSubtitleReview(jobId)
        .then((document) => {
          if (
            active &&
            requestGeneration === reviewRequestGenerationRef.current &&
            reviewMutationCountRef.current === 0
          ) {
            setReview(document);
          }
        })
        .catch(() => {
          // The existing review remains usable while a transient poll fails.
        });
    };
    const intervalId = window.setInterval(refreshReview, 1500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPendingPreviews, isUpdatingHookScene, jobId]);
}
