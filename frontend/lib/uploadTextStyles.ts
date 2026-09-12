import { defaultClipTextStyle, resolvedClipTextStyle, type ClipTextTarget } from "./clipTextStyle";
import { legacySubtitleYPercent } from "./textPositionPresets";
import type { ClipSettings, ClipTextStyle, ExportType, ResolvedClipTextStyle } from "./types";

export const UPLOAD_TEXT_STYLE_KEYS = [
  "shortTitleStyle", "shortHookStyle", "shortSubtitleStyle",
  "normalTitleStyle", "normalHookStyle", "normalSubtitleStyle"
] as const;

export function uploadTextStyleKey(mode: ExportType, target: ClipTextTarget) {
  return `${mode}${target[0].toUpperCase()}${target.slice(1)}Style` as typeof UPLOAD_TEXT_STYLE_KEYS[number];
}

// Keep legacy saved subtitle settings effective until that target is edited.
export function uploadDefaultTextStyle(
  settings: ClipSettings, mode: ExportType, target: ClipTextTarget
): ResolvedClipTextStyle {
  const short = mode === "short";
  const base = defaultClipTextStyle(target, mode);
  const subtitle = target === "subtitle";
  const fontSize = (short ? settings.shortSubtitleFontSize : settings.normalSubtitleFontSize)
    ?? settings.subtitleFontSize ?? (short ? 76 : 65);
  const lowerMargin = (short ? settings.shortSubtitleLowerMargin : settings.normalSubtitleLowerMargin)
    ?? settings.subtitleLowerMargin ?? (short ? 250 : 86);
  const alignment = (short ? settings.shortSubtitleAlignment : settings.normalSubtitleAlignment)
    ?? settings.subtitleAlignment ?? 2;
  const explicitY = short ? settings.shortSubtitleYPercent : settings.normalSubtitleYPercent;
  const xPercent = (short ? settings.shortSubtitleXPercent : settings.normalSubtitleXPercent) ?? 50;
  const outline = (short ? settings.shortSubtitleOutline : settings.normalSubtitleOutline)
    ?? settings.subtitleOutline ?? (short ? 5 : 4);
  const style: ClipTextStyle = {
    ...base,
    fontPreset: null,
    fontName: subtitle
      ? (short ? settings.shortSubtitleFontName : settings.normalSubtitleFontName) ?? settings.subtitleFontName ?? "Noto Sans CJK JP"
      : "Noto Sans JP Black",
    bold: subtitle,
    fontSize: subtitle ? fontSize : (short ? 88 : Math.max(fontSize + 6, 76)),
    primaryColor: subtitle
      ? (short ? settings.shortSubtitlePrimaryColor : settings.normalSubtitlePrimaryColor) ?? settings.subtitlePrimaryColor ?? "#FFFFFF"
      : "#FFFFFF",
    outlineColor: subtitle
      ? (short ? settings.shortSubtitleOutlineColor : settings.normalSubtitleOutlineColor) ?? settings.subtitleOutlineColor ?? "#000000"
      : "#000000",
    outlineWidth: outline,
    xPercent: subtitle ? xPercent : 50,
    yPercent: subtitle
      ? explicitY ?? legacySubtitleYPercent({ mode, alignment, lowerMargin, fontSize })
      : explicitY !== undefined ? (target === "title" ? 12.5 : 18.75) : (short ? 150 / 1920 * 100 : 86 / 1080 * 100)
  };
  const resolved = resolvedClipTextStyle(style, null, target, mode);
  return { ...resolved, marginX: short ? 86 : 154 };
}

export function withUploadTextStyle(
  settings: ClipSettings, mode: ExportType, target: ClipTextTarget, style: ClipTextStyle | null
): ClipSettings {
  return { ...settings, [uploadTextStyleKey(mode, target)]: style ?? undefined };
}
