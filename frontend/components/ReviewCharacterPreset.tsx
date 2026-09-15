"use client";

import { useEffect, useState } from "react";
import { bannerRequest } from "../lib/shortBanners";
import type { CharacterPresetDocument } from "../lib/characterPresets";

export function ReviewCharacterPreset({ disabled, onApply }: {
  disabled: boolean; onApply: (name: string) => Promise<boolean>;
}) {
  const [names, setNames] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true;
    void bannerRequest<CharacterPresetDocument>("character-presets").then(result => {
      if (active) setNames(result.presets.map(preset => preset.name));
    }).catch(() => { if (active) setMessage("キャラ設定の一覧を読み込めませんでした。"); });
    return () => { active = false; };
  }, []);
  return <fieldset disabled={disabled || busy} className="mt-3 border border-sky-200 bg-sky-50 p-3">
    <legend className="text-sm font-semibold">キャラ設定を読み込む</legend>
    <div className="flex flex-wrap gap-2">
      <select aria-label="読み込むキャラ設定" className="min-h-10 min-w-0 flex-1 border bg-white px-2 text-sm"
        value={selected} onChange={event => setSelected(event.target.value)}>
        <option value="">保存した設定を選択</option>
        {names.map(name => <option key={name} value={name}>{name}</option>)}
      </select>
      <button type="button" disabled={!selected || busy} className="min-h-10 bg-sky-700 px-3 text-sm text-white disabled:bg-neutral-300"
        onClick={async () => {
          setBusy(true); setMessage("");
          try { if (await onApply(selected)) setMessage(`${selected}をこのジョブの全動画に反映しました。`); }
          finally { setBusy(false); }
        }}>{busy ? "読込中…" : "このジョブに反映"}</button>
    </div>
    <p className="mt-2 text-xs text-neutral-600">帯画像・文字スタイル・投稿情報・通常タイトル末尾・サムネイル設定を読み込みます。個別の文字書式も切り替わります。字幕の文章・切り抜き区間・本数・画角は保持します。</p>
    {message && <p role="status" className="mt-2 text-xs">{message}</p>}
  </fieldset>;
}
