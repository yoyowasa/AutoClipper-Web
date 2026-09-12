import type { ClipSettings, ClipTextStyle } from "./types";
import { UPLOAD_TEXT_STYLE_KEYS } from "./uploadTextStyles";

export const SUBTITLE_STYLE_PRESET_LIMIT = 10;

export const SUBTITLE_STYLE_PRESET_STORAGE_KEY =
  "autoclipper.subtitle-style-presets.v1";

export const SUBTITLE_STYLE_KEYS = [
  ...UPLOAD_TEXT_STYLE_KEYS,
  "subtitleFontName",
  "subtitleFontSize",
  "subtitleOutline",
  "subtitleLowerMargin",
  "subtitleAlignment",
  "subtitlePrimaryColor",
  "subtitleOutlineColor",
  "shortSubtitleFontName",
  "shortSubtitleFontSize",
  "shortSubtitleOutline",
  "shortSubtitleLowerMargin",
  "shortSubtitleAlignment",
  "shortSubtitleXPercent",
  "shortSubtitleYPercent",
  "shortSubtitlePrimaryColor",
  "shortSubtitleOutlineColor",
  "normalSubtitleFontName",
  "normalSubtitleFontSize",
  "normalSubtitleOutline",
  "normalSubtitleLowerMargin",
  "normalSubtitleAlignment",
  "normalSubtitleXPercent",
  "normalSubtitleYPercent",
  "normalSubtitlePrimaryColor",
  "normalSubtitleOutlineColor"
] as const satisfies readonly (keyof ClipSettings)[];

export type SubtitleStyleKey = (typeof SUBTITLE_STYLE_KEYS)[number];
export type SubtitleStyleSnapshot = Partial<
  Pick<ClipSettings, SubtitleStyleKey>
>;

export type SubtitleStylePreset = {
  name: string;
  savedAt: string;
  style: SubtitleStyleSnapshot;
};

export type SubtitleStylePresetSlots = Array<SubtitleStylePreset | null>;

export type SubtitleStylePresetDocument = {
  version: 1;
  slots: SubtitleStylePresetSlots;
};

export function emptySubtitleStylePresetSlots(): SubtitleStylePresetSlots {
  return Array.from({ length: SUBTITLE_STYLE_PRESET_LIMIT }, () => null);
}

export function captureSubtitleStyle(
  settings: ClipSettings
): SubtitleStyleSnapshot {
  const snapshot: SubtitleStyleSnapshot = {};
  for (const key of SUBTITLE_STYLE_KEYS) {
    const value = settings[key];
    if (value !== undefined) {
      Object.assign(snapshot, { [key]: value });
    }
  }
  return snapshot;
}

export function applySubtitleStyle(
  settings: ClipSettings,
  style: SubtitleStyleSnapshot
): ClipSettings {
  const next = { ...settings };
  for (const key of SUBTITLE_STYLE_KEYS) {
    delete next[key];
  }
  return {
    ...next,
    ...style
  };
}

function sanitizeStyle(value: unknown): SubtitleStyleSnapshot {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  const source = value as Record<string, unknown>;
  const style: SubtitleStyleSnapshot = {};
  for (const key of SUBTITLE_STYLE_KEYS) {
    const fieldValue = source[key];
    if (UPLOAD_TEXT_STYLE_KEYS.includes(key as typeof UPLOAD_TEXT_STYLE_KEYS[number])) {
      if (fieldValue && typeof fieldValue === "object" && !Array.isArray(fieldValue)) {
        const candidate = fieldValue as ClipTextStyle;
        if (Number.isFinite(candidate.fontSize) && typeof candidate.primaryColor === "string") {
          Object.assign(style, { [key]: { ...candidate } });
        }
      }
    } else if (typeof fieldValue === "string" || typeof fieldValue === "number") {
      Object.assign(style, { [key]: fieldValue });
    }
  }
  return style;
}

function sanitizePreset(value: unknown): SubtitleStylePreset | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const source = value as Record<string, unknown>;
  if (typeof source.name !== "string" || typeof source.savedAt !== "string") {
    return null;
  }
  const name = source.name.trim().slice(0, 40);
  if (!name) {
    return null;
  }
  return {
    name,
    savedAt: source.savedAt,
    style: sanitizeStyle(source.style)
  };
}

export function parseSubtitleStylePresetSlots(
  storedValue: string | null
): SubtitleStylePresetSlots {
  if (!storedValue) {
    return emptySubtitleStylePresetSlots();
  }
  const payload = JSON.parse(storedValue) as Partial<SubtitleStylePresetDocument>;
  if (payload.version !== 1 || !Array.isArray(payload.slots)) {
    return emptySubtitleStylePresetSlots();
  }
  return Array.from({ length: SUBTITLE_STYLE_PRESET_LIMIT }, (_, index) =>
    sanitizePreset(payload.slots?.[index])
  );
}

export function serializeSubtitleStylePresetSlots(
  slots: SubtitleStylePresetSlots
): string {
  const payload: SubtitleStylePresetDocument = {
    version: 1,
    slots
  };
  return JSON.stringify(payload);
}
