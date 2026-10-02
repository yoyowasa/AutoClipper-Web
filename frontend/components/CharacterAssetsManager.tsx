"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import {
  CHARACTER_EMOTIONS, characterAssetImageUrl, characterAssetSlots, deleteCharacterAsset,
  getCharacterAssets, uploadCharacterAsset, visibleCharacterAssetWarnings, type CharacterAssetList, type CharacterEmotion
} from "../lib/characterAssets";

export function CharacterAssetsManager({ presetId, disabled, onBusyChange, revision = 0, onAssetsChange }: {
  presetId: string; disabled?: boolean; onBusyChange: (busy: boolean) => void;
  revision?: number; onAssetsChange?: () => void;
}) {
  const [data, setData] = useState<CharacterAssetList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    void getCharacterAssets(presetId).then(result => {
      if (!cancelled) { setData(result); setError(""); }
    }).catch(reason => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : "素材を読み込めませんでした。");
    });
    return () => { cancelled = true; };
  }, [presetId, reload, revision]);

  async function upload(emotion: CharacterEmotion, files: File[]) {
    if (!data || files.length === 0) return;
    const free = data.maxPerEmotion - data.emotions[emotion].length;
    if (files.length > free) { setError(`この表情の空き枠は${free}枚です。選ぶ画像を減らしてください。`); return; }
    if (files.some(file => file.size > data.maxImageBytes)) { setError("画像は1枚20MBまでです。"); return; }
    setBusy(true); onBusyChange(true); setError(""); setNotice("");
    let uploaded = 0;
    const errors: string[] = [];
    try {
      for (const file of files) {
        try { await uploadCharacterAsset(presetId, emotion, file); uploaded += 1; }
        catch (reason) { errors.push(`${file.name}: ${reason instanceof Error ? reason.message : "登録に失敗しました。"}`); }
      }
      setData(await getCharacterAssets(presetId));
      onAssetsChange?.();
      if (uploaded) setNotice(`${uploaded}枚の素材を登録しました。`);
      if (errors.length) setError(errors.join("\n"));
    } catch (reason) {
      setError(`登録結果の読込に失敗しました。一覧を再読込してください。${reason instanceof Error ? reason.message : ""}`);
    } finally { setBusy(false); onBusyChange(false); }
  }

  async function remove(assetId: string) {
    setBusy(true); onBusyChange(true); setError(""); setNotice("");
    try {
      await deleteCharacterAsset(presetId, assetId);
      setData(await getCharacterAssets(presetId));
      setNotice("素材を削除しました。");
      onAssetsChange?.();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "削除に失敗しました。一覧を再読込してください。"); }
    finally { setBusy(false); onBusyChange(false); }
  }

  return <section aria-label="キャラの表情素材" className="grid gap-2 border-t border-sky-200 pt-3">
    <h3 className="text-sm font-semibold">サムネ用の表情素材（各5枚まで）</h3>
    <p>配信者・事務所の切り抜きガイドラインで使用が認められた素材だけを登録してください。</p>
    <p>胸から上が写った画像を登録してください。サムネでは高さを人物枠に合わせます。</p>
    {data && <p className="text-neutral-600">PNG・JPEG・WebP / 1枚20MBまで / 短い辺{data.minSidePixels}px以上。複数選択で空き枠へ順に登録できます。</p>}
    {!data && !error && <p role="status">素材を読み込み中…</p>}
    <div className="overflow-x-auto">
      <div className="grid min-w-[640px] grid-cols-4 gap-2">
        {CHARACTER_EMOTIONS.map(emotion => <div key={emotion.value} className="grid content-start gap-2">
          <h4 className="text-center font-semibold">{emotion.label}（{data?.emotions[emotion.value].length ?? 0}/5）</h4>
          {characterAssetSlots(data?.emotions[emotion.value] ?? [], data?.maxPerEmotion ?? 5).map((asset, index) =>
            <div key={index} className="grid content-start gap-1 rounded border border-sky-200 bg-white p-2"
              aria-label={`${emotion.label}の素材${index + 1}`}>
              <span className="text-neutral-500">{index + 1}</span>
              {asset ? <>
                <a href={characterAssetImageUrl(asset)} target="_blank" rel="noopener noreferrer"
                  aria-label={`${emotion.label}の素材${index + 1}をプレビュー`} className="block bg-neutral-100">
                  <Image unoptimized src={characterAssetImageUrl(asset)} alt={`${emotion.label}の表情素材${index + 1}`}
                    width={asset.width} height={asset.height} className="h-24 w-full object-contain" />
                </a>
                <span>{asset.width} × {asset.height}px{asset.hasAlpha ? " / 透過あり" : " / 背景付き"}</span>
                {visibleCharacterAssetWarnings(asset.warnings).map(warning => <p key={warning} className="text-amber-800">{warning}</p>)}
                <button type="button" disabled={disabled || busy} className="min-h-9 border border-neutral-300 disabled:opacity-40"
                  onClick={() => void remove(asset.id)} aria-label={`${emotion.label}の素材${index + 1}を削除`}>削除</button>
              </> : <label className="grid min-h-24 content-center gap-1 bg-neutral-50 p-1">
                <span>空き枠へ登録</span>
                <input type="file" multiple accept="image/png,image/jpeg,image/webp" className="w-full text-[10px]"
                  aria-label={`${emotion.label}の素材${index + 1}をアップロード`} disabled={disabled || busy || !data}
                  onChange={event => {
                    const files = Array.from(event.currentTarget.files ?? []);
                    event.currentTarget.value = "";
                    void upload(emotion.value, files);
                  }} />
              </label>}
            </div>)}
        </div>)}
      </div>
    </div>
    {notice && <p role="status" className="text-emerald-700">{notice}</p>}
    {error && <p role="alert" className="whitespace-pre-line text-red-700">{error}</p>}
    <button type="button" disabled={disabled || busy} className="justify-self-start underline disabled:opacity-40"
      onClick={() => setReload(value => value + 1)}>素材一覧を再読込</button>
  </section>;
}
