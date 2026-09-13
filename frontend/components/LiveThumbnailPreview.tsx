"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { prepareThumbnailPreview, renderThumbnailPreview, toBrowserApiUrl } from "../lib/api";
import type { ResultExportItem, ThumbnailCopyText, ThumbnailTextStyles } from "../lib/types";

export type ThumbnailDraft = { text: ThumbnailCopyText; styles: ThumbnailTextStyles };

export function LiveThumbnailPreview({ item, draft, active }: { item: ResultExportItem; draft: ThumbnailDraft; active: boolean }) {
  const [source, setSource] = useState<{ key: string; frameKey: string } | null>(null);
  const [image, setImage] = useState<{ url: string; key: string } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const objectUrl = useRef("");
  const saving = item.thumbnailStatus === "generating";
  const sourceContext = JSON.stringify([item.id, item.thumbnailRenderRevision, saving, retry]);
  const frameKey = source?.key === sourceContext ? source.frameKey : "";
  const requestKey = JSON.stringify({ frameKey, text: draft.text, textStyles: draft.styles });

  useEffect(() => {
    if (!active || saving) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let cancelled = false;
    const started = Date.now();
    const prepare = async (force: boolean) => {
      try {
        const state = await prepareThumbnailPreview(item.id, controller.signal, force);
        if (cancelled) return;
        if (state.state === "ready") { setSource({ key: sourceContext, frameKey: state.frameKey }); setError(""); }
        else if (state.state === "failed") setError(state.error || "プレビューを準備できませんでした。");
        else if (Date.now() - started > 120000) setError("場面の読み込みに時間がかかっています。再試行してください。");
        else timer = setTimeout(() => void prepare(false), 400);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "プレビューを準備できませんでした。");
      }
    };
    void prepare(retry > 0);
    return () => { cancelled = true; controller.abort(); clearTimeout(timer); };
  }, [active, item.id, item.thumbnailRenderRevision, saving, retry, sourceContext]);

  useEffect(() => {
    if (!active || saving || !frameKey) return;
    const controller = new AbortController();
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const blob = await renderThumbnailPreview(item.id, JSON.parse(requestKey), controller.signal);
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = url;
        setImage({ url, key: requestKey }); setError("");
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "プレビューを描画できませんでした。");
      }
    }, 180);
    return () => { cancelled = true; controller.abort(); clearTimeout(timer); };
  }, [active, frameKey, item.id, requestKey, saving, retry]);

  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); }, []);

  const current = image?.key === requestKey && !saving;
  const src = image?.url || (item.thumbnailUrl ? toBrowserApiUrl(item.thumbnailUrl) : "");
  return <section className="flex max-h-full w-full min-w-0 flex-col overflow-hidden rounded border border-neutral-300 bg-neutral-50">
    {src ? <Image src={src} alt="編集中のサムネイルプレビュー" width={1280} height={720} unoptimized
      className="aspect-video h-auto min-h-0 w-full flex-1 bg-neutral-950 object-contain" />
      : <div className="aspect-video bg-neutral-950" />}
    <div className="shrink-0 border-t border-neutral-300 px-3 py-2 text-xs" role="status" aria-live="polite">
      <p className="font-semibold">{saving ? "サムネを保存中…" : error ? "プレビューを更新できませんでした" : !frameKey ? "場面を読み込み中…" : current ? "編集中のプレビュー" : "変更をプレビューへ反映中…"}</p>
      {error ? <><p className="mt-1 text-red-700">{error}</p><button type="button" onClick={() => setRetry(v => v + 1)}
        className="mt-2 min-h-9 border border-neutral-400 bg-white px-3">プレビューを再読み込み</button></>
        : <p className="mt-1 text-neutral-600">文言・書体・サイズ・色は自動反映。確定するときだけ保存してください。</p>}
    </div>
  </section>;
}
