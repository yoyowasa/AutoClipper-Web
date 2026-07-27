import type {
  ClipTextFontPreset,
  ClipTextStyle,
  ExportType
} from "./types";

export type ClipTextTarget = "title" | "hook" | "subtitle";

export const CLIP_TEXT_FONT_OPTIONS: ReadonlyArray<{
  value: ClipTextFontPreset;
  label: string;
}> = [
  { value: "sans", label: "標準ゴシック" },
  { value: "sans_bold", label: "太字ゴシック" },
  { value: "heavy", label: "極太ゴシック" },
  { value: "serif", label: "明朝" },
  { value: "mono", label: "等幅ゴシック" }
];

const SHORT_DEFAULTS: Record<ClipTextTarget, ClipTextStyle> = {
  title: {
    fontPreset: "sans_bold",
    fontSize: 88,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 10
  },
  hook: {
    fontPreset: "sans_bold",
    fontSize: 88,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 10
  },
  subtitle: {
    fontPreset: "sans_bold",
    fontSize: 76,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 87
  }
};

const NORMAL_SUBTITLE_DEFAULT: ClipTextStyle = {
  fontPreset: "sans_bold",
  fontSize: 65,
  primaryColor: "#FFFFFF",
  outlineColor: "#000000",
  outlineWidth: 4,
  xPercent: 50,
  yPercent: 92
};

export function defaultClipTextStyle(
  target: ClipTextTarget,
  clipType: ExportType
): ClipTextStyle {
  const source =
    clipType === "normal" && target === "subtitle"
      ? NORMAL_SUBTITLE_DEFAULT
      : SHORT_DEFAULTS[target];
  return { ...source };
}

export function resolvedClipTextStyle(
  style: ClipTextStyle | null | undefined,
  target: ClipTextTarget,
  clipType: ExportType
): ClipTextStyle {
  return style ? { ...style } : defaultClipTextStyle(target, clipType);
}

export function clipTextFontFamily(fontPreset: ClipTextFontPreset): string {
  if (fontPreset === "heavy") {
    return '"Source Han Sans JP Heavy", "Noto Sans CJK JP", "Yu Gothic", sans-serif';
  }
  if (fontPreset === "serif") {
    return '"Noto Serif CJK JP", "Yu Mincho", YuMincho, serif';
  }
  if (fontPreset === "mono") {
    return '"Noto Sans Mono CJK JP", "MS Gothic", monospace';
  }
  return '"Noto Sans CJK JP", "Yu Gothic", Meiryo, sans-serif';
}

export function clipTextFontWeight(fontPreset: ClipTextFontPreset): number {
  return fontPreset === "sans" || fontPreset === "serif" ? 500 : 800;
}
