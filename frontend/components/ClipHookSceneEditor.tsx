"use client";

import { useMemo, useState } from "react";

type HookSceneEditableClip = {
  start: number;
  end: number;
  duration: number;
  hookSceneStart: number | null;
  hookSceneEnd: number | null;
};

type ClipHookSceneEditorProps = {
  clip: HookSceneEditableClip;
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

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
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
  const clipDuration = Math.max(0, clip.end - clip.start);
  const initialStart = Math.max(
    0,
    (clip.hookSceneStart ?? clip.start) - clip.start
  );
  const initialEnd = Math.max(
    0,
    (clip.hookSceneEnd ?? Math.min(clip.end, clip.start + 2)) - clip.start
  );
  const [startParts, setStartParts] = useState(() =>
    splitTime(initialStart)
  );
  const [endParts, setEndParts] = useState(() =>
    splitTime(initialEnd)
  );
  const start = combineTime(startParts);
  const end = combineTime(endParts);
  const sourceStart = start === null ? null : clip.start + start;
  const sourceEnd = end === null ? null : clip.start + end;
  const playheadClipTime = clamp(
    playheadSourceTime - clip.start,
    0,
    clipDuration
  );
  const hasSavedHook =
    clip.hookSceneStart !== null && clip.hookSceneEnd !== null;
  const duration = start !== null && end !== null ? end - start : null;
  const projectedDuration =
    duration !== null && duration > 0 ? clip.duration + duration : null;
  const clipAlreadyExceedsMaximum =
    clip.duration > shortMaxDuration + 0.001;
  const validation = useMemo(() => {
    if (start === null || end === null) {
      return "分と秒を正しく入力してください";
    }
    if (start < -0.001 || end > clipDuration + 0.001) {
      return `clip内 0:00.0〜${formatTime(clipDuration)}で指定してください`;
    }
    if (duration === null || duration < 0.5 || duration > 3) {
      return "冒頭へ複製する場面は0.5〜3秒にしてください";
    }
    if (
      !clipAlreadyExceedsMaximum &&
      clip.duration + duration > shortMaxDuration + 0.001
    ) {
      return `完成尺が上限 ${formatTime(shortMaxDuration)} を超えます`;
    }
    return null;
  }, [
    clip.duration,
    clipAlreadyExceedsMaximum,
    clipDuration,
    duration,
    end,
    shortMaxDuration,
    start
  ]);
  const changed =
    sourceStart !== null &&
    sourceEnd !== null &&
    (!hasSavedHook ||
      Math.abs(sourceStart - (clip.hookSceneStart ?? 0)) >= 0.0005 ||
      Math.abs(sourceEnd - (clip.hookSceneEnd ?? 0)) >= 0.0005);

  function setRange(rangeStart: number, length: number) {
    const boundedStart = Math.min(
      Math.max(rangeStart, 0),
      Math.max(0, clipDuration - length)
    );
    const boundedEnd = Math.min(clipDuration, boundedStart + length);
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
            時間はメイン動画・字幕と同じくclip先頭を0:00とします。元動画時刻も併記します。
          </p>
        </div>
        <span className="border border-amber-300 bg-white px-2 py-1 text-xs font-semibold text-amber-900">
          {hasSavedHook ? "設定済み" : "未設定"}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs leading-5 text-neutral-700">
          <span className="font-semibold">
            現在位置（clip内）: {formatTime(playheadClipTime)}
          </span>
          <span className="ml-2 text-neutral-500">
            元動画: {formatTime(playheadSourceTime)}
          </span>
        </span>
        {HOOK_LENGTHS.map((seconds) => (
          <button
            className="min-h-9 border border-neutral-300 bg-white px-3 text-xs font-semibold text-neutral-900 disabled:opacity-50"
            disabled={disabled}
            key={seconds}
            type="button"
            onClick={() => setRange(playheadClipTime, seconds)}
          >
            ここから{seconds}秒
          </button>
        ))}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <HookTimeInput
          disabled={disabled}
          label="clip内の開始"
          parts={startParts}
          onChange={setStartParts}
        />
        <HookTimeInput
          disabled={disabled}
          label="clip内の終了"
          parts={endParts}
          onChange={setEndParts}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-amber-200 pt-3">
        <div className="text-xs leading-5 text-neutral-700">
          <p>
            clip内: {start === null ? "--" : formatTime(start)} -{" "}
            {end === null ? "--" : formatTime(end)}
          </p>
          <p className="text-neutral-500">
            元動画: {sourceStart === null ? "--" : formatTime(sourceStart)} -{" "}
            {sourceEnd === null ? "--" : formatTime(sourceEnd)}
          </p>
          <p className="font-semibold text-neutral-950">
            完成予定:{" "}
            {projectedDuration === null ? "--" : formatTime(projectedDuration)}
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
              if (sourceStart !== null && sourceEnd !== null && !validation) {
                onSave(sourceStart, sourceEnd);
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
        <>
          {clipAlreadyExceedsMaximum && projectedDuration !== null ? (
            <p className="mt-2 text-xs font-medium text-amber-800">
              元のclipが上限 {formatTime(shortMaxDuration)} を超えています。
              追加後 {formatTime(projectedDuration)} で保存します。
            </p>
          ) : null}
          <p className="mt-2 text-xs text-neutral-500">
            対象ショートの軽量プレビューだけを作り直します。OpenAI APIは使いません。
          </p>
        </>
      )}
    </section>
  );
}
