"use client";

import { formatTime, clipLabel } from "../../lib/subtitleReview/display";
import { isPreviewReady } from "../../lib/subtitleReview/preview";
import { segmentDraftKey } from "../../lib/subtitleReview/sharedSegments";
import { isClipContentDirty } from "../../lib/subtitleReview/drafts";
import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";
import { ReviewRenderControls } from "./ReviewActions";

export function ReviewClipList({ context }: { context: SubtitleReviewViewContext }) {
  const {
    activeClipType,
    normalClips,
    selectClipType,
    shortClips,
    isEditable,
    review,
    openedFromReupload,
    visibleClips,
    clipContentDrafts,
    rawDirtySegmentIds: dirtySegmentIds,
    shortFramingDrafts,
    selectedClipId,
    isUpdatingHookScene,
    selectClip,
    bodyDuration
  } = context;
  return (
    <aside className="subtitle-review-clips flex min-h-0 flex-col border border-neutral-300">
<div
          aria-label="編集する動画形式"
          className="grid grid-cols-1 border border-neutral-300 bg-neutral-100 p-1"
          role="tablist"
        >
          <button
            aria-selected={activeClipType === "normal"}
            className={`min-h-11 px-2 text-sm font-semibold ${
              activeClipType === "normal"
                ? "bg-neutral-950 text-white"
                : "bg-white text-neutral-700"
            } disabled:cursor-not-allowed disabled:text-neutral-400`}
            disabled={normalClips.length === 0}
            role="tab"
            type="button"
            onClick={() => selectClipType("normal")}
          >
            通常編集（{normalClips.length}本）
          </button>
          <button
            aria-selected={activeClipType === "short"}
            className={`min-h-11 px-2 text-sm font-semibold ${
              activeClipType === "short"
                ? "bg-neutral-950 text-white"
                : "bg-white text-neutral-700"
            } disabled:cursor-not-allowed disabled:text-neutral-400`}
            disabled={shortClips.length === 0}
            role="tab"
            type="button"
            onClick={() => selectClipType("short")}
          >
            ショート編集（{shortClips.length}本）
          </button>
        </div>
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="border-b border-neutral-200 px-4 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold">
                  {activeClipType === "normal" ? "通常clip" : "ショートclip"}
                </p>
                <div className="flex flex-wrap justify-end gap-1">
                  {isEditable &&
                  (review.renderRevision > 1 || review.reeditSourceJobId) ? (
                    <span className="bg-violet-100 px-2 py-1 text-[10px] font-semibold text-violet-800">
                      1本のみ再編集
                    </span>
                  ) : null}
                  {openedFromReupload ? (
                    <span className="bg-emerald-100 px-2 py-1 text-[10px] font-semibold text-emerald-800">
                      MP4照合済み
                    </span>
                  ) : null}
                </div>
              </div>
              <p className="mt-1 text-xs text-neutral-500">選ぶと動画と字幕が切り替わります</p>
              <div className="mt-3 h-2 overflow-hidden bg-neutral-100">
                <div
                  className="h-full bg-sky-600"
                  style={{
                    width: `${review.totalClipCount > 0
                      ? (review.confirmedClipCount / review.totalClipCount) * 100
                      : 0}%`
                  }}
                />
              </div>
            </div>
            <div className="max-h-64 min-h-0 overflow-y-auto lg:max-h-none lg:flex-1">
              {visibleClips.map((clip) => {
                const clipDraft = clipContentDrafts[clip.id];
                const contentDirty = isClipContentDirty(clip, clipContentDrafts)
                  || clip.segmentIds.some(id => dirtySegmentIds.has(segmentDraftKey(clip, id))) || Boolean(shortFramingDrafts?.[clip.id]);
                return (
                  <button
                    className={`block w-full border-b border-neutral-200 px-4 py-4 text-left disabled:cursor-wait disabled:opacity-60 ${
                      clip.id === selectedClipId ? "bg-neutral-950 text-white" : "bg-white"
                    }`}
                    disabled={isUpdatingHookScene}
                    key={clip.id}
                    type="button"
                    onClick={() => selectClip(clip)}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <span className="text-xs font-semibold uppercase">
                        {clipLabel(clip, review.clips)}
                      </span>
                      <span
                        className={`text-xs font-medium ${
                          contentDirty
                            ? clip.id === selectedClipId
                              ? "text-amber-200"
                              : "text-amber-700"
                            : clip.confirmed
                              ? clip.id === selectedClipId
                                ? "text-emerald-300"
                                : "text-emerald-700"
                              : clip.id === selectedClipId
                                ? "text-amber-200"
                                : "text-amber-700"
                        }`}
                      >
                        {contentDirty ? "未保存" : clip.confirmed ? "確認済み" : "未確認"}
                      </span>
                    </span>
                    <span className="mt-2 block line-clamp-2 text-sm font-medium">
                      {clipDraft ? clipDraft.title : clip.title}
                    </span>
                    {!isPreviewReady(clip, review.state) ? (
                      <span
                        className={`mt-2 block text-[11px] font-semibold ${
                          clip.previewState === "failed"
                            ? clip.id === selectedClipId
                              ? "text-red-200"
                              : "text-red-700"
                            : clip.id === selectedClipId
                              ? "text-sky-200"
                              : "text-sky-700"
                        }`}
                      >
                        {clip.previewState === "failed"
                          ? "プレビュー生成失敗"
                          : clip.previewDeferred || clip.previewState === "stale"
                            ? "確定すると正式プレビューを作成"
                            : "完成表示プレビューを更新中"}
                      </span>
                    ) : null}
                    <span
                      className={`mt-2 block text-xs ${
                        clip.id === selectedClipId ? "text-neutral-300" : "text-neutral-500"
                      }`}
                    >
                      clip長 {formatTime(clip.duration)} ・ {clip.segmentIds.length}字幕
                      {clip.hookSceneStart !== null &&
                      clip.hookSceneEnd !== null
                        ? ` ・ 冒頭複製${formatTime(
                            clip.hookSceneEnd - clip.hookSceneStart
                          )}`
                        : ""}
                      {clip.editedSegmentCount > 0
                        ? ` ・ 修正${clip.editedSegmentCount}件`
                        : ""}
                      {clip.id === selectedClipId
                        ? ` ・ 本編${formatTime(bodyDuration)} ・ 元動画${formatTime(
                            clip.start
                          )}-${formatTime(clip.end)}`
                        : ""}
                    </span>
                  </button>
                );
              })}
            </div>
              <ReviewRenderControls context={context} />
            </div>
          </aside>
  );
}
