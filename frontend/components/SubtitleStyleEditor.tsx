"use client";

import { useState } from "react";

import type { ClipSettings } from "../lib/types";
import {
  SubtitleStylePreview,
  type SubtitlePreviewMode
} from "./SubtitleStylePreview";

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
    primaryColor: "shortSubtitlePrimaryColor",
    outlineColor: "shortSubtitleOutlineColor"
  },
  normal: {
    fontName: "normalSubtitleFontName",
    fontSize: "normalSubtitleFontSize",
    outline: "normalSubtitleOutline",
    lowerMargin: "normalSubtitleLowerMargin",
    alignment: "normalSubtitleAlignment",
    primaryColor: "normalSubtitlePrimaryColor",
    outlineColor: "normalSubtitleOutlineColor"
  }
};

const STYLE_DEFAULTS = {
  short: {
    fontSize: 76,
    outline: 5,
    lowerMargin: 250,
    alignment: 2
  },
  normal: {
    fontSize: 65,
    outline: 4,
    lowerMargin: 86,
    alignment: 2
  }
} as const;

const SUBTITLE_FONT_OPTIONS = [
  { value: "", label: "標準ゴシック（Noto Sans CJK JP）" },
  {
    value: "Source Han Sans JP Heavy",
    label: "極太ゴシック（Source Han Sans JP Heavy）"
  },
  { value: "Noto Serif CJK JP", label: "明朝（Noto Serif CJK JP）" },
  { value: "Noto Sans Mono CJK JP", label: "等幅ゴシック（Noto Sans Mono CJK JP）" }
] as const;

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

  return (
    <section className="border-t border-neutral-200 pt-5 md:col-span-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-neutral-950">字幕スタイル</h2>
          <div
            aria-label="字幕スタイルの対象"
            className="mt-3 inline-flex border border-neutral-300 bg-neutral-100 p-1"
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

      <SubtitleStylePreview mode={mode} settings={settings} />

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
            {SUBTITLE_FONT_OPTIONS.map((font) => (
              <option key={font.value || "default"} value={font.value}>
                {font.label}
              </option>
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

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">表示位置</span>
          <select
            className="min-h-10 border border-neutral-300 bg-white px-3 text-sm"
            disabled={disabled}
            value={(alignment ?? "").toString()}
            onChange={(event) =>
              onChange(
                withStyleValue(
                  settings,
                  mode,
                  "alignment",
                  event.target.value === "" ? undefined : Number(event.target.value)
                )
              )
            }
          >
            <option value="">標準（下）</option>
            <option value="2">下</option>
            <option value="5">中央</option>
            <option value="8">上</option>
          </select>
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">画面端からの余白</span>
          <input
            className="min-h-10 border border-neutral-300 px-3 text-sm"
            disabled={disabled || alignment === 5}
            max={mode === "short" ? 1600 : 900}
            min={0}
            placeholder={`既定 ${defaults.lowerMargin}`}
            step={10}
            type="number"
            value={lowerMargin ?? ""}
            onChange={(event) =>
              onChange(
                withStyleValue(
                  settings,
                  mode,
                  "lowerMargin",
                  event.target.value === "" ? undefined : Number(event.target.value)
                )
              )
            }
          />
        </label>
      </div>
    </section>
  );
}
