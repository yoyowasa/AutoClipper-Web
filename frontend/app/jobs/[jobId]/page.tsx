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
        if (nextJob.status === "completed" || nextJob.status === "failed") {
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

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {job ? (
          <>
            <JobProgress job={job} />
            <ProgressTimeline status={job.status} />
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
