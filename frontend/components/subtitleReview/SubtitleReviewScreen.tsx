"use client";

import Link from "next/link";
import { useState } from "react";
import type { SubtitleReviewContext, SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";
import { ReviewSubtitleSegments } from "./ReviewSubtitleSegments";
import { ReviewTextStyles } from "./ReviewStyleFraming";
import { ReviewContentEditor } from "./ReviewContentEditor";
import { ReviewPreview } from "./ReviewPreview";
import { ReviewClipList } from "./ReviewClipList";
import { ReviewBoundaryReeditButton, ReviewReturnToClipPlanButton } from "./ReviewActions";
import { AutomaticReviewStatus } from "./AutomaticReviewStatus";
import { automaticReviewIsConfirmed } from "../../lib/subtitleReview/automaticStatus";

export function SubtitleReviewScreen({ model }: { model: SubtitleReviewContext }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const { review, error, jobId, workspaceTab, setWorkspaceTab, selectedClip, hasReviewMutationInFlight } = model;
  if (!review) {
    return (
      <main className="min-h-screen bg-[#f7f7f4] px-6 py-8 text-neutral-950">
        <div className="mx-auto w-full max-w-6xl border border-neutral-300 bg-white p-6 text-sm">
          {error ?? "字幕確認データを読み込んでいます"}
        </div>
      </main>
    );
  }
  const allConfirmed =
    review.totalClipCount > 0 && review.confirmedClipCount === review.totalClipCount;
  const context: SubtitleReviewViewContext = { ...model, review, allConfirmed };
  const compactStatus = automaticReviewIsConfirmed(review);
  return (
    <main className="subtitle-review-screen min-h-screen bg-[#f7f7f4] px-3 py-2 text-neutral-950 sm:px-5">
      <section className="subtitle-review-shell mx-auto flex w-full flex-col gap-2">
        <header className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-2 border-b border-neutral-300 py-1">
          <h1 className="text-lg font-semibold sm:text-xl">clip別 字幕確認</h1>
          {!compactStatus && <p className="text-xs text-neutral-600">
            確認 {review.confirmedClipCount} / {review.totalClipCount} ・ 修正{" "}
            {review.editedSegmentCount}件
          </p>}
          {!compactStatus && <span
            className={`px-2 py-1 text-[11px] font-semibold ${
              review.state === "completed"
                ? "bg-emerald-100 text-emerald-800"
                : review.state === "awaiting_review"
                  ? "bg-sky-100 text-sky-800"
                  : "bg-amber-100 text-amber-800"
            }`}
          >
            {review.state === "completed"
              ? "完了"
              : review.state === "awaiting_review"
                ? hasReviewMutationInFlight ? "保存中" : "字幕確認中"
                : "書き出し中"}
          </span>}
          {compactStatus && <button type="button" className="text-xs underline" onClick={() => setDetailsOpen(value => !value)}>
            {detailsOpen ? "詳細編集を閉じる" : "詳細編集（任意）"}
          </button>}
          {review.state === "awaiting_review" && (!review.subtitleOnlyAuto || detailsOpen) && <ReviewBoundaryReeditButton context={context} />}
          {review.state === "awaiting_review" && (!review.subtitleOnlyAuto || detailsOpen) && <ReviewReturnToClipPlanButton context={context} />}
          <Link
            className="ml-auto inline-flex min-h-9 items-center border border-neutral-300 bg-white px-3 text-xs font-medium sm:text-sm"
            href={`/jobs/${jobId}`}
          >
            処理状況へ戻る
          </Link>
        </header>

        {!review.subtitleOnlyAuto && review.state !== "awaiting_review" ? (
          <div className="border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-900">
            {review.state === "completed"
              ? "字幕確認と書き出しは完了しています。この画面は確認履歴として表示しています。"
              : "字幕は確定済みです。現在、動画を書き出しています。"}
          </div>
        ) : null}

        {!review.subtitleOnlyAuto && error ? (
          <div className="border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {review.subtitleOnlyAuto && !compactStatus && <div className="flex flex-wrap items-center gap-3 border border-sky-200 bg-sky-50 p-3 text-sm">
          <p>字幕の文字を直してclipごとに確定してください。タイトル・フック・投稿文・サムネを自動で決め、全clipの準備が整うと書き出します。</p>
          <button type="button" className="underline" onClick={() => setDetailsOpen(value => !value)}>
            {detailsOpen ? "詳細編集を閉じる" : "詳細編集（任意）"}
          </button>
        </div>}
        <AutomaticReviewStatus review={review} error={error} selectedClip={selectedClip} />

        {(!compactStatus || detailsOpen) && <div data-clip-type={selectedClip?.type} className="subtitle-review-grid grid overflow-hidden border border-neutral-300 bg-white lg:grid-cols-[230px_minmax(0,1fr)_390px] xl:grid-cols-[260px_minmax(0,1fr)_clamp(360px,26vw,480px)] 2xl:h-[calc(100vh-4.5rem)] 2xl:min-h-[760px] 2xl:grid-cols-[clamp(210px,13vw,260px)_minmax(560px,1fr)_clamp(320px,22vw,440px)] 2xl:grid-rows-[minmax(500px,62vh)_minmax(260px,1fr)]">
          <ReviewClipList context={context} />



          <ReviewPreview context={context} />

          <section className="contents">
            {selectedClip ? (
              <div className="contents">
                {(!review.subtitleOnlyAuto || detailsOpen) && <div data-tab={workspaceTab} className="subtitle-review-editors grid min-w-0 bg-white lg:col-span-3 lg:row-start-2 2xl:col-span-3 2xl:col-start-1 2xl:row-start-2 2xl:h-full 2xl:min-h-0 2xl:grid-cols-4 2xl:overflow-hidden">
                  <div role="tablist" aria-label="編集項目" className="subtitle-editor-tabs flex border-b bg-neutral-50">
                    <button type="button" role="tab" aria-selected={workspaceTab === "content"} onClick={() => setWorkspaceTab("content")} className="px-4 py-2 text-sm font-semibold aria-selected:bg-neutral-950 aria-selected:text-white">タイトル・フック</button>
                    <button type="button" role="tab" aria-selected={workspaceTab === "style"} onClick={() => setWorkspaceTab("style")} className="px-4 py-2 text-sm font-semibold aria-selected:bg-neutral-950 aria-selected:text-white">書式・位置・色</button>
                  </div>
                  <ReviewContentEditor key={`content-${selectedClip.id}`} context={context} />

                  <ReviewTextStyles key={selectedClip.id} context={context} />
                </div>}
                <ReviewSubtitleSegments context={context} showStyleControls={!review.subtitleOnlyAuto || detailsOpen} />
              </div>
            ) : null}
          </section>
        </div>}

      </section>
    </main>
  );
}
