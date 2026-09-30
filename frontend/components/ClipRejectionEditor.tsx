"use client";
import { rejectionLabels, type RejectionDraft } from "../lib/clipRejections";

export function ClipRejectionEditor({ label, value, disabled, onChange }: {
  label: string; value: RejectionDraft; disabled: boolean; onChange: (value: RejectionDraft) => void;
}) {
  return <div className="border-b border-neutral-300 bg-white px-4 py-3">
    <p className="text-xs font-semibold">不採用の理由: {rejectionLabels[value.reason]}</p>
    <div className="mt-2 flex flex-wrap gap-1" role="group" aria-label={`${label}の不採用理由`}>
      {(["no_content", "missing_context", "weak_highlight", "other"] as const).map(reason =>
        <button key={reason} type="button" disabled={disabled} aria-pressed={value.reason === reason}
          className={`rounded border px-2 py-1 text-xs disabled:opacity-50 ${value.reason === reason ? "border-blue-700 bg-blue-50 text-blue-800" : "border-neutral-300"}`}
          onClick={() => onChange({ ...value, reason: value.reason === reason ? "unspecified" : reason })}>
          {rejectionLabels[reason]}
        </button>)}
    </div>
    <label className="mt-2 block text-xs text-neutral-600">補足（任意・500文字以内）
      <textarea className="mt-1 w-full rounded border border-neutral-300 p-2 text-sm" rows={2} maxLength={500}
        aria-label={`${label}の不採用の補足`} disabled={disabled} value={value.note}
        onChange={event => onChange({ ...value, note: event.target.value })} />
    </label>
  </div>;
}
