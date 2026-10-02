"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { getThumbnailAssets } from "../lib/api";
import { CHARACTER_EMOTIONS, characterAssetImageUrl, type CharacterAssetList } from "../lib/characterAssets";
import type { ThumbnailSubjectSelection } from "../lib/types";

export function ThumbnailAssetPicker({ exportId, value, onChange, disabled }: {
  exportId: string; value: ThumbnailSubjectSelection;
  onChange: (value: ThumbnailSubjectSelection) => void; disabled?: boolean;
}) {
  const [assets, setAssets] = useState<CharacterAssetList | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    void getThumbnailAssets(exportId).then(next => { if (!cancelled) { setAssets(next); setError(""); } })
      .catch(cause => { if (!cancelled) setError(cause instanceof Error ? cause.message : "素材を読み込めませんでした。"); });
    return () => { cancelled = true; };
  }, [exportId, retry]);
  const all = assets ? CHARACTER_EMOTIONS.flatMap(({ value: emotion }) => assets.emotions[emotion]) : [];
  const selected = all.find(asset => asset.id === value.characterAssetId);
  const emotion = selected?.emotion ?? value.emotion;
  return <fieldset disabled={disabled} className="mt-3 border border-amber-300 bg-white p-3">
    <legend className="px-1 text-xs font-bold">人物の画像</legend>
    <div className="grid grid-cols-2 gap-2 text-sm">
      <button type="button" aria-pressed={value.subjectSource === "video"} onClick={() => onChange({ subjectSource: "video" })}
        className="min-h-10 border border-sky-700 px-2 aria-pressed:bg-sky-100">動画のコマ</button>
      <button type="button" aria-pressed={value.subjectSource === "asset"} disabled={!all.length}
        onClick={() => onChange({ subjectSource: "asset", characterAssetId: all[0].id, emotion: all[0].emotion })}
        className="min-h-10 border border-sky-700 px-2 aria-pressed:bg-sky-100 disabled:text-neutral-400">素材</button>
    </div>
    {error ? <div role="alert" className="mt-2 text-xs text-red-700">{error}
      <button type="button" className="ml-2 underline" onClick={() => { setAssets(null); setError(""); setRetry(v => v + 1); }}>再読み込み</button></div>
      : !assets ? <p className="mt-2 text-xs">素材を読み込み中…</p>
      : !all.length ? <p className="mt-2 text-xs text-neutral-600">このキャラには素材がありません。動画のコマを使います。</p> : null}
    {value.subjectSource === "asset" && <>
      <div className="mt-3 grid grid-cols-4 gap-2">
        {CHARACTER_EMOTIONS.map(({ value: next, label }) => <button key={next} type="button"
          aria-pressed={emotion === next} disabled={!assets?.emotions[next].length}
          onClick={() => { const asset = assets!.emotions[next][0]; onChange({ subjectSource: "asset", emotion: next, characterAssetId: asset.id }); }}
          className="min-h-9 border border-neutral-400 text-sm aria-pressed:bg-sky-100 disabled:text-neutral-400">{label}</button>)}
      </div>
      <div className="mt-2 grid grid-cols-5 gap-2" aria-label="選んだ表情の素材一覧">
        {(emotion ? assets?.emotions[emotion] ?? [] : []).map(asset => <button key={asset.id} type="button"
          aria-label={`素材 ${asset.slot}`} aria-pressed={asset.id === value.characterAssetId}
          onClick={() => onChange({ subjectSource: "asset", characterAssetId: asset.id, emotion: asset.emotion })}
          className="overflow-hidden border-2 border-neutral-300 bg-neutral-100 aria-pressed:border-sky-700">
          <Image src={characterAssetImageUrl(asset)} alt={`素材 ${asset.slot}`} width={96} height={128} unoptimized
            className="aspect-[3/4] w-full object-contain" />
        </button>)}
      </div>
      {assets && !selected && <p role="alert" className="mt-2 text-xs text-red-700">素材が見つかりません。表情と素材を選び直してください。</p>}
      {selected?.warnings.map(warning => <p key={warning} className="mt-2 text-xs text-amber-800">{warning}</p>)}
    </>}
  </fieldset>;
}
