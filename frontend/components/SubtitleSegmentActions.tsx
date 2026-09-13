"use client";

import { useState } from "react";
import type { SubtitleReviewSegment, SubtitleStructureRequest } from "../lib/types";

export function SubtitleSegmentActions({ segment, next, text, nextText, cursor, origin, playhead, disabled, onEdit }: {
  segment: SubtitleReviewSegment; next?: SubtitleReviewSegment; text: string; nextText: string;
  cursor: number | null; origin: number; playhead: number; disabled: boolean;
  onEdit: (request: SubtitleStructureRequest) => Promise<void>;
}) {
  const [split, setSplit] = useState<{ offset: number; time: string } | null>(null);
  const update = { segmentId: segment.id, before: segment.text, text };
  const pieces = Array.from(text);
  const splitAt = split ? Number(split.time) + origin : 0;
  const validSplit = split && split.time.trim() && Number.isFinite(splitAt) &&
    splitAt > segment.start && splitAt < segment.end && pieces.slice(0, split.offset).join("").trim() &&
    pieces.slice(split.offset).join("").trim();
  return (
    <details className="mt-2 border border-neutral-200 bg-neutral-50 px-2 py-1 text-xs">
      <summary className="cursor-pointer">区間の結合・分割{segment.singleLine ? "・１行表示" : ""}</summary>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" disabled={disabled || !next} className="border px-2 py-1 disabled:opacity-40"
          onClick={() => next && void onEdit({ action: "merge", segments: [update,
            { segmentId: next.id, before: next.text, text: nextText }] })}>次の区間と結合・保存</button>
        <button type="button" disabled={disabled || !cursor || cursor >= pieces.length} className="border px-2 py-1 disabled:opacity-40"
          onClick={() => { if (cursor) setSplit({ offset: cursor, time: ((segment.start +
            (segment.end - segment.start) * cursor / pieces.length) - origin).toFixed(2) }); }}>
          カーソル位置で分割
        </button>
        <button type="button" disabled={disabled} aria-pressed={segment.singleLine ?? false}
          className="border px-2 py-1 aria-pressed:bg-sky-100 disabled:opacity-40"
          onClick={() => void onEdit({ action: "line", segments: [update], singleLine: !segment.singleLine })}>
          {segment.singleLine ? "自動改行に戻す" : "１行で表示・保存"}
        </button>
      </div>
      {next ? <p className="mt-2 break-words text-neutral-600">結合後：{text.trim()}{nextText.trim()}</p> : null}
      <p className="mt-1 text-neutral-500">分割は字幕内にカーソルを置いて選択。対象の未保存文も保存します。</p>
      {split ? <div className="mt-2 space-y-2 border-t pt-2">
        <p className="break-words">前：{pieces.slice(0, split.offset).join("")}<br />後：{pieces.slice(split.offset).join("")}</p>
        <label className="block">分割時刻（clip内・秒）
          <input aria-label="分割時刻（clip内・秒）" type="number" step="0.01" className="mt-1 w-full border p-1"
            value={split.time} onChange={e => setSplit({ ...split, time: e.target.value })} />
        </label>
        <p className="text-neutral-500">文字数からの仮時刻です。音声に合わせて調整してください。</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={disabled || playhead <= segment.start || playhead >= segment.end}
            className="border px-2 py-1 disabled:opacity-40"
            onClick={() => setSplit({ ...split, time: (playhead - origin).toFixed(2) })}>再生位置を使う</button>
          <button type="button" disabled={disabled || !validSplit} className="border bg-sky-100 px-2 py-1 disabled:opacity-40"
            onClick={() => void onEdit({ action: "split", segments: [update], splitOffset: split.offset,
              splitTime: splitAt })}>分割して保存</button>
          <button type="button" className="border px-2 py-1" onClick={() => setSplit(null)}>閉じる</button>
        </div>
      </div> : null}
    </details>
  );
}
