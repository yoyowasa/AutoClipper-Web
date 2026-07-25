import type { ClipSettings } from "./types";

export const SUBTITLE_STYLE_PRESET_STORAGE_KEY =
  "autoclipper.subtitle-style-presets.v1";

export const SUBTITLE_STYLE_KEYS = [
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
  "shortSubtitlePrimaryColor",
  "shortSubtitleOutlineColor",
  "normalSubtitleFontName",
  "normalSubtitleFontSize",
  "normalSubtitleOutline",
  "normalSubtitleLowerMargin",
  "normalSubtitleAlignment",
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

export type SubtitleStylePresetSlots = [
  SubtitleStylePreset | null,
  SubtitleStylePreset | null,
  SubtitleStylePreset | null
];

type StoredSubtitleStylePresets = {
  version: 1;
  slots: SubtitleStylePresetSlots;
};

export function emptySubtitleStylePresetSlots(): SubtitleStylePresetSlots {
  return [null, null, null];
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
    if (typeof fieldValue === "string" || typeof fieldValue === "number") {
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
  const payload = JSON.parse(storedValue) as Partial<StoredSubtitleStylePresets>;
  if (payload.version !== 1 || !Array.isArray(payload.slots)) {
    return emptySubtitleStylePresetSlots();
  }
  return [
    sanitizePreset(payload.slots[0]),
    sanitizePreset(payload.slots[1]),
    sanitizePreset(payload.slots[2])
  ];
}

export function serializeSubtitleStylePresetSlots(
  slots: SubtitleStylePresetSlots
): string {
  const payload: StoredSubtitleStylePresets = {
    version: 1,
    slots
  };
  return JSON.stringify(payload);
}
