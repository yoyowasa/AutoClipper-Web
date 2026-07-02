import { formatDuration, formatScore } from "../lib/format";
import { toApiUrl } from "../lib/api";
import type { ResultExportItem } from "../lib/types";

function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : formatScore(value);
}

function formatTime(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${value.toFixed(2)}s`;
}

function resolutionText(item: ResultExportItem): string {
  const width = item.resolution?.width;
  const height = item.resolution?.height;
  return width && height ? `${width}x${height}` : "unknown";
}

function readableToken(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  return value.replaceAll("_", " ");
}

function scoreSourceLabel(item: ResultExportItem): string {
  if (item.openaiScoreSource) {
    return readableToken(item.openaiScoreSource);
  }
  if (item.aiScore !== null) {
    return "AI";
  }
  return "rule";
}

export function ResultVideoCard({
  item,
  auditAvailable = false
}: {
  item: ResultExportItem;
  auditAvailable?: boolean;
}) {
  const warnings = item.auditWarnings ?? [];
  const scoreSource = scoreSourceLabel(item);
  const showOverlayStatus = item.type === "short";

  return (
    <article className="rounded-md border border-neutral-300 bg-white p-5 shadow-sm shadow-neutral-200/60">
      <div className="flex min-h-40 flex-col justify-between gap-5">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-neutral-300 bg-neutral-50 px-2 py-1 text-xs font-medium uppercase text-neutral-600">
              {item.type}
            </span>
            <span className="text-sm text-neutral-500">{formatDuration(item.duration)}</span>
            <span className="text-sm text-neutral-500">score {formatNumber(item.finalScore ?? item.score)}</span>
            {item.belowQualityThreshold ? (
              <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-900">
                below threshold
              </span>
            ) : null}
            {item.boundaryRefined ? (
              <span className="rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-900">
                boundary refined
              </span>
            ) : null}
          </div>
          <h2 className="break-words text-lg font-semibold leading-snug text-neutral-950">{item.title}</h2>
          <div className="grid gap-2 text-xs text-neutral-600 sm:grid-cols-2">
            <span>title: {readableToken(item.titleSource)}</span>
            <span>score source: {scoreSource}</span>
            <span>rule {formatNumber(item.ruleScore)}</span>
            <span>AI {formatNumber(item.aiScore)}</span>
            <span>resolution {resolutionText(item)}</span>
            {showOverlayStatus ? (
              <span>
                overlay title: {item.overlayTitleRendered ? "rendered" : item.overlayTitleExpected ? "missing" : "off"}
              </span>
            ) : null}
          </div>
          {warnings.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {warnings.map((warning) => (
                <span
                  key={warning}
                  className="rounded-md border border-red-200 bg-red-50 px-2 py-1 text-xs font-medium text-red-800"
                >
                  {readableToken(warning)}
                </span>
              ))}
            </div>
          ) : !auditAvailable ? (
            <span className="text-xs font-medium text-neutral-500">Audit not available</span>
          ) : (
            <span className="text-xs font-medium text-emerald-700">No audit warnings</span>
          )}
        </div>

        <details className="rounded-md border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-700">
          <summary className="cursor-pointer font-medium text-neutral-900">Details</summary>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            <div>
              <dt className="font-medium text-neutral-500">Range</dt>
              <dd>
                {formatTime(item.refinedStart ?? item.start)} - {formatTime(item.refinedEnd ?? item.end)}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-500">Original range</dt>
              <dd>
                {formatTime(item.originalStart)} - {formatTime(item.originalEnd)}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-500">Selection</dt>
              <dd>{readableToken(item.selectionReason)}</dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-500">Quality warning</dt>
              <dd>{readableToken(item.qualityWarning)}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="font-medium text-neutral-500">Subtitle path</dt>
              <dd className="break-all">{item.subtitlePath ?? "n/a"}</dd>
            </div>
          </dl>
        </details>

        <div className="flex flex-wrap gap-2">
          <a
            className="inline-flex min-h-10 items-center rounded-md bg-neutral-950 px-4 text-sm font-medium text-white"
            href={toApiUrl(item.downloadUrl)}
          >
            Download MP4
          </a>
          <a
            className="inline-flex min-h-10 items-center rounded-md border border-neutral-300 px-4 text-sm font-medium text-neutral-800"
            href={toApiUrl(item.videoUrl)}
            target="_blank"
          >
            Open
          </a>
          {item.metadataUrl ? (
            <a
              className="inline-flex min-h-10 items-center rounded-md border border-neutral-300 px-4 text-sm font-medium text-neutral-800"
              href={toApiUrl(item.metadataUrl)}
              target="_blank"
            >
              Metadata
            </a>
          ) : null}
          {item.subtitleUrl ? (
            <a
              className="inline-flex min-h-10 items-center rounded-md border border-neutral-300 px-4 text-sm font-medium text-neutral-800"
              href={toApiUrl(item.subtitleUrl)}
              target="_blank"
            >
              Subtitle
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}
