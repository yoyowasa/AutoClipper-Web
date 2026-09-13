"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { applyCharacter, captureCharacter, newCharacter, type CharacterPresetDocument } from "../lib/characterPresets";
import { bannerRequest } from "../lib/shortBanners";
import { captureSubtitleStyle } from "../lib/subtitleStylePresets";
import type { ClipSettings } from "../lib/types";

export function CharacterPresetManager({ settings, disabled, onChange }: {
  settings: ClipSettings; disabled?: boolean; onChange: (settings: ClipSettings) => void;
}) {
  const [document, setDocument] = useState<CharacterPresetDocument>({ presets: [], selectedName: "" });
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const latest = useRef({ settings, onChange });
  useLayoutEffect(() => { latest.current = { settings, onChange }; }, [settings, onChange]);
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        let result = await bannerRequest<CharacterPresetDocument>("character-presets");
        if (cancelled) return;
        if (result.legacyImport) {
          result = { ...result, legacyImport: false, presets: result.presets.map((preset) => ({
            ...preset, settings: { ...captureSubtitleStyle(latest.current.settings), ...preset.settings }
          })) };
          result = await bannerRequest<CharacterPresetDocument>("character-presets", {
            method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(result)
          });
          if (cancelled) return;
        }
        setDocument(result); setReady(true); setName(result.selectedName);
        const selected = result.presets.find((preset) => preset.name === result.selectedName);
        latest.current.onChange(selected ? applyCharacter(latest.current.settings, selected) : newCharacter(latest.current.settings));
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "読込に失敗しました。"); }
    }
    void load(); return () => { cancelled = true; };
  }, []);

  async function persist(next: CharacterPresetDocument) {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await bannerRequest<CharacterPresetDocument>("character-presets", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(next)
      });
      setDocument(result); return true;
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存に失敗しました。"); return false; }
    finally { setBusy(false); }
  }
  async function choose(value: string) {
    if (!await persist({ ...document, selectedName: value })) return;
    setName(value);
    const preset = document.presets.find((item) => item.name === value);
    onChange(preset ? applyCharacter(latest.current.settings, preset) : newCharacter(latest.current.settings));
    setNotice(preset ? "キャラ設定を一括で呼び出しました。" : "新規キャラ：ショートのみ・帯なしから設定できます。");
  }
  async function save() {
    const savedName = name.trim();
    const snapshot = captureCharacter(latest.current.settings);
    const next = { name: savedName, settings: snapshot };
    const presets = document.presets.some((item) => item.name === savedName)
      ? document.presets.map((item) => item.name === savedName ? next : item) : [...document.presets, next];
    if (await persist({ presets, selectedName: savedName })) {
      onChange({ ...latest.current.settings, characterPresetName: savedName });
      setNotice("投稿情報・上下帯・文字スタイル・通常タイトル末尾・サムネイル・出力本数を保存しました。");
    }
  }
  const existing = document.presets.some((item) => item.name === name.trim());
  return <fieldset disabled={disabled || busy || !ready} className="grid gap-2 border-t border-neutral-200 bg-sky-50 p-3 text-xs">
    <legend className="sr-only">キャラ別一括設定</legend>
    <strong className="text-sm">キャラ別一括設定</strong>
    <label className="grid gap-1">使うキャラ設定
      <select aria-label="使うキャラ設定" className="min-h-10 min-w-0 border border-neutral-300 bg-white px-2"
        value={document.selectedName} onChange={(event) => void choose(event.target.value)}>
        <option value="">新しいキャラ（ショートのみ）</option>
        {document.presets.map((preset) => <option key={preset.name} value={preset.name}>{preset.name}</option>)}
      </select>
    </label>
    <label className="grid gap-1">保存名（チャンネル名＋キャラ名など）
      <input className="min-h-9 min-w-0 border border-neutral-300 px-2" maxLength={80} value={name} placeholder="例：切り抜きチャンネルA／キャラ名" onChange={(event) => setName(event.target.value)} />
    </label>
    <button className="min-h-10 bg-neutral-950 px-2 text-white disabled:opacity-40" type="button"
      disabled={!name.trim() || (!existing && document.presets.length >= 50)} onClick={() => void save()}>
      {existing ? "この名前のキャラ設定を上書き保存" : "現在の設定をキャラごと保存"}
    </button>
    <span className="text-neutral-600">{document.presets.length} / 50 保存済み。元配信タイトル・URLは動画ごとの入力です。</span>
    {document.selectedName && <button type="button" className="text-left text-neutral-600" onClick={async () => {
      if (await persist({ presets: document.presets.filter((item) => item.name !== document.selectedName), selectedName: "" })) {
        setName(""); onChange(newCharacter(latest.current.settings)); setNotice("保存一覧から削除しました。作成済み動画の設定・画像は残ります。");
      }
    }}>このキャラ設定を保存一覧から削除</button>}
    {notice && <p role="status" className="text-emerald-700">{notice}</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </fieldset>;
}
