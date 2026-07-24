import type { JobStatus } from "../lib/types";

const STATUS_STYLES: Record<JobStatus, string> = {
  uploaded: "border-neutral-300 bg-neutral-100 text-neutral-700",
  queued: "border-neutral-300 bg-neutral-100 text-neutral-700",
  probing: "border-sky-200 bg-sky-50 text-sky-800",
  extracting_audio: "border-sky-200 bg-sky-50 text-sky-800",
  transcribing: "border-sky-200 bg-sky-50 text-sky-800",
  correcting_subtitles: "border-sky-200 bg-sky-50 text-sky-800",
  detecting_scenes: "border-sky-200 bg-sky-50 text-sky-800",
  generating_candidates: "border-blue-200 bg-blue-50 text-blue-800",
  scoring_candidates: "border-blue-200 bg-blue-50 text-blue-800",
  selecting_clips: "border-blue-200 bg-blue-50 text-blue-800",
  preparing_subtitle_review: "border-sky-200 bg-sky-50 text-sky-800",
  awaiting_subtitle_review: "border-sky-300 bg-sky-50 text-sky-900",
  rendering_normal_clips: "border-amber-200 bg-amber-50 text-amber-800",
  rendering_shorts: "border-amber-200 bg-amber-50 text-amber-800",
  packaging_zip: "border-emerald-200 bg-emerald-50 text-emerald-800",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-800",
  failed: "border-red-200 bg-red-50 text-red-800"
};

const STATUS_LABELS: Partial<Record<JobStatus, string>> = {
  preparing_subtitle_review: "字幕確認動画を準備中",
  awaiting_subtitle_review: "字幕確認待ち",
  rendering_normal_clips: "通常切り抜き書き出し中",
  rendering_shorts: "ショート書き出し中",
  packaging_zip: "ZIP作成中",
  completed: "完了",
  failed: "失敗"
};

export function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-md border px-2.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status] ?? status.replaceAll("_", " ")}
    </span>
  );
}
