"use client";

import { subtitleFontFamily } from "../lib/clipTextStyle";
import {
  legacySubtitleYPercent,
  matchingPositionPreset,
  positionPixels,
  verticalPositionPresets
} from "../lib/textPositionPresets";
import type { ClipSettings } from "../lib/types";

export type SubtitlePreviewMode = "short" | "normal";

type SubtitleStylePreviewProps = {
  settings: ClipSettings;
  mode: SubtitlePreviewMode;
  compact?: boolean;
};

const PREVIEW_DEFAULTS = {
  short: {
    height: 1920,
    fontSize: 76,
    outline: 5,
    lowerMargin: 250,
    xPercent: 50,
    yPercent: 68.75
  },
  normal: {
    height: 1080,
    fontSize: 65,
    outline: 4,
    lowerMargin: 86,
    xPercent: 50,
    yPercent: 84
  }
} as const;

export function SubtitleStylePreview({
  settings,
  mode,
  compact = false
}: SubtitleStylePreviewProps) {
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
  const xPercent =
    (isShort
      ? settings.shortSubtitleXPercent
      : settings.normalSubtitleXPercent) ?? defaults.xPercent;
  const yPercent =
    (isShort
      ? settings.shortSubtitleYPercent
      : settings.normalSubtitleYPercent) ??
    legacySubtitleYPercent({
      mode,
      alignment,
      lowerMargin,
      fontSize
    });
  const verticalPresets = verticalPositionPresets(mode);
  const selectedPosition = matchingPositionPreset(verticalPresets, yPercent);
  const position = positionPixels(mode, xPercent, yPercent);
  const fontSizePercent = Math.min(12, Math.max(3.2, (fontSize / defaults.height) * 100));
  const strokeWidth = Math.min(4, Math.max(0, outline * 0.22));

  return (
    <div
      className={
        compact
          ? "grid items-start gap-3"
          : "mt-4 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_220px]"
      }
    >
      <div className="flex min-w-0 flex-col items-center">
        <div
          className={`relative w-full overflow-hidden border border-neutral-400 bg-[#27343a] ${
            mode === "short"
              ? compact
                ? "max-w-[210px] aspect-[9/16]"
                : "max-w-[250px] aspect-[9/16]"
              : compact
                ? "max-w-[300px] aspect-video"
                : "max-w-[560px] aspect-video"
          }`}
          style={{ containerType: "size" }}
        >
          <div className="absolute inset-y-0 right-0 w-[38%] bg-[#8fa3a8]" />
          <div className="absolute left-[9%] top-[12%] h-[38%] w-[42%] border border-white/25 bg-[#42565d]" />
          <div className="absolute bottom-0 left-0 h-[18%] w-full bg-[#172126]" />
          {verticalPresets.map((preset) => {
            const selected = selectedPosition?.id === preset.id;
            return (
              <div
                aria-hidden="true"
                className={`absolute left-0 w-full border-t ${
                  selected ? "border-sky-300" : "border-white/10"
                }`}
                key={preset.id}
                style={{ top: `${preset.percent}%` }}
              >
                {selected ? (
                  <span className="absolute left-1 top-0 bg-sky-700/90 px-1 py-0.5 text-[8px] font-semibold text-white">
                    {preset.label}
                  </span>
                ) : null}
              </div>
            );
          })}
          <p
            className="absolute m-0 max-w-[88%] whitespace-pre-line text-center font-extrabold tracking-normal"
            style={{
              color: primaryColor,
              fontFamily: subtitleFontFamily(fontName),
              fontSize: `clamp(12px, ${fontSizePercent}cqh, 38px)`,
              left: `${xPercent}%`,
              lineHeight: 1.28,
              textShadow: `0 2px 2px ${outlineColor}`,
              top: `${yPercent}%`,
              transform: "translate(-50%, -50%)",
              WebkitTextStroke: `${strokeWidth}px ${outlineColor}`
            }}
          >
            {"この瞬間が一番おもしろい！\n切り抜き字幕のプレビュー"}
          </p>
        </div>
      </div>

      {compact ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-neutral-200 pt-3 text-xs">
          <div>
            <dt className="text-neutral-500">表示</dt>
            <dd className="m-0 mt-0.5 font-semibold text-neutral-950">
              {mode === "short" ? "9:16" : "16:9"}
            </dd>
          </div>
          <div>
            <dt className="text-neutral-500">文字</dt>
            <dd className="m-0 mt-0.5 font-semibold text-neutral-950">
              {fontSize}px / 縁 {outline}
            </dd>
          </div>
          <div>
            <dt className="text-neutral-500">位置</dt>
            <dd className="m-0 mt-0.5 font-semibold text-neutral-950">
              {selectedPosition?.label ?? "微調整"}
              <span className="block font-normal text-neutral-500">
                X {position.x} / Y {position.y}
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-neutral-500">配色</dt>
            <dd className="m-0 mt-1 flex items-center gap-2 font-mono text-[10px] text-neutral-700">
              <span
                aria-label={`文字色 ${primaryColor}`}
                className="h-4 w-4 border border-neutral-400"
                style={{ backgroundColor: primaryColor }}
              />
              <span
                aria-label={`縁取り色 ${outlineColor}`}
                className="h-4 w-4 border border-neutral-400"
                style={{ backgroundColor: outlineColor }}
              />
            </dd>
          </div>
        </dl>
      ) : (
        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-3 border-l border-neutral-200 pl-4 text-sm">
          <dt className="text-neutral-500">表示</dt>
          <dd className="m-0 font-medium text-neutral-950">
            {mode === "short" ? "9:16" : "16:9"}
          </dd>
          <dt className="text-neutral-500">文字サイズ</dt>
          <dd className="m-0 font-medium text-neutral-950">{fontSize}</dd>
          <dt className="text-neutral-500">縁取り</dt>
          <dd className="m-0 font-medium text-neutral-950">{outline}</dd>
          <dt className="text-neutral-500">位置</dt>
          <dd className="m-0 text-right font-medium text-neutral-950">
            {selectedPosition?.label ?? "微調整"}
            <span className="block text-xs font-normal text-neutral-500">
              X {position.x} / Y {position.y}
            </span>
          </dd>
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
      )}
    </div>
  );
}
