"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ResultVideoCard } from "../../../components/ResultVideoCard";
import { SaveFileButton } from "../../../components/SaveFileButton";
import {
  createClipReedit,
  getJobResults,
  regenerateExportThumbnail,
  toBrowserApiUrl
} from "../../../lib/api";
import type { JobAuditSummary, JobResultsResponse, ResultExportItem } from "../../../lib/types";

const IMPORTANT_AUDIT_WARNINGS = [
  "missing_title",
  "subtitle_too_dense",
  "title_subtitle_overlap",
  "title_subtitle_vertical_overlap",
  "external_subtitle_autoload_risk",
  "likely_abrupt_start",
  "likely_abrupt_ending",
  "backfilled_clip",
  "below_quality_threshold"
];

function readJobId(param: string | string[] | undefined): string {
  if (Array.isArray(param)) {
    return param[0] ?? "";
  }
  return param ?? "";
}

function readableWarning(value: string): string {
  return value.replaceAll("_", " ");
}

function AuditSummaryPanel({ summary }: { summary: JobAuditSummary | null }) {
  if (!summary) {
    return (
      <section className="rounded-md border border-neutral-300 bg-white p-4 text-sm text-neutral-600">
        Audit report not available yet.
      </section>
    );
  }

  const visibleWarnings = IMPORTANT_AUDIT_WARNINGS.map((warning) => ({
    warning,
    count: summary.warningCounts[warning] ?? 0
  })).filter((item) => item.count > 0);

  return (
    <section className="rounded-md border border-neutral-300 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Audit summary</h2>
          <p className="mt-1 text-sm text-neutral-600">
            Normal {summary.generatedNormalCount ?? "-"} / Shorts {summary.generatedShortCount ?? "-"} / Inspect{" "}
            {summary.clipsRequiringHumanVisualInspectionCount ?? 0}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {visibleWarnings.length > 0 ? (
          visibleWarnings.map((item) => (
            <span
              key={item.warning}
              className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-900"
            >
              {readableWarning(item.warning)}: {item.count}
            </span>
          ))
        ) : (
          <span className="text-sm font-medium text-emerald-700">No tracked audit warnings</span>
        )}
      </div>
    </section>
  );
}

export default function ResultsPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const [results, setResults] = useState<JobResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reopeningClipId, setReopeningClipId] = useState<string | null>(null);
  const [regeneratingThumbnailId, setRegeneratingThumbnailId] = useState<string | null>(null);

  const loadResults = useCallback(async () => {
    if (!jobId) {
      return;
    }
    try {
      const payload = await getJobResults(jobId);
      setResults(payload);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Results fetch failed");
    }
  }, [jobId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadResults();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadResults]);

  const thumbnailGenerationActive = Boolean(
    results?.normalClips.some((item) => item.thumbnailStatus === "generating")
  );

  useEffect(() => {
    if (!thumbnailGenerationActive) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadResults();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [loadResults, thumbnailGenerationActive]);

  async function reopenForEditing(item: ResultExportItem) {
    if (!item.candidateId) {
      setError("この動画の編集元clipを特定できません");
      return;
    }
    setReopeningClipId(item.candidateId);
    setError(null);
    try {
      const review = await createClipReedit(jobId, item.candidateId);
      router.push(
        `/jobs/${review.jobId}/subtitles?clipId=${encodeURIComponent(item.candidateId)}&source=reedit`
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "完成jobを再編集用に開けませんでした"
      );
      setReopeningClipId(null);
    }
  }

  async function regenerateThumbnail(item: ResultExportItem) {
    const frameSeconds = Math.min(
      item.duration,
      Math.max(0, item.thumbnailFrameSeconds ?? item.duration * 0.38)
    );
    const subjectAnchorX = item.thumbnailSubjectAnchorX ?? 1;
    setRegeneratingThumbnailId(item.id);
    setError(null);
    try {
      await regenerateExportThumbnail(item.id, {
        frameSeconds,
        subjectAnchorX,
        advanceFrame: true
      });
      setResults((current) =>
        current
          ? {
              ...current,
              normalClips: current.normalClips.map((clip) =>
                clip.id === item.id
                  ? {
                      ...clip,
                      thumbnailSubjectAnchorX: subjectAnchorX,
                      thumbnailStatus: "generating"
                    }
                  : clip
              )
            }
          : current
      );
      setRegeneratingThumbnailId(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "サムネだけの再生成を開始できませんでした"
      );
      setRegeneratingThumbnailId(null);
    }
  }

  return (
    <main className="min-h-screen bg-[#f7f7f4] px-6 py-8 text-neutral-950">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-5">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-neutral-300 pb-5">
          <div>
            <p className="text-sm font-medium uppercase text-neutral-500">AutoClipper</p>
            <h1 className="mt-2 break-all text-3xl font-semibold">Results</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            {results?.reeditSourceJobId ? (
              <Link
                className="inline-flex min-h-11 items-center rounded-md border border-sky-700 bg-white px-5 text-sm font-medium text-sky-800"
                href={`/results/${results.reeditSourceJobId}`}
              >
                元の完成動画一覧へ戻る
              </Link>
            ) : null}
            {results ? (
              <SaveFileButton
                className="inline-flex min-h-11 items-center rounded-md bg-neutral-950 px-5 text-sm font-medium text-white"
                url={toBrowserApiUrl(results.zipDownloadUrl)}
                suggestedName={`${jobId}.zip`}
                mimeType="application/zip"
                extension=".zip"
                description="ZIP archive"
                label="ZIPを保存"
              />
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
            {results.canReopenForEditing ? (
              <section className="border border-sky-300 bg-sky-50 px-5 py-4 text-sm text-sky-900">
                各動画の「この動画だけ再編集」から1本だけ開けます。通常動画は再編集画面でショートへ変更できます。
              </section>
            ) : null}

            <AuditSummaryPanel summary={results.auditSummary} />

            <section className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-4">
                <h2 className="text-xl font-semibold">Normal clips</h2>
                <span className="text-sm text-neutral-500">{results.normalClips.length}</span>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {results.normalClips.map((item, index) => (
                  <ResultVideoCard
                    key={item.id}
                    item={item}
                    auditAvailable={Boolean(results.auditSummary)}
                    isReediting={reopeningClipId === item.candidateId}
                    isRegeneratingThumbnail={regeneratingThumbnailId === item.id}
                    onReedit={results.canReopenForEditing ? reopenForEditing : undefined}
                    onRegenerateThumbnail={regenerateThumbnail}
                    suggestedFilename={`normal_${String(index + 1).padStart(2, "0")}.mp4`}
                    thumbnailPriority={index === 0}
                  />
                ))}
              </div>
            </section>

            <section className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-4">
                <h2 className="text-xl font-semibold">Shorts</h2>
                <span className="text-sm text-neutral-500">{results.shorts.length}</span>
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {results.shorts.map((item, index) => (
                  <ResultVideoCard
                    key={item.id}
                    item={item}
                    auditAvailable={Boolean(results.auditSummary)}
                    isReediting={reopeningClipId === item.candidateId}
                    onReedit={results.canReopenForEditing ? reopenForEditing : undefined}
                    suggestedFilename={`short_${String(index + 1).padStart(2, "0")}.mp4`}
                  />
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
