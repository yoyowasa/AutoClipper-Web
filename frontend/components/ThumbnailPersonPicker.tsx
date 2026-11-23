"use client";

import Image from "next/image";
import { toBrowserApiUrl } from "../lib/api";
import type { ThumbnailPerson } from "../lib/types";

/** Choose who the thumbnail centers on inside one saved still. Index 0 is the automatic choice. */
export function ThumbnailPersonPicker({ imageUrl, people, selectedIndex, disabled, onSelect }: {
  imageUrl: string; people: ThumbnailPerson[]; selectedIndex: number; disabled?: boolean;
  onSelect: (index: number) => void;
}) {
  if (people.length < 2) return null;
  const label = (index: number) => index === 0 ? "人物1（自動）" : `人物${index + 1}`;
  return <fieldset disabled={disabled} className="mt-3 border border-amber-300 bg-white p-3">
    <legend className="px-1 text-xs font-bold">中心にする人物</legend>
    <div className="relative w-full" aria-label="場面内の人物">
      <Image src={toBrowserApiUrl(imageUrl)} alt="選択中の場面" width={240} height={135} unoptimized className="h-auto w-full" />
      {people.map(person => <button key={person.index} type="button" aria-pressed={person.index === selectedIndex}
        aria-label={`${label(person.index)}を中心にする`} onClick={() => onSelect(person.index)}
        style={{ left: `${(person.x - person.width / 2) * 100}%`, top: `${(person.y - person.height / 2) * 100}%`,
          width: `${person.width * 100}%`, height: `${person.height * 100}%` }}
        className="absolute border-2 border-white/80 shadow-[0_0_0_1px_rgba(0,0,0,.6)] aria-pressed:border-sky-500 aria-pressed:bg-sky-500/20">
        <span className="absolute -top-5 left-0 whitespace-nowrap bg-black/70 px-1 text-[10px] text-white">{person.index + 1}</span>
      </button>)}
    </div>
    <div className="mt-2 flex flex-wrap gap-2">
      {people.map(person => <button key={person.index} type="button" aria-pressed={person.index === selectedIndex}
        onClick={() => onSelect(person.index)}
        className="min-h-9 border border-sky-700 px-2 text-xs aria-pressed:bg-sky-100 aria-pressed:font-semibold">
        {label(person.index)}
      </button>)}
    </div>
    <p className="mt-1 text-xs text-neutral-600">枠を押すとその人物の顔を中心に合わせます。半身が2倍以内の拡大で収まる人物だけ表示します。</p>
  </fieldset>;
}
