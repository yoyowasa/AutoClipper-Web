import type { JobStatusResponse } from "../lib/types";
import { StatusBadge } from "./StatusBadge";

export function JobProgress({ job }: { job: JobStatusResponse }) {
  const detailNumber = (key: string) => {
    const value = job.details[key];
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  };
  const correctionProgress = detailNumber("stageProgress");
  const correctionCompleted = detailNumber("correctionBatchesCompleted");
  const correctionTotal = detailNumber("correctionBatchesTotal");
  const correctionRetries = detailNumber("correctionRetryCount");
  const correctionTargetsCompleted = detailNumber("correctionTargetsCompleted");
  const correctionTargetsTotal = detailNumber("correctionTargetsTotal");
  const transcriptSegmentCount = detailNumber("transcriptSegmentCount");
  const showCorrectionProgress =
    job.status === "correcting_subtitles" &&
    correctionProgress !== null &&
    correctionCompleted !== null &&
    correctionTotal !== null;
  const currentStep =
    job.status === "awaiting_subtitle_review" ? "字幕を確認してください" : job.currentStep;

  return (
    <section className="rounded-md border border-neutral-300 bg-white p-5">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-neutral-500">Job</p>
            <h1 className="mt-1 break-all text-2xl font-semibold text-neutral-950">{job.id}</h1>
          </div>
          <StatusBadge status={job.status} />
        </div>

        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-neutral-700">{currentStep}</p>
            {job.error ? (
              <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                <p className="font-medium">{job.error.code}</p>
                <p className="mt-1">{job.error.message}</p>
              </div>
            ) : null}
          </div>
          <p className="text-2xl font-semibold tabular-nums text-neutral-950">{job.progress}%</p>
        </div>

        <div className="h-3 overflow-hidden rounded-md bg-neutral-100">
          <div
            className="h-full rounded-md bg-neutral-950 transition-all"
            style={{ width: `${job.progress}%` }}
          />
        </div>

        {showCorrectionProgress ? (
          <div className="border-t border-neutral-200 pt-4" data-testid="subtitle-correction-progress">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <p className="font-medium text-neutral-800">字幕校正</p>
              <p className="tabular-nums text-neutral-700">
                {correctionCompleted}/{correctionTotal} batches ({correctionProgress}%)
              </p>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-md bg-neutral-100">
              <div
                aria-label="Subtitle correction progress"
                className="h-full rounded-md bg-sky-600 transition-all"
                style={{ width: `${Math.max(0, Math.min(100, correctionProgress))}%` }}
              />
            </div>
            {correctionRetries && correctionRetries > 0 ? (
              <p className="mt-2 text-xs text-amber-700">API retry: {correctionRetries}</p>
            ) : null}
            {correctionTargetsTotal !== null && transcriptSegmentCount !== null ? (
              <p className="mt-2 text-xs text-neutral-600">
                対象segment {correctionTargetsCompleted ?? 0}/{correctionTargetsTotal} ・ 全segment{" "}
                {transcriptSegmentCount}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
