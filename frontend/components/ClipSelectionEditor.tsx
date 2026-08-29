"use client";

import type { ClipSelectionPreset, ClipSettings } from "../lib/types";
import { isManualTimeMode } from "../lib/manualClipRanges";

type ClipSelectionEditorProps = {
  settings: ClipSettings;
  disabled?: boolean;
  compact?: boolean;
  workspace?: boolean;
  onChange: (settings: ClipSettings) => void;
};

const PRESET_OPTIONS: Array<{ value: ClipSelectionPreset; label: string }> = [
  { value: "auto", label: "おすすめ自動" },
  { value: "highlights", label: "見どころ" },
  { value: "funny", label: "笑い・リアクション" },
  { value: "important", label: "重要発言" },
  { value: "emotional", label: "感情・本音" },
  { value: "informative", label: "情報・解説" }
];

type OutputPreferenceProps = {
  disabled: boolean;
  guidance: string;
  label: string;
  manualTimeMode: boolean;
  placeholder: string;
  preset: ClipSelectionPreset;
  onGuidanceChange: (value: string) => void;
  onPresetChange: (value: ClipSelectionPreset) => void;
};

function OutputPreference({
  disabled,
  guidance,
  label,
  manualTimeMode,
  placeholder,
  preset,
  onGuidanceChange,
  onPresetChange
}: OutputPreferenceProps) {
  return (
    <fieldset className="min-w-0 border border-neutral-300 bg-white p-4 disabled:opacity-50" disabled={disabled}>
      <legend className="px-1 text-sm font-semibold text-neutral-900">{label}</legend>
      {manualTimeMode ? (
        <p className="mb-3 border-l-4 border-amber-400 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          時間指定中のため、自動おすすめは使用しません。
        </p>
      ) : null}
      <label className="mt-1 flex flex-col gap-2">
        <span className="text-xs font-medium text-neutral-600">狙う場面</span>
        <select
          className="min-h-10 w-full rounded-md border border-neutral-300 bg-white px-3 text-sm"
          value={preset}
          onChange={(event) => onPresetChange(event.target.value as ClipSelectionPreset)}
        >
          {PRESET_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="mt-4 flex flex-col gap-2">
        <span className="text-xs font-medium text-neutral-600">具体的な方針（任意）</span>
        <textarea
          className="min-h-24 w-full resize-y rounded-md border border-neutral-300 px-3 py-2 text-sm"
          maxLength={1000}
          placeholder={placeholder}
          value={guidance}
          onChange={(event) => onGuidanceChange(event.target.value)}
        />
      </label>
    </fieldset>
  );
}

export function ClipSelectionEditor({
  settings,
  disabled = false,
  compact = false,
  workspace = false,
  onChange
}: ClipSelectionEditorProps) {
  const normalManual = isManualTimeMode(settings, "normal");
  const shortManual = isManualTimeMode(settings, "short");
  const hasAutomaticOutput =
    (settings.normalClipCount > 0 && !normalManual) ||
    (settings.shortCount > 0 && !shortManual);
  const usesCodexInitialSelection =
    hasAutomaticOutput &&
    !normalManual &&
    !shortManual &&
    settings.initialSelectionProvider === "codex";

  return (
    <section
      className={`border-y border-neutral-200 py-5 md:col-span-2 ${
        workspace ? "2xl:col-span-4" : ""
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-neutral-900">切り抜き内容</h3>
        <span
          className={`border px-2 py-1 text-xs font-semibold ${
            !hasAutomaticOutput
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : usesCodexInitialSelection
                ? "border-emerald-300 bg-emerald-50 text-emerald-800"
              : settings.useOpenAIScoring
              ? "border-sky-300 bg-sky-50 text-sky-800"
              : "border-neutral-300 bg-neutral-50 text-neutral-600"
          }`}
        >
          {!hasAutomaticOutput
            ? "時間指定・自動選定なし"
            : usesCodexInitialSelection
              ? "Codexで初期選定"
            : settings.useOpenAIScoring
              ? "AI文脈判定"
              : "ローカル語句判定"}
        </span>
      </div>
      <p className="mt-2 text-xs leading-5 text-neutral-600">
        {usesCodexInitialSelection
          ? "文字起こし完了後、全体の文脈から通常・ショートの区間をCodexが直接選びます。"
          : "従来選定は候補をローカル評価します。必要な場合だけOpenAI APIの文脈判定を追加できます。"}
      </p>

      <div className={`mt-4 grid gap-4 ${compact ? "" : "lg:grid-cols-2"}`}>
        <OutputPreference
          disabled={disabled || settings.normalClipCount === 0 || normalManual}
          guidance={settings.normalClipGuidance}
          label="通常切り抜き"
          manualTimeMode={normalManual}
          placeholder="例: 休んだ理由と復帰後の予定。運動会を欠席した経緯を優先。"
          preset={settings.normalClipSelectionPreset}
          onGuidanceChange={(value) => onChange({ ...settings, normalClipGuidance: value })}
          onPresetChange={(value) =>
            onChange({ ...settings, normalClipSelectionPreset: value })
          }
        />
        <OutputPreference
          disabled={disabled || settings.shortCount === 0 || shortManual}
          guidance={settings.shortClipGuidance}
          label="ショート"
          manualTimeMode={shortManual}
          placeholder="例: 一言で引きがある驚き、笑い、大きなリアクション。"
          preset={settings.shortClipSelectionPreset}
          onGuidanceChange={(value) => onChange({ ...settings, shortClipGuidance: value })}
          onPresetChange={(value) =>
            onChange({ ...settings, shortClipSelectionPreset: value })
          }
        />
      </div>

      <div className={`mt-4 grid gap-3 ${compact ? "" : "sm:grid-cols-2"}`}>
        <label className="flex min-h-11 items-start gap-3 border border-neutral-300 px-4 py-3">
          <input
            checked={usesCodexInitialSelection}
            className="mt-0.5 h-4 w-4"
            disabled={disabled || !hasAutomaticOutput || normalManual || shortManual}
            type="checkbox"
            onChange={(event) =>
              onChange({
                ...settings,
                initialSelectionProvider: event.target.checked ? "codex" : "legacy",
                useOpenAIScoring: event.target.checked ? false : settings.useOpenAIScoring,
                ensureSelectedOpenAIScored: event.target.checked
                  ? false
                  : settings.ensureSelectedOpenAIScored
              })
            }
          />
          <span>
            <span className="block text-sm font-medium text-neutral-800">Codexで初期選定</span>
            <span className="mt-1 block text-xs text-neutral-500">
              全体の文字起こしから通常・ショート区間を直接選定
            </span>
          </span>
        </label>
        <label className="flex min-h-11 items-start gap-3 border border-neutral-300 px-4 py-3">
          <input
            checked={settings.excludeIntroOutro}
            className="mt-0.5 h-4 w-4"
            disabled={disabled || !hasAutomaticOutput}
            type="checkbox"
            onChange={(event) =>
              onChange({ ...settings, excludeIntroOutro: event.target.checked })
            }
          />
          <span className="text-sm font-medium text-neutral-800">冒頭・終了挨拶を除外</span>
        </label>
        <label className="flex min-h-11 items-start gap-3 border border-neutral-300 px-4 py-3">
          <input
            checked={settings.excludePromotionalContent}
            className="mt-0.5 h-4 w-4"
            disabled={disabled || !hasAutomaticOutput}
            type="checkbox"
            onChange={(event) =>
              onChange({
                ...settings,
                excludePromotionalContent: event.target.checked
              })
            }
          />
          <span className="text-sm font-medium text-neutral-800">告知・視聴案内を除外</span>
        </label>
        <label className="flex min-h-11 items-start gap-3 border border-neutral-300 px-4 py-3">
          <input
            checked={settings.selectionPolicy === "strict_quality"}
            className="mt-0.5 h-4 w-4"
            disabled={disabled || !hasAutomaticOutput}
            type="checkbox"
            onChange={(event) =>
              onChange({
                ...settings,
                selectionPolicy: event.target.checked ? "strict_quality" : "fill_requested"
              })
            }
          />
          <span className="text-sm font-medium text-neutral-800">
            品質優先（良い場面がなければ本数を減らす）
          </span>
        </label>
        <label className="flex min-h-11 items-start gap-3 border border-neutral-300 px-4 py-3">
          <input
            checked={settings.useOpenAIScoring}
            className="mt-0.5 h-4 w-4"
            disabled={disabled || !hasAutomaticOutput || usesCodexInitialSelection}
            type="checkbox"
            onChange={(event) =>
              onChange({
                ...settings,
                useOpenAIScoring: event.target.checked
              })
            }
          />
          <span>
            <span className="block text-sm font-medium text-neutral-800">AIで内容を判定</span>
            <span className="mt-1 block text-xs text-neutral-500">
              従来候補にOpenAI APIを使用・最大{settings.openaiCandidateLimit}候補
            </span>
          </span>
        </label>
      </div>
    </section>
  );
}
