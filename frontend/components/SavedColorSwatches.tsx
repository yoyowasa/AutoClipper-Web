"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "autoclipper.saved-colors.v1";
const CHANGE_EVENT = "autoclipper-saved-colors-changed";

function readColors(): string[] {
  const raw: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
  return Array.isArray(raw)
    ? [...new Set(raw.filter((color): color is string =>
        typeof color === "string" && /^#[0-9a-f]{6}$/i.test(color)
      ).map(color => color.toUpperCase()))]
    : [];
}

export function SavedColorSwatches({ color, label, disabled, onSelect }: {
  color: string; label: string; disabled?: boolean; onSelect: (color: string) => void;
}) {
  const [colors, setColors] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  const [managing, setManaging] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const refresh = () => {
      try { setColors(readColors()); setReady(true); setError(""); }
      catch { setReady(false); setError("保存した色を読み込めませんでした。"); }
    };
    refresh();
    window.addEventListener("storage", refresh);
    window.addEventListener(CHANGE_EVENT, refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener(CHANGE_EVENT, refresh);
    };
  }, []);

  function persist(value: string, remove = false) {
    try {
      const current = readColors();
      const next = remove ? current.filter(item => item !== value) : [...new Set([...current, value])];
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      window.dispatchEvent(new Event(CHANGE_EVENT));
      setError("");
    } catch { setError("色を保存できませんでした。"); }
  }

  const normalizedColor = color.toUpperCase();
  const saved = colors.includes(normalizedColor);
  return <div className="flex min-h-9 flex-wrap items-center gap-1.5 border-l border-neutral-300 pl-2" aria-label={`${label}の保存色`}>
    <span className="text-[10px] text-neutral-500">保存色</span>
    {colors.map(value => <span className="inline-flex items-center" key={value}>
      <button type="button" className="h-7 w-7 border border-neutral-400 aria-pressed:ring-2 aria-pressed:ring-sky-600"
        aria-label={`${label}に保存色 ${value}を使用`} aria-pressed={normalizedColor === value}
        title={value} style={{ backgroundColor: value }} disabled={disabled || !ready}
        onClick={() => onSelect(value)} />
      {managing && <button type="button" className="h-7 px-1 text-xs text-red-700"
        aria-label={`保存色 ${value}を削除`} disabled={disabled || !ready}
        onClick={() => persist(value, true)}>×</button>}
    </span>)}
    <button type="button" className="min-h-8 border border-neutral-300 px-2 text-[11px] disabled:text-neutral-400"
      disabled={disabled || !ready || saved || !/^#[0-9A-F]{6}$/.test(normalizedColor)}
      title="左の色選択でスポイト・手動指定した色を保存します。同じブラウザで共通です。"
      onClick={() => persist(normalizedColor)}>{saved ? "保存済み" : "＋今の色を保存"}</button>
    {colors.length > 0 && <button type="button" className="min-h-8 px-1 text-[10px] text-neutral-500"
      disabled={disabled} onClick={() => setManaging(!managing)}>{managing ? "完了" : "整理"}</button>}
    {error && <span role="alert" className="text-xs text-red-700">{error}</span>}
  </div>;
}
