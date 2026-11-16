import type { ClipTextStyle, SubtitleStyleOverride } from "../types";

// One-click colours for the subtitle rows. A colour is the colour part of a per-subtitle style;
// size, font and position stay with each subtitle.
export const SPEAKER_COLOR_KEYS = ["primaryColor", "outlineColor", "outerOutlineColor"] as const;
export type SpeakerColor = Partial<Pick<ClipTextStyle, (typeof SPEAKER_COLOR_KEYS)[number]>>;
export const MAX_SPEAKER_COLORS = 4;
const HEX = /^#[0-9A-Fa-f]{6}$/;
type Range = { start: number; end: number };

export function speakerColorOf(style?: Partial<ClipTextStyle> | null): SpeakerColor | null {
  const color: SpeakerColor = {};
  for (const key of SPEAKER_COLOR_KEYS) {
    const value = style?.[key];
    if (typeof value === "string" && HEX.test(value)) color[key] = value.toUpperCase();
  }
  return Object.keys(color).length ? color : null;
}

export const speakerColorKey = (color: SpeakerColor) => SPEAKER_COLOR_KEYS.map((key) => color[key] ?? "").join("|");

/** Colours already used in this job come first, then the ones remembered for the character. */
export function speakerColors(styleLists: SubtitleStyleOverride[][], remembered: SpeakerColor[]): SpeakerColor[] {
  const found = new Map<string, SpeakerColor>();
  const used = styleLists.flatMap((list) => [...list].sort((a, b) => a.start - b.start).map((item) => speakerColorOf(item.style)));
  for (const color of [...used, ...remembered]) {
    if (color && !found.has(speakerColorKey(color))) found.set(speakerColorKey(color), color);
  }
  return [...found.values()].slice(0, MAX_SPEAKER_COLORS);
}

export function hasSpeakerColor(styles: SubtitleStyleOverride[], segment: Range, color: SpeakerColor): boolean {
  const current = speakerColorOf(styles.find((item) => item.start === segment.start && item.end === segment.end)?.style);
  return Boolean(current && speakerColorKey(current) === speakerColorKey(color));
}

/** Paint the subtitles with the colour. With toggle, a subtitle that already has it goes back to the common colour. */
export function paintSubtitles(styles: SubtitleStyleOverride[], segments: Range[], color: SpeakerColor,
  toggle = false): SubtitleStyleOverride[] {
  let next = styles;
  for (const segment of segments) {
    const same = (item: Range) => item.start === segment.start && item.end === segment.end;
    const existing = next.find(same);
    const style: Partial<ClipTextStyle> = { ...existing?.style };
    for (const key of SPEAKER_COLOR_KEYS) delete style[key];
    if (!(toggle && hasSpeakerColor(next, segment, color))) Object.assign(style, color);
    next = next.filter((item) => !same(item));
    if (Object.keys(style).length) next = [...next, { ...existing, start: segment.start, end: segment.end, style, styleVersion: 2 }];
  }
  return next;
}

/** Subtitles from the last painted one to the clicked one, in time order; only the clicked one without an anchor. */
export function subtitlesBetween<T extends Range & { id: string }>(segments: T[], anchorId: string | null, id: string): T[] {
  const ordered = [...segments].sort((a, b) => a.start - b.start);
  const to = ordered.findIndex((item) => item.id === id);
  const from = ordered.findIndex((item) => item.id === anchorId);
  if (to < 0) return [];
  return from < 0 ? [ordered[to]] : ordered.slice(Math.min(from, to), Math.max(from, to) + 1);
}

const storageKey = (character: string) => `autoclipper.speakerColors.v1:${character}`;
type ColorStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function rememberedColorsText(storage: ColorStorage | undefined, character: string): string {
  try {
    return storage?.getItem(storageKey(character)) ?? "";
  } catch {
    return "";
  }
}

export function parseRememberedColors(text: string): SpeakerColor[] {
  try {
    const parsed: unknown = JSON.parse(text || "[]");
    if (!Array.isArray(parsed)) return [];
    return speakerColors([], parsed.map((item) => speakerColorOf(item as Partial<ClipTextStyle>)).filter((item) => item !== null));
  } catch {
    return [];
  }
}

export const readRememberedColors = (storage: ColorStorage | undefined, character: string) =>
  parseRememberedColors(rememberedColorsText(storage, character));

export function writeRememberedColors(storage: ColorStorage | undefined, character: string, colors: SpeakerColor[]): void {
  try {
    if (colors.length) storage?.setItem(storageKey(character), JSON.stringify(colors.slice(0, MAX_SPEAKER_COLORS)));
    else storage?.removeItem(storageKey(character));
  } catch {
    // Remembering colours is a convenience; the buttons still work for this job.
  }
}
