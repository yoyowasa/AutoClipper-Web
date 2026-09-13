"use client";

import { useEffect, useRef, useState } from "react";
import type { ResultExportItem, ThumbnailCopyText, ThumbnailTextStyles } from "../lib/types";
import { ResultThumbnailEditor } from "./ResultThumbnailEditor";
import { LiveThumbnailPreview, type ThumbnailDraft } from "./LiveThumbnailPreview";
import { thumbnailTextDefaults } from "../lib/thumbnailStyle";

export function ResultThumbnailWorkspace({ item, busy, onRender }: {
  item: ResultExportItem;
  busy?: boolean;
  onRender: (crop: "standard" | "close", styles: ThumbnailTextStyles, text: ThumbnailCopyText, advance: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ThumbnailDraft>(() => ({
    text: { heading: item.thumbnailKicker ?? "", upper: item.thumbnailLine1 ?? "", lower: item.thumbnailLine2 ?? "" },
    styles: item.thumbnailTextStyles ?? thumbnailTextDefaults(),
  }));

  useEffect(() => {
    if (!open || !dialog.current) return;
    const element = dialog.current;
    const previousBodyOverflow = document.body.style.overflow;
    const previousRootOverflow = document.documentElement.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousRootOverflow;
    };
  }, [open]);

  return <>
    <button type="button" onClick={() => setOpen(true)}
      className="min-h-11 w-full border border-sky-700 bg-sky-50 px-4 text-sm font-semibold text-sky-900">
      サムネを編集
    </button>
    <dialog ref={dialog} aria-label="サムネイル編集" onClose={() => setOpen(false)}
      className="fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none overflow-hidden bg-neutral-50 p-3 text-neutral-950 backdrop:bg-black/50">
      <div className="flex h-full min-h-0 flex-col gap-3">
        <header className="flex shrink-0 items-center gap-3 border-b border-neutral-300 pb-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">サムネイル編集</h2>
            <p className="truncate text-xs text-neutral-600" title={item.title}>{item.title}</p>
          </div>
          <button type="button" autoFocus onClick={() => setOpen(false)}
            className="min-h-10 shrink-0 border border-neutral-400 bg-white px-4 text-sm font-semibold">結果一覧へ戻る</button>
        </header>
        <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,0.65fr)_minmax(0,1fr)] gap-3 overflow-hidden lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)] lg:grid-rows-1">
          <div aria-label="固定サムネプレビュー"
            className="flex min-h-0 min-w-0 items-start justify-center overflow-hidden bg-white [&>section]:flex [&>section]:max-h-full [&>section]:w-full [&>section]:flex-col [&_img]:min-h-0 [&_img]:flex-1 [&_img]:object-contain [&_section>div]:shrink-0">
            <LiveThumbnailPreview item={item} draft={draft} active={open} />
          </div>
          <ResultThumbnailEditor item={item} busy={busy} onRender={onRender} onDraftChange={setDraft} />
        </div>
      </div>
    </dialog>
  </>;
}
