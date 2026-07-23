"use client";

import type { ClipSettings } from "../lib/types";

export type SubtitlePreviewMode = "short" | "normal";

type SubtitleStylePreviewProps = {
  settings: ClipSettings;
  mode: SubtitlePreviewMode;
};

const PREVIEW_DEFAULTS = {
  short: {
    height: 1920,
    fontSize: 76,
    outline: 5,
    lowerMargin: 250
  },
  normal: {
    height: 1080,
    fontSize: 65,
    outline: 4,
    lowerMargin: 86
  }
} as const;

function previewFontFamily(fontName: string | undefined): string {
  if (fontName === "Source Han Sans JP Heavy") {
    return '"Source Han Sans JP Heavy", "Noto Sans CJK JP", "Yu Gothic", sans-serif';
  }
  if (fontName === "Noto Serif CJK JP") {
    return '"Noto Serif CJK JP", "Yu Mincho", YuMincho, serif';
  }
  if (fontName === "Noto Sans Mono CJK JP") {
    return '"Noto Sans Mono CJK JP", "MS Gothic", monospace';
  }
  return '"Noto Sans CJK JP", "Yu Gothic", Meiryo, sans-serif';
}

function alignmentLabel(alignment: number): string {
  if (alignment === 8) {
    return "上";
  }
  if (alignment === 5) {
    return "中央";
  }
  return "下";
}

export function SubtitleStylePreview({ settings, mode }: SubtitleStylePreviewProps) {
  const defaults = PREVIEW_DEFAULTS[mode];
  const isShort = mode === "short";
  const fontName =
    (isShort ? settings.shortSubtitleFontName : settings.normalSubtitleFontName) ??
    settings.subtitleFontName;
  const fontSize =
    (isShort ? settings.shortSubtitleFontSize : settings.normalSubtitleFontSize) ??
    settings.subtitleFontSize ??
    defaults.fontSize;
  const outline =
    (isShort ? settings.shortSubtitleOutline : settings.normalSubtitleOutline) ??
    settings.subtitleOutline ??
    defaults.outline;
  const lowerMargin =
    (isShort ? settings.shortSubtitleLowerMargin : settings.normalSubtitleLowerMargin) ??
    settings.subtitleLowerMargin ??
    defaults.lowerMargin;
  const alignment =
    (isShort ? settings.shortSubtitleAlignment : settings.normalSubtitleAlignment) ??
    settings.subtitleAlignment ??
    2;
  const primaryColor =
    (isShort
      ? settings.shortSubtitlePrimaryColor
      : settings.normalSubtitlePrimaryColor) ??
    settings.subtitlePrimaryColor ??
    "#FFFFFF";
  const outlineColor =
    (isShort
      ? settings.shortSubtitleOutlineColor
      : settings.normalSubtitleOutlineColor) ??
    settings.subtitleOutlineColor ??
    "#000000";
  const lowerMarginPercent = Math.min(42, Math.max(0, (lowerMargin / defaults.height) * 100));
  const fontSizePercent = Math.min(12, Math.max(3.2, (fontSize / defaults.height) * 100));
  const strokeWidth = Math.min(4, Math.max(0, outline * 0.22));
  const verticalPosition =
    alignment === 8 ? "flex-start" : alignment === 5 ? "center" : "flex-end";

  return (
    <div className="mt-4 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_220px]">
      <div className="flex min-w-0 flex-col items-center">
        <div
          className={`relative w-full overflow-hidden border border-neutral-400 bg-[#27343a] ${
            mode === "short" ? "max-w-[250px] aspect-[9/16]" : "max-w-[560px] aspect-video"
          }`}
          style={{ containerType: "size" }}
        >
          <div className="absolute inset-y-0 right-0 w-[38%] bg-[#8fa3a8]" />
          <div className="absolute left-[9%] top-[12%] h-[38%] w-[42%] border border-white/25 bg-[#42565d]" />
          <div className="absolute bottom-0 left-0 h-[18%] w-full bg-[#172126]" />
          <div
            className="absolute inset-0 flex flex-col items-center px-[7%] py-[7%] text-center"
            style={{
              justifyContent: verticalPosition,
              paddingBottom: alignment === 2 ? `${Math.max(7, lowerMarginPercent)}%` : undefined,
              paddingTop: alignment === 8 ? `${Math.max(7, lowerMarginPercent)}%` : undefined
            }}
          >
            <p
              className="m-0 whitespace-pre-line font-extrabold tracking-normal"
              style={{
                color: primaryColor,
                fontFamily: previewFontFamily(fontName),
                fontSize: `clamp(12px, ${fontSizePercent}cqh, 38px)`,
                lineHeight: 1.28,
                textShadow: `0 2px 2px ${outlineColor}`,
                WebkitTextStroke: `${strokeWidth}px ${outlineColor}`
              }}
            >
              {"この瞬間が一番おもしろい！\n切り抜き字幕のプレビュー"}
            </p>
          </div>
        </div>
      </div>

      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-3 border-l border-neutral-200 pl-4 text-sm">
        <dt className="text-neutral-500">表示</dt>
        <dd className="m-0 font-medium text-neutral-950">
          {mode === "short" ? "9:16" : "16:9"}
        </dd>
        <dt className="text-neutral-500">文字サイズ</dt>
        <dd className="m-0 font-medium text-neutral-950">{fontSize}</dd>
        <dt className="text-neutral-500">縁取り</dt>
        <dd className="m-0 font-medium text-neutral-950">{outline}</dd>
        <dt className="text-neutral-500">端の余白</dt>
        <dd className="m-0 font-medium text-neutral-950">{lowerMargin}</dd>
        <dt className="text-neutral-500">位置</dt>
        <dd className="m-0 font-medium text-neutral-950">{alignmentLabel(alignment)}</dd>
        <dt className="text-neutral-500">文字色</dt>
        <dd className="m-0 flex items-center gap-2 font-mono text-xs font-medium text-neutral-950">
          <span
            aria-hidden="true"
            className="h-4 w-4 border border-neutral-400"
            style={{ backgroundColor: primaryColor }}
          />
          {primaryColor}
        </dd>
        <dt className="text-neutral-500">縁色</dt>
        <dd className="m-0 flex items-center gap-2 font-mono text-xs font-medium text-neutral-950">
          <span
            aria-hidden="true"
            className="h-4 w-4 border border-neutral-400"
            style={{ backgroundColor: outlineColor }}
          />
          {outlineColor}
        </dd>
      </dl>
    </div>
  );
}
