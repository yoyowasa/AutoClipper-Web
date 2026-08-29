"use client";

import { useEffect, useRef, useState } from "react";

import {
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
  workspace?: boolean;
  revealKey?: number;
  onChange: (settings: ClipSettings) => void;
};

function firstInvalidFieldLabel(settings: ClipSettings): string | null {
  for (const type of ["normal", "short"] as const) {
    if (!isManualTimeMode(settings, type)) {
      continue;
    }
    const label = type === "normal" ? "通常切り抜き" : "ショート";
    const rows = manualRangeRows(settings, type);
    const seen = new Set<string>();
    for (const [index, range] of rows.entries()) {
      if (range.startSeconds === null) {
        return `${label}${index + 1} 開始 分`;
      }
      if (range.endSeconds === null || range.endSeconds <= range.startSeconds) {
        return `${label}${index + 1} 終了 分`;
      }
      const key = `${range.startSeconds}:${range.endSeconds}`;
      if (seen.has(key)) {
        return `${label}${index + 1} 開始 分`;
      }
      seen.add(key);
    }
  }
  return null;
}

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
    const hasManualRanges =
      next.normalClipTimeRanges.length > 0 || next.shortClipTimeRanges.length > 0;
    onChange(
      hasManualRanges
        ? {
            ...next,
            initialSelectionProvider: "legacy",
            useOpenAIScoring: false,
            ensureSelectedOpenAIScored: false
          }
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
  workspace = false,
  revealKey = 0,
  onChange
}: ManualClipRangeEditorProps) {
  const manualActive =
    isManualTimeMode(settings, "normal") || isManualTimeMode(settings, "short");
  const [isOpen, setIsOpen] = useState(manualActive);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const lastHandledRevealKey = useRef(0);

  useEffect(() => {
    if (
      !workspace ||
      revealKey === 0 ||
      lastHandledRevealKey.current === revealKey
    ) {
      return;
    }
    lastHandledRevealKey.current = revealKey;
    let focusFrame = 0;
    const openFrame = requestAnimationFrame(() => {
      setIsOpen(true);
      focusFrame = requestAnimationFrame(() => {
        const targetLabel = firstInvalidFieldLabel(settings);
        const inputs = detailsRef.current?.querySelectorAll<HTMLInputElement>("input");
        const target = targetLabel
          ? Array.from(inputs ?? []).find(
              (input) => input.getAttribute("aria-label") === targetLabel
            )
          : null;
        target?.focus();
      });
    });
    return () => {
      cancelAnimationFrame(openFrame);
      cancelAnimationFrame(focusFrame);
    };
  }, [revealKey, settings, workspace]);
  const editorContent = (
    <>
      <p className="text-xs leading-5 text-neutral-600">
        空欄ならおすすめから自動選定します。どれか入力すると時間指定モードになり、
        表示されている本数すべての開始・終了時間が必要です。
      </p>
      <div
        className={`mt-3 grid gap-4 ${workspace ? "2xl:grid-cols-2" : "xl:grid-cols-2"}`}
      >
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
    </>
  );

  if (workspace) {
    return (
      <details
        className="md:col-span-2 2xl:col-span-4"
        data-testid="manual-range-details"
        open={isOpen}
        ref={detailsRef}
        onToggle={(event) => setIsOpen(event.currentTarget.open)}
      >
        <summary className="cursor-pointer text-sm font-semibold text-neutral-900">
          <span className="ml-1 inline-flex w-[calc(100%_-_1.25rem)] items-center justify-between gap-3 align-middle">
            <span>切り抜く時間を指定（任意）</span>
            <span className="text-xs font-normal text-neutral-500">
              {manualActive ? "時間指定中" : "自動選定"}
            </span>
          </span>
        </summary>
        <div className="border-x border-b border-neutral-200 p-3">{editorContent}</div>
      </details>
    );
  }

  return (
    <section className="border-y border-neutral-200 py-5 md:col-span-2">
      <h3 className="text-sm font-semibold text-neutral-900">切り抜く時間を指定（任意）</h3>
      <div className="mt-2">{editorContent}</div>
    </section>
  );
}
