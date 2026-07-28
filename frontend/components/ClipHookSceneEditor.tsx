"use client";

import { useMemo, useState } from "react";

import type { ClipPlanClip } from "../lib/types";

type ClipHookSceneEditorProps = {
  clip: ClipPlanClip;
  disabled?: boolean;
  saving?: boolean;
  playheadSourceTime: number;
  shortMaxDuration: number;
  onSave: (start: number | null, end: number | null) => void;
};

type TimeParts = {
  minutes: string;
  seconds: string;
};

const HOOK_LENGTHS = [1, 2, 3] as const;

function splitTime(value: number): TimeParts {
  const safe = Math.max(0, value);
  const minutes = Math.floor(safe / 60);
  const seconds = Math.round((safe - minutes * 60) * 1000) / 1000;
  return {
    minutes: String(minutes),
    seconds: String(seconds)
  };
}

function combineTime(parts: TimeParts): number | null {
  const minutes = Number(parts.minutes);
  const seconds = Number(parts.seconds);
  if (
    parts.minutes.trim() === "" ||
    parts.seconds.trim() === "" ||
    !Number.isFinite(minutes) ||
    !Number.isFinite(seconds) ||
    minutes < 0 ||
    seconds < 0 ||
    seconds >= 60
  ) {
    return null;
  }
  return Math.round((minutes * 60 + seconds) * 1000) / 1000;
}

function formatTime(value: number): string {
  const safe = Math.max(0, value);
  const minutes = Math.floor(safe / 60);
  const seconds = safe - minutes * 60;
  return `${minutes}:${seconds.toFixed(1).padStart(4, "0")}`;
}

function HookTimeInput({
  disabled,
  label,
  parts,
  onChange
}: {
  disabled: boolean;
  label: string;
  parts: TimeParts;
  onChange: (parts: TimeParts) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-neutral-700">{label}</span>
      <span className="mt-2 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] items-center gap-2">
        <input
          aria-label={`${label} 分`}
          className="min-h-10 min-w-0 border border-neutral-300 bg-white px-2 text-sm tabular-nums"
          disabled={disabled}
          min={0}
          step={1}
          type="number"
          value={parts.minutes}
          onChange={(event) =>
            onChange({ ...parts, minutes: event.target.value })
          }
        />
        <span className="text-xs text-neutral-500">分</span>
        <input
          aria-label={`${label} 秒`}
          className="min-h-10 min-w-0 border border-neutral-300 bg-white px-2 text-sm tabular-nums"
          disabled={disabled}
          max={59.999}
          min={0}
          step={0.001}
          type="number"
          value={parts.seconds}
          onChange={(event) =>
            onChange({ ...parts, seconds: event.target.value })
          }
        />
        <span className="text-xs text-neutral-500">秒</span>
      </span>
    </label>
  );
}

export function ClipHookSceneEditor({
  clip,
  disabled = false,
  saving = false,
  playheadSourceTime,
  shortMaxDuration,
  onSave
}: ClipHookSceneEditorProps) {
  const [startParts, setStartParts] = useState(() =>
    splitTime(clip.hookSceneStart ?? clip.start)
  );
  const [endParts, setEndParts] = useState(() =>
    splitTime(clip.hookSceneEnd ?? Math.min(clip.end, clip.start + 2))
  );
  const start = combineTime(startParts);
  const end = combineTime(endParts);
  const hasSavedHook =
    clip.hookSceneStart !== null && clip.hookSceneEnd !== null;
  const duration = start !== null && end !== null ? end - start : null;
  const validation = useMemo(() => {
    if (start === null || end === null) {
      return "分と秒を正しく入力してください";
    }
    if (start < clip.start - 0.001 || end > clip.end + 0.001) {
      return "選択したショートの範囲内で指定してください";
    }
    if (duration === null || duration < 0.5 || duration > 3) {
      return "冒頭へ複製する場面は0.5〜3秒にしてください";
    }
    if (clip.duration + duration > shortMaxDuration + 0.001) {
      return `完成尺が上限 ${formatTime(shortMaxDuration)} を超えます`;
    }
    return null;
  }, [clip.duration, clip.end, clip.start, duration, end, shortMaxDuration, start]);
  const changed =
    start !== null &&
    end !== null &&
    (!hasSavedHook ||
      Math.abs(start - (clip.hookSceneStart ?? 0)) >= 0.0005 ||
      Math.abs(end - (clip.hookSceneEnd ?? 0)) >= 0.0005);

  function setRange(rangeStart: number, length: number) {
    const boundedStart = Math.min(
      Math.max(rangeStart, clip.start),
      Math.max(clip.start, clip.end - length)
    );
    const boundedEnd = Math.min(clip.end, boundedStart + length);
    setStartParts(splitTime(boundedStart));
    setEndParts(splitTime(boundedEnd));
  }

  return (
    <section className="border-b border-neutral-300 bg-amber-50 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-neutral-950">
            冒頭へ見せ場を複製
          </h3>
          <p className="mt-1 text-xs leading-5 text-neutral-600">
            指定場面をショートの先頭へ追加します。元の場面は本編にも残ります。
          </p>
        </div>
        <span className="border border-amber-300 bg-white px-2 py-1 text-xs font-semibold text-amber-900">
          {hasSavedHook ? "設定済み" : "未設定"}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-neutral-700">
          現在位置: {formatTime(playheadSourceTime)}
        </span>
        {HOOK_LENGTHS.map((seconds) => (
          <button
            className="min-h-9 border border-neutral-300 bg-white px-3 text-xs font-semibold text-neutral-900 disabled:opacity-50"
            disabled={disabled}
            key={seconds}
            type="button"
            onClick={() => setRange(playheadSourceTime, seconds)}
          >
            ここから{seconds}秒
          </button>
        ))}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <HookTimeInput
          disabled={disabled}
          label="場面の開始"
          parts={startParts}
          onChange={setStartParts}
        />
        <HookTimeInput
          disabled={disabled}
          label="場面の終了"
          parts={endParts}
          onChange={setEndParts}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-amber-200 pt-3">
        <div className="text-xs leading-5 text-neutral-700">
          <p>
            複製場面: {start === null ? "--" : formatTime(start)} -{" "}
            {end === null ? "--" : formatTime(end)}
          </p>
          <p className="font-semibold text-neutral-950">
            完成予定:{" "}
            {duration !== null && duration > 0
              ? formatTime(clip.duration + duration)
              : "--"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {hasSavedHook ? (
            <button
              className="min-h-10 border border-neutral-300 bg-white px-3 text-xs font-semibold text-neutral-800 disabled:opacity-50"
              disabled={disabled}
              type="button"
              onClick={() => onSave(null, null)}
            >
              冒頭複製を解除
            </button>
          ) : null}
          <button
            className="min-h-10 bg-amber-600 px-4 text-xs font-semibold text-white disabled:bg-neutral-300"
            disabled={disabled || !changed || validation !== null}
            type="button"
            onClick={() => {
              if (start !== null && end !== null && !validation) {
                onSave(start, end);
              }
            }}
          >
            {saving ? "プレビュー更新中" : "この場面を冒頭へ追加"}
          </button>
        </div>
      </div>
      {validation ? (
        <p className="mt-2 text-xs font-medium text-red-700">{validation}</p>
      ) : (
        <p className="mt-2 text-xs text-neutral-500">
          対象ショートの軽量プレビューだけを作り直します。OpenAI APIは使いません。
        </p>
      )}
    </section>
  );
}
