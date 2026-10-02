"use client";

import Image from "next/image";
import { toBrowserApiUrl } from "../lib/api";
import type { ThumbnailFrameCandidate } from "../lib/types";

export function ThumbnailFramePicker({ candidates, selectedId, cropMode, disabled, onSelect, onCropChange }: {
  candidates: ThumbnailFrameCandidate[]; selectedId?: string; cropMode: "standard" | "close";
  disabled?: boolean; onSelect: (id: string) => void; onCropChange: (mode: "standard" | "close") => void;
}) {
  const selected = candidates.find(c => c.id === selectedId);
  return <fieldset disabled={disabled} className="mt-3 border border-amber-300 bg-white p-3">
    <legend className="px-1 text-xs font-bold">動画からの人物候補</legend>
    <div className="grid max-h-60 grid-cols-4 gap-2 overflow-y-auto" aria-label="保存済みの人物候補">
      {candidates.map(candidate => <button key={candidate.id} type="button" aria-pressed={candidate.id === selectedId}
        aria-label={`動画の候補 ${candidate.second.toFixed(1)}秒`} onClick={() => onSelect(candidate.id)}
        className="border-2 border-neutral-300 text-xs aria-pressed:border-sky-700">
        <Image src={toBrowserApiUrl(candidate.imageUrl)} alt={`${candidate.second.toFixed(1)}秒の人物`} width={240} height={135}
          unoptimized className="aspect-video w-full object-contain" />
        {candidate.second.toFixed(1)}秒
      </button>)}
    </div>
    <div className="mt-2 grid grid-cols-2 gap-2">
      {([["standard", "半身"], ["close", "顔のアップ"]] as const).map(([mode, label]) => <button key={mode}
        type="button" aria-pressed={cropMode === mode} disabled={mode === "close" && !selected?.closeAvailable}
        onClick={() => onCropChange(mode)} className="min-h-10 border border-sky-700 text-xs aria-pressed:bg-sky-100 disabled:text-neutral-400">
        {label}
      </button>)}
    </div>
    {selected && !selected.closeAvailable && <p className="mt-1 text-xs text-neutral-600">この候補は2倍以内の拡大で顔のアップにできません。</p>}
  </fieldset>;
}
