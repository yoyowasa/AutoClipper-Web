import type { JobStatus, JobStatusDetails } from "../lib/types";
import { initialSelectionStatusDisplay } from "../lib/initialSelectionStatus";

const toneClass = {
  neutral: "border-neutral-300 bg-neutral-50 text-neutral-800",
  info: "border-sky-300 bg-sky-50 text-sky-900",
  success: "border-emerald-300 bg-emerald-50 text-emerald-900",
  warning: "border-amber-400 bg-amber-50 text-amber-950",
  danger: "border-red-300 bg-red-50 text-red-900"
} as const;

export function InitialSelectionStatusBanner({
  details,
  jobStatus,
  currentStep,
  className = ""
}: {
  details: JobStatusDetails;
  jobStatus?: JobStatus;
  currentStep?: string;
  className?: string;
}) {
  const display = initialSelectionStatusDisplay(details, jobStatus, currentStep);
  if (!display) {
    return null;
  }

  return (
    <div
      className={`border px-4 py-3 text-sm ${toneClass[display.tone]} ${className}`.trim()}
      data-initial-selection-state={display.state}
      data-testid="codex-initial-selection-status"
      role={
        display.state === "failed" ||
        display.state === "fallback" ||
        display.state === "unknown"
          ? "alert"
          : "status"
      }
    >
      <p className="font-semibold">{display.title}</p>
      <p className="mt-1 leading-5">{display.description}</p>
      {display.detail ? (
        <p className="mt-1 break-words text-xs opacity-80">詳細: {display.detail}</p>
      ) : null}
    </div>
  );
}
