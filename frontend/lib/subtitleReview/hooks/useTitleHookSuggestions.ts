"use client";

import { requestTitleHookSuggestions } from "../../api";
import type { TitleHookSuggestion } from "../../types";
import { clamp } from "../display";
import { limitToTwoTextLines } from "../text";
import { canonicalSuggestionDraft, sha256Hex } from "../suggestions";
import { postMetadataSourceForProvider } from "../posting";
import type { SubtitleReviewContext } from "./context";

export function useTitleHookSuggestions(context: SubtitleReviewContext) {
  async function generateTitleHookSuggestions(forceRegenerate: boolean) {
    const {
      selectedClip,
      selectedSuggestionInputSnapshot,
      suggestionRequestGenerationRef,
      setRequestingSuggestionClipId,
      setTitleHookSuggestionRecords,
      selectedSuggestionSegments,
      jobId
    } = context;
    if (!selectedClip) {
      return;
    }
    const clipId = selectedClip.id;
    const inputSnapshot = selectedSuggestionInputSnapshot;
    const requestGeneration =
      (suggestionRequestGenerationRef.current[clipId] ?? 0) + 1;
    suggestionRequestGenerationRef.current[clipId] = requestGeneration;
    setRequestingSuggestionClipId(clipId);
    setTitleHookSuggestionRecords((current) => ({
      ...current,
      [clipId]: {
        draftHashVerified: false,
        inputSnapshot,
        requestGeneration,
        response: {
          clipId,
          state: "queued",
          inputHash: null,
          draftHash: null,
          model: null,
          provider: null,
          revisionHash: null,
          recommendedSuggestionId: null,
          youtubeDescription: "",
          hashtags: [],
          descriptionEvidenceSegmentIds: [],
          suggestions: [],
          error: null,
          generatedAt: null
        }
      }
    }));
    try {
      const currentDraftHash = await sha256Hex(
        canonicalSuggestionDraft(selectedSuggestionSegments)
      );
      if (suggestionRequestGenerationRef.current[clipId] !== requestGeneration) {
        return;
      }
      const response = await requestTitleHookSuggestions(jobId, clipId, {
        segments: selectedSuggestionSegments,
        forceRegenerate
      });
      if (suggestionRequestGenerationRef.current[clipId] !== requestGeneration) {
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
    } catch (caught) {
      if (suggestionRequestGenerationRef.current[clipId] !== requestGeneration) {
        return;
      }
      setTitleHookSuggestionRecords((current) => ({
        ...current,
        [clipId]: {
          draftHashVerified: false,
          inputSnapshot,
          requestGeneration,
          response: {
            clipId,
            state: "failed",
            inputHash: null,
            draftHash: null,
            model: null,
            provider: null,
            revisionHash: null,
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
      if (suggestionRequestGenerationRef.current[clipId] === requestGeneration) {
        setRequestingSuggestionClipId((current) =>
          current === clipId ? null : current
        );
      }
    }
  }

  function applyTitleHookSuggestion(suggestion: TitleHookSuggestion) {
    const {
      selectedClip,
      selectedSuggestionsAreStale,
      selectedSuggestionRecord,
      bodyDuration,
      updateClipContentDraft,
      selectedClipContentDraft,
      setSelectedTextStyleTarget
    } = context;
    if (!selectedClip || selectedSuggestionsAreStale) {
      return;
    }
    const suggestionResponse = selectedSuggestionRecord?.response;
    const titleCandidates =
      suggestionResponse?.suggestions.map((item) => ({
        id: item.id,
        title: item.publicationTitle,
        intent: item.intent,
        reason: item.reason,
        evidenceSegmentIds: item.evidenceSegmentIds
      })) ?? [];
    const suggestedHookStart = clamp(
      suggestion.hookSceneStart ?? 0,
      0,
      bodyDuration
    );
    const suggestedHookEnd = clamp(
      suggestion.hookSceneEnd ?? 0,
      suggestedHookStart,
      bodyDuration
    );
    const hasValidHookScene =
      Boolean(suggestion.hookText.trim()) &&
      suggestion.hookSceneStart !== null &&
      suggestion.hookSceneEnd !== null &&
      suggestedHookEnd > suggestedHookStart;
    updateClipContentDraft(selectedClip.id, {
      publicationTitle: suggestion.publicationTitle
        .trim()
        .split(/\s+/u)
        .filter(Boolean)
        .join(" ")
        .slice(0, 100),
      titleCandidates,
      recommendedTitleId: suggestionResponse?.recommendedSuggestionId ?? null,
      selectedTitleId: suggestion.id,
      youtubeDescription: suggestionResponse?.youtubeDescription ?? "",
      youtubeHashtagsText: (suggestionResponse?.hashtags ?? []).join(" "),
      youtubeTagsText: selectedClipContentDraft?.youtubeTagsText ?? "",
      descriptionEvidenceSegmentIds:
        suggestionResponse?.descriptionEvidenceSegmentIds ?? [],
      postMetadataSource: postMetadataSourceForProvider(suggestionResponse?.provider),
      postMetadataRevisionHash: suggestionResponse?.revisionHash ?? null,
      title: limitToTwoTextLines(suggestion.overlayTitle).slice(0, 80),
      hookText: limitToTwoTextLines(suggestion.hookText).slice(0, 120),
      hookDurationSeconds: clamp(suggestion.hookDurationSeconds, 1, 8),
      hookSceneStart: hasValidHookScene
        ? selectedClip.start + suggestedHookStart
        : null,
      hookSceneEnd: hasValidHookScene
        ? selectedClip.start + suggestedHookEnd
        : null,
      thumbnailKicker: context.review?.subtitleOnlyAuto ? selectedClipContentDraft?.thumbnailKicker ?? "" :
        selectedClip.type === "normal"
          ? (suggestion.thumbnailKicker ?? "").trim().slice(0, 40)
          : "",
      thumbnailLine1: context.review?.subtitleOnlyAuto ? selectedClipContentDraft?.thumbnailLine1 ?? "" :
        selectedClip.type === "normal"
          ? (suggestion.thumbnailLine1 ?? "").trim().slice(0, 60)
          : "",
      thumbnailLine2: context.review?.subtitleOnlyAuto ? selectedClipContentDraft?.thumbnailLine2 ?? "" :
        selectedClip.type === "normal"
          ? (suggestion.thumbnailLine2 ?? "").trim().slice(0, 60)
          : "",
      thumbnailFrameSeconds: context.review?.subtitleOnlyAuto ? selectedClipContentDraft?.thumbnailFrameSeconds ?? null :
        selectedClip.type === "normal" &&
        suggestion.thumbnailFrameSeconds !== null
          ? clamp(suggestion.thumbnailFrameSeconds, 0, bodyDuration)
          : null
    });
    setSelectedTextStyleTarget("title");
  }

  async function copyPostField(field: string, value: string) {
    const { setCopiedPostField, setError } = context;
    if (!value.trim()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopiedPostField(field);
      setError(null);
    } catch {
      setError("クリップボードへコピーできませんでした。");
    }
  }

  function clearSelectedHook() {
    const { selectedClip, updateClipContentDraft } = context;
    if (!selectedClip) {
      return;
    }
    updateClipContentDraft(selectedClip.id, {
      hookText: "",
      hookSceneStart: null,
      hookSceneEnd: null
    });
  }

  function previewTitleHookSuggestion(suggestion: TitleHookSuggestion) {
    const {
      videoRef,
      selectedClip,
      selectedPlayerReady,
      bodyDuration,
      hookSceneDuration,
      suggestionPlaybackEndRef,
      setClipTime,
      setPreviewingSuggestionId
    } = context;
    const video = videoRef.current;
    if (
      !video ||
      !selectedClip ||
      !selectedPlayerReady ||
      suggestion.hookSceneStart === null ||
      suggestion.hookSceneEnd === null ||
      suggestion.hookSceneEnd <= suggestion.hookSceneStart
    ) {
      return;
    }
    const relativePreviewStart = clamp(suggestion.hookSceneStart, 0, bodyDuration);
    const relativePreviewEnd = clamp(
      suggestion.hookSceneEnd,
      relativePreviewStart,
      bodyDuration
    );
    const previewStart = hookSceneDuration + relativePreviewStart;
    const previewEnd = hookSceneDuration + relativePreviewEnd;
    if (previewEnd <= previewStart) {
      return;
    }
    video.pause();
    video.currentTime = previewStart;
    suggestionPlaybackEndRef.current = previewEnd;
    setClipTime(previewStart);
    setPreviewingSuggestionId(suggestion.id);
    void video.play().catch(() => {
      suggestionPlaybackEndRef.current = null;
      setPreviewingSuggestionId(null);
    });
  }
  return { generateTitleHookSuggestions, applyTitleHookSuggestion, copyPostField, clearSelectedHook, previewTitleHookSuggestion };
}
