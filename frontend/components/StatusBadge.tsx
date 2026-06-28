import type { JobStatus } from "../lib/types";

const STATUS_STYLES: Record<JobStatus, string> = {
  uploaded: "border-neutral-300 bg-neutral-100 text-neutral-700",
  queued: "border-neutral-300 bg-neutral-100 text-neutral-700",
  probing: "border-sky-200 bg-sky-50 text-sky-800",
  extracting_audio: "border-sky-200 bg-sky-50 text-sky-800",
  transcribing: "border-sky-200 bg-sky-50 text-sky-800",
  detecting_scenes: "border-sky-200 bg-sky-50 text-sky-800",
  generating_candidates: "border-blue-200 bg-blue-50 text-blue-800",
  scoring_candidates: "border-blue-200 bg-blue-50 text-blue-800",
  selecting_clips: "border-blue-200 bg-blue-50 text-blue-800",
  rendering_normal_clips: "border-amber-200 bg-amber-50 text-amber-800",
  rendering_shorts: "border-amber-200 bg-amber-50 text-amber-800",
  packaging_zip: "border-emerald-200 bg-emerald-50 text-emerald-800",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-800",
  failed: "border-red-200 bg-red-50 text-red-800"
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-md border px-2.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}
