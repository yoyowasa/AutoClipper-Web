"use client";

import type { ClipSettings } from "../lib/types";
import { ClipSelectionEditor } from "./ClipSelectionEditor";
import { ManualClipRangeEditor } from "./ManualClipRangeEditor";
import { SubtitleStyleEditor } from "./SubtitleStyleEditor";
import {
  isManualTimeMode,
  resizeManualRanges
} from "../lib/manualClipRanges";

type SettingsPanelProps = {
  settings: ClipSettings;
  disabled?: boolean;
  workspace?: boolean;
  revealManualRanges?: number;
  onChange: (settings: ClipSettings) => void;
};

export const DEFAULT_SETTINGS: ClipSettings = {
  workflowMode: "automatic",
  automationMode: "manual",
  manualSubtitleMode: "auto",
  mode: "high_quality",
  profile: "auto",
  normalClipCount: 2,
  shortCount: 3,
  normalMinDuration: 90,
  normalMaxDuration: 600,
  shortMinDuration: 20,
  shortMaxDuration: 75,
  normalClipSelectionPreset: "auto",
  shortClipSelectionPreset: "auto",
  normalClipGuidance: "",
  shortClipGuidance: "",
  normalClipTimeRanges: [],
  shortClipTimeRanges: [],
  excludeIntroOutro: true,
  excludePromotionalContent: false,
  selectionPolicy: "strict_quality",
  crossTypeOverlapDedupe: false,
  heatmapIntervalMode: false,
  initialSelectionProvider: "codex",
  useOpenAIScoring: false,
  openaiCandidateLimit: 8,
  openaiModel: "gpt-5.5",
  openaiFallbackToRuleScore: true,
  ensureSelectedOpenAIScored: true,
  openaiFinalistScoringLimit: 7,
  enableBoundaryRefinement: true,
  boundaryLeadingPaddingSeconds: 0.4,
  boundaryTrailingPaddingSeconds: 0.6,
  maxBoundaryExpansionSeconds: 3,
  allowBoundaryExpansionBeyondMaxDuration: false,
  burnSubtitles: true,
  requireClipPlanReview: true,
  requireSubtitleReview: true,
  maxCharsPerLineShort: 16,
  maxCharsPerLineNormal: 28,
  maxLines: 2,
  minSubtitleDuration: 1.1,
  maxSubtitleDuration: 4.2,
  minGapBetweenSubtitles: 0.08,
  shortSubtitleXPercent: 50,
  shortSubtitleYPercent: 68.75,
  normalSubtitleXPercent: 50,
  normalSubtitleYPercent: 84,
  whisperModelSize: "base",
  transcriptionLanguage: "ja",
  transcriptionDevice: "cpu",
  transcriptionComputeType: "auto",
  subtitleCorrectionMode: "off",
  subtitleCorrectionScope: "all",
  subtitleCorrectionSuspicionThreshold: 0.4,
  subtitleCorrectionModel: "gpt-5.5",
  subtitleCorrectionReasoningEffort: "default",
  subtitleCorrectionMinConfidence: 0.9,
  subtitleCorrectionBatchSize: 40,
  subtitleCorrectionContextSegments: 2,
  subtitleCorrectionFallbackEnabled: true,
  shortLayout: "auto",
  shortOverlayTitleMode: "auto",
  shortTopBannerEnabled: true,
  shortBottomBannerEnabled: true
};

export function settingsForRuntimeProfile(profile: string | null): ClipSettings {
  if (profile === "gpu") {
    return {
      ...DEFAULT_SETTINGS,
      whisperModelSize: "turbo",
      transcriptionLanguage: "ja",
      transcriptionDevice: "cuda",
      transcriptionComputeType: "float16"
    };
  }
  return { ...DEFAULT_SETTINGS };
}

type OutputMode = "both" | "normal_only" | "short_only";

function outputModeForSettings(settings: ClipSettings): OutputMode {
  if (settings.normalClipCount === 0) {
    return "short_only";
  }
  if (settings.shortCount === 0) {
    return "normal_only";
  }
  return "both";
}

function withOutputMode(settings: ClipSettings, mode: OutputMode): ClipSettings {
  if (mode === "normal_only") {
    return {
      ...settings,
      normalClipCount: settings.normalClipCount || DEFAULT_SETTINGS.normalClipCount,
      shortCount: 0,
      shortClipTimeRanges: []
    };
  }
  if (mode === "short_only") {
    return {
      ...settings,
      normalClipCount: 0,
      shortCount: settings.shortCount || DEFAULT_SETTINGS.shortCount,
      normalClipTimeRanges: []
    };
  }
  return {
    ...settings,
    normalClipCount: settings.normalClipCount || DEFAULT_SETTINGS.normalClipCount,
    shortCount: settings.shortCount || DEFAULT_SETTINGS.shortCount
  };
}

export function SettingsPanel({
  settings,
  disabled = false,
  workspace = false,
  revealManualRanges = 0,
  onChange
}: SettingsPanelProps) {
  const outputMode = outputModeForSettings(settings);

  return (
    <section
      className={
        workspace
          ? "top-workspace-settings bg-white"
          : "rounded-md border border-neutral-300 bg-white p-5"
      }
      data-density={workspace ? "workspace" : "default"}
    >
      <div
        className={
          workspace
            ? "grid gap-3 p-3 md:grid-cols-2 2xl:grid-cols-4"
            : "grid gap-5 md:grid-cols-2"
        }
      >
        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">処理モード</span>
          <select
            className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
            disabled={disabled}
            value={settings.mode}
            onChange={(event) =>
              onChange({ ...settings, mode: event.target.value as ClipSettings["mode"] })
            }
          >
            <option value="high_quality">高品質</option>
            <option value="fast">高速</option>
          </select>
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">動画タイプ</span>
          <select
            className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
            disabled={disabled}
            value={settings.profile}
            onChange={(event) =>
              onChange({ ...settings, profile: event.target.value as ClipSettings["profile"] })
            }
          >
            <option value="auto">自動</option>
            <option value="talk">トーク</option>
            <option value="gameplay">ゲーム</option>
            <option value="lecture">講義</option>
          </select>
        </label>

        <fieldset className="md:col-span-2">
          <legend className="text-sm font-medium text-neutral-700">作成する動画</legend>
          <div
            aria-label="生成対象"
            className="mt-2 grid w-full grid-cols-3 border border-neutral-300 bg-neutral-100 p-1 sm:w-auto"
            role="group"
          >
            {(
              [
                ["both", "両方"],
                ["normal_only", "通常のみ"],
                ["short_only", "ショートのみ"]
              ] as const
            ).map(([value, label]) => (
              <button
                aria-pressed={outputMode === value}
                className={`min-h-10 px-3 text-sm font-medium ${
                  outputMode === value ? "bg-neutral-950 text-white" : "text-neutral-600"
                }`}
                disabled={disabled}
                key={value}
                type="button"
                onClick={() => onChange(withOutputMode(settings, value))}
              >
                {label}
              </button>
            ))}
          </div>
        </fieldset>

        {settings.normalClipCount > 0 ? (
          <label
            className={`flex flex-col gap-2 ${
              workspace
                ? settings.shortCount === 0
                  ? "md:col-span-2 2xl:col-span-4"
                  : "2xl:col-span-2"
                : ""
            }`}
          >
            <span className="text-sm font-medium text-neutral-700">通常切り抜きの本数</span>
            <input
              className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
              disabled={disabled}
              max={12}
              min={1}
              type="number"
              value={settings.normalClipCount}
              onChange={(event) => {
                const count = Math.min(12, Math.max(1, Number(event.target.value) || 1));
                onChange(resizeManualRanges({
                  ...settings,
                  normalClipCount: count
                }, "normal", count));
              }}
            />
          </label>
        ) : null}

        {settings.shortCount > 0 ? (
          <label
            className={`flex flex-col gap-2 ${
              workspace
                ? settings.normalClipCount === 0
                  ? "md:col-span-2 2xl:col-span-4"
                  : "2xl:col-span-2"
                : ""
            }`}
          >
            <span className="text-sm font-medium text-neutral-700">ショートの本数</span>
            <input
              className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
              disabled={disabled}
              max={24}
              min={1}
              type="number"
              value={settings.shortCount}
              onChange={(event) => {
                const count = Math.min(24, Math.max(1, Number(event.target.value) || 1));
                onChange(resizeManualRanges({
                  ...settings,
                  shortCount: count
                }, "short", count));
              }}
            />
          </label>
        ) : null}

        <ManualClipRangeEditor
          disabled={disabled}
          revealKey={revealManualRanges}
          settings={settings}
          workspace={workspace}
          onChange={onChange}
        />

        <ClipSelectionEditor
          disabled={disabled}
          settings={settings}
          workspace={workspace}
          onChange={onChange}
        />

        <section
          className={`border-y border-neutral-200 py-5 md:col-span-2 ${
            workspace ? "2xl:col-span-4" : ""
          }`}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-neutral-900">
              {settings.shortCount > 0 ? "ショート・字幕" : "字幕"}
            </h3>
            <span className="text-xs text-neutral-500">表示方法と確認工程</span>
          </div>
          <div
            className={`mt-3 grid items-end gap-3 ${
              settings.shortCount > 0
                ? "lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
                : "lg:grid-cols-[auto]"
            }`}
          >
            {settings.shortCount > 0 ? (
              <>
                <label className="flex min-w-0 flex-col gap-2">
                  <span className="text-sm font-medium text-neutral-700">ショート画面</span>
                  <select
                    className="min-h-10 w-full border border-neutral-300 bg-white px-3 text-sm"
                    disabled={disabled || settings.shortCount === 0}
                    value={settings.shortLayout}
                    onChange={(event) =>
                      onChange({
                        ...settings,
                        shortLayout: event.target.value as ClipSettings["shortLayout"]
                      })
                    }
                  >
                    <option value="auto">自動</option>
                    <option value="face_tracking_crop">人物アップ（顔を追従）</option>
                    <option value="center_crop">中央を切り抜く</option>
                    <option value="blur_background">ぼかし背景</option>
                  </select>
                </label>

                <fieldset className="flex min-w-0 flex-col gap-2">
                  <legend className="text-sm font-medium text-neutral-700">
                    ショート帯（基本ON）
                  </legend>
                  <div className="grid min-h-10 grid-cols-2 border border-neutral-300 bg-white">
                    <label className="flex cursor-pointer items-center gap-2 border-r border-neutral-300 px-3">
                      <input
                        checked={settings.shortTopBannerEnabled}
                        className="h-4 w-4"
                        disabled={disabled || settings.shortCount === 0}
                        type="checkbox"
                        onChange={(event) =>
                          onChange({
                            ...settings,
                            shortTopBannerEnabled: event.target.checked
                          })
                        }
                      />
                      <span className="text-sm font-medium text-neutral-700">上: 柄帯</span>
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 px-3">
                      <input
                        checked={settings.shortBottomBannerEnabled}
                        className="h-4 w-4"
                        disabled={disabled || settings.shortCount === 0}
                        type="checkbox"
                        onChange={(event) =>
                          onChange({
                            ...settings,
                            shortBottomBannerEnabled: event.target.checked
                          })
                        }
                      />
                      <span className="text-sm font-medium text-neutral-700">下: ロゴ</span>
                    </label>
                  </div>
                  <p className="text-xs leading-5 text-neutral-500">
                    上帯と下帯の間へ映像を収め、人物が帯に隠れない画角で書き出します。
                  </p>
                </fieldset>
              </>
            ) : null}

            <label className="flex min-h-10 items-center gap-3 border border-neutral-300 bg-white px-3 lg:justify-self-start">
              <input
                checked={settings.burnSubtitles}
                className="h-4 w-4"
                disabled={disabled || settings.automationMode === "guarded"}
                type="checkbox"
                onChange={(event) =>
                  onChange({
                    ...settings,
                    burnSubtitles: event.target.checked,
                    automationMode:
                      !event.target.checked &&
                      (settings.automationMode === "shadow" ||
                        settings.automationMode === "guarded")
                        ? "manual"
                        : settings.automationMode
                  })
                }
              />
              <span className="whitespace-nowrap text-sm font-medium text-neutral-700">
                字幕を焼き込む
              </span>
            </label>
          </div>

          <details className="mt-3" data-testid="review-settings-details">
            <summary className="cursor-pointer text-sm font-medium text-neutral-700">
              <span className="ml-1 inline-flex w-[calc(100%_-_1.25rem)] items-center justify-between gap-3 align-middle">
                <span>開始後の確認</span>
                <span className="text-xs font-normal text-neutral-500">
                  {settings.automationMode === "guarded"
                    ? "自動判定できない項目または問題時のみ確認"
                    : !settings.burnSubtitles
                    ? "なし"
                    : [
                        settings.requireClipPlanReview ? "予定確認" : null,
                        settings.requireSubtitleReview ? "字幕確認" : null
                      ]
                        .filter((value): value is string => value !== null)
                        .join(" + ") || "なし"}
                </span>
              </span>
            </summary>
            <div className="grid gap-3 border-x border-b border-neutral-200 p-3 md:grid-cols-2">
              <label className="flex flex-col gap-1 md:col-span-2">
                <span className="text-sm font-semibold text-neutral-900">自動化レベル</span>
                <select
                  className="min-h-10 border border-neutral-300 bg-white px-3 text-sm"
                  disabled={disabled}
                  value={settings.automationMode}
                  onChange={(event) => {
                    const automationMode = event.target.value as ClipSettings["automationMode"];
                    const requiresReviewPipeline =
                      automationMode === "shadow" || automationMode === "guarded";
                    onChange({
                      ...settings,
                      automationMode,
                      burnSubtitles: requiresReviewPipeline ? true : settings.burnSubtitles,
                      requireClipPlanReview: requiresReviewPipeline
                        ? true
                        : settings.requireClipPlanReview,
                      requireSubtitleReview: requiresReviewPipeline
                        ? true
                        : settings.requireSubtitleReview
                    });
                  }}
                >
                  <option value="manual">手動確認（現行）</option>
                  <option value="shadow">Shadow（自動判断を保存し、全件確認）</option>
                  <option value="guarded">問題だけ確認</option>
                  <option disabled value="auto">完全自動（準備中）</option>
                </select>
                <span className="text-xs text-neutral-600">
                  {settings.automationMode === "guarded"
                    ? "自動判定できない項目または問題時のみ確認します。"
                    : "Shadowは処理結果を変えず、判断記録を残して全工程を確認します。"}
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input
                  checked={
                    settings.automationMode === "guarded" || settings.requireClipPlanReview
                  }
                  className="mt-0.5 h-4 w-4"
                  disabled={
                    disabled ||
                    settings.automationMode === "guarded" ||
                    !settings.burnSubtitles ||
                    !settings.requireSubtitleReview
                  }
                  type="checkbox"
                  onChange={(event) =>
                    onChange({
                      ...settings,
                      requireClipPlanReview: event.target.checked,
                      automationMode:
                        !event.target.checked && settings.automationMode === "shadow"
                          ? "manual"
                          : settings.automationMode
                    })
                  }
                />
                <span>
                  <span className="block text-sm font-semibold text-neutral-900">
                    切り抜き予定を確認
                  </span>
                  <span className="mt-1 block text-xs text-neutral-600">
                    範囲を再生し、必要なら場面を選び直します。
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input
                  checked={
                    settings.automationMode === "guarded" || settings.requireSubtitleReview
                  }
                  className="mt-0.5 h-4 w-4"
                  disabled={
                    disabled || settings.automationMode === "guarded" || !settings.burnSubtitles
                  }
                  type="checkbox"
                  onChange={(event) =>
                    onChange({
                      ...settings,
                      requireSubtitleReview: event.target.checked,
                      requireClipPlanReview: event.target.checked
                        ? settings.requireClipPlanReview
                        : false,
                      automationMode:
                        !event.target.checked && settings.automationMode === "shadow"
                          ? "manual"
                          : settings.automationMode
                    })
                  }
                />
                <span>
                  <span className="block text-sm font-semibold text-neutral-900">字幕を確認</span>
                  <span className="mt-1 block text-xs text-neutral-600">
                    書き出し前に字幕を確認します。
                  </span>
                </span>
              </label>
              {!settings.burnSubtitles ? (
                <p className="text-xs text-amber-700 md:col-span-2">
                  字幕焼き込みがOFFのため、確認工程は実行されません。
                </p>
              ) : null}
            </div>
          </details>
        </section>

        <details className={workspace ? "md:col-span-2 2xl:col-span-4" : "md:col-span-2"}>
          <summary className="cursor-pointer text-sm font-medium text-neutral-700">
            詳細な長さ設定
          </summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">Normal min seconds</span>
              <input
                className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                disabled={
                  disabled ||
                  settings.normalClipCount === 0 ||
                  isManualTimeMode(settings, "normal")
                }
                min={1}
                step={1}
                type="number"
                value={settings.normalMinDuration}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    normalMinDuration: Number(event.target.value)
                  })
                }
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">Normal max seconds</span>
              <input
                className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                disabled={
                  disabled ||
                  settings.normalClipCount === 0 ||
                  isManualTimeMode(settings, "normal")
                }
                min={1}
                step={1}
                type="number"
                value={settings.normalMaxDuration}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    normalMaxDuration: Number(event.target.value)
                  })
                }
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">Short min seconds</span>
              <input
                className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                disabled={
                  disabled ||
                  settings.shortCount === 0 ||
                  isManualTimeMode(settings, "short")
                }
                min={1}
                step={1}
                type="number"
                value={settings.shortMinDuration}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    shortMinDuration: Number(event.target.value)
                  })
                }
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">Short max seconds</span>
              <input
                className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                disabled={
                  disabled ||
                  settings.shortCount === 0 ||
                  isManualTimeMode(settings, "short")
                }
                min={1}
                step={1}
                type="number"
                value={settings.shortMaxDuration}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    shortMaxDuration: Number(event.target.value)
                  })
                }
              />
            </label>
          </div>
        </details>

        <div className={workspace ? "md:col-span-2 2xl:col-span-4" : "md:col-span-2"}>
          <SubtitleStyleEditor disabled={disabled} settings={settings} onChange={onChange} />
        </div>

        <details className={workspace ? "md:col-span-2 2xl:col-span-4" : "md:col-span-2"}>
          <summary className="cursor-pointer text-sm font-medium text-neutral-700">
            文字起こし・字幕校正
          </summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">文字起こし精度</span>
              <select
                className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                disabled={disabled}
                value={settings.whisperModelSize}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    whisperModelSize: event.target.value as ClipSettings["whisperModelSize"]
                  })
                }
              >
                <option value="base">標準（base）</option>
                <option value="small">日本語高精度（small）</option>
                <option value="medium">高精度・低速（medium）</option>
                <option value="large-v3">実験的（large-v3）</option>
                <option value="turbo">高速large-v3系（turbo）</option>
              </select>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">文字起こしデバイス</span>
              <select
                className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                disabled={disabled}
                value={settings.transcriptionDevice}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    transcriptionDevice: event.target.value as ClipSettings["transcriptionDevice"]
                  })
                }
              >
                <option value="cpu">CPU（互換設定）</option>
                <option value="auto">自動（GPU優先）</option>
                <option value="cuda">NVIDIA GPU（利用不能時は失敗）</option>
              </select>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">演算精度</span>
              <select
                className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                disabled={disabled}
                value={settings.transcriptionComputeType}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    transcriptionComputeType:
                      event.target.value as ClipSettings["transcriptionComputeType"]
                  })
                }
              >
                <option value="auto">自動（GPU=float16 / CPU=int8）</option>
                <option value="int8">int8</option>
                <option value="float16">float16</option>
                <option value="int8_float16">int8_float16</option>
              </select>
            </label>

            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">音声言語</span>
              <div
                aria-label="音声言語"
                className="flex min-h-10 items-center rounded-md border border-neutral-300 bg-neutral-100 px-3 text-sm text-neutral-700"
              >
                日本語（固定）
              </div>
            </div>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">OpenAI字幕校正</span>
              <select
                className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                data-testid="subtitle-correction-mode"
                disabled={disabled}
                value={settings.subtitleCorrectionMode}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    subtitleCorrectionMode: event.target.value as ClipSettings["subtitleCorrectionMode"]
                  })
                }
              >
                <option value="off">使用しない</option>
                <option value="openai">誤変換を校正する</option>
              </select>
            </label>

            {settings.subtitleCorrectionMode === "openai" && (
              <>
                <label className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-neutral-700">校正対象</span>
                  <select
                    className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                    disabled={disabled}
                    value={settings.subtitleCorrectionScope}
                    onChange={(event) =>
                      onChange({
                        ...settings,
                        subtitleCorrectionScope: event.target.value as ClipSettings["subtitleCorrectionScope"]
                      })
                    }
                  >
                    <option value="all">すべての字幕</option>
                    <option value="suspicious">疑わしい字幕のみ</option>
                  </select>
                </label>

                {settings.subtitleCorrectionScope === "suspicious" ? (
                  <label className="flex flex-col gap-2">
                    <span className="text-sm font-medium text-neutral-700">疑わしさの閾値</span>
                    <input
                      className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                      disabled={disabled}
                      max={1}
                      min={0}
                      step={0.05}
                      type="number"
                      value={settings.subtitleCorrectionSuspicionThreshold}
                      onChange={(event) =>
                        onChange({
                          ...settings,
                          subtitleCorrectionSuspicionThreshold: Number(event.target.value)
                        })
                      }
                    />
                  </label>
                ) : null}

                <label className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-neutral-700">校正モデル</span>
                  <input
                    className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                    disabled={disabled}
                    type="text"
                    value={settings.subtitleCorrectionModel}
                    onChange={(event) =>
                      onChange({ ...settings, subtitleCorrectionModel: event.target.value })
                    }
                  />
                </label>

                <label className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-neutral-700">推論量</span>
                  <select
                    className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                    disabled={disabled}
                    value={settings.subtitleCorrectionReasoningEffort}
                    onChange={(event) =>
                      onChange({
                        ...settings,
                        subtitleCorrectionReasoningEffort:
                          event.target.value as ClipSettings["subtitleCorrectionReasoningEffort"]
                      })
                    }
                  >
                    <option value="default">モデル既定</option>
                    <option value="none">なし（省コスト・高速、重要字幕は要確認）</option>
                    <option value="minimal">最小</option>
                    <option value="low">低</option>
                    <option value="medium">中</option>
                    <option value="high">高</option>
                    <option value="xhigh">特高</option>
                    <option value="max">最大</option>
                  </select>
                </label>

                <label className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-neutral-700">適用信頼度</span>
                  <input
                    className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                    disabled={disabled}
                    max={1}
                    min={0}
                    step={0.05}
                    type="number"
                    value={settings.subtitleCorrectionMinConfidence}
                    onChange={(event) =>
                      onChange({
                        ...settings,
                        subtitleCorrectionMinConfidence: Number(event.target.value)
                      })
                    }
                  />
                </label>

                <label className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-neutral-700">1回の字幕数</span>
                  <input
                    className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                    disabled={disabled}
                    max={100}
                    min={1}
                    step={1}
                    type="number"
                    value={settings.subtitleCorrectionBatchSize}
                    onChange={(event) =>
                      onChange({
                        ...settings,
                        subtitleCorrectionBatchSize: Number(event.target.value)
                      })
                    }
                  />
                </label>

                <label className="flex flex-col gap-2">
                  <span className="text-sm font-medium text-neutral-700">前後の文脈数</span>
                  <input
                    className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                    disabled={disabled}
                    max={10}
                    min={0}
                    step={1}
                    type="number"
                    value={settings.subtitleCorrectionContextSegments}
                    onChange={(event) =>
                      onChange({
                        ...settings,
                        subtitleCorrectionContextSegments: Number(event.target.value)
                      })
                    }
                  />
                </label>

                <label className="flex min-h-10 items-center gap-3 self-end">
                  <input
                    checked={settings.subtitleCorrectionFallbackEnabled}
                    className="h-4 w-4"
                    disabled={disabled}
                    type="checkbox"
                    onChange={(event) =>
                      onChange({
                        ...settings,
                        subtitleCorrectionFallbackEnabled: event.target.checked
                      })
                    }
                  />
                  <span className="text-sm font-medium text-neutral-700">API失敗時は元字幕を使用</span>
                </label>
              </>
            )}
          </div>
        </details>
      </div>
    </section>
  );
}
