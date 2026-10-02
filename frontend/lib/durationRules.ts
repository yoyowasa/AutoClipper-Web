import type { ClipSettings } from "./types";

export const NORMAL_MIN_SECONDS = 90;
export const NORMAL_MAX_SECONDS = 600;
export const NORMAL_LONGFORM_MAX_SECONDS = 1800;

export function longformLabel(type: string, duration: number): string | null {
  return type === "normal" && duration > NORMAL_MAX_SECONDS ? "長尺（10分超）" : null;
}
export const SHORT_MAX_DEFAULT_SECONDS = 75;
export const SHORT_MAX_CEILING_SECONDS = 180;

export function effectiveShortMax(value: number = SHORT_MAX_DEFAULT_SECONDS): number {
  return Number.isFinite(value) ? Math.max(1, Math.min(SHORT_MAX_CEILING_SECONDS, value)) : SHORT_MAX_DEFAULT_SECONDS;
}

export function validateClipDuration(type: "normal" | "short", duration: number, shortMax: number): string | null {
  if (!Number.isFinite(duration) || duration <= 0) return "切り抜きの終了は開始より後にしてください。";
  if (type === "normal" && duration < NORMAL_MIN_SECONDS) return "通常切り抜きは90秒以上です。";
  if (type === "normal" && duration > NORMAL_LONGFORM_MAX_SECONDS) return "通常切り抜きは最長30分です。";
  if (type === "short" && duration > shortMax) return `ショートは${shortMax}秒以内です（設定の上限）。`;
  return null;
}

export function durationSettingsError(settings: Pick<ClipSettings,
  "normalMinDuration" | "normalMaxDuration" | "shortMinDuration" | "shortMaxDuration">): string | null {
  const { normalMinDuration, normalMaxDuration, shortMinDuration, shortMaxDuration } = settings;
  if (![normalMinDuration, normalMaxDuration].every(value =>
    Number.isFinite(value) && value >= NORMAL_MIN_SECONDS && value <= NORMAL_MAX_SECONDS)) {
    return "通常切り抜きは90秒〜10分です。";
  }
  if (normalMinDuration > normalMaxDuration) return "通常切り抜きの最低尺は最長尺以下にしてください。";
  if (!Number.isFinite(shortMaxDuration) || shortMaxDuration < 1 || shortMaxDuration > SHORT_MAX_CEILING_SECONDS) {
    return "ショートの上限は1〜180秒で設定してください。";
  }
  if (!Number.isFinite(shortMinDuration) || shortMinDuration < 0 || shortMinDuration > shortMaxDuration) {
    return "ショートの探索目安は0秒以上、設定の上限以下にしてください。";
  }
  return null;
}
