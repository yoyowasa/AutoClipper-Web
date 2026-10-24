"use client";

import { segmentDraftKey } from "../sharedSegments";
import { useEffect } from "react";
import { getTitleHookSuggestions, requestTitleHookSuggestions } from "../../api";
import type { SubtitleReviewSegment } from "../../types";
import { canonicalSuggestionDraft, sha256Hex } from "../suggestions";
import type { SubtitleReviewContext } from "./context";

export function useAutomaticTitleSuggestions(context: Pick<SubtitleReviewContext,
    "jobId"
    | "review"
    | "drafts"
    | "autoSuggestionAttemptedClipIdsRef"
    | "setAutoGeneratingSuggestionClipIds"
    | "suggestionRequestGenerationRef"
    | "setTitleHookSuggestionRecords">) {
  const {
    jobId,
    review,
    drafts,
    autoSuggestionAttemptedClipIdsRef,
    setAutoGeneratingSuggestionClipIds,
    suggestionRequestGenerationRef,
    setTitleHookSuggestionRecords
  } = context;
  useEffect(() => {
    if (
      !jobId ||
      !review ||
      review.jobId !== jobId ||
      review.state !== "awaiting_review" ||
      review.clips.length === 0 ||
      review.segments.some((segment) => !(segment.id in drafts))
    ) {
      return;
    }
    const pendingClips = review.clips.filter(
      (clip) => !autoSuggestionAttemptedClipIdsRef.current.has(clip.id)
    );
    if (pendingClips.length === 0) {
      return;
    }
    for (const clip of pendingClips) {
      autoSuggestionAttemptedClipIdsRef.current.add(clip.id);
    }
    const queue = [...pendingClips];
    const runNext = async () => {
      while (true) {
        const clip = queue.shift();
        if (!clip) {
          return;
        }
        const segments = clip.segmentIds
          .map((segmentId) => review.segments.find((segment) => segment.id === segmentId))
          .filter((segment): segment is SubtitleReviewSegment => Boolean(segment))
          .sort((left, right) => left.index - right.index)
          .map((segment) => ({
            segmentId: segment.id,
            text: drafts[segmentDraftKey(clip, segment.id)] ?? segment.text
          }));
        const inputSnapshot = JSON.stringify(segments);
        setAutoGeneratingSuggestionClipIds((current) =>
          new Set(current).add(clip.id)
        );
        try {
          const existing = await getTitleHookSuggestions(jobId, clip.id);
          const response =
            existing ??
            (await requestTitleHookSuggestions(jobId, clip.id, {
              segments,
              forceRegenerate: false
            }));
          const currentDraftHash = await sha256Hex(canonicalSuggestionDraft(segments));
          const requestGeneration =
            (suggestionRequestGenerationRef.current[clip.id] ?? 0) + 1;
          suggestionRequestGenerationRef.current[clip.id] = requestGeneration;
          setTitleHookSuggestionRecords((current) => ({
            ...current,
            [clip.id]: {
              response,
              draftHashVerified:
                Boolean(response.draftHash) && response.draftHash === currentDraftHash,
              inputSnapshot,
              requestGeneration
            }
          }));
        } catch (caught) {
          const requestGeneration =
            (suggestionRequestGenerationRef.current[clip.id] ?? 0) + 1;
          suggestionRequestGenerationRef.current[clip.id] = requestGeneration;
          setTitleHookSuggestionRecords((current) => ({
            ...current,
            [clip.id]: {
              draftHashVerified: false,
              inputSnapshot,
              requestGeneration,
              response: {
                clipId: clip.id,
                state: "failed",
                inputHash: null,
                draftHash: null,
                revisionHash: null,
                model: null,
                provider: null,
                recommendedSuggestionId: null,
                youtubeDescription: "",
                hashtags: [],
                descriptionEvidenceSegmentIds: [],
                suggestions: [],
                error:
                  caught instanceof Error
                    ? caught.message
                    : "投稿案を生成できませんでした",
                generatedAt: null
              }
            }
          }));
        } finally {
          setAutoGeneratingSuggestionClipIds((current) => {
            const next = new Set(current);
            next.delete(clip.id);
            return next;
          });
        }
      }
    };
    const workers = Array.from(
      { length: Math.min(2, pendingClips.length) },
      () => runNext()
    );
    void Promise.all(workers);
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drafts, jobId, review]);
}

export function useSuggestionHydration(context: Pick<SubtitleReviewContext,
    "jobId"
    | "selectedSuggestionClipId"
    | "selectedSuggestionRecord"
    | "selectedSuggestionInputSnapshot"
    | "suggestionRequestGenerationRef"
    | "selectedSuggestionSegments"
    | "setSuggestionHydrationRetryVersion"
    | "setTitleHookSuggestionRecords"
    | "suggestionHydrationRetryVersion">) {
  const {
    jobId,
    selectedSuggestionClipId,
    selectedSuggestionRecord,
    selectedSuggestionInputSnapshot,
    suggestionRequestGenerationRef,
    selectedSuggestionSegments,
    setSuggestionHydrationRetryVersion,
    setTitleHookSuggestionRecords,
    suggestionHydrationRetryVersion
  } = context;
  useEffect(() => {
    if (
      !jobId ||
      !selectedSuggestionClipId ||
      selectedSuggestionRecord
    ) {
      return;
    }
    let active = true;
    let retryTimeoutId: number | null = null;
    const clipId = selectedSuggestionClipId;
    const inputSnapshot = selectedSuggestionInputSnapshot;
    const requestGeneration =
      (suggestionRequestGenerationRef.current[clipId] ?? 0) + 1;
    suggestionRequestGenerationRef.current[clipId] = requestGeneration;
    void Promise.all([
      getTitleHookSuggestions(jobId, clipId),
      sha256Hex(canonicalSuggestionDraft(selectedSuggestionSegments))
    ])
      .then(([response, currentDraftHash]) => {
        if (
          !active ||
          suggestionRequestGenerationRef.current[clipId] !== requestGeneration
        ) {
          return;
        }
        if (!response) {
          retryTimeoutId = window.setTimeout(
            () => setSuggestionHydrationRetryVersion((current) => current + 1),
            15000
          );
          return;
        }
        setTitleHookSuggestionRecords((current) => ({
          ...current,
          [clipId]: {
            response,
            draftHashVerified:
              Boolean(response.draftHash) && response.draftHash === currentDraftHash,
            inputSnapshot,
            requestGeneration
          }
        }));
      })
      .catch(() => {
        if (active) {
          retryTimeoutId = window.setTimeout(
            () => setSuggestionHydrationRetryVersion((current) => current + 1),
            3000
          );
        }
      });
    return () => {
      active = false;
      if (retryTimeoutId !== null) {
        window.clearTimeout(retryTimeoutId);
      }
    };
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    jobId,
    selectedSuggestionClipId,
    selectedSuggestionInputSnapshot,
    selectedSuggestionRecord,
    selectedSuggestionSegments,
    suggestionHydrationRetryVersion
  ]);
}

export function useSuggestionStatusPoll(context: Pick<SubtitleReviewContext,
    "jobId"
    | "selectedSuggestionClipId"
    | "selectedSuggestionInputHash"
    | "selectedSuggestionState"
    | "selectedSuggestionRequestGeneration"
    | "setTitleHookSuggestionRecords">) {
  const {
    jobId,
    selectedSuggestionClipId,
    selectedSuggestionInputHash,
    selectedSuggestionState,
    selectedSuggestionRequestGeneration,
    setTitleHookSuggestionRecords
  } = context;
  useEffect(() => {
    if (
      !jobId ||
      !selectedSuggestionClipId ||
      !selectedSuggestionInputHash ||
      (selectedSuggestionState !== "queued" &&
        selectedSuggestionState !== "generating")
    ) {
      return;
    }
    let active = true;
    let pollInFlight = false;
    const clipId = selectedSuggestionClipId;
    const expectedInputHash = selectedSuggestionInputHash;
    const requestGeneration = selectedSuggestionRequestGeneration;
    const pollSuggestions = () => {
      if (pollInFlight) {
        return;
      }
      pollInFlight = true;
      void getTitleHookSuggestions(jobId, clipId)
        .then((response) => {
          if (!active || !response) {
            return;
          }
          setTitleHookSuggestionRecords((current) => {
            const currentRecord = current[clipId];
            if (!currentRecord || currentRecord.requestGeneration !== requestGeneration) {
              return current;
            }
            if (response.inputHash !== expectedInputHash) {
              return {
                ...current,
                [clipId]: {
                  ...currentRecord,
                  response: {
                    ...currentRecord.response,
                    state: "failed",
                    suggestions: [],
                    error:
                      "別の字幕内容から再生成されました。現在の字幕からもう一度生成してください。"
                  }
                }
              };
            }
            return {
              ...current,
              [clipId]: {
                ...currentRecord,
                response
              }
            };
          });
        })
        .catch(() => {
          // Keep polling after a transient network error. The worker state remains authoritative.
        })
        .finally(() => {
          pollInFlight = false;
        });
    };
    pollSuggestions();
    const intervalId = window.setInterval(pollSuggestions, 1500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    jobId,
    selectedSuggestionClipId,
    selectedSuggestionInputHash,
    selectedSuggestionRequestGeneration,
    selectedSuggestionState
  ]);
}
