"use client";

import { useEffect, useMemo, useState } from "react";

import type { ClipPlanClip } from "../lib/types";

type ClipBoundaryEditorProps = {
  clip: ClipPlanClip;
  sourceDuration: number | null;
  disabled?: boolean;
  saving?: boolean;
  onDraftChange?: (draft: ClipBoundaryDraft | null) => void;
  onSave: (start: number, end: number) => void;
};

export type ClipBoundaryDraft = {
  clipId: string;
  start: number;
  end: number;
};

type TimeParts = {
  minutes: string;
  seconds: string;
};

const QUICK_ADJUSTMENTS = [5, 15, 30, 60] as const;

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
  if (parts.minutes.trim() === "" || parts.seconds.trim() === "") {
    return null;
  }
  const minutes = Number(parts.minutes);
  const seconds = Number(parts.seconds);
  if (
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
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  const secondText = seconds.toFixed(1).padStart(4, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${secondText}`
    : `${minutes}:${secondText}`;
}

function BoundaryTimeInput({
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
    <div>
      <p className="text-xs font-semibold text-neutral-700">{label}</p>
      <div className="mt-2 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] items-center gap-2">
        <input
          aria-label={`${label} 分`}
          className="min-h-10 min-w-0 border border-neutral-300 px-2 text-sm tabular-nums"
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
          className="min-h-10 min-w-0 border border-neutral-300 px-2 text-sm tabular-nums"
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
      </div>
    </div>
  );
}

export function ClipBoundaryEditor({
  clip,
  sourceDuration,
  disabled = false,
  saving = false,
  onDraftChange,
  onSave
}: ClipBoundaryEditorProps) {
  const recommendedStart = clip.recommendedStart ?? clip.start;
  const recommendedEnd = clip.recommendedEnd ?? clip.end;
  const [startParts, setStartParts] = useState(() => splitTime(clip.start));
  const [endParts, setEndParts] = useState(() => splitTime(clip.end));
  const start = combineTime(startParts);
  const end = combineTime(endParts);

  const validation = useMemo(() => {
    if (start === null || end === null) {
      return "分と秒を正しく入力してください";
    }
    if (end <= start) {
      return "終了は開始より後にしてください";
    }
    if (end - start < 1) {
      return "切り抜き範囲は1秒以上にしてください";
    }
    if (sourceDuration !== null && end > sourceDuration + 0.001) {
      return `元動画の長さ ${formatTime(sourceDuration)} を超えています`;
    }
    return null;
  }, [end, sourceDuration, start]);
  const changed =
    start !== null &&
    end !== null &&
    (Math.abs(start - clip.start) >= 0.0005 ||
      Math.abs(end - clip.end) >= 0.0005);
  const draftDuration =
    start !== null && end !== null && end > start ? end - start : null;

  useEffect(() => {
    if (!onDraftChange) {
      return;
    }
    if (start === null || end === null || validation !== null) {
      onDraftChange(null);
      return;
    }
    onDraftChange({
      clipId: clip.id,
      start,
      end
    });
  }, [clip.id, end, onDraftChange, start, validation]);

  function replaceStart(value: number) {
    setStartParts(splitTime(Math.max(0, value)));
  }

  function replaceEnd(value: number) {
    const bounded =
      sourceDuration === null ? value : Math.min(value, sourceDuration);
    setEndParts(splitTime(Math.max(0, bounded)));
  }

  function resetRecommended() {
    replaceStart(recommendedStart);
    replaceEnd(recommendedEnd);
  }

  return (
    <section className="border-b border-neutral-300 bg-blue-50 px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-neutral-950">
            このclipの開始・終了を調整
          </h3>
          <p className="mt-1 text-xs leading-5 text-neutral-600">
            分・秒を直接変更するか、前後の追加ボタンを使います。選ばれた場面は維持され、字幕生成も行いません。
          </p>
        </div>
        {clip.manuallyAdjusted ? (
          <span className="border border-blue-300 bg-white px-2 py-1 text-xs font-semibold text-blue-800">
            手動調整済み
          </span>
        ) : null}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <BoundaryTimeInput
            disabled={disabled}
            label="開始時刻"
            parts={startParts}
            onChange={setStartParts}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {QUICK_ADJUSTMENTS.map((seconds) => (
              <button
                className="min-h-8 border border-neutral-300 bg-white px-2 text-xs font-medium text-neutral-800 disabled:opacity-50"
                disabled={disabled || start === null || start <= 0}
                key={`before-${seconds}`}
                type="button"
                onClick={() => replaceStart((start ?? clip.start) - seconds)}
              >
                前に+{seconds === 60 ? "1分" : `${seconds}秒`}
              </button>
            ))}
          </div>
        </div>

        <div>
          <BoundaryTimeInput
            disabled={disabled}
            label="終了時刻"
            parts={endParts}
            onChange={setEndParts}
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {QUICK_ADJUSTMENTS.map((seconds) => (
              <button
                className="min-h-8 border border-neutral-300 bg-white px-2 text-xs font-medium text-neutral-800 disabled:opacity-50"
                disabled={
                  disabled ||
                  end === null ||
                  (sourceDuration !== null && end >= sourceDuration)
                }
                key={`after-${seconds}`}
                type="button"
                onClick={() => replaceEnd((end ?? clip.end) + seconds)}
              >
                後に+{seconds === 60 ? "1分" : `${seconds}秒`}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 border-t border-blue-200 pt-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-xs leading-5 text-neutral-700">
            <p>
              自動選定: {formatTime(recommendedStart)} -{" "}
              {formatTime(recommendedEnd)}
            </p>
            <p className="font-semibold text-neutral-950">
              変更後: {start === null ? "--" : formatTime(start)} -{" "}
              {end === null ? "--" : formatTime(end)}
              {draftDuration === null
                ? ""
                : `（長さ ${formatTime(draftDuration)}）`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="min-h-10 border border-neutral-300 bg-white px-3 text-xs font-semibold text-neutral-800 disabled:opacity-50"
              disabled={disabled}
              type="button"
              onClick={resetRecommended}
            >
              自動選定の範囲へ戻す
            </button>
            <button
              className="min-h-10 bg-blue-700 px-4 text-xs font-semibold text-white disabled:bg-neutral-300"
              disabled={disabled || !changed || validation !== null}
              type="button"
              onClick={() => {
                if (start !== null && end !== null && !validation) {
                  onSave(start, end);
                }
              }}
            >
              {saving ? "プレビュー更新中" : "この範囲でプレビュー更新"}
            </button>
          </div>
        </div>
        {validation ? (
          <p className="mt-2 text-xs font-medium text-red-700">{validation}</p>
        ) : (
          <p className="mt-2 text-xs text-neutral-500">
            対象clip 1本の軽量動画だけを作り直します。OpenAI API料金は発生しません。
          </p>
        )}
      </div>
    </section>
  );
}
