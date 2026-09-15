"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import {
  CLIP_TEXT_FONT_GROUPS,
  assPreviewFontMetrics,
  clipTextFontWeight,
  resolvedClipTextStyle,
  subtitleFontFamily,
  type ClipTextTarget
} from "../lib/clipTextStyle";
import {
  HORIZONTAL_POSITION_PRESETS,
  matchingPositionPreset,
  verticalPositionPresets
} from "../lib/textPositionPresets";
import {
  fitOverlayPreviewText,
  splitSubtitlePreviewLines
} from "../lib/subtitlePreview";
import type {
  ClipTextFontPreset,
  ClipTextStyle,
  ExportType,
  ResolvedClipTextStyle
} from "../lib/types";

type ClipTextStyles = Record<ClipTextTarget, ClipTextStyle | null>;
type ResolvedClipTextStyles = Record<
  ClipTextTarget,
  ResolvedClipTextStyle | null
>;

type ClipTextStyleEditorProps = {
  scopeDescription?: string;
  subtitleScopeLabel?: string;
  onCommonSubtitleStyle?: () => void;
  clipType: ExportType;
  disabled?: boolean;
  layout?: "stacked" | "workspace";
  selectedTarget?: ClipTextTarget;
  showPreview?: boolean;
  shortTitleOutputEnabled?: boolean;
  shortTopBannerEnabled?: boolean;
  shortTopBannerUrl?: string;
  shortBottomBannerEnabled?: boolean;
  shortBottomBannerUrl?: string;
  styles: ClipTextStyles;
  resolvedStyles: ResolvedClipTextStyles;
  defaultResolvedStyles: ResolvedClipTextStyles;
  subtitleMaxCharsPerLine?: number | null;
  subtitleMaxLines?: number | null;
  previewWidth?: number | null;
  previewHeight?: number | null;
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
  resolvedStyles: ResolvedClipTextStyles;
  defaultResolvedStyles: ResolvedClipTextStyles;
  subtitleMaxCharsPerLine?: number | null;
  subtitleMaxLines?: number | null;
  previewWidth?: number | null;
  previewHeight?: number | null;
  titleText: string;
  hookText: string;
  subtitleText: string;
};

export type ClipTextOverlayProps = {
  clipType: ExportType;
  target: ClipTextTarget;
  style: ClipTextStyle | null;
  resolvedStyle: ResolvedClipTextStyle | null;
  defaultResolvedStyle: ResolvedClipTextStyle | null;
  subtitleMaxCharsPerLine?: number | null;
  subtitleMaxLines?: number | null;
  previewWidth?: number | null;
  text: string;
};

const TARGET_LABELS: Record<ClipTextTarget, string> = {
  title: "タイトル",
  hook: "フック",
  subtitle: "字幕"
};

const COLOR_PRESETS = [
  "#FFFFFF", "#FFF200", "#5EE7F7", "#FF8FAB", "#9BFF9B",
  "#FF4040", "#FF9F43", "#4080FF", "#B57BFF", "#000000"
];

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

function styleDraftFromResolved(style: ResolvedClipTextStyle): ClipTextStyle {
  const xPercent =
    style.positionMode === "layout"
      ? Math.min(95, Math.max(5, style.xPercent))
      : style.xPercent;
  const yPercent =
    style.positionMode === "layout"
      ? Math.min(95, Math.max(5, style.yPercent))
      : style.yPercent;
  return {
    fontPreset: style.fontPreset,
    fontName: style.fontName,
    bold: style.bold,
    fontSize: style.fontSize,
    primaryColor: style.primaryColor,
    outlineColor: style.outlineColor,
    outlineWidth: style.outlineWidth,
    outerOutlineWidth: style.outerOutlineWidth ?? 0,
    outerOutlineColor: style.outerOutlineColor ?? "#FFFFFF",
    xPercent,
    yPercent,
    positionMode: style.positionMode
  };
}

function alignmentTransform(alignment: number): string {
  const normalized = Math.min(9, Math.max(1, Math.trunc(alignment)));
  const column = (normalized - 1) % 3;
  const row = Math.floor((normalized - 1) / 3);
  const translateX = column === 0 ? 0 : column === 1 ? -50 : -100;
  const translateY = row === 0 ? -100 : row === 1 ? -50 : 0;
  return `translate(${translateX}%, ${translateY}%)`;
}

export function ClipTextOverlay({
  clipType,
  target,
  style: storedStyle,
  resolvedStyle,
  defaultResolvedStyle,
  subtitleMaxCharsPerLine,
  subtitleMaxLines,
  previewWidth,
  text
}: ClipTextOverlayProps) {
  const style = resolvedClipTextStyle(
    storedStyle,
    defaultResolvedStyle ?? resolvedStyle,
    target,
    clipType
  );
  const lineLimit =
    target === "title" || target === "hook"
      ? 20
      : (subtitleMaxCharsPerLine ?? (clipType === "short" ? 16 : 28));
  const maxLines =
    target === "title" || target === "hook"
      ? 2
      : Math.min(2, Math.max(1, subtitleMaxLines ?? 2));
  const outputWidth = previewWidth ?? (clipType === "short" ? 1080 : 1920);
  const fontMetrics = assPreviewFontMetrics(style.fontName);
  const textForFit =
    target === "subtitle"
      ? splitSubtitlePreviewLines(text, lineLimit, maxLines)
      : text;
  const overlayFit = fitOverlayPreviewText(textForFit, {
    outputWidth,
    fontSize: style.fontSize,
    fontSizeScale: fontMetrics.fontSizeScale,
    marginX: style.marginX,
    outlineWidth: style.outlineWidth + (style.outerOutlineWidth ?? 0),
    shadow: style.shadow,
    alignment: style.alignment,
    xPercent: style.xPercent,
    maxLines
  });
  const previewText = overlayFit.lines.join("\n");
  if (!previewText) {
    return null;
  }
  const effectiveFontSize = overlayFit.effectiveFontSize;
  const fontSizePercent =
    ((effectiveFontSize * fontMetrics.fontSizeScale) / outputWidth) * 100;
  const outlinePercent = (style.outlineWidth / outputWidth) * 200;
  const shadowPercent = (style.shadow / outputWidth) * 100;
  return (<>
    {(style.outerOutlineWidth ?? 0) > 0 ? <p aria-hidden="true"
      className="pointer-events-none absolute z-30 m-0 max-w-none whitespace-pre text-center"
      style={{ color: style.primaryColor, fontFamily: subtitleFontFamily(style.fontName),
        fontSize: `${fontSizePercent}cqw`, fontWeight: style.fontPreset ? clipTextFontWeight(style.fontPreset) : style.bold ? 700 : 400,
        lineHeight: fontMetrics.lineHeight, left: `${style.xPercent}%`, top: `${style.yPercent}%`,
        transform: alignmentTransform(style.alignment), paintOrder: "stroke fill",
        WebkitTextStroke: `${(style.outlineWidth + (style.outerOutlineWidth ?? 0)) / outputWidth * 200}cqw ${style.outerOutlineColor ?? "#FFFFFF"}`
      }}>{previewText}</p> : null}
    <p
      aria-hidden="true"
      className="pointer-events-none absolute z-30 m-0 max-w-none whitespace-pre text-center"
      data-overlay-fits={String(overlayFit.fits)}
      style={{
        color: style.primaryColor,
        fontFamily: subtitleFontFamily(style.fontName),
        fontSize: `${fontSizePercent}cqw`,
        fontWeight:
          style.fontPreset !== null
            ? clipTextFontWeight(style.fontPreset)
            : style.bold
              ? 700
              : 400,
        lineHeight: fontMetrics.lineHeight,
        left: `${style.xPercent}%`,
        top: `${style.yPercent}%`,
        transform: alignmentTransform(style.alignment),
        WebkitTextStroke: `${outlinePercent}cqw ${style.outlineColor}`,
        paintOrder: "stroke fill",
        textShadow: `${shadowPercent}cqw ${shadowPercent}cqw 0 rgba(0, 0, 0, 0.5)`
      }}
    >
      {previewText}
    </p>
  </>);
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
  resolvedStyles,
  defaultResolvedStyles,
  subtitleMaxCharsPerLine,
  subtitleMaxLines,
  previewWidth,
  previewHeight,
  titleText,
  hookText,
  subtitleText
}: ClipTextStylePreviewProps) {
  const availableTargets: ClipTextTarget[] = ["title", "hook", "subtitle"];
  const target = availableTargets.includes(selectedTarget)
    ? selectedTarget
    : availableTargets[0];
  const style = resolvedClipTextStyle(
    styles[target],
    defaultResolvedStyles[target] ?? resolvedStyles[target],
    target,
    clipType
  );
  const verticalPresets = verticalPositionPresets(clipType);
  const selectedVerticalPreset = matchingPositionPreset(
    verticalPresets,
    style.yPercent
  );
  const previewLineLimit =
    target === "title" || target === "hook"
      ? 20
      : (subtitleMaxCharsPerLine ?? (clipType === "short" ? 16 : 28));
  const previewMaxLines =
    target === "title" || target === "hook"
      ? 2
      : Math.min(2, Math.max(1, subtitleMaxLines ?? 2));
  const previewSample = sampleText(target, titleText, hookText, subtitleText);
  const titleOutputDisabled =
    clipType === "short" &&
    target === "title" &&
    shortTitleOutputEnabled === false;
  const outputWidth = previewWidth ?? (clipType === "short" ? 1080 : 1920);
  const outputHeight = previewHeight ?? (clipType === "short" ? 1920 : 1080);
  const fontMetrics = assPreviewFontMetrics(style.fontName);
  const previewTextForFit =
    target === "subtitle"
      ? splitSubtitlePreviewLines(
          previewSample,
          previewLineLimit,
          previewMaxLines
        )
      : previewSample;
  const overlayFit = fitOverlayPreviewText(previewTextForFit, {
    outputWidth,
    fontSize: style.fontSize,
    fontSizeScale: fontMetrics.fontSizeScale,
    marginX: style.marginX,
    outlineWidth: style.outlineWidth + (style.outerOutlineWidth ?? 0),
    shadow: style.shadow,
    alignment: style.alignment,
    xPercent: style.xPercent,
    maxLines: previewMaxLines
  });
  const sizeClass =
    displayMode === "workspace"
      ? clipType === "short"
        ? "w-full max-w-[230px] lg:h-full lg:max-h-full lg:w-auto lg:max-w-full"
        : "w-full max-w-md lg:max-w-3xl"
      : clipType === "short"
        ? "w-full max-w-[230px]"
        : "w-full max-w-md";

  return (
    <div
      aria-label={`${TARGET_LABELS[target]}配置プレビュー`}
      className={`relative overflow-hidden border border-neutral-400 bg-[#25343A] ${sizeClass}`}
      style={{
        aspectRatio: `${outputWidth} / ${outputHeight}`,
        containerType: "inline-size"
      }}
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
      {titleOutputDisabled ? (
        <div className="absolute inset-0 z-30 flex items-center justify-center p-3 text-center">
          <span className="bg-neutral-950/85 px-2 py-1 text-[10px] font-semibold text-white">
            タイトルは書き出しOFF
          </span>
        </div>
      ) : (
        <>
          <ClipTextOverlay clipType={clipType} target={target} style={styles[target]}
            resolvedStyle={resolvedStyles[target]} defaultResolvedStyle={defaultResolvedStyles[target]}
            subtitleMaxCharsPerLine={subtitleMaxCharsPerLine} subtitleMaxLines={subtitleMaxLines}
            previewWidth={outputWidth} text={previewSample} />
          {!overlayFit.fits ? (
            <span className="absolute inset-x-2 bottom-2 z-40 bg-red-700/90 px-2 py-1 text-center text-[9px] font-semibold text-white">
              2行に収まりません。文字を短くするかサイズを調整してください
            </span>
          ) : null}
        </>
      )}
    </div>
  );
}

export function ClipTextStyleEditor({
  scopeDescription = "選択中のclipだけに反映",
  subtitleScopeLabel,
  onCommonSubtitleStyle,
  clipType,
  disabled = false,
  layout = "stacked",
  selectedTarget,
  showPreview = true,
  shortTitleOutputEnabled,
  shortTopBannerEnabled,
  shortTopBannerUrl,
  shortBottomBannerEnabled,
  shortBottomBannerUrl,
  styles,
  resolvedStyles,
  defaultResolvedStyles,
  subtitleMaxCharsPerLine,
  subtitleMaxLines,
  previewWidth,
  previewHeight,
  titleText,
  hookText,
  subtitleText,
  onChange,
  onSelectedTargetChange
}: ClipTextStyleEditorProps) {
  const [failedFont, setFailedFont] = useState<string | null>(null);
  const [internalTarget, setInternalTarget] = useState<ClipTextTarget>("title");
  const availableTargets: ClipTextTarget[] = ["title", "hook", "subtitle"];
  const requestedTarget = selectedTarget ?? internalTarget;
  const target = availableTargets.includes(requestedTarget)
    ? requestedTarget
    : availableTargets[0];
  const storedStyle = styles[target];
  const style = resolvedClipTextStyle(
    storedStyle,
    defaultResolvedStyles[target] ?? resolvedStyles[target],
    target,
    clipType
  );
  const verticalPresets = verticalPositionPresets(clipType);
  const selectedHorizontalPreset = matchingPositionPreset(
    HORIZONTAL_POSITION_PRESETS,
    style.xPercent
  );
  const selectedVerticalPreset = matchingPositionPreset(
    verticalPresets,
    style.yPercent
  );
  const outputWidth = previewWidth ?? (clipType === "short" ? 1080 : 1920);
  const outputHeight = previewHeight ?? (clipType === "short" ? 1920 : 1080);
  const currentPosition = {
    x: Math.round((outputWidth * style.xPercent) / 100),
    y: Math.round((outputHeight * style.yPercent) / 100)
  };

  useEffect(() => {
    let active = true;
    document.fonts.load(`400 16px ${JSON.stringify(style.fontName)}`).then(
      () => { if (active) setFailedFont(null); },
      () => { if (active) setFailedFont(style.fontName); }
    );
    return () => { active = false; };
  }, [style.fontName]);

  function updateStyle(patch: Partial<ClipTextStyle>) {
    const draft = storedStyle ?? styleDraftFromResolved(style);
    onChange(target, { ...draft, ...patch });
  }

  function changeTarget(nextTarget: ClipTextTarget) {
    setInternalTarget(nextTarget);
    onSelectedTargetChange?.(nextTarget);
  }

  function applyUsagePreset(preset: UsagePreset) {
    updateStyle({
      fontSize: preset.fontSize,
      xPercent: preset.xPercent,
      yPercent: preset.yPercent,
      positionMode: "explicit"
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
            {target === "subtitle" && subtitleScopeLabel ? <div className="mt-2 bg-sky-50 p-2 text-xs">
              <span>{subtitleScopeLabel}</span>
              <button type="button" className="ml-2 underline" onClick={onCommonSubtitleStyle}>共通書式を編集</button>
            </div> : null}
            <p className="mt-0.5 text-[10px] text-neutral-500">
              {scopeDescription}
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
            availableTargets.length === 1
              ? "grid-cols-1"
              : availableTargets.length === 2
                ? "grid-cols-2"
                : "grid-cols-3"
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
          {failedFont === style.fontName ? <span role="alert" className="text-red-700">
            このフォントを読み込めません。ローカル導入ファイルを確認してください。
          </span> : null}
          <select
            className="min-h-9 border border-neutral-300 bg-white px-2 text-sm font-normal"
            disabled={disabled}
            value={style.fontPreset ?? "__current_font__"}
            onChange={(event) => {
              if (event.target.value === "__current_font__") {
                return;
              }
              updateStyle({
                bold: null,
                fontName: null,
                fontPreset: event.target.value as ClipTextFontPreset
              });
            }}
          >
            {style.fontPreset === null ? (
              <option disabled value="__current_font__">
                {style.fontName}（現在設定）
              </option>
            ) : null}
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
              min={clipType === "normal" ? 12 : 20}
              type="number"
              value={style.fontSize}
              onChange={(event) =>
                updateStyle({ fontSize: Number(event.target.value) })
              }
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-semibold text-neutral-700">
            内縁の幅
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
          <label className="flex flex-col gap-1 text-xs font-semibold text-neutral-700">
            外縁の幅（0でOFF）
            <input aria-label="外縁の幅" className="h-9 border border-neutral-300 px-2"
              disabled={disabled} type="number" min={0} max={20} value={style.outerOutlineWidth ?? 0}
              onChange={(event) => updateStyle({ outerOutlineWidth: Number(event.target.value) })} />
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
                  onClick={() =>
                    updateStyle({
                      yPercent: preset.percent,
                      positionMode: "explicit"
                    })
                  }
                >
                  <span className="block text-[10px] font-semibold">
                    {preset.label}
                  </span>
                  <span className="block text-[8px] text-neutral-500">
                    Y {Math.round((outputHeight * preset.percent) / 100)}
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
                  onClick={() =>
                    updateStyle({
                      xPercent: preset.percent,
                      positionMode: "explicit"
                    })
                  }
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
                  updateStyle({
                    xPercent: Number(event.target.value),
                    positionMode: "explicit"
                  })
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
                  updateStyle({
                    yPercent: Number(event.target.value),
                    positionMode: "explicit"
                  })
                }
              />
            </label>
          </div>
        </details>
      </div>

      <div className={`${panelClass} 2xl:border-b-0`}>
        <div
          className={
            showPreview
              ? "grid min-w-0 gap-3 2xl:grid-cols-[minmax(0,1fr)_minmax(150px,180px)] 2xl:items-start"
              : undefined
          }
        >
          <div className="min-w-0">
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
              <legend className="text-xs font-semibold text-neutral-700">内縁の色</legend>
              <div className="mt-1 flex min-h-9 flex-wrap items-center gap-1.5">
                <input
                  aria-label="内縁の色を選択"
                  className="h-9 w-10 border border-neutral-300 bg-white p-1"
                  disabled={disabled}
                  type="color"
                  value={style.outlineColor}
                  onChange={(event) =>
                    updateStyle({ outlineColor: event.target.value.toUpperCase() })
                  }
                />
                {COLOR_PRESETS.map((color) => (
                  <button
                    aria-label={`内縁の色 ${color}`}
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

            <fieldset className="mt-3">
              <legend className="text-xs font-semibold text-neutral-700">外縁の色</legend>
              <div className="mt-1 flex min-h-9 flex-wrap items-center gap-1.5">
                <input
                  aria-label="外縁の色"
                  className="h-9 w-10 border border-neutral-300 bg-white p-1"
                  disabled={disabled}
                  type="color"
                  value={style.outerOutlineColor ?? "#FFFFFF"}
                  onChange={(event) =>
                    updateStyle({ outerOutlineColor: event.target.value.toUpperCase() })
                  }
                />
                {COLOR_PRESETS.map((color) => (
                  <button
                    aria-label={`外縁の色 ${color}`}
                    aria-pressed={(style.outerOutlineColor ?? "#FFFFFF") === color}
                    className="h-7 w-7 border border-neutral-400 aria-pressed:ring-2 aria-pressed:ring-sky-600"
                    disabled={disabled}
                    key={color}
                    style={{ backgroundColor: color }}
                    type="button"
                    onClick={() => updateStyle({ outerOutlineColor: color })}
                  />
                ))}
              </div>
            </fieldset>
          </div>

          {showPreview ? (
            <div className="min-w-0 border border-neutral-300 bg-neutral-100 p-2">
              <p className="mb-2 text-[10px] font-semibold text-sky-800">
                編集中プレビュー（即時反映）
              </p>
              <div className="flex justify-center">
                <ClipTextStylePreview
                  clipType={clipType}
                  selectedTarget={target}
                  shortTitleOutputEnabled={shortTitleOutputEnabled}
                  shortTopBannerEnabled={shortTopBannerEnabled}
                  shortTopBannerUrl={shortTopBannerUrl}
                  shortBottomBannerEnabled={shortBottomBannerEnabled}
                  shortBottomBannerUrl={shortBottomBannerUrl}
                  styles={styles}
                  resolvedStyles={resolvedStyles}
                  defaultResolvedStyles={defaultResolvedStyles}
                  subtitleMaxCharsPerLine={subtitleMaxCharsPerLine}
                  subtitleMaxLines={subtitleMaxLines}
                  previewWidth={previewWidth}
                  previewHeight={previewHeight}
                  subtitleText={subtitleText}
                  titleText={titleText}
                  hookText={hookText}
                />
              </div>
            </div>
          ) : null}
        </div>

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
