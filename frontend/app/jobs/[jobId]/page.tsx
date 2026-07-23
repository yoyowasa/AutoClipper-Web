"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { JobProgress } from "../../../components/JobProgress";
import { ProgressTimeline } from "../../../components/ProgressTimeline";
import { getJobStatus } from "../../../lib/api";
import type { JobStatusResponse } from "../../../lib/types";

function readJobId(param: string | string[] | undefined): string {
  if (Array.isArray(param)) {
    return param[0] ?? "";
  }
  return param ?? "";
}

export default function JobPage() {
  const params = useParams();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

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

        <div className="border border-emerald-300 bg-emerald-50 px-5 py-4">
          <p className="text-sm font-semibold text-emerald-950">
            動画のアップロードが完了しました
          </p>
          <p className="mt-1 text-sm text-emerald-800">
            切り抜き処理を開始しています。この画面は自動更新されます。
          </p>
        </div>

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {job ? (
          <>
            <JobProgress job={job} />
            <ProgressTimeline
              hasSubtitleReview={typeof job.details.subtitleReviewState === "string"}
              status={job.status}
            />
            {job.status === "awaiting_subtitle_review" ? (
              <section className="border border-sky-300 bg-sky-50 px-5 py-5">
                <p className="text-sm font-semibold text-sky-950">
                  clip選定が完了しました。次は字幕確認です。
                </p>
                <p className="mt-1 text-sm text-sky-800">
                  確認済み {Number(job.details.subtitleReviewConfirmedClips ?? 0)} /{" "}
                  {Number(job.details.subtitleReviewTotalClips ?? 0)}
                </p>
                <Link
                  className="mt-4 inline-flex min-h-11 items-center bg-sky-700 px-5 text-sm font-semibold text-white"
                  href={`/jobs/${job.id}/subtitles`}
                >
                  字幕確認へ進む
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
