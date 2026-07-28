"use client";

import { useState } from "react";

import {
  CLIP_TEXT_FONT_GROUPS,
  clipTextFontFamily,
  clipTextFontWeight,
  resolvedClipTextStyle,
  type ClipTextTarget
} from "../lib/clipTextStyle";
import {
  HORIZONTAL_POSITION_PRESETS,
  matchingPositionPreset,
  positionPixels,
  verticalPositionPresets
} from "../lib/textPositionPresets";
import type { ClipTextStyle, ExportType } from "../lib/types";

type ClipTextStyles = Record<ClipTextTarget, ClipTextStyle | null>;

type ClipTextStyleEditorProps = {
  activeTarget?: ClipTextTarget;
  clipType: ExportType;
  disabled?: boolean;
  hidePreview?: boolean;
  layout?: "stacked" | "wide";
  styles: ClipTextStyles;
  titleText: string;
  hookText: string;
  subtitleText: string;
  onActiveTargetChange?: (target: ClipTextTarget) => void;
  onChange: (target: ClipTextTarget, style: ClipTextStyle | null) => void;
};

type ClipTextStylePreviewProps = {
  clipType: ExportType;
  hookText: string;
  styles: ClipTextStyles;
  subtitleText: string;
  target: ClipTextTarget;
  titleText: string;
};

const TARGET_LABELS: Record<ClipTextTarget, string> = {
  title: "タイトル",
  hook: "フック",
  subtitle: "字幕"
};

const COLOR_PRESETS = ["#FFFFFF", "#FFF200", "#5EE7F7", "#FF8FAB", "#9BFF9B", "#000000"];

type UsagePreset = {
  id: string;
  label: string;
  description: string;
  fontSize: number;
  xPercent: number;
  yPercent: number;
};

const SHORT_USAGE_PRESETS: Record<ClipTextTarget, ReadonlyArray<UsagePreset>> = {
  title: [
    {
      id: "title",
      label: "タイトル上",
      description: "100px・Y 240",
      fontSize: 100,
      xPercent: 50,
      yPercent: 12.5
    }
  ],
  hook: [
    {
      id: "hook",
      label: "冒頭フック",
      description: "112px・Y 360",
      fontSize: 112,
      xPercent: 50,
      yPercent: 18.75
    }
  ],
  subtitle: [
    {
      id: "dialogue",
      label: "通常の会話字幕",
      description: "70px・Y 1320",
      fontSize: 70,
      xPercent: 50,
      yPercent: 68.75
    },
    {
      id: "keyword",
      label: "強調キーワード",
      description: "96px・Y 1320",
      fontSize: 96,
      xPercent: 50,
      yPercent: 68.75
    },
    {
      id: "punchline",
      label: "オチ・ツッコミ",
      description: "112px・Y 1100",
      fontSize: 112,
      xPercent: 50,
      yPercent: 57.3
    }
  ]
};

function sampleText(
  target: ClipTextTarget,
  titleText: string,
  hookText: string,
  subtitleText: string
): string {
  if (target === "title") {
    return titleText.trim() || "表示タイトル";
  }
  if (target === "hook") {
    return hookText.trim() || "冒頭フック";
  }
  return subtitleText.trim() || "字幕の位置と見た目を確認";
}

export function ClipTextStylePreview({
  clipType,
  hookText,
  styles,
  subtitleText,
  target,
  titleText
}: ClipTextStylePreviewProps) {
  const availableTargets: ClipTextTarget[] =
    clipType === "short" ? ["title", "hook", "subtitle"] : ["subtitle"];
  const resolvedTarget = availableTargets.includes(target) ? target : availableTargets[0];
  const style = resolvedClipTextStyle(styles[resolvedTarget], resolvedTarget, clipType);
  const verticalPresets = verticalPositionPresets(clipType);
  const selectedVerticalPreset = matchingPositionPreset(
    verticalPresets,
    style.yPercent
  );
  const previewText = sampleText(
    resolvedTarget,
    titleText,
    hookText,
    subtitleText
  );
  const outputWidthPercent = clipType === "short" ? 10.8 : 19.2;
  const previewFontSizePercent = style.fontSize / outputWidthPercent;
  const previewOutlinePercent = style.outlineWidth / outputWidthPercent;

  return (
    <div
      aria-label={`${TARGET_LABELS[resolvedTarget]}配置プレビュー`}
      className={`relative w-full overflow-hidden border border-neutral-400 bg-[#25343A] ${
        clipType === "short" ? "aspect-[9/16]" : "aspect-video"
      }`}
      style={{ containerType: "inline-size" }}
    >
      <div className="absolute inset-y-0 right-0 w-[36%] bg-[#82959C]" />
      <div className="absolute bottom-0 left-0 h-[18%] w-full bg-[#111A1E]" />
      {verticalPresets.map((preset) => {
        const selected = selectedVerticalPreset?.id === preset.id;
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
        className="absolute m-0 max-w-[90%] whitespace-pre-line text-center leading-[1.2]"
        style={{
          color: style.primaryColor,
          fontFamily: clipTextFontFamily(style.fontPreset),
          fontSize: `clamp(4px, ${previewFontSizePercent}cqw, 52px)`,
          fontWeight: clipTextFontWeight(style.fontPreset),
          left: `${style.xPercent}%`,
          top: `${style.yPercent}%`,
          transform: "translate(-50%, -50%)",
          WebkitTextStroke: `clamp(0px, ${previewOutlinePercent}cqw, 4px) ${style.outlineColor}`,
          textShadow: `0 2px 2px ${style.outlineColor}`
        }}
      >
        {previewText}
      </p>
    </div>
  );
}

export function ClipTextStyleEditor({
  activeTarget,
  clipType,
  disabled = false,
  hidePreview = false,
  layout = "stacked",
  styles,
  titleText,
  hookText,
  subtitleText,
  onActiveTargetChange,
  onChange
}: ClipTextStyleEditorProps) {
  const [internalTarget, setInternalTarget] = useState<ClipTextTarget>(
    clipType === "short" ? "title" : "subtitle"
  );
  const availableTargets: ClipTextTarget[] =
    clipType === "short" ? ["title", "hook", "subtitle"] : ["subtitle"];
  const requestedTarget = activeTarget ?? internalTarget;
  const target = availableTargets.includes(requestedTarget)
    ? requestedTarget
    : availableTargets[0];
  const storedStyle = styles[target];
  const style = resolvedClipTextStyle(storedStyle, target, clipType);
  const verticalPresets = verticalPositionPresets(clipType);
  const selectedHorizontalPreset = matchingPositionPreset(
    HORIZONTAL_POSITION_PRESETS,
    style.xPercent
  );
  const selectedVerticalPreset = matchingPositionPreset(
    verticalPresets,
    style.yPercent
  );
  const currentPosition = positionPixels(
    clipType,
    style.xPercent,
    style.yPercent
  );

  function updateStyle(patch: Partial<ClipTextStyle>) {
    onChange(target, { ...style, ...patch });
  }

  function selectTarget(nextTarget: ClipTextTarget) {
    if (activeTarget === undefined) {
      setInternalTarget(nextTarget);
    }
    onActiveTargetChange?.(nextTarget);
  }

  function applyUsagePreset(preset: UsagePreset) {
    updateStyle({
      fontSize: preset.fontSize,
      xPercent: preset.xPercent,
      yPercent: preset.yPercent
    });
  }

  return (
    <section
      className={
        layout === "wide" ? "min-w-0" : "mt-4 border-t border-neutral-300 pt-4"
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h4 className="text-sm font-semibold text-neutral-950">文字スタイル</h4>
          <p className="mt-1 text-[11px] text-neutral-500">
            選択中のclipだけに反映します
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <label className="flex min-h-9 items-center gap-2 border border-sky-300 bg-sky-50 px-2 text-[11px] font-semibold text-sky-950">
            サイズ
            <input
              aria-label={`${TARGET_LABELS[target]}文字サイズ`}
              className="h-7 w-16 border border-neutral-300 bg-white px-2 text-sm font-normal tabular-nums"
              disabled={disabled}
              max={220}
              min={20}
              type="number"
              value={style.fontSize}
              onChange={(event) =>
                updateStyle({ fontSize: Number(event.target.value) })
              }
            />
          </label>
          <span
            className={`px-2 py-1 text-[11px] font-semibold ${
              storedStyle
                ? "bg-sky-100 text-sky-800"
                : "bg-neutral-200 text-neutral-600"
            }`}
          >
            {storedStyle ? "個別設定" : "既定値から編集"}
          </span>
          {storedStyle ? (
            <button
              className="min-h-8 border border-neutral-300 bg-white px-2 text-[11px] font-semibold text-neutral-700 disabled:text-neutral-400"
              disabled={disabled}
              type="button"
              onClick={() => onChange(target, null)}
            >
              既定値に戻す
            </button>
          ) : null}
        </div>
      </div>

      <div
        aria-label="文字スタイルの対象"
        className={`mt-3 grid border border-neutral-300 bg-neutral-100 p-1 ${
          availableTargets.length === 1 ? "grid-cols-1" : "grid-cols-3"
        }`}
        role="group"
      >
        {availableTargets.map((item) => (
          <button
            aria-pressed={target === item}
            className={`min-h-9 px-2 text-xs font-semibold ${
              target === item ? "bg-neutral-950 text-white" : "text-neutral-600"
            }`}
            disabled={disabled}
            key={item}
            type="button"
            onClick={() => selectTarget(item)}
          >
            {TARGET_LABELS[item]}
          </button>
        ))}
      </div>

      <div className="mt-3 grid gap-3 border border-sky-200 bg-sky-50 p-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-xs font-semibold text-neutral-700 sm:col-span-2">
          {TARGET_LABELS[target]}の書体
          <select
            className="min-h-10 border border-neutral-300 bg-white px-3 text-sm font-normal"
            disabled={disabled}
            value={style.fontPreset}
            onChange={(event) =>
              updateStyle({
                fontPreset: event.target.value as ClipTextStyle["fontPreset"]
              })
            }
          >
            {CLIP_TEXT_FONT_GROUPS.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs font-semibold text-neutral-700">
          縁の太さ
          <input
            className="h-10 border border-neutral-300 bg-white px-3 text-sm font-normal"
            disabled={disabled}
            max={20}
            min={0}
            type="number"
            value={style.outlineWidth}
            onChange={(event) => updateStyle({ outlineWidth: Number(event.target.value) })}
          />
        </label>
        <p className="text-[11px] leading-5 text-sky-900 sm:col-span-2">
          数値を変えると、選択中のclip専用設定として保存できます。
        </p>
      </div>

      {!hidePreview ? (
        <div className="mt-3 flex justify-center bg-neutral-100 p-3">
          <div
            className={
              clipType === "short" ? "w-full max-w-[230px]" : "w-full max-w-md"
            }
          >
            <ClipTextStylePreview
              clipType={clipType}
              hookText={hookText}
              styles={styles}
              subtitleText={subtitleText}
              target={target}
              titleText={titleText}
            />
          </div>
        </div>
      ) : null}

      {clipType === "short" ? (
        <fieldset className="mt-4">
          <legend className="text-xs font-semibold text-neutral-700">
            用途から設定
          </legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {SHORT_USAGE_PRESETS[target].map((preset) => (
              <button
                className="min-h-12 border border-neutral-300 bg-white px-2 py-2 text-left disabled:text-neutral-400"
                disabled={disabled}
                key={preset.id}
                type="button"
                onClick={() => applyUsagePreset(preset)}
              >
                <span className="block text-xs font-semibold text-neutral-900">
                  {preset.label}
                </span>
                <span className="mt-0.5 block text-[10px] text-neutral-500">
                  {preset.description}
                </span>
              </button>
            ))}
          </div>
        </fieldset>
      ) : null}

      <div className="mt-4 grid gap-4">
        <fieldset>
          <legend className="text-xs font-semibold text-neutral-700">
            縦位置
            <span className="ml-2 font-normal text-neutral-500">
              Y {currentPosition.y}px
            </span>
          </legend>
          <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">
            {verticalPresets.map((preset) => {
              const selected = selectedVerticalPreset?.id === preset.id;
              return (
                <button
                  aria-pressed={selected}
                  className={`min-h-11 border px-2 py-1.5 text-left ${
                    selected
                      ? "border-sky-700 bg-sky-50 text-sky-950"
                      : "border-neutral-300 bg-white text-neutral-700"
                  }`}
                  disabled={disabled}
                  key={preset.id}
                  type="button"
                  onClick={() => updateStyle({ yPercent: preset.percent })}
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

        <fieldset>
          <legend className="text-xs font-semibold text-neutral-700">
            横位置
            <span className="ml-2 font-normal text-neutral-500">
              X {currentPosition.x}px
            </span>
          </legend>
          <div className="mt-2 grid grid-cols-5 gap-1">
            {HORIZONTAL_POSITION_PRESETS.map((preset) => {
              const selected = selectedHorizontalPreset?.id === preset.id;
              return (
                <button
                  aria-pressed={selected}
                  className={`min-h-10 border px-1 text-[10px] font-semibold ${
                    selected
                      ? "border-sky-700 bg-sky-50 text-sky-950"
                      : "border-neutral-300 bg-white text-neutral-700"
                  }`}
                  disabled={disabled}
                  key={preset.id}
                  title={preset.purpose}
                  type="button"
                  onClick={() => updateStyle({ xPercent: preset.percent })}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        </fieldset>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <fieldset>
          <legend className="text-xs font-semibold text-neutral-700">文字色</legend>
          <div className="mt-1 flex min-h-10 items-center gap-1.5">
            <input
              aria-label="文字色を選択"
              className="h-10 w-11 border border-neutral-300 bg-white p-1"
              disabled={disabled}
              type="color"
              value={style.primaryColor}
              onChange={(event) =>
                updateStyle({ primaryColor: event.target.value.toUpperCase() })
              }
            />
            {COLOR_PRESETS.slice(0, 4).map((color) => (
              <button
                aria-label={`文字色 ${color}`}
                className="h-7 w-7 border border-neutral-400"
                disabled={disabled}
                key={color}
                style={{ backgroundColor: color }}
                type="button"
                onClick={() => updateStyle({ primaryColor: color })}
              />
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="text-xs font-semibold text-neutral-700">縁取り色</legend>
          <div className="mt-1 flex min-h-10 items-center gap-1.5">
            <input
              aria-label="縁取り色を選択"
              className="h-10 w-11 border border-neutral-300 bg-white p-1"
              disabled={disabled}
              type="color"
              value={style.outlineColor}
              onChange={(event) =>
                updateStyle({ outlineColor: event.target.value.toUpperCase() })
              }
            />
            {["#000000", "#FFFFFF", "#1F2937", "#7F1D1D"].map((color) => (
              <button
                aria-label={`縁取り色 ${color}`}
                className="h-7 w-7 border border-neutral-400"
                disabled={disabled}
                key={color}
                style={{ backgroundColor: color }}
                type="button"
                onClick={() => updateStyle({ outlineColor: color })}
              />
            ))}
          </div>
        </fieldset>

      </div>

      <details className="mt-3 border border-neutral-300 bg-neutral-50">
        <summary className="cursor-pointer px-3 py-2 text-xs font-semibold text-neutral-700">
          位置を1%単位で微調整
        </summary>
        <div className="grid gap-3 border-t border-neutral-300 p-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs font-semibold text-neutral-700">
            <span className="flex justify-between">
              横位置
              <span className="font-normal tabular-nums">
                {style.xPercent}% / X {currentPosition.x}px
              </span>
            </span>
            <input
              className="h-6 accent-sky-600"
              disabled={disabled}
              max={95}
              min={5}
              step={1}
              type="range"
              value={style.xPercent}
              onChange={(event) =>
                updateStyle({ xPercent: Number(event.target.value) })
              }
            />
          </label>

          <label className="flex flex-col gap-1 text-xs font-semibold text-neutral-700">
            <span className="flex justify-between">
              縦位置
              <span className="font-normal tabular-nums">
                {style.yPercent}% / Y {currentPosition.y}px
              </span>
            </span>
            <input
              className="h-6 accent-sky-600"
              disabled={disabled}
              max={95}
              min={5}
              step={1}
              type="range"
              value={style.yPercent}
              onChange={(event) =>
                updateStyle({ yPercent: Number(event.target.value) })
              }
            />
          </label>
        </div>
      </details>

      <button
        className="mt-3 min-h-9 w-full border border-neutral-300 px-3 text-xs font-semibold text-neutral-700 disabled:text-neutral-400"
        disabled={disabled || !storedStyle}
        type="button"
        onClick={() => onChange(target, null)}
      >
        {TARGET_LABELS[target]}の個別設定を解除
      </button>
    </section>
  );
}
