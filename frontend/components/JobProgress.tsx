import type { JobStatusResponse } from "../lib/types";
import { StatusBadge } from "./StatusBadge";

export function JobProgress({ job }: { job: JobStatusResponse }) {
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
            <p className="text-sm font-medium text-neutral-700">{job.currentStep}</p>
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
      </div>
    </section>
  );
}
