"use client";

import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";

export function ReviewRenderControls({ context }: { context: SubtitleReviewViewContext }) {
  const {
    review,
    isEditable,
    allConfirmed,
    allPreviewsReady,
    dirtySegmentIds,
    hasDirtyClipContent,
    hasDirtyShortFraming,
    isSavingShortBannerSettings,
    isFinalizing,
    startRendering
  } = context;
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
    selectClip
  } = context;
  if (!selectedClip) return null;
  return (
    <div className="border-t border-neutral-300 bg-neutral-50 p-4">
                  <p className="mb-3 text-xs text-neutral-600">
                    {selectedShortFramingDirty
                      ? "画角調整を保存してから、このclipをOKにしてください。"
                      : selectedClipHasDirtySegments || selectedClipHasDirtyContent
                      ? "メインの即時表示を確認し、OKでタイトル・文字設定・字幕をまとめて保存します。"
                      : selectedClip.confirmed && !selectedPreviewReady
                        ? "OK済みです。完成表示はバックグラウンドで更新しています。"
                        : selectedClip.confirmed
                          ? "このclipはOK済みです。"
                          : "メインの動画と字幕を確認し、OKで保存します。"}
                  </p>
                  <button
                    className="min-h-11 w-full bg-sky-700 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
                    disabled={
                      !isEditable ||
                      selectedShortFramingDirty ||
                      (selectedClip.confirmed &&
                        !selectedClipHasDirtySegments &&
                        !selectedClipHasDirtyContent) ||
                      !selectedClipContentDraft?.publicationTitle.trim() ||
                      !selectedHookDurationIsValid ||
                      isSavingShortBannerSettings ||
                      confirmingClipId === selectedClip.id
                    }
                    type="button"
                    onClick={() => void confirmSelectedClip()}
                  >
                    {confirmingClipId === selectedClip.id
                      ? "OKを反映中"
                      : selectedShortFramingDirty
                        ? "画角調整の保存が必要です"
                      : selectedClip.confirmed &&
                          !selectedClipHasDirtySegments &&
                          !selectedClipHasDirtyContent
                        ? "このclipはOK済み"
                        : "この内容を保存してOK"}
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
