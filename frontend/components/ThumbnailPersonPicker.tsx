"use client";

import Image from "next/image";
import type { MouseEvent } from "react";
import { toBrowserApiUrl } from "../lib/api";
import type { ThumbnailPerson, ThumbnailSubjectPoint } from "../lib/types";

/** Where a tap landed on the still, as 0-1 of its width and height. */
export function tappedPoint(event: MouseEvent<HTMLElement>): ThumbnailSubjectPoint {
  const rect = event.currentTarget.getBoundingClientRect();
  const clamp = (value: number) => Math.min(1, Math.max(0, Math.round(value * 1000) / 1000));
  return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
}

/**
 * Choose who the thumbnail centers on inside one saved still. Index 0 is the automatic choice.
 * A tap elsewhere on the still uses that spot as the face center, for faces the detector misses (profiles, closed eyes).
 */
export function ThumbnailPersonPicker({ imageUrl, people, selectedIndex, point, disabled, onSelect, onPoint }: {
  imageUrl: string; people: ThumbnailPerson[]; selectedIndex: number; point?: ThumbnailSubjectPoint; disabled?: boolean;
  onSelect: (index: number) => void; onPoint: (point: ThumbnailSubjectPoint) => void;
}) {
  const label = (index: number) => index === 0 ? "人物1（自動）" : `人物${index + 1}`;
  const pressed = (index: number) => !point && index === selectedIndex;
  return <fieldset disabled={disabled} className="mt-3 border border-amber-300 bg-white p-3">
    <legend className="px-1 text-xs font-bold">中心にする人物</legend>
    <div className="relative w-full" aria-label="場面内の人物">
      <button type="button" aria-label="押した位置を顔の中心にする" onClick={event => onPoint(tappedPoint(event))}
        className="block w-full cursor-crosshair">
        <Image src={toBrowserApiUrl(imageUrl)} alt="選択中の場面" width={240} height={135} unoptimized className="h-auto w-full" />
      </button>
      {people.map(person => <button key={person.index} type="button" aria-pressed={pressed(person.index)}
        aria-label={`${label(person.index)}を中心にする`} onClick={() => onSelect(person.index)}
        style={{ left: `${(person.x - person.width / 2) * 100}%`, top: `${(person.y - person.height / 2) * 100}%`,
          width: `${person.width * 100}%`, height: `${person.height * 100}%` }}
        className="absolute border-2 border-white/80 shadow-[0_0_0_1px_rgba(0,0,0,.6)] aria-pressed:border-sky-500 aria-pressed:bg-sky-500/20">
        <span className="absolute -top-5 left-0 whitespace-nowrap bg-black/70 px-1 text-[10px] text-white">{person.index + 1}</span>
      </button>)}
      {point && <span aria-label="押した位置" style={{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }}
        className="pointer-events-none absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-rose-500 shadow" />}
    </div>
    <div className="mt-2 flex flex-wrap gap-2">
      {people.map(person => <button key={person.index} type="button" aria-pressed={pressed(person.index)}
        onClick={() => onSelect(person.index)}
        className="min-h-9 border border-sky-700 px-2 text-xs aria-pressed:bg-sky-100 aria-pressed:font-semibold">
        {label(person.index)}
      </button>)}
      {point && <span className="self-center text-xs font-semibold text-rose-700">押した位置を使用中</span>}
    </div>
    <p className="mt-1 text-xs text-neutral-600">枠を押すとその人物、枠の無い人物は顔の中心を押すとその位置に合わせます（大きさは自動の顔と同じ）。半身が2倍以内の拡大で収まる位置だけ使えます。</p>
  </fieldset>;
}
