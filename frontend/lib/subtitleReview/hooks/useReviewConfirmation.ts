"use client";

import { applySubtitleReviewClip, finalizeSubtitleReview, reopenClipPlanForBoundaryReedit, returnSubtitleReviewToClipPlan } from "../../api";
import { postMetadataApplyPayload } from "../../youtubePosting";
import { writeReviewDraft, clearJobReviewDrafts } from "../draftStorage";
import { returnToClipPlanMessage } from "../returnToClipPlan";
import { validateClipDuration, validateHookSceneDuration } from "../../durationRules";
import { contentDraftForClip } from "../drafts";
import type { SubtitleReviewContext } from "./context";

export function useReviewConfirmation(context: SubtitleReviewContext) {
  async function confirmSelectedClip() {
    const {
      isSavingShortBannerSettings,
      setError,
      selectedClip,
      selectedClipContentDraft,
      selectedShortFramingDraft,
      selectedShortFramingDirty,
      setShortFramingDrafts,
      locallyUpdatedReviewRef,
      review,
      selectedHookDurationIsValid,
      selectedSegments,
      dirtySegmentIds,
      drafts,
      beginReviewMutation,
      setConfirmingClipId,
      jobId,
      isCurrentReviewMutation,
      setReview,
      setClipContentDrafts,
      setDrafts,
      setDirtySegmentIds,
      endReviewMutation
    } = context;
    if (isSavingShortBannerSettings) {
      setError("ショート帯設定の保存完了後に確認してください。");
      return;
    }
    if (!selectedClip || !selectedClipContentDraft) {
      return;
    }
    const title = selectedClipContentDraft.title.trim();
    const publicationTitle = selectedClipContentDraft.publicationTitle.trim();
    if (!publicationTitle) {
      setError("公開用タイトルを入力してください。");
      return;
    }
    if (!selectedHookDurationIsValid) {
      setError("冒頭フックの表示秒数は1〜8秒で入力してください。");
      return;
    }
    const bodyError = validateClipDuration(selectedClip.type, selectedClip.end - selectedClip.start, review?.shortMaxDuration ?? 75);
    const { hookSceneStart, hookSceneEnd } = selectedClipContentDraft;
    const hookError = hookSceneStart === null && hookSceneEnd === null ? null
      : hookSceneStart === null || hookSceneEnd === null || hookSceneStart < selectedClip.start || hookSceneEnd > selectedClip.end
        ? "フック映像は本編内の開始・終了を指定してください。" : validateHookSceneDuration(hookSceneEnd - hookSceneStart);
    if (bodyError || hookError) { setError(bodyError ?? hookError); return; }
    const segmentUpdates = selectedSegments
      .filter((segment) => dirtySegmentIds.has(segment.id))
      .map((segment) => ({
        segmentId: segment.id,
        text: drafts[segment.id] ?? segment.text
      }));
    const savedSegmentIds = new Set(segmentUpdates.map((segment) => segment.segmentId));
    const postMetadata = postMetadataApplyPayload(selectedClipContentDraft);
    const mutationGeneration = beginReviewMutation();
    setConfirmingClipId(selectedClip.id);
    setError(null);
    try {
      const updated = await applySubtitleReviewClip(jobId, selectedClip.id, {
        title,
        publicationTitle,
        ...postMetadata,
        hookText: selectedClipContentDraft.hookText.trim(),
        hookDurationSeconds: selectedClipContentDraft.hookDurationSeconds,
        hookSceneStart: selectedClipContentDraft.hookSceneStart,
        hookSceneEnd: selectedClipContentDraft.hookSceneEnd,
        thumbnailKicker: selectedClipContentDraft.thumbnailKicker.trim(),
        thumbnailLine1: selectedClipContentDraft.thumbnailLine1.trim(),
        thumbnailLine2: selectedClipContentDraft.thumbnailLine2.trim(),
        thumbnailFrameSeconds: selectedClipContentDraft.thumbnailFrameSeconds,
        titleStyle: selectedClipContentDraft.titleStyle,
        hookStyle: selectedClipContentDraft.hookStyle,
        subtitleStyle: selectedClipContentDraft.subtitleStyle,
        subtitleStyles: selectedClipContentDraft.subtitleStyles,
        ...(selectedShortFramingDirty && selectedShortFramingDraft ? { framing: selectedShortFramingDraft } : {}),
        segments: segmentUpdates
      });
      if (isCurrentReviewMutation(mutationGeneration)) {
        locallyUpdatedReviewRef.current = updated;
        writeReviewDraft(jobId, selectedClip.id, null);
        setShortFramingDrafts(current => { const next = { ...current }; delete next[selectedClip.id]; return next; });
        setReview(updated);
        const updatedClip = updated.clips.find((clip) => clip.id === selectedClip.id);
        if (updatedClip) {
          setClipContentDrafts((current) => ({
            ...current,
            [updatedClip.id]: contentDraftForClip(updatedClip)
          }));
        }
        setDrafts((current) => {
          const next = { ...current };
          for (const segment of updated.segments) {
            if (savedSegmentIds.has(segment.id)) {
              next[segment.id] = segment.text;
            }
          }
          return next;
        });
        setDirtySegmentIds((current) => {
          const next = new Set(current);
          for (const segmentId of savedSegmentIds) {
            next.delete(segmentId);
          }
          return next;
        });
      }

    } catch (caught) {
      setError(`clipの内容を保存できませんでした：${caught instanceof Error ? caught.message : "通信状態を確認してください。"}`);
    } finally {
      endReviewMutation();
      setConfirmingClipId(null);
    }
  }

  async function startRendering() {
    const {
      isSavingShortBannerSettings,
      setError,
      hasDirtyShortFraming,
      review,
      dirtySegmentIds,
      hasDirtyClipContent,
      allPreviewsReady,
      beginReviewMutation,
      setIsFinalizing,
      jobId,
      router,
      endReviewMutation
    } = context;
    if (isSavingShortBannerSettings) {
      setError("ショート帯設定の保存完了後にレンダリングしてください。");
      return;
    }
    if (hasDirtyShortFraming) {
      setError("未保存のショート画角があります。各clipの画角を保存してください。");
      return;
    }
    if (!review || dirtySegmentIds.size > 0 || hasDirtyClipContent) {
      setError("未保存のタイトル、投稿情報、フック、または字幕があります。先に保存してください。");
      return;
    }
    if (!allPreviewsReady) {
      setError("全clipの完成表示プレビューが揃ってからレンダリングしてください。");
      return;
    }
    beginReviewMutation();
    setIsFinalizing(true);
    setError(null);
    try {
      await finalizeSubtitleReview(jobId);
      router.push(`/jobs/${jobId}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "レンダリングを開始できませんでした");
      setIsFinalizing(false);
    } finally {
      endReviewMutation();
    }
  }

  async function returnToBoundaryEditor() {
    const {
      dirtySegmentIds,
      hasDirtyClipContent,
      hasDirtyShortFraming,
      setError,
      isEditable,
      beginReviewMutation,
      setIsReopeningBoundaries,
      jobId,
      router,
      endReviewMutation
    } = context;
    if (dirtySegmentIds.size > 0 || hasDirtyClipContent || hasDirtyShortFraming) {
      setError("未保存の字幕・タイトル・画角があります。各clipの変更を保存してから尺調整へ戻ってください。");
      return;
    }
    if (!isEditable) return;
    beginReviewMutation();
    setIsReopeningBoundaries(true);
    setError(null);
    try {
      await reopenClipPlanForBoundaryReedit(jobId);
      router.push(`/jobs/${jobId}/clips`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "尺調整画面へ戻れませんでした");
    } finally {
      setIsReopeningBoundaries(false);
      endReviewMutation();
    }
  }
  async function returnToClipPlan() {
    const { review, isEditable, hasReviewMutationInFlight, jobId, router, setError, beginReviewMutation,
      endReviewMutation, setIsReturningToClipPlan, setReview, setDrafts, setDirtySegmentIds,
      setClipContentDrafts, setShortFramingDrafts, dirtySegmentIds, hasDirtyClipContent, hasDirtyShortFraming } = context;
    if (!review || !isEditable || hasReviewMutationInFlight) return;
    if (review.returnToClipPlanAllowed === false) {
      setError("手動ワークフローは切り抜き確認へ戻す対象外です。");
      return;
    }
    if (!window.confirm(returnToClipPlanMessage(review, dirtySegmentIds.size > 0 || hasDirtyClipContent || hasDirtyShortFraming))) return;
    beginReviewMutation();
    setIsReturningToClipPlan(true);
    setError(null);
    try {
      await returnSubtitleReviewToClipPlan(jobId);
      // Stop persistence before clearing all clips, including drafts of removed clips.
      setReview(null);
      setDrafts({});
      setDirtySegmentIds(new Set());
      setClipContentDrafts({});
      setShortFramingDrafts({});
      clearJobReviewDrafts(jobId);
      router.push(`/jobs/${jobId}/clips`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "切り抜き確認に戻れませんでした。");
    } finally {
      setIsReturningToClipPlan(false);
      endReviewMutation();
    }
  }
  return { confirmSelectedClip, startRendering, returnToBoundaryEditor, returnToClipPlan };
}
