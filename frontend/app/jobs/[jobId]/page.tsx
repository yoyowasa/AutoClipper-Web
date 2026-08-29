"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { JobProgress } from "../../../components/JobProgress";
import { ProgressTimeline } from "../../../components/ProgressTimeline";
import { getJobStatus, retryJob } from "../../../lib/api";
import type { JobStatusResponse } from "../../../lib/types";

function readJobId(param: string | string[] | undefined): string {
  if (Array.isArray(param)) {
    return param[0] ?? "";
  }
  return param ?? "";
}

export default function JobPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  async function handleRetry() {
    if (!jobId || retrying) {
      return;
    }
    setRetrying(true);
    setRetryError(null);
    try {
      const retried = await retryJob(jobId);
      router.push(`/jobs/${retried.jobId}`);
    } catch (caught) {
      setRetryError(caught instanceof Error ? caught.message : "再処理を開始できませんでした");
      setRetrying(false);
    }
  }

  useEffect(() => {
    if (!jobId) {
      return undefined;
    }

    let isActive = true;

    async function refresh() {
      try {
        const nextJob = await getJobStatus(jobId);
        if (!isActive) {
          return;
        }
        setJob(nextJob);
        setError(null);
        if (
          nextJob.status === "completed" ||
          nextJob.status === "failed" ||
          nextJob.status === "awaiting_manual_edit" ||
          nextJob.status === "awaiting_clip_review" ||
          nextJob.status === "awaiting_subtitle_review"
        ) {
          if (intervalId) {
            clearInterval(intervalId);
          }
        }
      } catch (caught) {
        if (isActive) {
          setError(caught instanceof Error ? caught.message : "Status fetch failed");
        }
      }
    }

    const intervalId = setInterval(refresh, 2000);
    void refresh();

    return () => {
      isActive = false;
      clearInterval(intervalId);
    };
  }, [jobId]);

  const guardedAutomation = job?.details.automationEffectiveMode === "guarded";
  const guardedAutoPassedClips =
    typeof job?.details.automationGateAutoPassedClips === "number"
      ? job.details.automationGateAutoPassedClips
      : null;
  const guardedAttentionClips =
    typeof job?.details.automationGateAttentionClips === "number"
      ? job.details.automationGateAttentionClips
      : null;

  return (
    <main className="min-h-screen bg-[#f7f7f4] px-6 py-8 text-neutral-950">
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-5">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-neutral-300 pb-5">
          <div>
            <p className="text-sm font-medium uppercase text-neutral-500">AutoClipper</p>
            <h1 className="mt-2 text-3xl font-semibold">Job progress</h1>
          </div>
          <Link
            className="inline-flex min-h-11 items-center rounded-md border border-neutral-300 px-5 text-sm font-medium text-neutral-800"
            href="/upload"
          >
            New upload
          </Link>
        </header>

        {job && job.status !== "failed" ? (
          <div className="border border-emerald-300 bg-emerald-50 px-5 py-4">
            <p className="text-sm font-semibold text-emerald-950">
              動画のアップロードが完了しました
            </p>
            <p className="mt-1 text-sm text-emerald-800">
              切り抜き処理を開始しています。この画面は自動更新されます。
            </p>
          </div>
        ) : null}

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {job ? (
          <>
            <JobProgress job={job} />
            {job.status === "failed" && job.error?.code === "no_usable_selection" ? (
              <section className="border border-amber-300 bg-amber-50 px-5 py-5">
                <p className="text-sm font-semibold text-amber-950">
                  動画を選び直さず、このまま再処理できます。
                </p>
                <button
                  className="mt-4 inline-flex min-h-11 items-center bg-neutral-950 px-5 text-sm font-semibold text-white disabled:cursor-wait disabled:bg-neutral-400"
                  disabled={retrying}
                  onClick={() => void handleRetry()}
                  type="button"
                >
                  {retrying ? "再処理を開始中..." : "同じ動画・設定で再処理"}
                </button>
                {retryError ? <p className="mt-3 text-sm text-red-700">{retryError}</p> : null}
              </section>
            ) : null}
            <ProgressTimeline
              failureStatus={
                job.status === "failed" &&
                (job.error?.code === "no_usable_selection" ||
                  job.error?.code === "no_usable_selection_retry_exhausted")
                  ? "selecting_clips"
                  : undefined
              }
              hasClipPlanReview={
                typeof job.details.clipPlanState === "string" ||
                job.status === "awaiting_manual_edit" ||
                job.status === "awaiting_clip_review"
              }
              hasSubtitleReview={typeof job.details.subtitleReviewState === "string"}
              status={job.status}
            />
            {job.status === "awaiting_manual_edit" || job.status === "awaiting_clip_review" ? (
              <section className="border border-blue-300 bg-blue-50 px-5 py-5">
                <p className="text-sm font-semibold text-blue-950">
                  {job.status === "awaiting_manual_edit"
                    ? "元動画の準備ができました。手動で切り抜く範囲を作成できます。"
                    : guardedAutomation
                      ? "自動判定で確認が必要な切り抜き予定があります。"
                      : "切り抜き候補が決まりました。字幕を作る前に範囲を確認できます。"}
                </p>
                <p className="mt-1 text-sm text-blue-800">
                  {job.status === "awaiting_manual_edit"
                    ? "元動画を再生し、通常切り抜きとショートの開始・終了を指定してください。"
                    : guardedAutomation
                      ? "自動判定の結果を確認し、必要なら範囲を調整してください。"
                      : "各予定clipを再生し、合わなければ狙う場面を変更して再選定してください。"}
                </p>
                <Link
                  className="mt-4 inline-flex min-h-11 items-center bg-blue-700 px-5 text-sm font-semibold text-white"
                  href={`/jobs/${job.id}/clips`}
                >
                  {job.status === "awaiting_manual_edit"
                    ? "手動切り抜きを開く"
                    : guardedAutomation
                      ? "確認が必要な切り抜き予定を開く"
                      : "切り抜き予定を確認"}
                </Link>
              </section>
            ) : null}
            {job.status === "awaiting_subtitle_review" ? (
              <section className="border border-sky-300 bg-sky-50 px-5 py-5">
                <p className="text-sm font-semibold text-sky-950">
                  {guardedAutomation
                    ? "自動判定できない項目があります。"
                    : "clip選定が完了しました。次は字幕確認です。"}
                </p>
                <p className="mt-1 text-sm text-sky-800">
                  {guardedAutomation ? (
                    guardedAutoPassedClips !== null || guardedAttentionClips !== null ? (
                      <>
                        自動通過 {guardedAutoPassedClips ?? 0}件 ・ 要確認{" "}
                        {guardedAttentionClips ?? 0}件
                      </>
                    ) : (
                      <>自動判定の確認対象を開いてください。</>
                    )
                  ) : (
                    <>
                      確認済み {Number(job.details.subtitleReviewConfirmedClips ?? 0)} /{" "}
                      {Number(job.details.subtitleReviewTotalClips ?? 0)}
                    </>
                  )}
                </p>
                <Link
                  className="mt-4 inline-flex min-h-11 items-center bg-sky-700 px-5 text-sm font-semibold text-white"
                  href={`/jobs/${job.id}/subtitles`}
                >
                  {guardedAutomation ? "確認が必要な項目を開く" : "字幕確認へ進む"}
                </Link>
              </section>
            ) : null}
            {job.status === "completed" ? (
              <Link
                className="inline-flex min-h-11 w-fit items-center rounded-md bg-neutral-950 px-5 text-sm font-medium text-white"
                href={`/results/${job.id}`}
              >
                View results
              </Link>
            ) : null}
          </>
        ) : (
          <div className="rounded-md border border-neutral-300 bg-white p-5 text-sm text-neutral-600">
            Loading
          </div>
        )}
      </section>
    </main>
  );
}
