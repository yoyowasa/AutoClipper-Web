"use client";

import { useMemo } from "react";
import { clipSegmentDrafts, clipDirtySegmentIds } from "../sharedSegments";
import { subtitlePreviewEvents } from "../../subtitlePreview";
import { subtitleInsertionConflict } from "../../subtitlePauseInsert";
import type { SubtitleReviewSegment } from "../../types";
import { isPreviewReady, shortTitleOutputExpected } from "../preview";
import { normalizeReviewTitle } from "../text";
import { contentDraftForClip, isClipContentDirty } from "../drafts";
import { shortFramingEquals } from "../framing";
import { reviewNeedsPolling } from "../automaticStatus";
import { editingPreviewAvailable, livePlaybackSource } from "../livePlaybackSource";
import { usePersistedReviewDrafts } from "./usePersistedReviewDrafts";
import { useSubtitleReviewState } from "./useSubtitleReviewState";
import type { SubtitleReviewContext } from "./context";
import { useReviewMutations } from "./useReviewMutations";
import { useReviewPreviews } from "./useReviewPreviews";
import { useConfirmedSubtitleAutosave } from "./useConfirmedSubtitleAutosave";
import { useSubtitleEditing } from "./useSubtitleEditing";
import { useClipContentDraft } from "./useClipContentDraft";
import { useTitleHookSuggestions } from "./useTitleHookSuggestions";
import { useReviewConfirmation } from "./useReviewConfirmation";
import { useReviewDocumentLoad, useReviewSuggestionReset, useRetainedLivePreviews, useHookSceneUpdatePoll, usePendingPreviewPoll } from "./useReviewDocumentEffects";
import { useAutomaticTitleSuggestions, useSuggestionHydration, useSuggestionStatusPoll } from "./useTitleHookSuggestionEffects";
import { usePreviewResumeLayout, usePlayerLoadTimer, usePlaybackRateSync, useVolumeSync, useActiveSubtitleScroll, useClipSelectionScroll } from "./useReviewPreviewEffects";

export function useSubtitleReviewDocument() {
  const state = useSubtitleReviewState();
  const {
    jobId,
    videoRef,
    currentPlayerMediaRef,
    pendingPlayerResumeRef,
    subtitleListRef,
    segmentRowRefs,
    suggestionRequestGenerationRef,
    autoSuggestionAttemptedClipIdsRef,
    reviewRequestGenerationRef,
    reviewMutationCountRef,
    review,
    setReview,
    selectedClipId,
    setSelectedClipId,
    activeClipType,
    setActiveClipType,
    setLastSelectedClipIds,
    drafts: rawDrafts,
    setDrafts,
    clipContentDrafts,
    setClipContentDrafts,
    dirtySegmentIds: rawDirtySegmentIds,
    retryingPreviewClipId,
    isSavingShortBannerSettings,
    savingShortFramingClipId,
    shortFramingDrafts,
    isUpdatingHookScene,
    setIsUpdatingHookScene,
    confirmingClipId,
    isFinalizing,
    isReopeningBoundaries,
    isReturningToClipPlan,
    isPlaying,
    setIsBuffering,
    isPlayerReady,
    setIsPlayerReady,
    setVideoLoadSeconds,
    previewLoadFailedClipIds,
    setPreviewLoadFailedClipIds,
    clipTime,
    setClipTime,
    pausedSubtitleDraft,
    volume,
    isMuted,
    playbackRate,
    setError,
    setOpenedFromReupload,
    setSelectedTextStyleTarget,
    showSavedPreview,
    titleHookSuggestionRecords,
    setTitleHookSuggestionRecords,
    setAutoGeneratingSuggestionClipIds,
    isSavingBulkCorrection,
    isSavingStructure,
    retainedLivePreviews,
    setRetainedLivePreviews,
    suggestionHydrationRetryVersion,
    setSuggestionHydrationRetryVersion
  } = state;


  useReviewDocumentLoad({ jobId, reviewRequestGenerationRef, reviewMutationCountRef, setReview, setOpenedFromReupload, setSelectedClipId, setActiveClipType, setLastSelectedClipIds, setSelectedTextStyleTarget, setDrafts, setClipContentDrafts, setError });

  useReviewSuggestionReset({ autoSuggestionAttemptedClipIdsRef, setAutoGeneratingSuggestionClipIds, jobId });

  useRetainedLivePreviews({ review, setRetainedLivePreviews });

  useHookSceneUpdatePoll({ isUpdatingHookScene, jobId, reviewMutationCountRef, reviewRequestGenerationRef, setReview, setDrafts, setClipContentDrafts, setPreviewLoadFailedClipIds, selectedClipId, setClipTime, setIsPlayerReady, setIsBuffering, setIsUpdatingHookScene, setError });

  const selectedClip = useMemo(
    () => review?.clips.find((clip) => clip.id === selectedClipId) ?? null,
    [review, selectedClipId]
  );
  const drafts = useMemo(() => clipSegmentDrafts(selectedClip, review?.segments ?? [], rawDrafts), [selectedClip, review, rawDrafts]);
  const dirtySegmentIds = useMemo(() => clipDirtySegmentIds(selectedClip, rawDirtySegmentIds), [selectedClip, rawDirtySegmentIds]);
  const normalClips = useMemo(
    () => review?.clips.filter((clip) => clip.type === "normal") ?? [],
    [review]
  );
  const shortClips = useMemo(
    () => review?.clips.filter((clip) => clip.type === "short") ?? [],
    [review]
  );
  const visibleClips = activeClipType === "normal" ? normalClips : shortClips;
  const hasPendingPreviews = reviewNeedsPolling(review);

  usePendingPreviewPoll({ jobId, hasPendingPreviews, isUpdatingHookScene, reviewMutationCountRef, reviewRequestGenerationRef, setReview });

  const hasBlockingReviewMutation =
    isSavingBulkCorrection ||
    isSavingStructure ||
    retryingPreviewClipId !== null ||
    isUpdatingHookScene ||
    confirmingClipId !== null ||
    isSavingShortBannerSettings ||
    savingShortFramingClipId !== null ||
    isFinalizing ||
    isReopeningBoundaries || isReturningToClipPlan;
  const hasReviewMutationInFlight = hasBlockingReviewMutation || state.isSavingConfirmedSubtitles;
  const isEditable =
    review?.state === "awaiting_review" &&
    !hasReviewMutationInFlight && !(review.subtitleOnlyAuto && selectedClip?.confirmed);
  const isSubtitleEditable = Boolean(review && !hasReviewMutationInFlight && (review.state === "awaiting_review" ||
    (review.subtitleOnlyAuto && selectedClip?.confirmed && ["render_queued", "rendering", "completed"].includes(review.state))));
  const isSubtitleTextEditable = Boolean(review && !hasBlockingReviewMutation && (review.state === "awaiting_review" ||
    (review.subtitleOnlyAuto && selectedClip?.confirmed && ["render_queued", "rendering", "completed"].includes(review.state))));
  const segmentsById = useMemo(
    () => new Map(review?.segments.map((segment) => [segment.id, segment]) ?? []),
    [review]
  );
  const selectedSegments = useMemo(
    () =>
      selectedClip?.segmentIds
        .map((segmentId) => segmentsById.get(segmentId))
        .filter((segment): segment is SubtitleReviewSegment => Boolean(segment)) ?? [],
    [segmentsById, selectedClip]
  );
  const selectedSuggestionSegments = useMemo(
    () =>
      [...selectedSegments]
        .sort((left, right) => left.index - right.index)
        .map((segment) => ({
          segmentId: segment.id,
          text: drafts[segment.id] ?? segment.text
        })),
    [drafts, selectedSegments]
  );
  const selectedSuggestionInputSnapshot = useMemo(
    () => JSON.stringify(selectedSuggestionSegments),
    [selectedSuggestionSegments]
  );
  const selectedSuggestionRecord = selectedClip
    ? titleHookSuggestionRecords[selectedClip.id] ?? null
    : null;
  const selectedSuggestionClipId = selectedClip?.id ?? "";
  const selectedSuggestionState = selectedSuggestionRecord?.response.state ?? null;
  const selectedSuggestionInputHash =
    selectedSuggestionRecord?.response.inputHash ?? null;
  const selectedSuggestionRequestGeneration =
    selectedSuggestionRecord?.requestGeneration ?? 0;
  const selectedSuggestionsAreStale = Boolean(
    selectedSuggestionRecord &&
      selectedSuggestionRecord.response.suggestions.length > 0 &&
      (!selectedSuggestionRecord.draftHashVerified ||
        selectedSuggestionRecord.inputSnapshot !== selectedSuggestionInputSnapshot)
  );

  useAutomaticTitleSuggestions({ jobId, review, drafts: rawDrafts, autoSuggestionAttemptedClipIdsRef, setAutoGeneratingSuggestionClipIds, suggestionRequestGenerationRef, setTitleHookSuggestionRecords });

  useSuggestionHydration({ jobId, selectedSuggestionClipId, selectedSuggestionRecord, selectedSuggestionInputSnapshot, suggestionRequestGenerationRef, selectedSuggestionSegments, setSuggestionHydrationRetryVersion, setTitleHookSuggestionRecords, suggestionHydrationRetryVersion });

  useSuggestionStatusPoll({ jobId, selectedSuggestionClipId, selectedSuggestionInputHash, selectedSuggestionState, selectedSuggestionRequestGeneration, setTitleHookSuggestionRecords });
  const selectedClipContentDraft = selectedClip
    ? clipContentDrafts[selectedClip.id] ?? contentDraftForClip(selectedClip) : null;
  const bodyDuration = selectedClip
    ? Math.max(0, selectedClip.end - selectedClip.start)
    : 0;
  const hookSceneDuration = selectedClipContentDraft?.hookSceneStart != null && selectedClipContentDraft.hookSceneEnd != null
    ? Math.max(0, selectedClipContentDraft.hookSceneEnd - selectedClipContentDraft.hookSceneStart) : 0;
  const clipDuration = bodyDuration + hookSceneDuration;
  const selectedPreviewReady = isPreviewReady(selectedClip, review?.state);
  const allPreviewsReady = Boolean(
    review &&
      review.clips.length > 0 &&
      review.clips.every((clip) => isPreviewReady(clip, review.state))
  );
  const selectedVideoUrl = selectedPreviewReady
    ? selectedClip?.previewVideoUrl ?? null
    : null;
  const selectedPreviewVersion = selectedPreviewReady
    ? selectedClip?.previewSpecHash ?? ""
    : "";
  const retainedLivePreview = selectedClip
    ? retainedLivePreviews[selectedClip.id]
    : undefined;
  const editingMedia = selectedClip && review ? livePlaybackSource(selectedClip, review, retainedLivePreview) : null;
  const selectedLiveVideoUrl = editingMedia?.url ?? null;
  const selectedLivePreviewVersion = editingMedia?.version ?? "";
  const livePreviewReady = editingPreviewAvailable(review, selectedClip);
  const isShowingLivePreview = livePreviewReady && !showSavedPreview;
  const selectedPlayerVideoUrl = isShowingLivePreview
    ? selectedLiveVideoUrl ?? review?.sourceVideoUrl ?? null
    : selectedVideoUrl;
  const selectedPlayerPreviewVersion = isShowingLivePreview
    ? selectedLivePreviewVersion
    : selectedPreviewVersion;
  const selectedPlayerReady = Boolean(selectedPlayerVideoUrl);
  const playerMediaKey = selectedClip && selectedPlayerVideoUrl
    ? `${selectedClip.id}:${selectedPlayerVideoUrl}:${selectedPlayerPreviewVersion}`
    : "";
  usePreviewResumeLayout({ currentPlayerMediaRef, selectedClipId, playerMediaKey, pendingPlayerResumeRef, clipTime, isPlaying });
  const selectedPreviewLoadFailed = Boolean(
    selectedClip && previewLoadFailedClipIds.has(selectedClip.id)
  );
  const selectedClipHasDirtySegments = selectedSegments.some((segment) =>
    dirtySegmentIds.has(segment.id)
  );
  const selectedSavedShortFraming =
    selectedClip?.type === "short"
      ? {
          framingOffsetX: selectedClip.framingOffsetX,
          framingOffsetY: selectedClip.framingOffsetY,
          framingZoom: selectedClip.framingZoom,
          shortLayout: selectedClip.shortLayout ?? review?.shortLayout
        }
      : null;
  const selectedShortFramingDraft =
    selectedClip?.type === "short"
      ? shortFramingDrafts[selectedClip.id] ?? selectedSavedShortFraming
      : null;
  const selectedShortFramingDirty = Boolean(
    selectedClip?.type === "short" &&
      selectedShortFramingDraft &&
      selectedSavedShortFraming &&
      !shortFramingEquals(selectedShortFramingDraft, selectedSavedShortFraming)
  );
  const hasDirtyShortFraming = Boolean(
    review?.clips.some((clip) => {
      if (clip.type !== "short") {
        return false;
      }
      const draft = shortFramingDrafts[clip.id];
      return Boolean(
        draft &&
          !shortFramingEquals(draft, {
            framingOffsetX: clip.framingOffsetX,
            framingOffsetY: clip.framingOffsetY,
            framingZoom: clip.framingZoom,
            shortLayout: clip.shortLayout ?? review?.shortLayout
          })
      );
    })
  );
  const selectedShortPreviewRegenerating = Boolean(
    selectedClip?.type === "short" &&
      (savingShortFramingClipId === selectedClip.id ||
        selectedClip.previewState === "queued" ||
        selectedClip.previewState === "rendering")
  );
  const selectedClipHasDirtyContent = Boolean(
    selectedClip && isClipContentDirty(selectedClip, clipContentDrafts)
  );
  const hasDirtyClipContent = Boolean(
    review?.clips.some((clip) => isClipContentDirty(clip, clipContentDrafts))
  );
  const selectedHookDurationIsValid =
    Number.isFinite(selectedClipContentDraft?.hookDurationSeconds ?? Number.NaN) &&
    (selectedClipContentDraft?.hookDurationSeconds ?? 0) >= 1 &&
    (selectedClipContentDraft?.hookDurationSeconds ?? 0) <= 8;
  const hookSuppressionEnd = selectedClip
    ? Math.min(
        clipDuration,
        Math.max(
          hookSceneDuration,
          selectedClipContentDraft?.hookText.trim()
            ? selectedClipContentDraft.hookDurationSeconds
            : 0
        )
      )
    : 0;
  const isInHookSuppression = clipTime < hookSuppressionEnd;
  const absolutePlaybackTime = selectedClip
    ? hookSceneDuration > 0 &&
      selectedClipContentDraft?.hookSceneStart != null &&
      selectedClipContentDraft?.hookSceneEnd != null &&
      clipTime < hookSceneDuration
      ? Math.min(
          selectedClipContentDraft.hookSceneEnd,
          selectedClipContentDraft.hookSceneStart + clipTime
        )
      : selectedClip.start + Math.max(0, clipTime - hookSceneDuration)
    : 0;
  const activeSegment = useMemo(() => {
    if (!selectedClip || isInHookSuppression) {
      return null;
    }
    return selectedSegments.find(
      (segment) =>
        absolutePlaybackTime >= Math.max(segment.start, selectedClip.start) &&
        absolutePlaybackTime < Math.min(segment.end, selectedClip.end)
    );
  }, [absolutePlaybackTime, isInHookSuppression, selectedClip, selectedSegments]);
  const activeSegmentId = activeSegment?.id ?? null;
  const selectedClipTextStyles = {
    title: selectedClipContentDraft?.titleStyle ?? null,
    hook: selectedClipContentDraft?.hookStyle ?? null,
    subtitle: selectedClipContentDraft?.subtitleStyle ?? null
  };
  const selectedResolvedClipTextStyles = {
    title: selectedClip?.resolvedTitleStyle ?? null,
    hook: selectedClip?.resolvedHookStyle ?? null,
    subtitle: selectedClip?.resolvedSubtitleStyle ?? null
  };
  const selectedDefaultResolvedClipTextStyles = {
    title: selectedClip?.resolvedDefaultTitleStyle ?? null,
    hook: selectedClip?.resolvedDefaultHookStyle ?? null,
    subtitle: selectedClip?.resolvedDefaultSubtitleStyle ?? null
  };
  const selectedDraftTitleEdited = Boolean(
    selectedClip &&
      selectedClipContentDraft &&
      normalizeReviewTitle(selectedClipContentDraft.title) !==
        normalizeReviewTitle(selectedClip.originalTitle ?? selectedClip.title)
  );
  const selectedShortTitleOutputEnabled = Boolean(
    selectedClip?.type === "short" &&
      review &&
      shortTitleOutputExpected({
        renderMode: review.renderMode,
        storedMode: review.shortOverlayTitleMode,
        topBannerEnabled: review.shortTopBannerEnabled,
        titleManuallyReviewed: selectedDraftTitleEdited
      })
  );
  const subtitlePreviewEventList = useMemo(() => {
    if (!selectedClip) {
      return [];
    }
    const previewAddedSubtitle = pausedSubtitleDraft?.clipId === selectedClip.id &&
      pausedSubtitleDraft.text.trim() && pausedSubtitleDraft.end - pausedSubtitleDraft.start >= 0.1 &&
      !subtitleInsertionConflict(selectedSegments.map((segment) => ({
        ...segment, text: drafts[segment.id] ?? segment.text
      })), pausedSubtitleDraft.start, pausedSubtitleDraft.end)
      ? [{ start: pausedSubtitleDraft.start, end: pausedSubtitleDraft.end,
          text: pausedSubtitleDraft.text, preserveSegmentation: true }] : [];
    return subtitlePreviewEvents({
      segments: [...selectedSegments.map((segment) => ({
        start: segment.start,
        end: segment.end,
        text: drafts[segment.id] ?? segment.text,
        words: segment.words,
        preserveSegmentation: segment.preserveSegmentation,
        singleLine: segment.singleLine,
        style: selectedClipContentDraft?.subtitleStyles.find(
          (item) => item.start === segment.start && item.end === segment.end
        )?.style
      })), ...previewAddedSubtitle],
      candidateStart: selectedClip.start,
      candidateEnd: selectedClip.end,
      hookSceneDuration,
      suppressionEnd: hookSuppressionEnd,
      maxCharsPerLine:
        selectedClip.subtitleMaxCharsPerLine ??
        (selectedClip.type === "short" ? 16 : 28),
      maxLines: selectedClip.subtitleMaxLines ?? 2,
      minSubtitleDuration: selectedClip.subtitleMinDurationSeconds ?? 1.1,
      maxSubtitleDuration: selectedClip.subtitleMaxDurationSeconds ?? 4.2,
      minGapBetweenSubtitles: selectedClip.subtitleMinGapSeconds ?? 0.08
    });
  }, [
    drafts,
    hookSceneDuration,
    hookSuppressionEnd,
    selectedClip,
    selectedSegments,
    pausedSubtitleDraft,
    selectedClipContentDraft?.subtitleStyles
  ]);
  const activePreviewSubtitleEvent = useMemo(
    () =>
      subtitlePreviewEventList.find(
        (event) => clipTime >= event.start && clipTime < event.end
      ) ?? null,
    [clipTime, subtitlePreviewEventList]
  );
  const stylePreviewSubtitleText =
    activePreviewSubtitleEvent?.text ?? subtitlePreviewEventList[0]?.text ?? "";
  const liveHookText = selectedClipContentDraft?.hookText.trim() ?? "";
  const liveHookEnd = Math.min(
    clipDuration,
    selectedClipContentDraft?.hookDurationSeconds ?? 3
  );
  const liveTitleStart = selectedClip
    ? selectedClip.type === "normal"
      ? Math.max(hookSceneDuration, liveHookText ? liveHookEnd : 0)
      : liveHookText
        ? liveHookEnd
        : 0
    : 0;
  const showLiveHook = Boolean(
    isShowingLivePreview &&
      liveHookText &&
      clipTime < liveHookEnd
  );
  const showLiveTitle = Boolean(
    isShowingLivePreview &&
      selectedClip &&
      (selectedClip.type === "normal" || selectedShortTitleOutputEnabled) &&
      selectedClipContentDraft?.title.trim() &&
      clipTime >= liveTitleStart
  );
  const showLiveSubtitle = Boolean(
    isShowingLivePreview && activePreviewSubtitleEvent?.text
  );

  usePlayerLoadTimer({ isPlayerReady, selectedClip, selectedPlayerReady, setVideoLoadSeconds });

  usePlaybackRateSync({ videoRef, playbackRate });

  useVolumeSync({ videoRef, volume, isMuted });

  useActiveSubtitleScroll({ activeSegmentId, isPlaying, subtitleListRef, segmentRowRefs });

  useClipSelectionScroll({ subtitleListRef, selectedClipId });
  // Keep one render's values together, as in the original page's closures.
  // Function getters preserve cross-handler calls while the action hooks below
  // create their callbacks; they are only read when an event handler runs.
  usePersistedReviewDrafts(state);
  const context: SubtitleReviewContext = {
    ...state,
    rawDrafts, rawDirtySegmentIds, drafts, dirtySegmentIds,
    selectedClip,
    normalClips,
    shortClips,
    visibleClips,
    hasPendingPreviews,
    hasReviewMutationInFlight,
    isEditable, isSubtitleEditable, isSubtitleTextEditable,
    segmentsById,
    selectedSegments,
    selectedSuggestionSegments,
    selectedSuggestionInputSnapshot,
    selectedSuggestionRecord,
    selectedSuggestionClipId,
    selectedSuggestionState,
    selectedSuggestionInputHash,
    selectedSuggestionRequestGeneration,
    selectedSuggestionsAreStale,
    bodyDuration,
    hookSceneDuration,
    clipDuration,
    selectedPreviewReady,
    allPreviewsReady,
    selectedVideoUrl,
    selectedPreviewVersion,
    retainedLivePreview,
    selectedLiveVideoUrl,
    selectedLivePreviewVersion,
    livePreviewReady,
    isShowingLivePreview,
    selectedPlayerVideoUrl,
    selectedPlayerPreviewVersion,
    selectedPlayerReady,
    playerMediaKey,
    selectedPreviewLoadFailed,
    selectedClipHasDirtySegments,
    selectedClipContentDraft,
    selectedSavedShortFraming,
    selectedShortFramingDraft,
    selectedShortFramingDirty,
    hasDirtyShortFraming,
    selectedShortPreviewRegenerating,
    selectedClipHasDirtyContent,
    hasDirtyClipContent,
    selectedHookDurationIsValid,
    hookSuppressionEnd,
    isInHookSuppression,
    absolutePlaybackTime,
    activeSegment,
    activeSegmentId,
    selectedClipTextStyles,
    selectedResolvedClipTextStyles,
    selectedDefaultResolvedClipTextStyles,
    selectedDraftTitleEdited,
    selectedShortTitleOutputEnabled,
    subtitlePreviewEventList,
    activePreviewSubtitleEvent,
    stylePreviewSubtitleText,
    liveHookText,
    liveHookEnd,
    liveTitleStart,
    showLiveHook,
    showLiveTitle,
    showLiveSubtitle,
    get beginReviewMutation() { return beginReviewMutation; },
    get endReviewMutation() { return endReviewMutation; },
    get isCurrentReviewMutation() { return isCurrentReviewMutation; },
    get selectClip() { return selectClip; },
    get selectClipType() { return selectClipType; },
    get seekToClipTime() { return seekToClipTime; },
    get playFromClipStart() { return playFromClipStart; },
    get seekToSubtitle() { return seekToSubtitle; },
    get togglePlayback() { return togglePlayback; },
    get skipBy() { return skipBy; },
    get currentSourceTime() { return currentSourceTime; },
    get openPausedSubtitleDraft() { return openPausedSubtitleDraft; },
    get savePausedSubtitleDraft() { return savePausedSubtitleDraft; },
    get handleVideoTimeUpdate() { return handleVideoTimeUpdate; },
    get handleVideoSeeking() { return handleVideoSeeking; },
    get retryVideoLoad() { return retryVideoLoad; },
    get handleVideoError() { return handleVideoError; },
    get toggleMuted() { return toggleMuted; },
    get changeVolume() { return changeVolume; },
    get changePlaybackRate() { return changePlaybackRate; },
    get toggleFullscreen() { return toggleFullscreen; },
    get updateDraft() { return updateDraft; },
    get saveBulkCorrection() { return saveBulkCorrection; },
    get updateClipContentDraft() { return updateClipContentDraft; },
    get updateClipTextStyle() { return updateClipTextStyle; },
    get changeSelectedShortFraming() { return changeSelectedShortFraming; },
    get saveSelectedShortFraming() { return saveSelectedShortFraming; },
    get resetSelectedShortFraming() { return resetSelectedShortFraming; },
    get saveShortBannerSettings() { return saveShortBannerSettings; },
    get generateTitleHookSuggestions() { return generateTitleHookSuggestions; },
    get applyTitleHookSuggestion() { return applyTitleHookSuggestion; },
    get copyPostField() { return copyPostField; },
    get clearSelectedHook() { return clearSelectedHook; },
    get previewTitleHookSuggestion() { return previewTitleHookSuggestion; },
    get retrySelectedPreview() { return retrySelectedPreview; },
    get saveHookScene() { return saveHookScene; },
    get saveConfirmedSubtitles() { return saveConfirmedSubtitles; },
    get saveSubtitleStructure() { return saveSubtitleStructure; },
    get reopenConfirmedClip() { return reopenConfirmedClip; },
    get confirmSelectedClip() { return confirmSelectedClip; },
    get startRendering() { return startRendering; },
    get returnToBoundaryEditor() { return returnToBoundaryEditor; },
    get returnToClipPlan() { return returnToClipPlan; },
  };
  const { beginReviewMutation, endReviewMutation, isCurrentReviewMutation, selectClip, selectClipType, updateDraft } = useReviewMutations(context);
  const {
    seekToClipTime,
    playFromClipStart,
    seekToSubtitle,
    togglePlayback,
    skipBy,
    currentSourceTime,
    handleVideoTimeUpdate,
    handleVideoSeeking,
    retryVideoLoad,
    handleVideoError,
    toggleMuted,
    changeVolume,
    changePlaybackRate,
    toggleFullscreen,
    retrySelectedPreview
  } = useReviewPreviews(context);
  const { openPausedSubtitleDraft, savePausedSubtitleDraft, saveBulkCorrection, saveSubtitleStructure, saveConfirmedSubtitles } = useSubtitleEditing(context);
  const {
    updateClipContentDraft,
    updateClipTextStyle,
    changeSelectedShortFraming,
    saveSelectedShortFraming,
    resetSelectedShortFraming,
    saveShortBannerSettings,
    saveHookScene
  } = useClipContentDraft(context);
  const { generateTitleHookSuggestions, applyTitleHookSuggestion, copyPostField, clearSelectedHook, previewTitleHookSuggestion } = useTitleHookSuggestions(context);
  const { reopenConfirmedClip, confirmSelectedClip, startRendering, returnToBoundaryEditor, returnToClipPlan } = useReviewConfirmation(context);
  useConfirmedSubtitleAutosave(context);
  return context;
}
