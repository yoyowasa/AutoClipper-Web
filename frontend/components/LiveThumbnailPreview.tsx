"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { prepareThumbnailPreview, renderThumbnailPreview, toBrowserApiUrl } from "../lib/api";
import type { NormalThumbnailStyle, ResultExportItem, ThumbnailCopyText, ThumbnailSubjectPlacement, ThumbnailTextRegions, ThumbnailTextStyles } from "../lib/types";

export type ThumbnailDraft = { text: ThumbnailCopyText; styles: ThumbnailTextStyles; design: NormalThumbnailStyle["design"]; subjectPlacement: ThumbnailSubjectPlacement; subjectSource?: "video" | "asset"; characterAssetId?: string; frameCandidateId?: string; cropMode?: "standard" | "close" };

type TextRole = keyof ThumbnailTextStyles;
type Drag = { role: TextRole; pointerId: number; startX: number; startY: number; offsetX: number; offsetY: number; dx: number; dy: number };

function TextDragHandle({ role, region, style, onMoveText }: {
  role: TextRole; region: NonNullable<ThumbnailTextRegions[TextRole]>;
  style: ThumbnailTextStyles[TextRole]; onMoveText: (role: TextRole, dx: number, dy: number) => void;
}) {
  const dragRef = useRef<Drag | null>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const start = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault(); event.currentTarget.setPointerCapture(event.pointerId);
    const next = { role, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY,
      offsetX: style.offsetX ?? 0, offsetY: style.offsetY ?? 0, dx: 0, dy: 0 };
    dragRef.current = next; setDrag(next);
  };
  const move = (event: React.PointerEvent<HTMLButtonElement>) => {
    const current = dragRef.current;
    const rect = event.currentTarget.parentElement?.getBoundingClientRect();
    if (!current || current.pointerId !== event.pointerId || !rect) return;
    const dx = Math.max(-300 - current.offsetX, Math.min(300 - current.offsetX,
      Math.round((event.clientX - current.startX) * 1280 / rect.width)));
    const dy = Math.max(-250 - current.offsetY, Math.min(250 - current.offsetY,
      Math.round((event.clientY - current.startY) * 720 / rect.height)));
    dragRef.current = { ...current, dx, dy };
    setDrag(dragRef.current);
  };
  const end = (event: React.PointerEvent<HTMLButtonElement>, commit: boolean) => {
    const current = dragRef.current;
    if (!current || current.pointerId !== event.pointerId) return;
    dragRef.current = null; setDrag(null);
    if (commit && (current.dx || current.dy)) onMoveText(role, current.dx, current.dy);
  };
  return <button type="button" aria-label={`サムネ ${role === "heading" ? "見出し" : role === "upper" ? "上行" : "下行"}をドラッグして移動`}
    title="ドラッグして文字を移動" className="absolute z-10 cursor-grab touch-none border-2 border-transparent bg-transparent hover:border-sky-400 hover:bg-sky-400/10 focus-visible:border-sky-400 active:cursor-grabbing"
    style={{ left: `${(region.x - 8 + (drag?.dx ?? 0)) / 1280 * 100}%`,
      top: `${(region.y - 8 + (drag?.dy ?? 0)) / 720 * 100}%`,
      width: `${(region.width + 16) / 1280 * 100}%`, height: `${(region.height + 16) / 720 * 100}%`,
      borderColor: drag ? "#38bdf8" : undefined }}
    onPointerDown={start} onPointerMove={move} onPointerUp={event => end(event, true)} onPointerCancel={event => end(event, false)}>
    {drag && <span className="absolute bottom-full left-0 whitespace-nowrap bg-sky-700 px-1 text-[10px] text-white">{role === "heading" ? "見出し" : role === "upper" ? "上行" : "下行"}を移動中</span>}
  </button>;
}

export function LiveThumbnailPreview({ item, draft, active, onRegionsChange, onMoveText }: {
  item: ResultExportItem; draft: ThumbnailDraft; active: boolean;
  onRegionsChange: (regions: ThumbnailTextRegions | null) => void;
  onMoveText: (role: TextRole, dx: number, dy: number) => void;
}) {
  const [source, setSource] = useState<{ key: string; frameKey: string } | null>(null);
  const [image, setImage] = useState<{ url: string; key: string; regions: ThumbnailTextRegions; warnings: string[] } | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const objectUrl = useRef("");
  const saving = item.thumbnailStatus === "generating";
  const subjectSource = draft.subjectSource ?? "video";
  const characterAssetId = draft.characterAssetId;
  const frameCandidateId = draft.frameCandidateId;
  const cropMode = draft.cropMode ?? "standard";
  const sourceContext = JSON.stringify([item.id, item.thumbnailRenderRevision, saving, retry, subjectSource, characterAssetId, frameCandidateId]);
  const frameKey = source?.key === sourceContext ? source.frameKey : "";
  const requestKey = JSON.stringify({ frameKey, text: draft.text, textStyles: draft.styles, design: draft.design, subjectPlacement: draft.subjectPlacement, subjectSource, characterAssetId, frameCandidateId, cropMode });

  useEffect(() => { onRegionsChange(null); }, [requestKey, onRegionsChange]);

  useEffect(() => {
    if (!active || saving) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let cancelled = false;
    const started = Date.now();
    const prepare = async (force: boolean) => {
      try {
        const state = await prepareThumbnailPreview(item.id, controller.signal, force, { subjectSource, characterAssetId, frameCandidateId });
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
  }, [active, item.id, item.thumbnailRenderRevision, saving, retry, sourceContext, subjectSource, characterAssetId, frameCandidateId]);

  useEffect(() => {
    if (!active || saving || !frameKey) return;
    const controller = new AbortController();
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const { blob, regions, warnings } = await renderThumbnailPreview(item.id, JSON.parse(requestKey), controller.signal);
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = url;
        setImage({ url, key: requestKey, regions, warnings }); onRegionsChange(regions); setError("");
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "プレビューを描画できませんでした。");
      }
    }, 180);
    return () => { cancelled = true; controller.abort(); clearTimeout(timer); };
  }, [active, frameKey, item.id, requestKey, saving, retry, onRegionsChange]);

  useEffect(() => () => { if (objectUrl.current) URL.revokeObjectURL(objectUrl.current); }, []);

  const current = image?.key === requestKey && !saving;
  const src = image?.url || (item.thumbnailUrl ? toBrowserApiUrl(item.thumbnailUrl) : "");
  return <section className="flex max-h-full w-full min-w-0 flex-col overflow-hidden rounded border border-neutral-300 bg-neutral-50">
    {src ? <div className="relative aspect-video min-h-0 w-full bg-neutral-950">
      <Image src={src} alt="編集中のサムネイルプレビュー" width={1280} height={720} unoptimized
        className="h-full w-full object-contain" />
      {current && Object.entries(image?.regions ?? {}).map(([name, region]) => {
        const role = name as TextRole;
        if (!region) return null;
        return <TextDragHandle key={role} role={role} region={region} style={draft.styles[role]} onMoveText={onMoveText} />;
      })}
    </div>
      : <div className="aspect-video bg-neutral-950" />}
    <div className="shrink-0 border-t border-neutral-300 px-3 py-2 text-xs" role="status" aria-live="polite">
      <p className="font-semibold">{saving ? "サムネを保存中…" : error ? "プレビューを更新できませんでした" : !frameKey ? "場面を読み込み中…" : current ? "編集中のプレビュー" : "変更をプレビューへ反映中…"}</p>
      {current && image?.warnings.map(warning => <p key={warning} className="mt-1 text-amber-800">{warning}</p>)}
      {error ? <><p className="mt-1 text-red-700">{error}</p><button type="button" onClick={() => setRetry(v => v + 1)}
        className="mt-2 min-h-9 border border-neutral-400 bg-white px-3">プレビューを再読み込み</button></>
        : <p className="mt-1 text-neutral-600">文言・書体・人物の大きさと位置は自動反映。確定するときだけ保存してください。</p>}
    </div>
  </section>;
}
