"use client";

import { updateSubtitleReviewClipFraming, updateSubtitleReviewHookScene, updateSubtitleReviewShortBannerSettings } from "../../api";
import { type ClipTextTarget } from "../../clipTextStyle";
import type { ClipTextStyle, SubtitleReviewClipFramingUpdateRequest, SubtitleReviewDocument } from "../../types";
import { clamp } from "../display";
import { type ClipContentDraft, contentDraftForClip } from "../drafts";
import { shortFramingSignature, shortFramingEquals } from "../framing";
import type { SubtitleReviewContext } from "./context";

export function useClipContentDraft(context: SubtitleReviewContext) {
  function updateClipContentDraft(
    clipId: string,
    update: Partial<ClipContentDraft>
  ) {
    const { setShowSavedPreview, setClipContentDrafts, review } = context;
    setShowSavedPreview(false);
    setClipContentDrafts((current) => {
      const clip = review?.clips.find((item) => item.id === clipId);
      if (!clip) {
        return current;
      }
      return {
        ...current,
        [clipId]: {
          ...(current[clipId] ?? contentDraftForClip(clip)),
          ...update
        }
      };
    });
  }

  function updateClipTextStyle(
    target: ClipTextTarget,
    style: ClipTextStyle | null
  ) {
    const { selectedClip, updateClipContentDraft, selectedSegments, styledSegmentId, selectedClipContentDraft } = context;
    if (!selectedClip) {
      return;
    }
    if (target === "title") {
      updateClipContentDraft(selectedClip.id, { titleStyle: style });
      return;
    }
    if (target === "hook") {
      updateClipContentDraft(selectedClip.id, { hookStyle: style });
      return;
    }
    const segment = selectedSegments.find((item) => item.id === styledSegmentId);
    if (segment && selectedClipContentDraft) {
      const remaining = selectedClipContentDraft.subtitleStyles.filter(
        (item) => item.start !== segment.start || item.end !== segment.end
      );
      updateClipContentDraft(selectedClip.id, {
        subtitleStyles: style ? [...remaining, { start: segment.start, end: segment.end, style }] : remaining
      });
    } else {
      updateClipContentDraft(selectedClip.id, { subtitleStyle: style });
    }
  }

  function changeSelectedShortFraming(
    update: Partial<SubtitleReviewClipFramingUpdateRequest>
  ): SubtitleReviewClipFramingUpdateRequest | null {
    const { selectedClip, selectedShortFramingDraft, setShortFramingDrafts } = context;
    if (!selectedClip || selectedClip.type !== "short") {
      return null;
    }
    const current =
      selectedShortFramingDraft ?? {
        framingOffsetX: selectedClip.framingOffsetX,
        framingOffsetY: selectedClip.framingOffsetY,
        framingZoom: selectedClip.framingZoom
      };
    const next = {
      ...current,
      ...update
    };
    setShortFramingDrafts((drafts) => ({
      ...drafts,
      [selectedClip.id]: next
    }));
    return next;
  }

  async function saveSelectedShortFraming(
    clipId: string,
    framing: SubtitleReviewClipFramingUpdateRequest
  ) {
    const {
      review,
      isEditable,
      shortFramingSaveInFlightRef,
      setShortFramingDrafts,
      lastSavedShortFramingSignatureRef,
      beginReviewMutation,
      setSavingShortFramingClipId,
      setShowSavedPreview,
      setError,
      jobId,
      isCurrentReviewMutation,
      setReview,
      endReviewMutation
    } = context;
    const clip = review?.clips.find((item) => item.id === clipId);
    if (
      !clip ||
      clip.type !== "short" ||
      !isEditable ||
      shortFramingSaveInFlightRef.current.has(clipId)
    ) {
      return false;
    }
    const nextFraming = {
      framingOffsetX: clamp(framing.framingOffsetX, -100, 100),
      framingOffsetY: clamp(framing.framingOffsetY, -100, 100),
      framingZoom: clamp(framing.framingZoom, 1, 3)
    };
    const savedFraming = {
      framingOffsetX: clip.framingOffsetX,
      framingOffsetY: clip.framingOffsetY,
      framingZoom: clip.framingZoom
    };
    const signature = shortFramingSignature(nextFraming);
    const layoutChanged = framing.shortLayout !== undefined && framing.shortLayout !== (clip.shortLayout ?? review?.shortLayout);
    if (!layoutChanged && shortFramingEquals(nextFraming, savedFraming)) {
      setShortFramingDrafts((drafts) => {
        const next = { ...drafts };
        delete next[clipId];
        return next;
      });
      return true;
    }
    if (!layoutChanged && lastSavedShortFramingSignatureRef.current[clipId] === signature) {
      setShortFramingDrafts((drafts) => {
        const next = { ...drafts };
        delete next[clipId];
        return next;
      });
      return true;
    }

    shortFramingSaveInFlightRef.current.add(clipId);
    const mutationGeneration = beginReviewMutation();
    setSavingShortFramingClipId(clipId);
    setShowSavedPreview(false);
    setError(null);
    try {
      const updated = await updateSubtitleReviewClipFraming(
        jobId,
        clipId,
        { ...nextFraming, shortLayout: framing.shortLayout }
      );
      lastSavedShortFramingSignatureRef.current[clipId] = signature;
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(updated);
      }
      setShortFramingDrafts((drafts) => {
        if (
          !drafts[clipId] ||
          shortFramingSignature(drafts[clipId]) !== signature
        ) {
          return drafts;
        }
        const next = { ...drafts };
        delete next[clipId];
        return next;
      });
      return true;
    } catch (caught) {
      delete lastSavedShortFramingSignatureRef.current[clipId];
      setError(
        caught instanceof Error
          ? caught.message
          : "ショート画角を保存できませんでした"
      );
      return false;
    } finally {
      endReviewMutation();
      shortFramingSaveInFlightRef.current.delete(clipId);
      setSavingShortFramingClipId((current) =>
        current === clipId ? null : current
      );
    }
  }

  async function saveShortBannerSettings(
    shortLayout: SubtitleReviewDocument["shortLayout"],
    shortTopBannerEnabled: boolean,
    shortBottomBannerEnabled: boolean,
    assets: { shortTopBannerAssetId?: string; shortBottomBannerAssetId?: string; characterPresetName?: string } = {}
  ) {
    const {
      review,
      isEditable,
      hasReviewMutationInFlight,
      beginReviewMutation,
      setReview,
      setIsSavingShortBannerSettings,
      setError,
      jobId,
      isCurrentReviewMutation,
      setClipContentDrafts,
      endReviewMutation
    } = context;
    if (!review || !isEditable || hasReviewMutationInFlight) {
      return false;
    }
    const previousSettings = {
      shortOverlayTitleMode: review.shortOverlayTitleMode,
      shortLayout: review.shortLayout,
      shortTopBannerEnabled: review.shortTopBannerEnabled,
      shortBottomBannerEnabled: review.shortBottomBannerEnabled,
      clips: review.clips
    };
    const topBannerChanged =
      shortTopBannerEnabled !== review.shortTopBannerEnabled;
    const nextShortOverlayTitleMode: SubtitleReviewDocument["shortOverlayTitleMode"] =
      topBannerChanged && !shortTopBannerEnabled
        ? "always"
        : review.shortOverlayTitleMode;
    const optimisticSettings = {
      shortOverlayTitleMode: nextShortOverlayTitleMode,
      shortLayout,
      shortTopBannerEnabled,
      shortBottomBannerEnabled,
      clips:
        topBannerChanged
          ? review.clips.map((clip) =>
              clip.type === "short"
                ? { ...clip, overlayTitleExpected: true }
                : clip
            )
          : review.clips
    };
    const requestBody = {
      ...assets,
      shortLayout,
      shortTopBannerEnabled,
      shortBottomBannerEnabled
    };
    const mutationGeneration = beginReviewMutation();
    setReview((current) =>
      current
        ? {
            ...current,
            ...optimisticSettings
          }
        : current
    );
    setIsSavingShortBannerSettings(true);
    setError(null);
    try {
      const updated = await updateSubtitleReviewShortBannerSettings(
        jobId,
        requestBody
      );
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(updated);
        if (assets.characterPresetName) {
          setClipContentDrafts(current => {
            const next = { ...current };
            for (const clip of updated.clips) {
              const fresh = contentDraftForClip(clip);
              const before = review.clips.find(item => item.id === clip.id);
              const old = before ? contentDraftForClip(before) : fresh;
              const draft = { ...(current[clip.id] ?? fresh) };
              for (const key of Object.keys(fresh) as (keyof ClipContentDraft)[]) {
                if (["titleStyle", "hookStyle", "subtitleStyle", "subtitleStyles"].includes(key)
                    || JSON.stringify(draft[key]) === JSON.stringify(old[key])) {
                  Object.assign(draft, { [key]: fresh[key] });
                }
              }
              next[clip.id] = draft;
            }
            return next;
          });
        }
      }
      return true;
    } catch (caught) {
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview((current) =>
          current
            ? {
                ...current,
                ...previousSettings
              }
            : current
        );
      }
      setError(
        caught instanceof Error
          ? caught.message
          : "ショート画面設定を保存できませんでした"
      );
      return false;
    } finally {
      endReviewMutation();
      setIsSavingShortBannerSettings(false);
    }
  }

  async function saveHookScene(
    start: number | null,
    end: number | null
  ) {
    const {
      selectedClip,
      dirtySegmentIds,
      hasDirtyClipContent,
      setError,
      beginReviewMutation,
      videoRef,
      setIsUpdatingHookScene,
      jobId,
      endReviewMutation
    } = context;
    if (!selectedClip) {
      return;
    }
    if (dirtySegmentIds.size > 0 || hasDirtyClipContent) {
      setError(
        "未保存のタイトル、投稿情報、フック文字、文字スタイル、または字幕を先に保存してください。"
      );
      return;
    }
    beginReviewMutation();
    videoRef.current?.pause();
    setError(null);
    setIsUpdatingHookScene(true);
    try {
      await updateSubtitleReviewHookScene(jobId, selectedClip.id, {
        start,
        end
      });
    } catch (caught) {
      setIsUpdatingHookScene(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "冒頭フック映像を更新できませんでした"
      );
    } finally {
      endReviewMutation();
    }
  }
  return { updateClipContentDraft, updateClipTextStyle, changeSelectedShortFraming, saveSelectedShortFraming, saveShortBannerSettings, saveHookScene };
}
