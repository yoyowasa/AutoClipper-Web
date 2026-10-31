"use client";

import { useState } from "react";
import { matchingSubtitleCorrections, subtitleUndoUpdates, type CorrectionSelection, type SubtitleBatchUpdate, type SubtitleUndoUpdate } from "../lib/subtitleBulkCorrection";
import { subtitleTargetName } from "../lib/subtitleReview/sharedSegments";
import type { SubtitleReviewClip, SubtitleReviewSegment } from "../lib/types";

export function SubtitleBulkCorrection({ selection, onSelection, segments, clips, drafts, disabled, onSave, draftOnly = false, confirmedClipOnly = false }: {
  selection: CorrectionSelection | null;
  onSelection: (value: CorrectionSelection | null) => void;
  segments: SubtitleReviewSegment[];
  clips: SubtitleReviewClip[];
  drafts: Record<string, string>;
  disabled: boolean;
  draftOnly?: boolean;
  confirmedClipOnly?: boolean;
  onSave: (updates: SubtitleBatchUpdate[]) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [undo, setUndo] = useState<SubtitleUndoUpdate[]>([]);
  const matches = matchingSubtitleCorrections(segments, drafts, selection?.source ?? "", selection?.replacement ?? "");
  const count = matches.reduce((total, match) => total + match.count, 0);
  const clipCount = new Set(matches.flatMap((match) => match.clipIds)).size;
  // A confirmed edit can fork shared segment IDs. Follow the unchanged time slot,
  // and still require the last replacement text before offering an undo.
  const undoChanges = subtitleUndoUpdates(segments, undo);
  const canUndo = undo.length > 0 && undoChanges.length === undo.length && undoChanges.every((item) => {
    const segment = segments.find((value) => value.id === item.segmentId);
    return segment && (draftOnly || segment.text === item.before) && (drafts[item.segmentId] ?? segment.text) === item.before;
  });

  async function save(revert: boolean) {
    if (busy || disabled) return;
    const changes = revert ? undoChanges : matches.map(({ segmentId, before, text }) => ({ segmentId, before, text }));
    if (!changes.length) return;
    setBusy(true); setError("");
    try {
      await onSave(changes);
      setUndo(revert ? [] : matches.map(({ segmentId, current, text }) => {
        const segment = segments.find(item => item.id === segmentId)!;
        return { segmentId, before: text, text: current, index: segment.index, start: segment.start, end: segment.end };
      }));
      setNotice(revert ? "直前の一括修正を取り消しました。" : draftOnly ? `${count}か所を下書きに反映しました。${confirmedClipOnly ? "編集欄を離れると保存します。確定の解除は不要です。" : "clipの確定時に保存します。"}` : `${count}か所を修正して保存しました。対象の${clipCount}本は字幕を再確認してください。`);
      onSelection(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "一括修正を保存できませんでした。"); }
    finally { setBusy(false); }
  }

  return <section aria-label="同じ語句の一括修正" className="border-b border-neutral-300 bg-sky-50 px-4 py-3 text-xs">
    <p className="font-semibold">同じ語句をまとめて修正</p>
    <p className="mt-1 text-neutral-600">下の字幕で直したい語句を選択すると、同じ表記をまとめて直せます。</p>
    {selection && <div className="mt-2 grid gap-2">
      <p className="break-words">選択した語句：<strong>{selection.source}</strong></p>
      <label className="grid gap-1">正しい表記
        <input aria-label="一括修正の正しい表記" className="min-h-9 w-full border border-neutral-300 bg-white px-2 text-sm"
          maxLength={200} value={selection.replacement} disabled={disabled || busy}
          onChange={(event) => onSelection({ ...selection, replacement: event.target.value })} />
      </label>
      <p>{confirmedClipOnly ? "開いているclipだけを修正します。他のclipは確定・未確定にかかわらず変更しません。" : "確定済みのclipは対象外です。"}</p>
      <p>対象clip：{clips.filter(clip => matches.some(match => match.clipIds.includes(clip.id))).map(subtitleTargetName).join("、") || "なし"}</p>
      {selection.replacement && <p role="status">{count}か所・{matches.length}字幕・{clipCount}本</p>}
      {matches.length > 0 && <details>
        <summary className="cursor-pointer">修正前後を確認</summary>
        <div className="mt-2 max-h-40 space-y-2 overflow-y-auto">
          {matches.map((match) => <div className="border-b border-neutral-200 pb-2" key={match.segmentId}>
            <p className="text-neutral-500">元動画 {Math.floor(match.start / 60)}:{Math.floor(match.start % 60).toString().padStart(2, "0")}</p>
            <p className="break-words text-neutral-600">修正前：{match.current}</p>
            <p className="break-words font-medium">修正後：{match.text}</p>
          </div>)}
        </div>
      </details>}
      <p className="text-neutral-500">一致する表記だけを修正します。{draftOnly ? confirmedClipOnly ? "変更は下書きに反映し、編集欄を離れると保存します。" : "変更は下書きに反映し、clipの確定時にまとめて保存します。" : "対象の字幕に入力中の変更も一緒に保存します。"}</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={disabled || busy || !count || matches.some((match) => match.text.length > 4000)}
          className="min-h-9 bg-sky-700 px-3 font-semibold text-white disabled:opacity-40" onClick={() => void save(false)}>
          {busy ? "反映中…" : draftOnly ? `${count}か所をまとめて下書きへ反映` : `${count}か所をまとめて修正・保存`}
        </button>
        <button type="button" disabled={busy} className="min-h-9 border border-neutral-300 px-3" onClick={() => onSelection(null)}>閉じる</button>
      </div>
    </div>}
    {notice && <p role="status" className="mt-2 text-emerald-800">{notice}</p>}
    {undo.length > 0 && <button type="button" className="mt-2 min-h-9 border border-neutral-300 px-3 disabled:opacity-40"
      disabled={disabled || busy || !canUndo} onClick={() => void save(true)}>直前の一括修正を取り消す</button>}
    {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}
  </section>;
}
