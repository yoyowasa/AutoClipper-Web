"use client";

import type { ClipSettings } from "../lib/types";

type SettingsPanelProps = {
  settings: ClipSettings;
  disabled?: boolean;
  onChange: (settings: ClipSettings) => void;
};

export const DEFAULT_SETTINGS: ClipSettings = {
  mode: "high_quality",
  profile: "auto",
  normalClipCount: 2,
  shortCount: 3,
  normalMinDuration: 90,
  normalMaxDuration: 600,
  shortMinDuration: 20,
  shortMaxDuration: 75,
  selectionPolicy: "fill_requested",
  crossTypeOverlapDedupe: false,
  ensureSelectedOpenAIScored: true,
  openaiFinalistScoringLimit: 7,
  burnSubtitles: true,
  maxCharsPerLineShort: 16,
  maxCharsPerLineNormal: 28,
  maxLines: 2,
  minSubtitleDuration: 1.1,
  maxSubtitleDuration: 4.2,
  minGapBetweenSubtitles: 0.08,
  shortLayout: "auto"
};

export function SettingsPanel({
  settings,
  disabled = false,
  onChange
}: SettingsPanelProps) {
  return (
    <section className="rounded-md border border-neutral-300 bg-white p-5">
      <div className="grid gap-5 md:grid-cols-2">
        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">Mode</span>
          <select
            className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
            disabled={disabled}
            value={settings.mode}
            onChange={(event) =>
              onChange({ ...settings, mode: event.target.value as ClipSettings["mode"] })
            }
          >
            <option value="high_quality">High quality</option>
            <option value="fast">Fast</option>
          </select>
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">Profile</span>
          <select
            className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
            disabled={disabled}
            value={settings.profile}
            onChange={(event) =>
              onChange({ ...settings, profile: event.target.value as ClipSettings["profile"] })
            }
          >
            <option value="auto">Auto</option>
            <option value="talk">Talk</option>
            <option value="gameplay">Gameplay</option>
            <option value="lecture">Lecture</option>
          </select>
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">Normal clips</span>
          <input
            className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
            disabled={disabled}
            max={12}
            min={1}
            type="number"
            value={settings.normalClipCount}
            onChange={(event) =>
              onChange({
                ...settings,
                normalClipCount: Number(event.target.value)
              })
            }
          />
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">Shorts</span>
          <input
            className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
            disabled={disabled}
            max={24}
            min={1}
            type="number"
            value={settings.shortCount}
            onChange={(event) =>
              onChange({
                ...settings,
                shortCount: Number(event.target.value)
              })
            }
          />
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-neutral-700">Short layout</span>
          <select
            className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
            disabled={disabled}
            value={settings.shortLayout}
            onChange={(event) =>
              onChange({
                ...settings,
                shortLayout: event.target.value as ClipSettings["shortLayout"]
              })
            }
          >
            <option value="auto">Auto</option>
            <option value="center_crop">Center crop</option>
            <option value="blur_background">Blur background</option>
          </select>
        </label>

        <label className="flex min-h-10 items-center gap-3 self-end">
          <input
            checked={settings.burnSubtitles}
            className="h-4 w-4"
            disabled={disabled}
            type="checkbox"
            onChange={(event) =>
              onChange({
                ...settings,
                burnSubtitles: event.target.checked
              })
            }
          />
          <span className="text-sm font-medium text-neutral-700">Burn subtitles</span>
        </label>

        <details className="md:col-span-2">
          <summary className="cursor-pointer text-sm font-medium text-neutral-700">
            Advanced durations
          </summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">Selection policy</span>
              <select
                className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                disabled={disabled}
                value={settings.selectionPolicy}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    selectionPolicy: event.target.value as ClipSettings["selectionPolicy"]
                  })
                }
              >
                <option value="fill_requested">Fill requested</option>
                <option value="strict_quality">Strict quality</option>
              </select>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">Normal min seconds</span>
              <input
                className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                disabled={disabled}
                min={1}
                step={5}
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
                disabled={disabled}
                min={1}
                step={5}
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
                disabled={disabled}
                min={1}
                step={5}
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
                disabled={disabled}
                min={1}
                step={5}
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
      </div>
    </section>
  );
}
