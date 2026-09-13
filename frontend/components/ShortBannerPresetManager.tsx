"use client";

import Image from "next/image";
import { useLayoutEffect, useRef, useState } from "react";
import { bannerAssetUrl, bannerRequest } from "../lib/shortBanners";
import type { ClipSettings } from "../lib/types";

export function ShortBannerPresetManager({ settings, disabled = false, onChange }: {
  settings: ClipSettings; disabled?: boolean; onChange: (value: ClipSettings) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const latest = useRef(settings);
  useLayoutEffect(() => { latest.current = settings; }, [settings]);

  async function upload(position: "top" | "bottom", file: File) {
    setBusy(true); setError(""); setNotice("");
    try {
      const body = new FormData(); body.append("file", file);
      const result = await bannerRequest<{ assetId: string }>("short-banner-assets", { method: "POST", body });
      const patch = position === "top" ? { shortTopBannerAssetId: result.assetId, shortTopBannerEnabled: true }
        : { shortBottomBannerAssetId: result.assetId, shortBottomBannerEnabled: true };
      onChange({ ...latest.current, ...patch });
      setNotice("画像を反映しました。キャラ設定で一括保存してください。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "画像の保存に失敗しました。"); }
    finally { setBusy(false); }
  }

  return (
    <fieldset className="mt-3 min-w-0 border border-neutral-200 p-3" disabled={disabled || busy}>
      <legend className="px-1 text-sm font-medium">ショート帯</legend>
      <div className="flex flex-wrap items-center gap-3">
        {(["top", "bottom"] as const).map((position) => (
          <label key={position} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={position === "top" ? settings.shortTopBannerEnabled : settings.shortBottomBannerEnabled}
              onChange={(event) => onChange({ ...settings, [position === "top" ? "shortTopBannerEnabled" : "shortBottomBannerEnabled"]: event.target.checked })} />
            {position === "top" ? "上: 柄帯" : "下: ロゴ"}
          </label>
        ))}
        <details className="min-w-0 flex-1 basis-full">
          <summary className="cursor-pointer text-sm">帯画像を編集</summary>
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
        </details>
      </div>
      {busy && <p role="status" className="mt-2 text-xs">画像をアップロード中…</p>}
      {notice && <p role="status" className="mt-2 text-xs text-emerald-700">{notice}</p>}
      {error && <p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}
    </fieldset>
  );
}
