import type { JobStatus } from "../lib/types";

const BASE_STEPS: JobStatus[] = [
  "queued",
  "probing",
  "extracting_audio",
  "transcribing",
  "detecting_scenes",
  "generating_candidates",
  "scoring_candidates",
  "selecting_clips",
  "rendering_normal_clips",
  "rendering_shorts",
  "packaging_zip",
  "completed"
];

const STEP_LABELS: Partial<Record<JobStatus, string>> = {
  queued: "受付",
  probing: "動画確認",
  extracting_audio: "音声抽出",
  transcribing: "文字起こし",
  correcting_subtitles: "AI字幕校正",
  detecting_scenes: "シーン検出",
  generating_candidates: "候補生成",
  scoring_candidates: "候補評価",
  selecting_clips: "clip選定",
  reselecting_clips: "再選定",
  preparing_clip_review: "予定動画準備",
  awaiting_manual_edit: "手動範囲指定",
  awaiting_clip_review: "範囲確認",
  preparing_subtitle_review: "確認動画準備",
  awaiting_subtitle_review: "字幕確認",
  rendering_normal_clips: "通常切り抜き",
  rendering_shorts: "ショート",
  packaging_zip: "ZIP作成",
  completed: "完了"
};

type ProgressTimelineProps = {
  status: JobStatus;
  failureStatus?: JobStatus;
  hasClipPlanReview?: boolean;
  hasSubtitleReview?: boolean;
};

export function ProgressTimeline({
  status,
  failureStatus,
  hasClipPlanReview = false,
  hasSubtitleReview = false
}: ProgressTimelineProps) {
  let steps: JobStatus[] =
    status === "correcting_subtitles"
      ? [
          ...BASE_STEPS.slice(0, BASE_STEPS.indexOf("transcribing") + 1),
          "correcting_subtitles" as const,
          ...BASE_STEPS.slice(BASE_STEPS.indexOf("transcribing") + 1)
        ]
      : BASE_STEPS;
  if (
    hasClipPlanReview ||
    status === "reselecting_clips" ||
    status === "preparing_clip_review" ||
    status === "awaiting_manual_edit" ||
    status === "awaiting_clip_review"
  ) {
    const renderIndex = steps.indexOf("rendering_normal_clips");
    const clipReviewSteps: JobStatus[] =
      status === "awaiting_manual_edit"
        ? ["awaiting_manual_edit"]
        : status === "reselecting_clips"
        ? ["reselecting_clips", "preparing_clip_review", "awaiting_clip_review"]
        : ["preparing_clip_review", "awaiting_clip_review"];
    steps = [
      ...steps.slice(0, renderIndex),
      ...clipReviewSteps,
      ...steps.slice(renderIndex)
    ];
  }
  if (
    hasSubtitleReview ||
    status === "preparing_subtitle_review" ||
    status === "awaiting_subtitle_review"
  ) {
    const renderIndex = steps.indexOf("rendering_normal_clips");
    steps = [
      ...steps.slice(0, renderIndex),
      "preparing_subtitle_review",
      "awaiting_subtitle_review",
      ...steps.slice(renderIndex)
    ];
  }
  const visualStatus = status === "failed" && failureStatus ? failureStatus : status;
  const activeIndex = steps.indexOf(visualStatus);

  return (
    <section className="rounded-md border border-neutral-300 bg-white p-5">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {steps.map((step, index) => {
          const isDone = status === "completed" || (activeIndex >= 0 && index < activeIndex);
          const isCurrent = step === visualStatus;
          return (
            <div
              key={step}
              className={`flex min-h-11 items-center gap-3 rounded-md border px-3 ${
                isCurrent
                  ? status === "failed"
                    ? "border-red-300 bg-red-50 text-red-800"
                    : "border-neutral-950 bg-neutral-950 text-white"
                  : isDone
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-neutral-200 bg-neutral-50 text-neutral-500"
              }`}
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs">
                {isDone ? "OK" : index + 1}
              </span>
              <span className="truncate text-sm font-medium">
                {STEP_LABELS[step] ?? step.replaceAll("_", " ")}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
