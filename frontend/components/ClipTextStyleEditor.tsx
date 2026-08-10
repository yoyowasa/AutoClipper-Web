"use client";

import Image from "next/image";
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
  clipType: ExportType;
  disabled?: boolean;
  layout?: "stacked" | "workspace";
  selectedTarget?: ClipTextTarget;
  showPreview?: boolean;
  styles: ClipTextStyles;
  titleText: string;
  hookText: string;
  subtitleText: string;
  onChange: (target: ClipTextTarget, style: ClipTextStyle | null) => void;
  onSelectedTargetChange?: (target: ClipTextTarget) => void;
};

type ClipTextStylePreviewProps = {
  clipType: ExportType;
  displayMode?: "compact" | "workspace";
  selectedTarget: ClipTextTarget;
  shortTitleOutputEnabled?: boolean;
  shortTopBannerEnabled?: boolean;
  shortTopBannerUrl?: string;
  shortBottomBannerEnabled?: boolean;
  shortBottomBannerUrl?: string;
  styles: ClipTextStyles;
  titleText: string;
  hookText: string;
  subtitleText: string;
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
  displayMode = "compact",
  selectedTarget,
  shortTitleOutputEnabled,
  shortTopBannerEnabled = false,
  shortTopBannerUrl,
  shortBottomBannerEnabled = false,
  shortBottomBannerUrl,
  styles,
  titleText,
  hookText,
  subtitleText
}: ClipTextStylePreviewProps) {
  const availableTargets: ClipTextTarget[] =
    clipType === "short" ? ["title", "hook", "subtitle"] : ["subtitle"];
  const target = availableTargets.includes(selectedTarget)
    ? selectedTarget
    : availableTargets[0];
  const style = resolvedClipTextStyle(styles[target], target, clipType);
  const verticalPresets = verticalPositionPresets(clipType);
  const selectedVerticalPreset = matchingPositionPreset(
    verticalPresets,
    style.yPercent
  );
  const previewText = sampleText(target, titleText, hookText, subtitleText);
  const titleOutputDisabled =
    clipType === "short" &&
    target === "title" &&
    shortTitleOutputEnabled === false;
  const outputWidthPercent = clipType === "short" ? 10.8 : 19.2;
  const previewFontSizePercent = style.fontSize / outputWidthPercent;
  const previewOutlinePercent = style.outlineWidth / outputWidthPercent;
  const sizeClass =
    displayMode === "workspace"
      ? clipType === "short"
        ? "aspect-[9/16] w-full max-w-[230px] lg:h-full lg:max-h-full lg:w-auto lg:max-w-full"
        : "aspect-video w-full max-w-md lg:max-w-3xl"
      : clipType === "short"
        ? "aspect-[9/16] w-full max-w-[230px]"
        : "aspect-video w-full max-w-md";

  return (
    <div
      aria-label={`${TARGET_LABELS[target]}配置プレビュー`}
      className={`relative overflow-hidden border border-neutral-400 bg-[#25343A] ${sizeClass}`}
      style={{ containerType: "inline-size" }}
    >
      <div className="absolute inset-y-0 right-0 w-[36%] bg-[#82959C]" />
      <div className="absolute bottom-0 left-0 h-[18%] w-full bg-[#111A1E]" />
      {clipType === "short" && shortTopBannerUrl ? (
        <div
          aria-hidden="true"
          className={`pointer-events-none absolute inset-x-0 top-0 z-10 aspect-[3/1] overflow-hidden ${
            shortTopBannerEnabled ? "opacity-100" : "opacity-0"
          }`}
        >
          <Image
            fill
            unoptimized
            alt=""
            className="object-contain"
            draggable={false}
            loading="eager"
            sizes="(min-width: 1024px) 30vw, 230px"
            src={shortTopBannerUrl}
          />
        </div>
      ) : null}
      {clipType === "short" && shortBottomBannerUrl ? (
        <div
          aria-hidden="true"
          className={`pointer-events-none absolute inset-x-0 bottom-0 z-10 aspect-[3/1] overflow-hidden ${
            shortBottomBannerEnabled ? "opacity-100" : "opacity-0"
          }`}
        >
          <Image
            fill
            unoptimized
            alt=""
            className="object-contain"
            draggable={false}
            loading="eager"
            sizes="(min-width: 1024px) 30vw, 230px"
            src={shortBottomBannerUrl}
          />
        </div>
      ) : null}
      {verticalPresets.map((preset) => {
        const selected = selectedVerticalPreset?.id === preset.id;
        return (
          <div
            aria-hidden="true"
            className={`absolute left-0 z-20 w-full border-t ${
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
      {!titleOutputDisabled ? (
        <p
          className="absolute z-30 m-0 max-w-[90%] whitespace-pre-line text-center leading-[1.2]"
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
      ) : null}
    </div>
  );
}

export function ClipTextStyleEditor({
  clipType,
  disabled = false,
  layout = "stacked",
  selectedTarget,
  showPreview = true,
  styles,
  titleText,
  hookText,
  subtitleText,
  onChange,
  onSelectedTargetChange
}: ClipTextStyleEditorProps) {
  const [internalTarget, setInternalTarget] = useState<ClipTextTarget>(
    clipType === "short" ? "title" : "subtitle"
  );
  const availableTargets: ClipTextTarget[] =
    clipType === "short" ? ["title", "hook", "subtitle"] : ["subtitle"];
  const requestedTarget = selectedTarget ?? internalTarget;
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

  function changeTarget(nextTarget: ClipTextTarget) {
    setInternalTarget(nextTarget);
    onSelectedTargetChange?.(nextTarget);
  }

  function applyUsagePreset(preset: UsagePreset) {
    updateStyle({
      fontSize: preset.fontSize,
      xPercent: preset.xPercent,
      yPercent: preset.yPercent
    });
  }

  const panelClass =
    "min-h-0 border-b border-neutral-300 p-3 2xl:h-full 2xl:overflow-y-auto 2xl:border-b-0";

  return (
    <section
      className={
        layout === "workspace"
          ? "grid min-h-0 bg-white 2xl:col-span-3 2xl:h-full 2xl:grid-cols-3 2xl:divide-x 2xl:divide-neutral-300"
          : "mt-4 grid border-t border-neutral-300 bg-white lg:grid-cols-3 lg:divide-x lg:divide-neutral-300"
      }
    >
      <div className={panelClass}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold text-neutral-950">書体・サイズ</h4>
            <p className="mt-0.5 text-[10px] text-neutral-500">
              選択中のclipだけに反映
            </p>
          </div>
          <span
            className={`px-2 py-1 text-[10px] font-semibold ${
              storedStyle
                ? "bg-sky-100 text-sky-800"
                : "bg-neutral-200 text-neutral-600"
            }`}
          >
            {storedStyle ? "個別設定" : "既定値"}
          </span>
        </div>

        <div
          aria-label="文字スタイルの対象"
          className={`mt-2 grid border border-neutral-300 bg-neutral-100 p-1 ${
            availableTargets.length === 1 ? "grid-cols-1" : "grid-cols-3"
          }`}
          role="group"
        >
          {availableTargets.map((item) => (
            <button
              aria-pressed={target === item}
              className={`min-h-8 px-2 text-[11px] font-semibold ${
                target === item ? "bg-neutral-950 text-white" : "text-neutral-600"
              }`}
              disabled={disabled}
              key={item}
              type="button"
              onClick={() => changeTarget(item)}
            >
              {TARGET_LABELS[item]}
            </button>
          ))}
        </div>

        <label className="mt-2 flex flex-col gap-1 text-xs font-semibold text-neutral-700">
          {TARGET_LABELS[target]}の書体
          <select
            className="min-h-9 border border-neutral-300 bg-white px-2 text-sm font-normal"
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

        <div className="mt-2 grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1 text-xs font-semibold text-neutral-700">
            文字サイズ
            <input
              aria-label={`${TARGET_LABELS[target]}文字サイズ`}
              className="h-9 border border-neutral-300 bg-white px-2 text-sm font-normal tabular-nums"
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
          <label className="flex flex-col gap-1 text-xs font-semibold text-neutral-700">
            縁の太さ
            <input
              className="h-9 border border-neutral-300 bg-white px-2 text-sm font-normal"
              disabled={disabled}
              max={20}
              min={0}
              type="number"
              value={style.outlineWidth}
              onChange={(event) =>
                updateStyle({ outlineWidth: Number(event.target.value) })
              }
            />
          </label>
        </div>
      </div>

      <div className={panelClass}>
        <h4 className="text-sm font-semibold text-neutral-950">位置</h4>
        <p className="mt-0.5 text-[10px] text-neutral-500">
          用途プリセットまたは規定位置から選択
        </p>

        {clipType === "short" ? (
          <fieldset className="mt-2">
            <legend className="text-xs font-semibold text-neutral-700">
              用途から設定
            </legend>
            <div className="mt-1 grid gap-1">
              {SHORT_USAGE_PRESETS[target].map((preset) => (
                <button
                  className="min-h-9 border border-neutral-300 bg-white px-2 py-1 text-left disabled:text-neutral-400"
                  disabled={disabled}
                  key={preset.id}
                  type="button"
                  onClick={() => applyUsagePreset(preset)}
                >
                  <span className="text-[11px] font-semibold text-neutral-900">
                    {preset.label}
                  </span>
                  <span className="ml-2 text-[9px] text-neutral-500">
                    {preset.description}
                  </span>
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        <fieldset className="mt-2">
          <legend className="text-xs font-semibold text-neutral-700">
            縦位置
            <span className="ml-2 font-normal text-neutral-500">
              Y {currentPosition.y}px
            </span>
          </legend>
          <div className="mt-1 grid grid-cols-2 gap-1">
            {verticalPresets.map((preset) => {
              const selected = selectedVerticalPreset?.id === preset.id;
              return (
                <button
                  aria-pressed={selected}
                  className={`min-h-9 border px-2 py-1 text-left ${
                    selected
                      ? "border-sky-700 bg-sky-50 text-sky-950"
                      : "border-neutral-300 bg-white text-neutral-700"
                  }`}
                  disabled={disabled}
                  key={preset.id}
                  type="button"
                  onClick={() => updateStyle({ yPercent: preset.percent })}
                >
                  <span className="block text-[10px] font-semibold">
                    {preset.label}
                  </span>
                  <span className="block text-[8px] text-neutral-500">
                    {preset.purpose}
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>

        <fieldset className="mt-2">
          <legend className="text-xs font-semibold text-neutral-700">
            横位置
            <span className="ml-2 font-normal text-neutral-500">
              X {currentPosition.x}px
            </span>
          </legend>
          <div className="mt-1 grid grid-cols-5 gap-1">
            {HORIZONTAL_POSITION_PRESETS.map((preset) => {
              const selected = selectedHorizontalPreset?.id === preset.id;
              return (
                <button
                  aria-pressed={selected}
                  className={`min-h-8 border px-1 text-[9px] font-semibold ${
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

        <details className="mt-2 border border-neutral-300 bg-neutral-50">
          <summary className="cursor-pointer px-2 py-2 text-[11px] font-semibold text-neutral-700">
            位置を1%単位で微調整
          </summary>
          <div className="grid gap-2 border-t border-neutral-300 p-2">
            <label className="flex flex-col gap-1 text-[11px] font-semibold text-neutral-700">
              <span className="flex justify-between">
                横位置
                <span className="font-normal tabular-nums">
                  {style.xPercent}% / X {currentPosition.x}px
                </span>
              </span>
              <input
                className="h-5 accent-sky-600"
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
            <label className="flex flex-col gap-1 text-[11px] font-semibold text-neutral-700">
              <span className="flex justify-between">
                縦位置
                <span className="font-normal tabular-nums">
                  {style.yPercent}% / Y {currentPosition.y}px
                </span>
              </span>
              <input
                className="h-5 accent-sky-600"
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
      </div>

      <div className={`${panelClass} 2xl:border-b-0`}>
        <h4 className="text-sm font-semibold text-neutral-950">色</h4>
        <p className="mt-0.5 text-[10px] text-neutral-500">
          文字と縁取りを個別に設定
        </p>

        <fieldset className="mt-2">
          <legend className="text-xs font-semibold text-neutral-700">文字色</legend>
          <div className="mt-1 flex min-h-9 flex-wrap items-center gap-1.5">
            <input
              aria-label="文字色を選択"
              className="h-9 w-10 border border-neutral-300 bg-white p-1"
              disabled={disabled}
              type="color"
              value={style.primaryColor}
              onChange={(event) =>
                updateStyle({ primaryColor: event.target.value.toUpperCase() })
              }
            />
            {COLOR_PRESETS.map((color) => (
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

        <fieldset className="mt-3">
          <legend className="text-xs font-semibold text-neutral-700">縁取り色</legend>
          <div className="mt-1 flex min-h-9 flex-wrap items-center gap-1.5">
            <input
              aria-label="縁取り色を選択"
              className="h-9 w-10 border border-neutral-300 bg-white p-1"
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

        {showPreview ? (
          <div className="mt-3 flex justify-center bg-neutral-100 p-2">
            <ClipTextStylePreview
              clipType={clipType}
              selectedTarget={target}
              styles={styles}
              subtitleText={subtitleText}
              titleText={titleText}
              hookText={hookText}
            />
          </div>
        ) : null}

        <button
          className="mt-3 min-h-9 w-full border border-neutral-300 px-3 text-xs font-semibold text-neutral-700 disabled:text-neutral-400"
          disabled={disabled || !storedStyle}
          type="button"
          onClick={() => onChange(target, null)}
        >
          {TARGET_LABELS[target]}の個別設定を解除
        </button>
      </div>
    </section>
  );
}
