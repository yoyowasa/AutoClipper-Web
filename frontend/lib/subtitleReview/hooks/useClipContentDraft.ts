"use client";

import { updateSubtitleReviewShortBannerSettings } from "../../api";
import { type ClipTextTarget } from "../../clipTextStyle";
import type { ClipTextStyle, SubtitleReviewClipFramingUpdateRequest, SubtitleReviewDocument } from "../../types";
import { shortFramingEquals } from "../framing";
import { type ClipContentDraft, contentDraftForClip } from "../drafts";
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

  async function saveSelectedShortFraming(clipId: string, framing: SubtitleReviewClipFramingUpdateRequest) {
    const { setShortFramingDrafts, setShowSavedPreview, review } = context;
    const clip = review?.clips.find(item => item.id === clipId);
    const unchanged = clip && shortFramingEquals(framing, { framingOffsetX: clip.framingOffsetX,
      framingOffsetY: clip.framingOffsetY, framingZoom: clip.framingZoom, shortLayout: clip.shortLayout ?? review?.shortLayout });
    setShortFramingDrafts(current => {
      const next = { ...current };
      if (unchanged) delete next[clipId]; else next[clipId] = framing;
      return next;
    });
    setShowSavedPreview(false);
    return true;
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
      locallyUpdatedReviewRef,
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
        locallyUpdatedReviewRef.current = updated;
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

  async function saveHookScene(start: number | null, end: number | null) {
    const { selectedClip, updateClipContentDraft, videoRef } = context;
    if (!selectedClip) return;
    videoRef.current?.pause();
    updateClipContentDraft(selectedClip.id, { hookSceneStart: start, hookSceneEnd: end });
  }
  return { updateClipContentDraft, updateClipTextStyle, changeSelectedShortFraming, saveSelectedShortFraming, saveShortBannerSettings, saveHookScene };
}
