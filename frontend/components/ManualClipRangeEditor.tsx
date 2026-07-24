"use client";

import {
  allRequestedOutputsUseManualTime,
  clearManualRanges,
  isManualTimeMode,
  manualRangeRows,
  updateManualRangeTime
} from "../lib/manualClipRanges";
import type {
  ClipOutputType,
  TimeBoundary,
  TimeUnit
} from "../lib/manualClipRanges";
import type { ClipSettings, ClipTimeRange } from "../lib/types";

type ManualClipRangeEditorProps = {
  settings: ClipSettings;
  disabled?: boolean;
  onChange: (settings: ClipSettings) => void;
};

function timePart(
  range: ClipTimeRange,
  boundary: TimeBoundary,
  unit: TimeUnit
): number | "" {
  const total = range[boundary];
  if (total === null) {
    return "";
  }
  return unit === "minutes" ? Math.floor(total / 60) : Math.floor(total % 60);
}

function rangeDuration(range: ClipTimeRange): string | null {
  if (range.startSeconds === null || range.endSeconds === null) {
    return null;
  }
  const duration = range.endSeconds - range.startSeconds;
  if (duration <= 0) {
    return null;
  }
  const minutes = Math.floor(duration / 60);
  const seconds = Math.floor(duration % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function ManualRangeGroup({
  disabled,
  settings,
  type,
  onChange
}: ManualClipRangeEditorProps & { type: ClipOutputType }) {
  const count = type === "normal" ? settings.normalClipCount : settings.shortCount;
  if (count === 0) {
    return null;
  }

  const isManual = isManualTimeMode(settings, type);
  const rows = manualRangeRows(settings, type);
  const label = type === "normal" ? "通常切り抜き" : "ショート";

  function emit(next: ClipSettings) {
    onChange(
      allRequestedOutputsUseManualTime(next)
        ? { ...next, useOpenAIScoring: false }
        : next
    );
  }

  function update(
    index: number,
    boundary: TimeBoundary,
    unit: TimeUnit,
    rawValue: string
  ) {
    emit(updateManualRangeTime(settings, type, index, boundary, unit, rawValue));
  }

  return (
    <section className="border border-neutral-300 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-neutral-900">{label}</h4>
        <span
          className={`border px-2 py-1 text-xs font-semibold ${
            isManual
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : "border-neutral-300 bg-neutral-50 text-neutral-600"
          }`}
        >
          {isManual ? "時間指定モード" : "おすすめ自動"}
        </span>
      </div>

      <div className="mt-3 space-y-2">
        {rows.map((range, index) => {
          const duration = rangeDuration(range);
          return (
            <div
              className="grid gap-2 border-t border-neutral-200 pt-3 sm:grid-cols-[5rem_1fr_1fr_auto]"
              key={`${type}-${index}`}
            >
              <span className="pt-2 text-sm font-medium text-neutral-700">
                {label} {index + 1}
              </span>
              <div className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-1">
                <input
                  aria-label={`${label}${index + 1} 開始 分`}
                  className="min-h-10 min-w-0 border border-neutral-300 px-2 text-sm"
                  disabled={disabled}
                  min={0}
                  placeholder="分"
                  type="number"
                  value={timePart(range, "startSeconds", "minutes")}
                  onChange={(event) =>
                    update(index, "startSeconds", "minutes", event.target.value)
                  }
                />
                <span className="text-xs text-neutral-500">分</span>
                <input
                  aria-label={`${label}${index + 1} 開始 秒`}
                  className="min-h-10 min-w-0 border border-neutral-300 px-2 text-sm"
                  disabled={disabled}
                  max={59}
                  min={0}
                  placeholder="秒"
                  type="number"
                  value={timePart(range, "startSeconds", "seconds")}
                  onChange={(event) =>
                    update(index, "startSeconds", "seconds", event.target.value)
                  }
                />
                <span className="text-xs text-neutral-500">秒から</span>
              </div>
              <div className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-1">
                <input
                  aria-label={`${label}${index + 1} 終了 分`}
                  className="min-h-10 min-w-0 border border-neutral-300 px-2 text-sm"
                  disabled={disabled}
                  min={0}
                  placeholder="分"
                  type="number"
                  value={timePart(range, "endSeconds", "minutes")}
                  onChange={(event) =>
                    update(index, "endSeconds", "minutes", event.target.value)
                  }
                />
                <span className="text-xs text-neutral-500">分</span>
                <input
                  aria-label={`${label}${index + 1} 終了 秒`}
                  className="min-h-10 min-w-0 border border-neutral-300 px-2 text-sm"
                  disabled={disabled}
                  max={59}
                  min={0}
                  placeholder="秒"
                  type="number"
                  value={timePart(range, "endSeconds", "seconds")}
                  onChange={(event) =>
                    update(index, "endSeconds", "seconds", event.target.value)
                  }
                />
                <span className="text-xs text-neutral-500">秒まで</span>
              </div>
              <span className="min-w-16 pt-2 text-right text-xs text-neutral-500">
                {duration ? `長さ ${duration}` : "未入力"}
              </span>
            </div>
          );
        })}
      </div>

      {isManual ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-200 pt-3">
          <p className="text-xs leading-5 text-amber-900">
            この種類ではおすすめ・AI選定・境界の自動調整を使用しません。
          </p>
          <button
            className="min-h-9 border border-neutral-400 bg-white px-3 text-xs font-semibold text-neutral-800"
            disabled={disabled}
            type="button"
            onClick={() => emit(clearManualRanges(settings, type))}
          >
            時間指定をクリア
          </button>
        </div>
      ) : null}
    </section>
  );
}

export function ManualClipRangeEditor({
  settings,
  disabled = false,
  onChange
}: ManualClipRangeEditorProps) {
  return (
    <section className="border-y border-neutral-200 py-5 md:col-span-2">
      <h3 className="text-sm font-semibold text-neutral-900">切り抜く時間を指定（任意）</h3>
      <p className="mt-2 text-xs leading-5 text-neutral-600">
        空欄ならおすすめから自動選定します。どれか入力すると時間指定モードになり、
        表示されている本数すべての開始・終了時間が必要です。
      </p>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <ManualRangeGroup
          disabled={disabled}
          settings={settings}
          type="normal"
          onChange={onChange}
        />
        <ManualRangeGroup
          disabled={disabled}
          settings={settings}
          type="short"
          onChange={onChange}
        />
      </div>
    </section>
  );
}
