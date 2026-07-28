"use client";

import { useState } from "react";

import { SUBTITLE_FONT_GROUPS } from "../lib/clipTextStyle";
import {
  HORIZONTAL_POSITION_PRESETS,
  legacySubtitleYPercent,
  matchingPositionPreset,
  positionPixels,
  verticalPositionPresets
} from "../lib/textPositionPresets";
import type { ClipSettings } from "../lib/types";
import {
  SubtitleStylePreview,
  type SubtitlePreviewMode
} from "./SubtitleStylePreview";
import { SubtitleStylePresetManager } from "./SubtitleStylePresetManager";

type SubtitleStyleEditorProps = {
  settings: ClipSettings;
  disabled?: boolean;
  onChange: (settings: ClipSettings) => void;
};

type StyleField =
  | "fontName"
  | "fontSize"
  | "outline"
  | "lowerMargin"
  | "alignment"
  | "xPercent"
  | "yPercent"
  | "primaryColor"
  | "outlineColor";

const STYLE_KEYS: Record<
  SubtitlePreviewMode,
  Record<StyleField, keyof ClipSettings>
> = {
  short: {
    fontName: "shortSubtitleFontName",
    fontSize: "shortSubtitleFontSize",
    outline: "shortSubtitleOutline",
    lowerMargin: "shortSubtitleLowerMargin",
    alignment: "shortSubtitleAlignment",
    xPercent: "shortSubtitleXPercent",
    yPercent: "shortSubtitleYPercent",
    primaryColor: "shortSubtitlePrimaryColor",
    outlineColor: "shortSubtitleOutlineColor"
  },
  normal: {
    fontName: "normalSubtitleFontName",
    fontSize: "normalSubtitleFontSize",
    outline: "normalSubtitleOutline",
    lowerMargin: "normalSubtitleLowerMargin",
    alignment: "normalSubtitleAlignment",
    xPercent: "normalSubtitleXPercent",
    yPercent: "normalSubtitleYPercent",
    primaryColor: "normalSubtitlePrimaryColor",
    outlineColor: "normalSubtitleOutlineColor"
  }
};

const STYLE_DEFAULTS = {
  short: {
    fontSize: 76,
    outline: 5,
    lowerMargin: 250,
    alignment: 2,
    xPercent: 50,
    yPercent: 68.75
  },
  normal: {
    fontSize: 65,
    outline: 4,
    lowerMargin: 86,
    alignment: 2,
    xPercent: 50,
    yPercent: 84
  }
} as const;

const COLOR_PRESETS = [
  { value: "#FFFFFF", label: "白" },
  { value: "#FFF200", label: "黄" },
  { value: "#5EE7F7", label: "水色" },
  { value: "#FF8FAB", label: "ピンク" },
  { value: "#9BFF9B", label: "緑" },
  { value: "#000000", label: "黒" }
] as const;

function styleValue(
  settings: ClipSettings,
  mode: SubtitlePreviewMode,
  field: StyleField
): ClipSettings[keyof ClipSettings] {
  return settings[STYLE_KEYS[mode][field]];
}

function withStyleValue(
  settings: ClipSettings,
  mode: SubtitlePreviewMode,
  field: StyleField,
  value: string | number | undefined
): ClipSettings {
  return {
    ...settings,
    [STYLE_KEYS[mode][field]]: value
  };
}

function resetStyle(settings: ClipSettings, mode: SubtitlePreviewMode): ClipSettings {
  const keys = STYLE_KEYS[mode];
  return {
    ...settings,
    [keys.fontName]: undefined,
    [keys.fontSize]: undefined,
    [keys.outline]: undefined,
    [keys.lowerMargin]: undefined,
    [keys.alignment]: undefined,
    [keys.xPercent]: STYLE_DEFAULTS[mode].xPercent,
    [keys.yPercent]: STYLE_DEFAULTS[mode].yPercent,
    [keys.primaryColor]: undefined,
    [keys.outlineColor]: undefined
  };
}

type ColorControlProps = {
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
};

function ColorControl({ label, value, disabled, onChange }: ColorControlProps) {
  return (
    <fieldset className="min-w-0">
      <legend className="text-sm font-medium text-neutral-700">{label}</legend>
      <div className="mt-2 flex min-h-10 items-center gap-2">
        <input
          aria-label={`${label}を選択`}
          className="h-10 w-12 cursor-pointer border border-neutral-300 bg-white p-1 disabled:cursor-not-allowed"
          disabled={disabled}
          type="color"
          value={value}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
        />
        <span className="min-w-[68px] font-mono text-xs text-neutral-600">{value}</span>
        <div className="flex flex-wrap gap-1.5">
          {COLOR_PRESETS.map((color) => (
            <button
              aria-label={`${label}: ${color.label}`}
              className={`h-7 w-7 border ${
                value === color.value
                  ? "border-neutral-950 ring-2 ring-neutral-300"
                  : "border-neutral-300"
              }`}
              disabled={disabled}
              key={color.value}
              title={color.label}
              type="button"
              style={{ backgroundColor: color.value }}
              onClick={() => onChange(color.value)}
            />
          ))}
        </div>
      </div>
    </fieldset>
  );
}

export function SubtitleStyleEditor({
  settings,
  disabled = false,
  onChange
}: SubtitleStyleEditorProps) {
  const [mode, setMode] = useState<SubtitlePreviewMode>("short");
  const defaults = STYLE_DEFAULTS[mode];
  const fontName =
    (styleValue(settings, mode, "fontName") as string | undefined) ??
    settings.subtitleFontName ??
    "";
  const fontSize =
    (styleValue(settings, mode, "fontSize") as number | undefined) ??
    settings.subtitleFontSize;
  const outline =
    (styleValue(settings, mode, "outline") as number | undefined) ??
    settings.subtitleOutline;
  const lowerMargin =
    (styleValue(settings, mode, "lowerMargin") as number | undefined) ??
    settings.subtitleLowerMargin;
  const alignment =
    (styleValue(settings, mode, "alignment") as number | undefined) ??
    settings.subtitleAlignment;
  const primaryColor =
    (styleValue(settings, mode, "primaryColor") as string | undefined) ??
    settings.subtitlePrimaryColor ??
    "#FFFFFF";
  const outlineColor =
    (styleValue(settings, mode, "outlineColor") as string | undefined) ??
    settings.subtitleOutlineColor ??
    "#000000";
  const xPercent =
    (styleValue(settings, mode, "xPercent") as number | undefined) ??
    defaults.xPercent;
  const explicitYPercent = styleValue(settings, mode, "yPercent") as
    | number
    | undefined;
  const yPercent =
    explicitYPercent ??
    legacySubtitleYPercent({
      mode,
      alignment: alignment ?? defaults.alignment,
      lowerMargin: lowerMargin ?? defaults.lowerMargin,
      fontSize: fontSize ?? defaults.fontSize
    });
  const verticalPresets = verticalPositionPresets(mode);
  const selectedHorizontalPreset = matchingPositionPreset(
    HORIZONTAL_POSITION_PRESETS,
    xPercent
  );
  const selectedVerticalPreset = matchingPositionPreset(
    verticalPresets,
    yPercent
  );
  const position = positionPixels(mode, xPercent, yPercent);

  return (
    <section className="border-t border-neutral-200 pt-5 md:col-span-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-base font-semibold text-neutral-950">字幕スタイル</h2>
          <div
            aria-label="字幕スタイルの対象"
            className="inline-flex border border-neutral-300 bg-neutral-100 p-1"
            role="group"
          >
            <button
              aria-pressed={mode === "short"}
              className={`min-h-9 px-3 text-sm font-medium ${
                mode === "short" ? "bg-neutral-950 text-white" : "text-neutral-600"
              }`}
              disabled={disabled}
              type="button"
              onClick={() => setMode("short")}
            >
              ショート 9:16
            </button>
            <button
              aria-pressed={mode === "normal"}
              className={`min-h-9 px-3 text-sm font-medium ${
                mode === "normal" ? "bg-neutral-950 text-white" : "text-neutral-600"
              }`}
              disabled={disabled}
              type="button"
              onClick={() => setMode("normal")}
            >
              通常 16:9
            </button>
          </div>
        </div>
        <button
          className="min-h-9 border border-neutral-300 px-3 text-sm font-medium text-neutral-700"
          disabled={disabled}
          type="button"
          onClick={() => onChange(resetStyle(settings, mode))}
        >
          このスタイルを既定値に戻す
        </button>
      </div>

      <SubtitleStylePresetManager
        disabled={disabled}
        settings={settings}
        onChange={onChange}
      />

      <div className="mt-4 grid items-start gap-5 md:grid-cols-[260px_minmax(0,1fr)] lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="md:sticky md:top-4">
          <SubtitleStylePreview compact mode={mode} settings={settings} />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-2 sm:col-span-2">
          <span className="text-sm font-medium text-neutral-700">字幕フォント</span>
          <select
            className="min-h-10 border border-neutral-300 bg-white px-3 text-sm"
            data-testid={`${mode}-subtitle-font-select`}
            disabled={disabled}
            value={fontName}
            onChange={(event) =>
              onChange(
                withStyleValue(
                  settings,
                  mode,
                  "fontName",
                  event.target.value || undefined
                )
              )
            }
          >
            <option value="">既定（Noto Sans CJK JP）</option>
            {SUBTITLE_FONT_GROUPS.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.options.map((font) => (
                  <option key={font.value} value={font.value}>
                    {font.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">文字サイズ</span>
          <input
            className="min-h-10 border border-neutral-300 px-3 text-sm"
            disabled={disabled}
            max={mode === "short" ? 220 : 180}
            min={mode === "short" ? 20 : 12}
            placeholder={`既定 ${defaults.fontSize}`}
            step={2}
            type="number"
            value={fontSize ?? ""}
            onChange={(event) =>
              onChange(
                withStyleValue(
                  settings,
                  mode,
                  "fontSize",
                  event.target.value === "" ? undefined : Number(event.target.value)
                )
              )
            }
          />
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">縁取り幅</span>
          <input
            className="min-h-10 border border-neutral-300 px-3 text-sm"
            disabled={disabled}
            max={20}
            min={0}
            placeholder={`既定 ${defaults.outline}`}
            step={1}
            type="number"
            value={outline ?? ""}
            onChange={(event) =>
              onChange(
                withStyleValue(
                  settings,
                  mode,
                  "outline",
                  event.target.value === "" ? undefined : Number(event.target.value)
                )
              )
            }
          />
        </label>

        <ColorControl
          disabled={disabled}
          label="文字色"
          value={primaryColor}
          onChange={(value) =>
            onChange(withStyleValue(settings, mode, "primaryColor", value))
          }
        />

        <ColorControl
          disabled={disabled}
          label="縁取り色"
          value={outlineColor}
          onChange={(value) =>
            onChange(withStyleValue(settings, mode, "outlineColor", value))
          }
        />

        <fieldset className="sm:col-span-2">
          <legend className="text-sm font-medium text-neutral-700">
            縦位置
            <span className="ml-2 text-xs font-normal text-neutral-500">
              Y {position.y}px
            </span>
          </legend>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
            {verticalPresets.map((preset) => {
              const selected = selectedVerticalPreset?.id === preset.id;
              return (
                <button
                  aria-pressed={selected}
                  className={`min-h-12 border px-2 py-1.5 text-left ${
                    selected
                      ? "border-sky-700 bg-sky-50 text-sky-950"
                      : "border-neutral-300 bg-white text-neutral-700"
                  }`}
                  disabled={disabled}
                  key={preset.id}
                  type="button"
                  onClick={() =>
                    onChange(
                      withStyleValue(
                        settings,
                        mode,
                        "yPercent",
                        preset.percent
                      )
                    )
                  }
                >
                  <span className="block text-[11px] font-semibold">
                    {preset.label}
                  </span>
                  <span className="block text-[9px] text-neutral-500">
                    {preset.purpose}
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>

        <fieldset className="sm:col-span-2">
          <legend className="text-sm font-medium text-neutral-700">
            横位置
            <span className="ml-2 text-xs font-normal text-neutral-500">
              X {position.x}px
            </span>
          </legend>
          <div className="mt-2 grid grid-cols-5 gap-1.5">
            {HORIZONTAL_POSITION_PRESETS.map((preset) => {
              const selected = selectedHorizontalPreset?.id === preset.id;
              return (
                <button
                  aria-pressed={selected}
                  className={`min-h-10 border px-1 text-xs font-semibold ${
                    selected
                      ? "border-sky-700 bg-sky-50 text-sky-950"
                      : "border-neutral-300 bg-white text-neutral-700"
                  }`}
                  disabled={disabled}
                  key={preset.id}
                  title={preset.purpose}
                  type="button"
                  onClick={() =>
                    onChange(
                      withStyleValue(
                        settings,
                        mode,
                        "xPercent",
                        preset.percent
                      )
                    )
                  }
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <details className="border border-neutral-300 bg-neutral-50 sm:col-span-2">
          <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-neutral-700">
            位置を1%単位で微調整
          </summary>
          <div className="grid gap-4 border-t border-neutral-300 p-3 sm:grid-cols-2">
            <label className="flex flex-col gap-2">
              <span className="flex justify-between text-sm font-medium text-neutral-700">
                横位置
                <span className="text-xs font-normal tabular-nums">
                  {xPercent}% / X {position.x}px
                </span>
              </span>
              <input
                className="h-7 accent-sky-600"
                disabled={disabled}
                max={95}
                min={5}
                step={1}
                type="range"
                value={xPercent}
                onChange={(event) =>
                  onChange(
                    withStyleValue(
                      settings,
                      mode,
                      "xPercent",
                      Number(event.target.value)
                    )
                  )
                }
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="flex justify-between text-sm font-medium text-neutral-700">
                縦位置
                <span className="text-xs font-normal tabular-nums">
                  {yPercent.toFixed(1)}% / Y {position.y}px
                </span>
              </span>
              <input
                className="h-7 accent-sky-600"
                disabled={disabled}
                max={95}
                min={5}
                step={1}
                type="range"
                value={yPercent}
                onChange={(event) =>
                  onChange(
                    withStyleValue(
                      settings,
                      mode,
                      "yPercent",
                      Number(event.target.value)
                    )
                  )
                }
              />
            </label>
            {explicitYPercent === undefined ? (
              <p className="m-0 text-xs text-neutral-500 sm:col-span-2">
                保存済みの「上・中央・下＋余白」を現在の座標へ換算して表示しています。
                操作すると新しい座標方式へ切り替わります。
              </p>
            ) : null}
          </div>
        </details>
        </div>
      </div>
    </section>
  );
}
