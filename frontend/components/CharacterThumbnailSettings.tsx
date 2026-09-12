"use client";

import Image from "next/image";
import { useLayoutEffect, useRef, useState } from "react";
import { PLAIN_THUMBNAIL } from "../lib/characterPresets";
import { bannerAssetUrl, bannerRequest } from "../lib/shortBanners";
import type { ClipSettings, NormalThumbnailStyle } from "../lib/types";

export function CharacterThumbnailSettings({ settings, disabled, onChange }: {
  settings: ClipSettings; disabled?: boolean; onChange: (settings: ClipSettings) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const latest = useRef(settings);
  useLayoutEffect(() => { latest.current = settings; }, [settings]);
  const style = settings.normalThumbnailStyle ?? PLAIN_THUMBNAIL;
  const update = (patch: Partial<NormalThumbnailStyle>) => onChange({ ...settings, normalThumbnailStyle: { ...style, ...patch } });
  return <details className="border-t border-neutral-200 p-3 text-xs">
    <summary className="cursor-pointer font-bold">通常動画のタイトル末尾・サムネイル</summary>
    <fieldset disabled={disabled || busy} className="mt-3 grid gap-3">
      <p className="text-neutral-500">ショートのみの場合は出力に使用しません。キャラ設定には保存されます。</p>
      <label className="grid gap-1">通常タイトル末尾（空欄でなし）
        <input className="min-h-9 border border-neutral-300 px-2" maxLength={80} value={settings.normalTitleSuffix ?? ""}
          onChange={(event) => onChange({ ...settings, normalTitleSuffix: event.target.value })} />
      </label>
      <label className="grid gap-1">サムネイル背景
        <select className="min-h-9 border border-neutral-300 bg-white px-2" value={style.design}
          onChange={(event) => update({ design: event.target.value as NormalThumbnailStyle["design"] })}>
          <option value="plain">単色</option><option value="raden">らでん用（既存デザイン）</option>
          {style.backgroundAssetId && <option value="custom">アップロード画像</option>}
        </select>
      </label>
      <label className="grid min-w-0 gap-1">サムネイル背景画像を選択（16:9）
        <input className="min-w-0 w-full" type="file" accept="image/png,image/jpeg,image/webp" onChange={async (event) => {
          const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
          setBusy(true); setError("");
          try {
            const body = new FormData(); body.append("file", file);
            const result = await bannerRequest<{ assetId: string }>("short-banner-assets", { method: "POST", body });
            const current = latest.current;
            onChange({ ...current, normalThumbnailStyle: { ...(current.normalThumbnailStyle ?? PLAIN_THUMBNAIL), design: "custom", backgroundAssetId: result.assetId } });
          } catch (reason) { setError(reason instanceof Error ? reason.message : "画像を保存できませんでした。"); }
          finally { setBusy(false); }
        }} />
      </label>
      {style.design === "custom" && style.backgroundAssetId && <Image alt="サムネイル背景プレビュー" width={320} height={180} unoptimized
        className="w-full border border-neutral-200" src={bannerAssetUrl(style.backgroundAssetId)} />}
      <div className="grid grid-cols-2 gap-2">
        {([["backgroundColor", "背景色"], ["titleColor", "見出し1の色"], ["secondTitleColor", "見出し2の色"], ["outlineColor", "文字の外縁色"]] as const).map(([key, label]) => (
          <label key={key} className="grid gap-1">{label}<input type="color" aria-label={`サムネイル${label}`} value={style[key]} onInput={(event) => update({ [key]: event.currentTarget.value })} onChange={(event) => update({ [key]: event.target.value })} /></label>
        ))}
      </div>
      <p className="text-neutral-500">右側に動画の人物、左側に見出しを配置します。変更後は上のキャラ設定で一括保存。</p>
      {error && <p role="alert" className="text-red-700">{error}</p>}
    </fieldset>
  </details>;
}
