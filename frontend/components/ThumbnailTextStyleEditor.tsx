"use client";

import { useState } from "react";
import type { ThumbnailFontPreset, ThumbnailTextStyle, ThumbnailTextStyles } from "../lib/types";
import { THUMBNAIL_FONTS } from "../lib/thumbnailStyle";

const ROWS = [["heading", "見出し", 96], ["upper", "上行", 180], ["lower", "下行", 180]] as const;
const COLORS = ["#E0C57B", "#FFFFFF", "#FFD84A", "#5EE7F7", "#FF8FAB", "#9BFF9B", "#000000"];

function SizeInput({ label, value, max, onChange }: { label: string; value: number; max: number; onChange: (value: number) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  return <input aria-label={label} type="number" min={12} max={max} step={1}
    className="min-h-9 min-w-0 w-full border border-neutral-300 px-2" value={draft ?? value}
    onChange={event => {
      const next = event.target.value;
      setDraft(next);
      const size = Number(next);
      if (next.trim() && Number.isFinite(size) && size >= 12 && size <= max) onChange(Math.round(size));
    }}
    onBlur={() => { if (draft !== null && draft.trim() && Number.isFinite(Number(draft))) onChange(Math.max(12, Math.min(max, Math.round(Number(draft))))); setDraft(null); }} />;
}

export function ThumbnailTextStyleEditor({ value, onChange, disabled, texts }: {
  value: ThumbnailTextStyles; onChange: (value: ThumbnailTextStyles) => void; disabled?: boolean;
  texts?: Partial<Record<keyof ThumbnailTextStyles, string>>;
}) {
  const update = (role: keyof ThumbnailTextStyles, patch: Partial<ThumbnailTextStyle>) =>
    onChange({ ...value, [role]: { ...value[role], ...patch } });
  return <fieldset disabled={disabled} className="min-w-0 space-y-3">
    {ROWS.map(([role, label, maxSize]) => <div key={role} className="min-w-0 border border-neutral-300 bg-white p-2">
      <div className="mb-2 flex min-w-0 items-baseline gap-2">
        <span className="shrink-0 text-xs font-bold">{label}</span>
        {texts && <span className="truncate text-xs text-neutral-500" title={texts[role]}>{texts[role] || "空欄のため非表示"}</span>}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_75px] gap-2">
        <label className="grid min-w-0 gap-1 text-xs">フォント
          <select aria-label={`サムネ ${label} フォント`} className="min-h-9 min-w-0 w-full border border-neutral-300 bg-white px-2"
            value={value[role].fontPreset} onChange={event => update(role, { fontPreset: event.target.value as ThumbnailFontPreset })}>
            {THUMBNAIL_FONTS.map(font => <option key={font.value} value={font.value}>{font.label}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-xs">サイズ
          <SizeInput label={`サムネ ${label} サイズ`} value={value[role].fontSize} max={maxSize}
            onChange={fontSize => update(role, { fontSize, autoFit: false })} />
        </label>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <label className="mr-1 flex items-center gap-1 text-xs">文字色
          <input aria-label={`サムネ ${label} 文字色`} type="color" className="h-7 w-9 cursor-pointer border bg-white p-0.5"
            value={value[role].color} onChange={event => update(role, { color: event.target.value })} />
        </label>
        {COLORS.map(color => <button key={color} type="button" aria-label={`サムネ ${label} ${color}`}
          aria-pressed={value[role].color.toUpperCase() === color} style={{ backgroundColor: color }}
          className="h-6 w-6 border border-neutral-400 aria-pressed:outline aria-pressed:outline-2 aria-pressed:outline-sky-600"
          onClick={() => update(role, { color })} />)}
      </div>
      <label className="mt-2 flex items-center gap-2 text-xs">
        <input type="checkbox" aria-label={`サムネ ${label} 枠に収める`} checked={value[role].autoFit !== false}
          onChange={event => update(role, { autoFit: event.target.checked })} />
        枠に収める（自動縮小）
        <span className="text-neutral-500">{value[role].autoFit === false ? "指定サイズで表示" : "サイズは上限"}</span>
      </label>
    </div>)}
    <p className="text-xs text-neutral-500">サイズ変更時は自動縮小を解除し、指定した大きさで表示します。文字がはみ出す場合は「枠に収める」をONにしてください。</p>
  </fieldset>;
}
