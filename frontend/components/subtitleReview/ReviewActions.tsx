"use client";

import { contentDraftForClip } from "../../lib/subtitleReview/drafts";
import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";

export function ReviewRenderControls({ context }: { context: SubtitleReviewViewContext }) {
  const {
    review,
    isEditable,
    allConfirmed,
    allPreviewsReady,
    rawDirtySegmentIds: dirtySegmentIds,
    hasDirtyClipContent,
    hasDirtyShortFraming,
    isSavingShortBannerSettings,
    isFinalizing,
    startRendering
  } = context;
  if (review.subtitleOnlyAuto) return null;
  return (
    <div className="border-t border-neutral-300 bg-neutral-50 p-3">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-semibold">
                  確認 {review.confirmedClipCount} / {review.totalClipCount}
                </span>
                <span className="text-neutral-500">修正 {review.editedSegmentCount}件</span>
              </div>
              <button
                className="mt-2 min-h-10 w-full bg-emerald-700 px-3 py-2 text-xs font-semibold text-white disabled:bg-neutral-300"
                disabled={
                  !isEditable ||
                  !allConfirmed ||
                  !allPreviewsReady ||
                  dirtySegmentIds.size > 0 ||
                  hasDirtyClipContent ||
                  hasDirtyShortFraming ||
                  isSavingShortBannerSettings ||
                  isFinalizing
                }
                type="button"
                onClick={() => void startRendering()}
              >
                {isFinalizing
                  ? "レンダリング開始中"
                  : hasDirtyShortFraming
                    ? "未保存のショート画角があります"
                  : !allPreviewsReady
                    ? "プレビュー更新完了を待っています"
                    : "字幕を確定してレンダリング"}
              </button>
              </div>
  );
}

export function ReviewClipActions({ context }: { context: SubtitleReviewViewContext }) {
  const {
    selectedShortFramingDirty,
    selectedClipHasDirtySegments,
    selectedClipHasDirtyContent,
    selectedClip,
    selectedPreviewReady,
    isEditable,
    selectedClipContentDraft,
    selectedHookDurationIsValid,
    isSavingShortBannerSettings,
    confirmingClipId,
    confirmSelectedClip,
    hasReviewMutationInFlight,
    review,
    selectClip,
    dirtySegmentIds
  } = context;
  if (!selectedClip) return null;
  const savedContent = contentDraftForClip(selectedClip);
  const pendingChanges = selectedClip.segmentIds.filter(id => dirtySegmentIds.has(id)).length
    + (selectedShortFramingDirty ? 1 : 0)
    + (selectedClipContentDraft ? (Object.keys(savedContent) as (keyof typeof savedContent)[])
      .filter(key => JSON.stringify(savedContent[key]) !== JSON.stringify(selectedClipContentDraft[key])).length : 0);
  return (
    <div className="border-t border-neutral-300 bg-neutral-50 p-4">
                  {review.subtitleOnlyAuto && selectedClip.confirmed && <button type="button"
                    className="mb-2 min-h-9 w-full border border-neutral-400 bg-white text-sm" disabled={hasReviewMutationInFlight}
                    onClick={() => void context.reopenConfirmedClip()}>字幕を直し直す（このclipの自動処理を解除）</button>}
                  <p className="mb-2 text-xs font-semibold text-amber-800">未保存の変更 {pendingChanges}件</p>
                  <p className="mb-3 text-xs text-neutral-600">
                    {selectedClipHasDirtySegments || selectedClipHasDirtyContent || selectedShortFramingDirty
                      ? review.subtitleOnlyAuto ? "字幕を確定すると、このclipの自動決定を開始します。詳細編集の変更も保存します。"
                        : "簡易プレビューで下書きを確認し、確定で字幕・画角・フック・投稿情報をまとめて保存します。"
                      : review.subtitleOnlyAuto && selectedClip.automaticDecisionState === "failed" ? "字幕を確定して再試行"
                      : review.subtitleOnlyAuto && !selectedClip.confirmed ? "このclipの字幕を確定"
                      : selectedClip.confirmed && !selectedPreviewReady
                        ? "確定済みです。正式プレビューをバックグラウンドで作成中です。他のclipも編集できます。"
                        : selectedClip.confirmed
                          ? "このclipは確定済みです。"
                          : "簡易プレビューで確認し、このclipを確定してください。"}
                  </p>
                  <button
                    className="min-h-11 w-full bg-sky-700 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
                    disabled={
                      (!isEditable && !(review.subtitleOnlyAuto && selectedClip.automaticDecisionState === "failed" && !hasReviewMutationInFlight)) ||
                      (selectedClip.confirmed && selectedClip.automaticDecisionState !== "failed" &&
                        !selectedClipHasDirtySegments &&
                        !selectedClipHasDirtyContent && !selectedShortFramingDirty) ||
                      (!review.subtitleOnlyAuto && (!selectedClipContentDraft?.publicationTitle.trim() || !selectedHookDurationIsValid)) ||
                      isSavingShortBannerSettings ||
                      confirmingClipId === selectedClip.id
                    }
                    type="button"
                    onClick={() => void confirmSelectedClip()}
                  >
                    {confirmingClipId === selectedClip.id
                      ? "確定中"
                      : review.subtitleOnlyAuto && selectedClip.automaticDecisionState === "failed" ? "自動処理を再試行"
                      : selectedClip.confirmed &&
                          !selectedClipHasDirtySegments &&
                          !selectedClipHasDirtyContent && !selectedShortFramingDirty
                        ? "このclipは確定済み"
                        : review.subtitleOnlyAuto
                          ? selectedClip.type === "short" ? "このショートの字幕を確定" : "この動画の字幕を確定"
                          : selectedClip.type === "short" ? "このショートを確定" : "この動画を確定"}
                  </button>
                  <button type="button" className="mt-2 min-h-9 w-full border border-neutral-400 bg-white text-sm disabled:opacity-40"
                    disabled={hasReviewMutationInFlight || review.clips.length < 2}
                    onClick={() => {
                      const index = review.clips.findIndex(clip => clip.id === selectedClip.id);
                      selectClip(review.clips[(index + 1) % review.clips.length]);
                    }}>次のclipへ</button>
                </div>
  );
}

export function ReviewBoundaryReeditButton({ context }: { context: SubtitleReviewViewContext }) {
  const { isEditable, returnToBoundaryEditor, isReopeningBoundaries } = context;
  return (
    <button type="button"
            className="min-h-9 border border-sky-700 bg-white px-3 text-xs font-semibold text-sky-900 disabled:opacity-40 sm:text-sm"
            disabled={!isEditable} onClick={() => void returnToBoundaryEditor()}>
            {isReopeningBoundaries ? "尺調整を準備中…" : "尺調整へ戻る"}
          </button>
  );
}

export function ReviewReturnToClipPlanButton({ context }: { context: SubtitleReviewViewContext }) {
  return <div className="flex flex-col gap-1">
    <button type="button" className="min-h-9 border border-amber-700 bg-white px-3 text-xs font-semibold text-amber-900 disabled:opacity-40"
      disabled={!context.isEditable || context.review.returnToClipPlanAllowed === false}
      onClick={() => void context.returnToClipPlan()}>
      {context.isReturningToClipPlan ? "切り抜き確認へ戻しています" : "切り抜き確認に戻る"}
    </button>
    {context.review.returnToClipPlanAllowed === false ? <span className="text-xs text-neutral-600">手動ワークフローは対象外です。</span> : null}
  </div>;
}
