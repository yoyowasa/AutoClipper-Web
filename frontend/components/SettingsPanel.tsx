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
  enableBoundaryRefinement: true,
  boundaryLeadingPaddingSeconds: 0.4,
  boundaryTrailingPaddingSeconds: 0.6,
  maxBoundaryExpansionSeconds: 3,
  allowBoundaryExpansionBeyondMaxDuration: false,
  burnSubtitles: true,
  maxCharsPerLineShort: 16,
  maxCharsPerLineNormal: 28,
  maxLines: 2,
  minSubtitleDuration: 1.1,
  maxSubtitleDuration: 4.2,
  minGapBetweenSubtitles: 0.08,
  whisperModelSize: "base",
  transcriptionLanguage: "auto",
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
  shortOverlayTitleMode: "auto"
};

const SUBTITLE_FONT_OPTIONS = [
  { value: "", label: "標準ゴシック（Noto Sans CJK JP）" },
  { value: "Noto Serif CJK JP", label: "明朝（Noto Serif CJK JP）" },
  { value: "Noto Sans Mono CJK JP", label: "等幅ゴシック（Noto Sans Mono CJK JP）" }
] as const;

function withOptionalNumber(
  settings: ClipSettings,
  key: keyof ClipSettings,
  rawValue: string
): ClipSettings {
  return {
    ...settings,
    [key]: rawValue === "" ? undefined : Number(rawValue)
  };
}

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

        <label className="flex flex-col gap-2 md:col-span-2">
          <span className="text-sm font-medium text-neutral-700">Short overlay title</span>
          <select
            className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
            disabled={disabled}
            value={settings.shortOverlayTitleMode}
            onChange={(event) =>
              onChange({
                ...settings,
                shortOverlayTitleMode: event.target.value as ClipSettings["shortOverlayTitleMode"]
              })
            }
          >
            <option value="auto">Auto</option>
            <option value="always">Always</option>
            <option value="high_quality_only">High quality only</option>
            <option value="never">Never</option>
          </select>
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
                disabled={disabled}
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
                disabled={disabled}
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
                disabled={disabled}
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

        <details className="md:col-span-2">
          <summary className="cursor-pointer text-sm font-medium text-neutral-700">
            字幕スタイル
          </summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <label className="flex flex-col gap-2 sm:col-span-2">
              <span className="text-sm font-medium text-neutral-700">字幕フォント</span>
              <select
                className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                data-testid="subtitle-font-select"
                disabled={disabled}
                value={settings.subtitleFontName ?? ""}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    subtitleFontName: event.target.value || undefined
                  })
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
                className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                disabled={disabled}
                max={220}
                min={12}
                step={2}
                type="number"
                value={settings.subtitleFontSize ?? ""}
                onChange={(event) =>
                  onChange(withOptionalNumber(settings, "subtitleFontSize", event.target.value))
                }
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">縁取り</span>
              <input
                className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                disabled={disabled}
                max={20}
                min={0}
                step={1}
                type="number"
                value={settings.subtitleOutline ?? ""}
                onChange={(event) =>
                  onChange(withOptionalNumber(settings, "subtitleOutline", event.target.value))
                }
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">下余白</span>
              <input
                className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                disabled={disabled}
                max={1600}
                min={0}
                step={10}
                type="number"
                value={settings.subtitleLowerMargin ?? ""}
                onChange={(event) =>
                  onChange(
                    withOptionalNumber(settings, "subtitleLowerMargin", event.target.value)
                  )
                }
              />
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">表示位置</span>
              <select
                className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                disabled={disabled}
                value={settings.subtitleAlignment?.toString() ?? ""}
                onChange={(event) =>
                  onChange(withOptionalNumber(settings, "subtitleAlignment", event.target.value))
                }
              >
                <option value="">標準</option>
                <option value="2">下</option>
                <option value="5">中央</option>
                <option value="8">上</option>
              </select>
            </label>
          </div>
        </details>

        <details className="md:col-span-2">
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
              </select>
            </label>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-neutral-700">音声言語</span>
              <select
                className="min-h-10 rounded-md border border-neutral-300 bg-white px-3 text-sm"
                disabled={disabled}
                value={settings.transcriptionLanguage}
                onChange={(event) =>
                  onChange({
                    ...settings,
                    transcriptionLanguage: event.target.value as ClipSettings["transcriptionLanguage"]
                  })
                }
              >
                <option value="auto">自動判定</option>
                <option value="ja">日本語固定</option>
              </select>
            </label>

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
