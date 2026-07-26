"use client";

import { useEffect, useState } from "react";

import {
  getSubtitleStylePresets,
  saveSubtitleStylePresets
} from "../lib/api";
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

function defaultSlotName(index: number): string {
  return `字幕設定 ${index + 1}`;
}

function storeLocalBackup(slots: SubtitleStylePresetSlots): void {
  try {
    window.localStorage.setItem(
      SUBTITLE_STYLE_PRESET_STORAGE_KEY,
      serializeSubtitleStylePresetSlots(slots)
    );
  } catch {
    // SQLite is authoritative. A local backup is optional.
  }
}

function mergeLocalPresetsIntoEmptySlots(
  storedSlots: SubtitleStylePresetSlots,
  localSlots: SubtitleStylePresetSlots
): { slots: SubtitleStylePresetSlots; migrated: boolean } {
  const merged = [...storedSlots] as SubtitleStylePresetSlots;
  let migrated = false;
  for (let index = 0; index < merged.length; index += 1) {
    if (merged[index] === null && localSlots[index] !== null) {
      merged[index] = localSlots[index];
      migrated = true;
    }
  }
  return { slots: merged, migrated };
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
  const [slots, setSlots] = useState<SubtitleStylePresetSlots>(
    emptySubtitleStylePresetSlots
  );
  const [storageReady, setStorageReady] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [slotNameOverrides, setSlotNameOverrides] = useState<
    Partial<Record<number, string>>
  >({});
  const [notice, setNotice] = useState("");
  const [writeError, setWriteError] = useState("");
  const storageError = loadError || writeError;

  useEffect(() => {
    let cancelled = false;
    let localSlots = emptySubtitleStylePresetSlots();
    try {
      localSlots = parseSubtitleStylePresetSlots(
        window.localStorage.getItem(SUBTITLE_STYLE_PRESET_STORAGE_KEY)
      );
    } catch {
      localSlots = emptySubtitleStylePresetSlots();
    }

    async function load() {
      try {
        const stored = await getSubtitleStylePresets();
        const merged = mergeLocalPresetsIntoEmptySlots(
          stored.slots,
          localSlots
        );
        let nextSlots = merged.slots;
        if (merged.migrated) {
          const migrated = await saveSubtitleStylePresets(merged.slots);
          nextSlots = migrated.slots;
          if (!cancelled) {
            setNotice("以前のブラウザ保存をAutoClipper本体へ移行しました");
          }
        }
        if (!cancelled) {
          setSlots(nextSlots);
          storeLocalBackup(nextSlots);
          setLoadError("");
        }
      } catch {
        if (!cancelled) {
          setSlots(localSlots);
          setLoadError(
            "AutoClipper本体の保存先を読み込めません。再起動後の保持を確認できません"
          );
        }
      } finally {
        if (!cancelled) {
          setStorageReady(true);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  async function persist(nextSlots: SubtitleStylePresetSlots): Promise<boolean> {
    setIsSaving(true);
    try {
      const stored = await saveSubtitleStylePresets(nextSlots);
      setSlots(stored.slots);
      storeLocalBackup(stored.slots);
      setLoadError("");
      setWriteError("");
      return true;
    } catch {
      setWriteError("字幕設定をAutoClipper本体へ保存できませんでした");
      return false;
    } finally {
      setIsSaving(false);
    }
  }

  async function saveSlot(index: number) {
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
    if (await persist(nextSlots)) {
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

  async function deleteSlot(index: number) {
    const preset = slots[index];
    if (!preset || !window.confirm(`「${preset.name}」を削除しますか？`)) {
      return;
    }
    const nextSlots = [...slots] as SubtitleStylePresetSlots;
    nextSlots[index] = null;
    if (await persist(nextSlots)) {
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
            AutoClipper本体に保存。停止・再起動後も保持
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
                disabled={disabled || !storageReady || isSaving}
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
                disabled={disabled || !storageReady || isSaving || !preset}
                type="button"
                onClick={() => loadSlot(index)}
              >
                呼び出す
              </button>
              <button
                className="min-h-9 border border-neutral-300 px-2 text-xs font-semibold text-neutral-800 disabled:text-neutral-400"
                disabled={disabled || !storageReady || isSaving}
                type="button"
                onClick={() => void saveSlot(index)}
              >
                {preset ? "上書き保存" : "現在設定を保存"}
              </button>
            </div>
            {preset ? (
              <button
                className="mt-2 min-h-8 text-xs font-medium text-red-700 underline underline-offset-2 disabled:text-neutral-400"
                disabled={disabled || !storageReady || isSaving}
                type="button"
                onClick={() => void deleteSlot(index)}
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
