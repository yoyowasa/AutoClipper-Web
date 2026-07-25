"use client";

import { useMemo, useState, useSyncExternalStore } from "react";

import {
  SUBTITLE_STYLE_PRESET_STORAGE_KEY,
  applySubtitleStyle,
  captureSubtitleStyle,
  emptySubtitleStylePresetSlots,
  parseSubtitleStylePresetSlots,
  serializeSubtitleStylePresetSlots,
  type SubtitleStylePresetSlots
} from "../lib/subtitleStylePresets";
import type { ClipSettings } from "../lib/types";

type SubtitleStylePresetManagerProps = {
  settings: ClipSettings;
  disabled?: boolean;
  onChange: (settings: ClipSettings) => void;
};

const SUBTITLE_STYLE_PRESET_CHANGE_EVENT =
  "autoclipper:subtitle-style-presets-changed";

function defaultSlotName(index: number): string {
  return `字幕設定 ${index + 1}`;
}

function subscribeToSubtitleStylePresets(onStoreChange: () => void): () => void {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener(SUBTITLE_STYLE_PRESET_CHANGE_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener(SUBTITLE_STYLE_PRESET_CHANGE_EVENT, onStoreChange);
  };
}

function getStoredSubtitleStylePresets(): string | null {
  return window.localStorage.getItem(SUBTITLE_STYLE_PRESET_STORAGE_KEY);
}

function getServerSubtitleStylePresets(): undefined {
  return undefined;
}

function savedDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "保存済み";
  }
  return new Intl.DateTimeFormat("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

export function SubtitleStylePresetManager({
  settings,
  disabled = false,
  onChange
}: SubtitleStylePresetManagerProps) {
  const storedValue = useSyncExternalStore(
    subscribeToSubtitleStylePresets,
    getStoredSubtitleStylePresets,
    getServerSubtitleStylePresets
  );
  const parsedStorage = useMemo(() => {
    try {
      return {
        slots: parseSubtitleStylePresetSlots(storedValue ?? null),
        error: ""
      };
    } catch {
      return {
        slots: emptySubtitleStylePresetSlots(),
        error: "保存済み字幕設定を読み込めませんでした"
      };
    }
  }, [storedValue]);
  const slots = parsedStorage.slots;
  const storageReady = storedValue !== undefined;
  const [slotNameOverrides, setSlotNameOverrides] = useState<
    Partial<Record<number, string>>
  >({});
  const [notice, setNotice] = useState("");
  const [writeError, setWriteError] = useState("");
  const storageError = parsedStorage.error || writeError;

  function persist(nextSlots: SubtitleStylePresetSlots): boolean {
    try {
      window.localStorage.setItem(
        SUBTITLE_STYLE_PRESET_STORAGE_KEY,
        serializeSubtitleStylePresetSlots(nextSlots)
      );
      window.dispatchEvent(new Event(SUBTITLE_STYLE_PRESET_CHANGE_EVENT));
      setWriteError("");
      return true;
    } catch {
      setWriteError("字幕設定をブラウザへ保存できませんでした");
      return false;
    }
  }

  function saveSlot(index: number) {
    const name =
      slotNameOverrides[index]?.trim() ||
      slots[index]?.name ||
      defaultSlotName(index);
    const nextSlots = [...slots] as SubtitleStylePresetSlots;
    nextSlots[index] = {
      name,
      savedAt: new Date().toISOString(),
      style: captureSubtitleStyle(settings)
    };
    if (persist(nextSlots)) {
      setSlotNameOverrides((current) => ({ ...current, [index]: name }));
      setNotice(`「${name}」を保存しました`);
    }
  }

  function loadSlot(index: number) {
    const preset = slots[index];
    if (!preset) {
      return;
    }
    onChange(applySubtitleStyle(settings, preset.style));
    setNotice(`「${preset.name}」を呼び出しました`);
    setWriteError("");
  }

  function deleteSlot(index: number) {
    const preset = slots[index];
    if (!preset || !window.confirm(`「${preset.name}」を削除しますか？`)) {
      return;
    }
    const nextSlots = [...slots] as SubtitleStylePresetSlots;
    nextSlots[index] = null;
    if (persist(nextSlots)) {
      setSlotNameOverrides((current) => {
        const next = { ...current };
        delete next[index];
        return next;
      });
      setNotice(`「${preset.name}」を削除しました`);
    }
  }

  return (
    <div className="mt-5 border-y border-neutral-200 py-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-neutral-950">保存した字幕設定</h3>
          <p className="mt-1 text-xs text-neutral-500">
            このブラウザに通常・ショート両方のスタイルを保存
          </p>
        </div>
        {notice ? (
          <p aria-live="polite" className="text-xs font-medium text-emerald-700">
            {notice}
          </p>
        ) : null}
      </div>

      {storageError ? (
        <p className="mt-3 border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800">
          {storageError}
        </p>
      ) : null}

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        {slots.map((preset, index) => (
          <section
            className="border border-neutral-300 bg-white p-3"
            key={`subtitle-style-slot-${index + 1}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-blue-700">
                保存枠 {index + 1}
              </span>
              <span className="text-xs text-neutral-500">
                {preset ? savedDate(preset.savedAt) : "未保存"}
              </span>
            </div>
            <label className="mt-2 block">
              <span className="sr-only">保存枠 {index + 1} の名前</span>
              <input
                aria-label={`保存枠 ${index + 1} の名前`}
                className="min-h-9 w-full border border-neutral-300 px-2 text-sm"
                disabled={disabled || !storageReady}
                maxLength={40}
                value={
                  slotNameOverrides[index] ??
                  preset?.name ??
                  defaultSlotName(index)
                }
                onChange={(event) =>
                  setSlotNameOverrides((current) => ({
                    ...current,
                    [index]: event.target.value
                  }))
                }
              />
            </label>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <button
                className="min-h-9 border border-neutral-950 bg-neutral-950 px-2 text-xs font-semibold text-white disabled:border-neutral-300 disabled:bg-neutral-200 disabled:text-neutral-500"
                disabled={disabled || !storageReady || !preset}
                type="button"
                onClick={() => loadSlot(index)}
              >
                呼び出す
              </button>
              <button
                className="min-h-9 border border-neutral-300 px-2 text-xs font-semibold text-neutral-800 disabled:text-neutral-400"
                disabled={disabled || !storageReady}
                type="button"
                onClick={() => saveSlot(index)}
              >
                {preset ? "上書き保存" : "現在設定を保存"}
              </button>
            </div>
            {preset ? (
              <button
                className="mt-2 min-h-8 text-xs font-medium text-red-700 underline underline-offset-2 disabled:text-neutral-400"
                disabled={disabled || !storageReady}
                type="button"
                onClick={() => deleteSlot(index)}
              >
                この保存枠を削除
              </button>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  );
}
