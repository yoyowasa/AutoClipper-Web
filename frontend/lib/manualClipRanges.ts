import type { ClipSettings, ClipTimeRange } from "./types";

export type ClipOutputType = "normal" | "short";
export type TimeBoundary = "startSeconds" | "endSeconds";
export type TimeUnit = "minutes" | "seconds";

function rangeKey(type: ClipOutputType) {
  return type === "normal" ? "normalClipTimeRanges" : "shortClipTimeRanges";
}

function requestedCount(settings: ClipSettings, type: ClipOutputType) {
  return type === "normal" ? settings.normalClipCount : settings.shortCount;
}

function emptyRange(): ClipTimeRange {
  return { startSeconds: null, endSeconds: null };
}

export function isManualTimeMode(settings: ClipSettings, type: ClipOutputType): boolean {
  return settings[rangeKey(type)].length > 0;
}

export function manualRangeRows(
  settings: ClipSettings,
  type: ClipOutputType
): ClipTimeRange[] {
  const count = requestedCount(settings, type);
  const ranges = settings[rangeKey(type)];
  return Array.from({ length: count }, (_, index) => ranges[index] ?? emptyRange());
}

export function resizeManualRanges(
  settings: ClipSettings,
  type: ClipOutputType,
  count: number
): ClipSettings {
  const key = rangeKey(type);
  if (settings[key].length === 0) {
    return settings;
  }
  return {
    ...settings,
    [key]: Array.from({ length: count }, (_, index) => settings[key][index] ?? emptyRange())
  };
}

export function clearManualRanges(
  settings: ClipSettings,
  type: ClipOutputType
): ClipSettings {
  return {
    ...settings,
    [rangeKey(type)]: []
  };
}

export function updateManualRangeTime(
  settings: ClipSettings,
  type: ClipOutputType,
  index: number,
  boundary: TimeBoundary,
  unit: TimeUnit,
  rawValue: string
): ClipSettings {
  const key = rangeKey(type);
  const ranges = manualRangeRows(settings, type);
  const current = ranges[index] ?? emptyRange();
  const currentTotal = current[boundary];
  const currentMinutes = currentTotal === null ? 0 : Math.floor(currentTotal / 60);
  const currentSeconds = currentTotal === null ? 0 : Math.floor(currentTotal % 60);
  const parsed = rawValue === "" ? null : Math.max(0, Math.floor(Number(rawValue) || 0));

  let nextTotal: number | null;
  if (unit === "minutes") {
    nextTotal =
      parsed === null
        ? currentSeconds > 0
          ? currentSeconds
          : null
        : parsed * 60 + currentSeconds;
  } else {
    const seconds = parsed === null ? 0 : Math.min(59, parsed);
    nextTotal =
      parsed === null && currentMinutes === 0
        ? null
        : currentMinutes * 60 + seconds;
  }

  ranges[index] = { ...current, [boundary]: nextTotal };
  const hasAnyValue = ranges.some(
    (range) => range.startSeconds !== null || range.endSeconds !== null
  );
  return {
    ...settings,
    [key]: hasAnyValue ? ranges : []
  };
}

export function manualRangeValidationError(settings: ClipSettings): string | null {
  for (const type of ["normal", "short"] as const) {
    const ranges = settings[rangeKey(type)];
    if (ranges.length === 0) {
      continue;
    }
    const label = type === "normal" ? "通常切り抜き" : "ショート";
    const count = requestedCount(settings, type);
    if (ranges.length !== count) {
      return `${label}の時間指定は${count}本すべて入力してください。`;
    }
    const seen = new Set<string>();
    for (const [index, range] of ranges.entries()) {
      if (range.startSeconds === null || range.endSeconds === null) {
        return `${label}${index + 1}の開始時間と終了時間を入力してください。`;
      }
      if (range.endSeconds <= range.startSeconds) {
        return `${label}${index + 1}は終了時間を開始時間より後にしてください。`;
      }
      const key = `${range.startSeconds}:${range.endSeconds}`;
      if (seen.has(key)) {
        return `${label}${index + 1}が前の時間指定と重複しています。`;
      }
      seen.add(key);
    }
  }
  return null;
}

export function allRequestedOutputsUseManualTime(settings: ClipSettings): boolean {
  const requestedTypes = (["normal", "short"] as const).filter(
    (type) => requestedCount(settings, type) > 0
  );
  return (
    requestedTypes.length > 0 &&
    requestedTypes.every((type) => isManualTimeMode(settings, type))
  );
}
