import type { JobStatus } from "../lib/types";

const STEPS: JobStatus[] = [
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

export function ProgressTimeline({ status }: { status: JobStatus }) {
  const activeIndex = STEPS.indexOf(status);

  return (
    <section className="rounded-md border border-neutral-300 bg-white p-5">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {STEPS.map((step, index) => {
          const isDone = status === "completed" || (activeIndex >= 0 && index < activeIndex);
          const isCurrent = step === status;
          return (
            <div
              key={step}
              className={`flex min-h-11 items-center gap-3 rounded-md border px-3 ${
                isCurrent
                  ? "border-neutral-950 bg-neutral-950 text-white"
                  : isDone
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-neutral-200 bg-neutral-50 text-neutral-500"
              }`}
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs">
                {isDone ? "OK" : index + 1}
              </span>
              <span className="truncate text-sm font-medium">{step.replaceAll("_", " ")}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
