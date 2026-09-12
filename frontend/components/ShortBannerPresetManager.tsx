"use client";

import Image from "next/image";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { applyBannerPreset, bannerAssetUrl, bannerRequest, RADEN_BANNERS, type ShortBannerPreset } from "../lib/shortBanners";
import type { ClipSettings } from "../lib/types";

export function ShortBannerPresetManager({ settings, disabled = false, onChange }: {
  settings: ClipSettings; disabled?: boolean; onChange: (value: ClipSettings) => void;
}) {
  const [presets, setPresets] = useState<ShortBannerPreset[]>([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState(settings.shortBannerPresetName ?? "");
  const [selected, setSelected] = useState(settings.shortBannerPresetName ?? "");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const latest = useRef(settings);
  useLayoutEffect(() => { latest.current = settings; }, [settings]);
  useEffect(() => {
    let cancelled = false;
    bannerRequest<{ presets: ShortBannerPreset[] }>("short-banner-presets")
      .then((result) => { if (!cancelled) { setPresets(result.presets); setReady(true); } })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); });
    return () => { cancelled = true; };
  }, []);

  async function save(remove = false) {
    setBusy(true); setError(""); setNotice("");
    const savedName = name.trim();
    const current = latest.current;
    const snapshot: ShortBannerPreset = { name: savedName,
      topAssetId: current.shortTopBannerAssetId ?? "raden-top",
      bottomAssetId: current.shortBottomBannerAssetId ?? "raden-bottom",
      topEnabled: current.shortTopBannerEnabled, bottomEnabled: current.shortBottomBannerEnabled };
    const next = remove ? presets.filter((preset) => preset.name !== selected)
      : presets.some((preset) => preset.name === savedName)
        ? presets.map((preset) => preset.name === savedName ? snapshot : preset) : [...presets, snapshot];
    try {
      const result = await bannerRequest<{ presets: ShortBannerPreset[] }>("short-banner-presets", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ presets: next })
      });
      setPresets(result.presets); setSelected(remove ? "" : savedName);
      if (!remove) onChange({ ...latest.current, shortBannerPresetName: savedName });
      setNotice(remove ? "保存一覧から削除しました。使用中の帯画像は残ります。" : `${savedName}を保存しました。`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存に失敗しました。"); }
    finally { setBusy(false); }
  }

  async function upload(position: "top" | "bottom", file: File) {
    setBusy(true); setError(""); setNotice("");
    try {
      const body = new FormData(); body.append("file", file);
      const result = await bannerRequest<{ assetId: string }>("short-banner-assets", { method: "POST", body });
      const patch = position === "top" ? { shortTopBannerAssetId: result.assetId, shortTopBannerEnabled: true }
        : { shortBottomBannerAssetId: result.assetId, shortBottomBannerEnabled: true };
      onChange({ ...latest.current, ...patch });
      setSelected("__editing");
      setNotice("画像を反映しました。名前を付けて保存できます。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "画像の保存に失敗しました。"); }
    finally { setBusy(false); }
  }

  const overwrites = presets.some((preset) => preset.name === name.trim());
  const matchingPreset = presets.find((preset) =>
    preset.topAssetId === (settings.shortTopBannerAssetId ?? "raden-top") &&
    preset.bottomAssetId === (settings.shortBottomBannerAssetId ?? "raden-bottom") &&
    preset.topEnabled === settings.shortTopBannerEnabled && preset.bottomEnabled === settings.shortBottomBannerEnabled);
  const activeValue = !settings.shortTopBannerEnabled && !settings.shortBottomBannerEnabled ? "__off"
    : matchingPreset?.name ?? ((settings.shortTopBannerAssetId ?? "raden-top") === "raden-top" &&
      (settings.shortBottomBannerAssetId ?? "raden-bottom") === "raden-bottom" &&
      settings.shortTopBannerEnabled && settings.shortBottomBannerEnabled ? "" : "__editing");
  return (
    <fieldset className="mt-3 min-w-0 border border-neutral-200 p-3" disabled={disabled || busy}>
      <legend className="px-1 text-sm font-medium">ショート帯</legend>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex min-w-0 items-center gap-2 text-sm">
          帯だけ呼び出す
          <select aria-label="帯だけ呼び出す" className="min-h-10 max-w-64 border border-neutral-300 bg-white px-3" value={activeValue}
            onChange={(event) => {
              const value = event.target.value;
              if (value === "__off") {
                onChange({ ...latest.current, shortTopBannerEnabled: false, shortBottomBannerEnabled: false });
                return;
              }
              const preset = presets.find((item) => item.name === value) ?? RADEN_BANNERS;
              setSelected(value); setName(value); setNotice("");
              onChange(applyBannerPreset(latest.current, preset));
            }}>
            <option value="">らでん用（標準）</option>
            <option value="__off">帯なし</option>
            {activeValue === "__editing" && <option value="__editing" disabled>編集中の帯</option>}
            {presets.map((preset) => <option key={preset.name} value={preset.name}>{preset.name}</option>)}
          </select>
        </label>
        {(["top", "bottom"] as const).map((position) => (
          <label key={position} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={position === "top" ? settings.shortTopBannerEnabled : settings.shortBottomBannerEnabled}
              onChange={(event) => onChange({ ...settings, [position === "top" ? "shortTopBannerEnabled" : "shortBottomBannerEnabled"]: event.target.checked })} />
            {position === "top" ? "上: 柄帯" : "下: ロゴ"}
          </label>
        ))}
        <details className="min-w-0 flex-1 basis-full">
          <summary className="cursor-pointer text-sm">帯画像を編集／帯だけ保存 <span className="text-xs text-neutral-500">{presets.length} / 10 保存済み</span></summary>
          <p className="mt-2 text-xs text-neutral-600">上下の画像とON/OFFは、左の「キャラ別一括設定」で他の項目とまとめて保存できます。</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {(["top", "bottom"] as const).map((position) => {
              const label = position === "top" ? "上帯" : "下帯";
              const assetId = position === "top" ? settings.shortTopBannerAssetId ?? "raden-top" : settings.shortBottomBannerAssetId ?? "raden-bottom";
              return <label key={position} className="flex min-w-0 flex-col gap-2 text-sm">{label}の画像
                <Image alt={`${label}のプレビュー`} src={bannerAssetUrl(assetId)} width={324} height={108} unoptimized
                  className="h-24 w-full border border-neutral-200 bg-neutral-100 object-contain" />
                <input aria-label={`${label}の画像`} type="file" accept="image/png,image/jpeg,image/webp" className="min-w-0 w-full text-xs"
                  onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(position, file); }} />
              </label>;
            })}
          </div>
          <p className="mt-2 text-xs text-neutral-500">PNG・JPEG・WebP、10MBまで。横3:縦1の画像を推奨。上下それぞれ帯の枠に合わせて表示します。</p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-sm">保存名（誰用か）
              <input className="min-h-10 border border-neutral-300 px-3" maxLength={80} placeholder="例：らでん用・雑談" value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <button type="button" className="min-h-10 border border-neutral-300 px-3 text-sm disabled:opacity-40"
              disabled={!ready || !name.trim() || (!overwrites && presets.length >= 10)} onClick={() => void save()}>
              {overwrites ? "同じ名前の帯に上書き保存" : "名前を付けて保存"}
            </button>
            {presets.some((preset) => preset.name === selected) && <button type="button" className="min-h-10 px-3 text-sm" disabled={!ready} onClick={() => void save(true)}>保存一覧から削除</button>}
          </div>
        </details>
      </div>
      {busy && <p role="status" className="mt-2 text-xs">保存中…</p>}
      {notice && <p role="status" className="mt-2 text-xs text-emerald-700">{notice}</p>}
      {error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}
    </fieldset>
  );
}
