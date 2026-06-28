"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ResultVideoCard } from "../../../components/ResultVideoCard";
import { getJobResults, toApiUrl } from "../../../lib/api";
import type { JobResultsResponse } from "../../../lib/types";

function readJobId(param: string | string[] | undefined): string {
  if (Array.isArray(param)) {
    return param[0] ?? "";
  }
  return param ?? "";
}

export default function ResultsPage() {
  const params = useParams();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const [results, setResults] = useState<JobResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    async function loadResults() {
      try {
        const payload = await getJobResults(jobId);
        setResults(payload);
        setError(null);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Results fetch failed");
      }
    }

    void loadResults();
  }, [jobId]);

  return (
    <main className="min-h-screen bg-[#f7f7f4] px-6 py-8 text-neutral-950">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-5">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-neutral-300 pb-5">
          <div>
            <p className="text-sm font-medium uppercase text-neutral-500">AutoClipper</p>
            <h1 className="mt-2 break-all text-3xl font-semibold">Results</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            {results ? (
              <a
                className="inline-flex min-h-11 items-center rounded-md bg-neutral-950 px-5 text-sm font-medium text-white"
                href={toApiUrl(results.zipDownloadUrl)}
              >
                Download ZIP
              </a>
            ) : null}
            <Link
              className="inline-flex min-h-11 items-center rounded-md border border-neutral-300 px-5 text-sm font-medium text-neutral-800"
              href="/upload"
            >
              New upload
            </Link>
          </div>
        </header>

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        {results ? (
          <>
            <section className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-4">
                <h2 className="text-xl font-semibold">Normal clips</h2>
                <span className="text-sm text-neutral-500">{results.normalClips.length}</span>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {results.normalClips.map((item) => (
                  <ResultVideoCard key={item.id} item={item} />
                ))}
              </div>
            </section>

            <section className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-4">
                <h2 className="text-xl font-semibold">Shorts</h2>
                <span className="text-sm text-neutral-500">{results.shorts.length}</span>
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {results.shorts.map((item) => (
                  <ResultVideoCard key={item.id} item={item} />
                ))}
              </div>
            </section>
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
