import { formatDuration, formatScore } from "../lib/format";
import { toApiUrl } from "../lib/api";
import type { ResultExportItem } from "../lib/types";

export function ResultVideoCard({ item }: { item: ResultExportItem }) {
  return (
    <article className="rounded-md border border-neutral-300 bg-white p-5">
      <div className="flex min-h-40 flex-col justify-between gap-5">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-neutral-300 bg-neutral-50 px-2 py-1 text-xs font-medium uppercase text-neutral-600">
              {item.type}
            </span>
            <span className="text-sm text-neutral-500">{formatDuration(item.duration)}</span>
            <span className="text-sm text-neutral-500">score {formatScore(item.score)}</span>
          </div>
          <h2 className="text-lg font-semibold text-neutral-950">{item.title}</h2>
        </div>

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
        </div>
      </div>
    </article>
  );
}
