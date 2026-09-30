"use client";

import type { Dispatch, SetStateAction } from "react";

import { ClipSelectionEditor } from "./ClipSelectionEditor";
import type { ClipPlanDocument, ClipSettings, JobStatusResponse } from "../lib/types";

type ClipReselectionPanelProps = {
  plan: ClipPlanDocument;
  keptClipIds: string[];
  remainingReselectionCount: number;
  excludePreviousSelection: boolean;
  setExcludePreviousSelection: Dispatch<SetStateAction<boolean>>;
  controlsDisabled: boolean;
  draftSettings: ClipSettings;
  setDraftSettings: Dispatch<SetStateAction<ClipSettings | null>>;
  isReselecting: boolean;
  job: JobStatusResponse | null;
  handleReselect: () => Promise<void>;
};

export function ClipReselectionPanel({
  plan,
  keptClipIds,
  remainingReselectionCount,
  excludePreviousSelection,
  setExcludePreviousSelection,
  controlsDisabled,
  draftSettings,
  setDraftSettings,
  isReselecting,
  job,
  handleReselect
}: ClipReselectionPanelProps) {
  return (
    <details>
            <summary className="cursor-pointer text-sm font-semibold text-neutral-700">
              再選定（別の場面を選び直す）
            </summary>
            <div className="mt-3">
              <h2 className="mt-1 text-lg font-semibold">狙う場面を調整</h2>
              <p className="mt-2 text-sm font-semibold text-sky-800">
                {plan.clips.filter(clip => keptClipIds.includes(clip.id)).length}本キープ・
                {remainingReselectionCount}本を再選定
              </p>
              <label className="mt-3 flex items-center gap-2 text-sm">
                <input type="checkbox" checked={excludePreviousSelection} disabled={controlsDisabled}
                  onChange={event => setExcludePreviousSelection(event.target.checked)} />
                これまでの候補を避けて選ぶ
              </label>
              <p className="mt-1 text-xs text-neutral-600">ONではこのジョブで提示済みの区間を除外します。同じ場所も選び直す場合はOFFにしてください。</p>
              <p className="mt-2 text-sm leading-6 text-neutral-600">
                保存済みの文字起こし・音声・映像解析を使うため、動画の再アップロードや再文字起こしは行いません。
              </p>
            </div>

            <div className="mt-4 flex flex-col gap-3 border border-neutral-300 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-neutral-900">候補基準</p>
                <p className="mt-1 text-xs leading-5 text-neutral-600">
                  {draftSettings.heatmapIntervalMode
                    ? "字幕・会話内容から場面を選び、人気度JSONは優先度の参考にだけ使います。開始・終了はJSON区間へ合わせません。"
                    : "字幕・会話内容だけで場面と開始・終了を選びます。"}
                </p>
              </div>
              <div
                aria-label="再選定の候補基準"
                className="grid shrink-0 grid-cols-2 border border-neutral-300"
                role="group"
              >
                <button
                  aria-pressed={!draftSettings.heatmapIntervalMode}
                  className={`min-h-9 px-3 text-xs font-semibold ${
                    !draftSettings.heatmapIntervalMode
                      ? "bg-neutral-950 text-white"
                      : "bg-white text-neutral-600 hover:bg-neutral-50"
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                  disabled={controlsDisabled}
                  type="button"
                  onClick={() =>
                    setDraftSettings((current) =>
                      current ? { ...current, heatmapIntervalMode: false } : current
                    )
                  }
                >
                  内容のみ
                </button>
                <button
                  aria-pressed={draftSettings.heatmapIntervalMode}
                  className={`min-h-9 px-3 text-xs font-semibold ${
                    draftSettings.heatmapIntervalMode
                      ? "bg-emerald-700 text-white"
                      : "bg-white text-neutral-600 hover:bg-neutral-50"
                  } disabled:cursor-not-allowed disabled:opacity-50`}
                  disabled={controlsDisabled}
                  type="button"
                  onClick={() =>
                    setDraftSettings((current) =>
                      current ? { ...current, heatmapIntervalMode: true } : current
                    )
                  }
                >
                  JSONを参考
                </button>
              </div>
            </div>

            <div className="mt-3">
              <ClipSelectionEditor
                disabled={controlsDisabled}
                settings={draftSettings}
                onChange={setDraftSettings}
              />
            </div>

            <div className="mt-3 border border-neutral-300 bg-white px-4 py-3">
              <p className="text-sm font-semibold text-neutral-900">通常切り抜きの候補尺</p>
              <p className="mt-1 text-xs text-neutral-600">
                「10分前後」を探す場合は、例えば最低480秒・最長600秒に設定します。条件に合う場面がなければ短い候補で埋めません。
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <label className="flex flex-col gap-1 text-xs font-medium text-neutral-700">
                  最低（秒）
                  <input className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                    disabled={controlsDisabled} min={1} step={1} type="number"
                    value={draftSettings.normalMinDuration}
                    onChange={event => setDraftSettings(current => current ? { ...current, normalMinDuration: Number(event.target.value) } : current)} />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-neutral-700">
                  最長（秒）
                  <input className="min-h-10 rounded-md border border-neutral-300 px-3 text-sm"
                    disabled={controlsDisabled} min={1} step={1} type="number"
                    value={draftSettings.normalMaxDuration}
                    onChange={event => setDraftSettings(current => current ? { ...current, normalMaxDuration: Number(event.target.value) } : current)} />
                </label>
              </div>
              {draftSettings.normalMinDuration > draftSettings.normalMaxDuration ? (
                <p className="mt-2 text-xs text-red-700">最低尺は最長尺以下にしてください。</p>
              ) : null}
            </div>

            <button
              className="mt-4 min-h-11 w-full border border-neutral-950 bg-white px-4 text-sm font-semibold text-neutral-950 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={controlsDisabled || remainingReselectionCount === 0 ||
                !Number.isFinite(draftSettings.normalMinDuration) || !Number.isFinite(draftSettings.normalMaxDuration) ||
                draftSettings.normalMinDuration <= 0 || draftSettings.normalMaxDuration <= 0 ||
                draftSettings.normalMinDuration > draftSettings.normalMaxDuration}
              type="button"
              onClick={() => void handleReselect()}
            >
              {isReselecting
                ? job?.currentStep || "再選定中"
                : `キープ以外の${remainingReselectionCount}本を再選定`}
            </button>
    </details>
  );
}
