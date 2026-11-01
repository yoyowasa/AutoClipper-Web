"use client";

import { unconfirmAutomaticReviewClip, applySubtitleReviewClip, finalizeSubtitleReview, reopenClipPlanForBoundaryReedit, returnSubtitleReviewToClipPlan } from "../../api";
import { postMetadataApplyPayload } from "../../youtubePosting";
import { writeReviewDraft, clearJobReviewDrafts } from "../draftStorage";
import { returnToClipPlanMessage } from "../returnToClipPlan";
import { validateClipDuration, validateHookSceneDuration } from "../../durationRules";
import { segmentDraftKey, sharedSubtitleNotice } from "../sharedSegments";
import { contentDraftForClip } from "../drafts";
import { canEditManualFraming } from "../manualFraming";
import { automaticApplyPayload } from "../automaticConfirmation";
import type { SubtitleReviewContext } from "./context";

export function useReviewConfirmation(context: SubtitleReviewContext) {
  async function reopenConfirmedClip() {
    if (!context.selectedClip || context.hasReviewMutationInFlight) return;
    context.beginReviewMutation();
    context.setConfirmingClipId(context.selectedClip.id);
    try {
      context.setReview(await unconfirmAutomaticReviewClip(context.jobId, context.selectedClip.id));
      context.setError(null);
    } catch (caught) {
      context.setError(caught instanceof Error ? caught.message : "字幕の確定を解除できませんでした。");
    } finally {
      context.endReviewMutation();
      context.setConfirmingClipId(null);
    }
  }

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
    if (review?.subtitleOnlyAuto && selectedClip?.confirmed &&
      selectedClip.segmentIds.some(id => dirtySegmentIds.has(id))) {
      // Use the same scoped caption save as blur autosave. Applying the whole
      // clip would re-confirm it and could submit unrelated content drafts.
      await context.saveConfirmedSubtitles(selectedClip.id);
      return;
    }
    if (!selectedClip || !selectedClipContentDraft) {
      return;
    }
    const title = selectedClipContentDraft.title.trim();
    const publicationTitle = selectedClipContentDraft.publicationTitle.trim();
    if (!review?.subtitleOnlyAuto && !publicationTitle) {
      setError("公開用タイトルを入力してください。");
      return;
    }
    if (!review?.subtitleOnlyAuto && !selectedHookDurationIsValid) {
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
    const notice = review && sharedSubtitleNotice(review, selectedSegments.filter(segment => dirtySegmentIds.has(segment.id)), selectedClip.id);
    if (notice && !window.confirm(`${notice}\n確定済みの他のclipは変更しません。保存しますか？`)) return;
    const savedSegmentIds = new Set(segmentUpdates.map((segment) => segment.segmentId));
    const postMetadata = postMetadataApplyPayload(selectedClipContentDraft);
    context.setSubtitleWorkspaceOpen?.(true);
    const mutationGeneration = beginReviewMutation();
    setConfirmingClipId(selectedClip.id);
    setError(null);
    try {
      const payload = {
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
        ...(selectedShortFramingDirty && selectedShortFramingDraft && review && canEditManualFraming(review, selectedClip)
          ? { framing: selectedShortFramingDraft } : {}),
        segments: segmentUpdates
      };
      const updated = await applySubtitleReviewClip(jobId, selectedClip.id,
        review?.subtitleOnlyAuto ? automaticApplyPayload(selectedClip, payload) : payload);
      if (isCurrentReviewMutation(mutationGeneration)) {
        locallyUpdatedReviewRef.current = updated;
        writeReviewDraft(jobId, selectedClip.id, null);
        setShortFramingDrafts(current => { const next = { ...current }; delete next[selectedClip.id]; return next; });
        setReview(updated);
        const updatedClip = updated.clips.find((clip) => clip.id === selectedClip.id);
        if (updatedClip) {
          setClipContentDrafts((current) => ({
            ...current,
            [updatedClip.id]: { ...contentDraftForClip(updatedClip), ...(updated.subtitleOnlyAuto ? { _editedFields: [] } : {}) }
          }));
        }
        setDrafts((current) => {
          const next = { ...current };
          for (const segment of updated.segments) {
            if (savedSegmentIds.has(segment.id)) {
              next[segment.id] = segment.text;
              delete next[segmentDraftKey(selectedClip, segment.id)];
            }
          }
          return next;
        });
        setDirtySegmentIds((current) => {
          const next = new Set(current);
          for (const segmentId of savedSegmentIds) {
            next.delete(segmentId);
            next.delete(segmentDraftKey(selectedClip, segmentId));
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
      rawDirtySegmentIds,
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
    if (!review || rawDirtySegmentIds.size > 0 || hasDirtyClipContent) {
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
      rawDirtySegmentIds,
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
    if (rawDirtySegmentIds.size > 0 || hasDirtyClipContent || hasDirtyShortFraming) {
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
      setClipContentDrafts, setShortFramingDrafts, rawDirtySegmentIds, hasDirtyClipContent, hasDirtyShortFraming } = context;
    if (!review || !isEditable || hasReviewMutationInFlight) return;
    if (review.returnToClipPlanAllowed === false) {
      setError("手動ワークフローは切り抜き確認へ戻す対象外です。");
      return;
    }
    if (!window.confirm(returnToClipPlanMessage(review, rawDirtySegmentIds.size > 0 || hasDirtyClipContent || hasDirtyShortFraming))) return;
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
  return { reopenConfirmedClip, confirmSelectedClip, startRendering, returnToBoundaryEditor, returnToClipPlan };
}
