"use client";

import { useState } from "react";

import type { SubtitleReviewConvertToShortRequest } from "../lib/types";

type Props = {
  busy: boolean;
  clipDurationSeconds: number;
  currentPositionSeconds: number;
  disabled: boolean;
  hasUnsavedChanges: boolean;
  hookDurationSeconds: number;
  hookRangeEndSeconds: number | null;
  hookRangeStartSeconds: number | null;
  shortMaxDurationSeconds: number;
  onConvert: (request: SubtitleReviewConvertToShortRequest) => void;
};

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, value));
const rounded = (value: number) => Math.round(value * 1000) / 1000;

function formatTime(value: number): string {
  const safe = Math.max(0, value);
  const minutes = Math.floor(safe / 60);
  return `${minutes}:${(safe - minutes * 60).toFixed(1).padStart(4, "0")}`;
}

function defaultRange(clip: number, playhead: number, limit: number) {
  if (clip <= limit + 0.001) {
    return { start: 0, end: rounded(clip) };
  }
  const preferred = Math.min(60, limit);
  let start = clamp(playhead, 0, Math.max(0, clip - 1));
  let end = Math.min(clip, start + preferred);
  if (end - start < 1) {
    end = clip;
    start = Math.max(0, end - preferred);
  }
  return { start: rounded(start), end: rounded(end) };
}

export function ShortConversionEditor({
  busy,
  clipDurationSeconds,
  currentPositionSeconds,
  disabled,
  hasUnsavedChanges,
  hookDurationSeconds,
  hookRangeEndSeconds,
  hookRangeStartSeconds,
  shortMaxDurationSeconds,
  onConvert
}: Props) {
  const [open, setOpen] = useState(false);
  const [startValue, setStartValue] = useState("0");
  const [endValue, setEndValue] = useState(String(rounded(clipDurationSeconds)));
  const bodyLimit = Math.max(0, shortMaxDurationSeconds - hookDurationSeconds);
  const start = startValue.trim() === "" ? Number.NaN : Number(startValue);
  const end = endValue.trim() === "" ? Number.NaN : Number(endValue);
  const duration = Number.isFinite(start) && Number.isFinite(end) ? end - start : Number.NaN;
  const totalDuration = duration + hookDurationSeconds;

  let error: string | null = null;
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    error = "開始・終了を秒数で入力してください。";
  } else if (start < 0 || end > clipDurationSeconds + 0.001) {
    error = `0秒〜${formatTime(clipDurationSeconds)}内で指定してください。`;
  } else if (duration < 1) {
    error = "ショート本編は1秒以上にしてください。";
  } else if (totalDuration > shortMaxDurationSeconds + 0.001) {
    error = `本編と冒頭複製の合計を${formatTime(shortMaxDurationSeconds)}以内にしてください。`;
  } else if (
    hookRangeStartSeconds !== null &&
    hookRangeEndSeconds !== null &&
    (hookRangeStartSeconds < start - 0.001 || hookRangeEndSeconds > end + 0.001)
  ) {
    error = "冒頭フック映像も選択範囲内に含めてください。";
  }

  function openEditor() {
    const range = defaultRange(clipDurationSeconds, currentPositionSeconds, bodyLimit);
    setStartValue(String(range.start));
    setEndValue(String(range.end));
    setOpen(true);
  }

  function setCurrent(boundary: "start" | "end") {
    const value = String(rounded(clamp(currentPositionSeconds, 0, clipDurationSeconds)));
    if (boundary === "start") setStartValue(value);
    else setEndValue(value);
  }

  return (
    <section className="border border-emerald-300 bg-emerald-50 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-emerald-950">この通常動画からショートを作成</h2>
          <p className="mt-1 text-xs leading-5 text-emerald-800">
            元の完成動画は残します。使う範囲を決めてからショート画角を選びます。
          </p>
        </div>
        {!open ? (
          <button
            className="min-h-10 bg-emerald-700 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
            disabled={disabled || bodyLimit < 1}
            type="button"
            onClick={openEditor}
          >
            範囲を決めてショート化
          </button>
        ) : null}
      </div>

      {bodyLimit < 1 ? (
        <p className="mt-2 text-xs font-semibold text-red-800">
          冒頭複製を含めると本編を1秒以上確保できません。先に冒頭複製を短くするか解除してください。
        </p>
      ) : null}

      {open ? (
        <div className="mt-3 border-t border-emerald-200 pt-3">
          <div className="grid gap-3 sm:grid-cols-2">
            {(["start", "end"] as const).map((boundary) => {
              const isStart = boundary === "start";
              const value = isStart ? startValue : endValue;
              return (
                <label className="text-xs font-semibold text-neutral-800" key={boundary}>
                  clip内の{isStart ? "開始" : "終了"}（秒）
                  <input
                    className="mt-1 min-h-10 w-full border border-neutral-300 bg-white px-3 text-sm tabular-nums"
                    disabled={disabled}
                    max={clipDurationSeconds}
                    min={0}
                    step={0.1}
                    type="number"
                    value={value}
                    onChange={(event) =>
                      isStart ? setStartValue(event.target.value) : setEndValue(event.target.value)
                    }
                  />
                  <button
                    className="mt-1 min-h-8 w-full border border-neutral-300 bg-white px-2 text-xs font-semibold"
                    disabled={disabled}
                    type="button"
                    onClick={() => setCurrent(boundary)}
                  >
                    現在位置を{isStart ? "開始" : "終了"}にする（{formatTime(currentPositionSeconds)}）
                  </button>
                </label>
              );
            })}
          </div>

          <div className="mt-3 flex flex-wrap justify-between gap-2 border-y border-emerald-200 py-2 text-xs">
            <span>本編 {Number.isFinite(duration) && duration > 0 ? formatTime(duration) : "--"}</span>
            <span className="font-semibold">
              合計 {Number.isFinite(totalDuration) && totalDuration > 0 ? formatTime(totalDuration) : "--"}
              {hookDurationSeconds > 0 ? `（冒頭複製 ${formatTime(hookDurationSeconds)}を含む）` : ""}
              {` / 上限 ${formatTime(shortMaxDurationSeconds)}`}
            </span>
          </div>
          {hasUnsavedChanges ? (
            <p className="mt-2 text-xs font-semibold text-sky-800">
              未保存のタイトル・フック・字幕・文字スタイルは、変換前に自動保存します。
            </p>
          ) : null}
          {error ? <p className="mt-2 text-xs font-semibold text-red-800">{error}</p> : null}

          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <button
              className="min-h-10 border border-neutral-300 bg-white px-4 text-sm font-semibold"
              disabled={disabled}
              type="button"
              onClick={() => setOpen(false)}
            >
              閉じる
            </button>
            <button
              className="min-h-10 bg-emerald-700 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
              disabled={disabled || error !== null}
              type="button"
              onClick={() => onConvert({ startSeconds: rounded(start), endSeconds: rounded(end) })}
            >
              {busy ? "保存してショート化中" : "この範囲でショート編集へ"}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
