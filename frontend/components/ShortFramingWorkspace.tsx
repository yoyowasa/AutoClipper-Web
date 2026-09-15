"use client";

import { useEffect, useRef, useState } from "react";
import { toBrowserApiUrl } from "../lib/api";
import { prepareShortFramingGuide } from "../lib/shortFramingApi";
import { framingAtPoint, framingGeometry, type Framing, type FramingGuide } from "../lib/shortFraming";
import type { SubtitleReviewDocument } from "../lib/types";
import { drawShortBannerGuide, drawSourceBannerGuide, SHORT_BANNER_GUIDE } from "../lib/shortFramingBannerGuide";

type Layout = SubtitleReviewDocument["shortLayout"];
const layouts: { value: Layout; label: string }[] = [
  { value: "auto", label: "自動（人物を優先）" },
  { value: "face_tracking_crop", label: "人物アップ（顔を追従）" },
  { value: "center_crop", label: "中央を拡大" },
  { value: "blur_background", label: "全体表示（ぼかし背景）" },
];
type FrameSnapshot = { image: HTMLCanvasElement; position: number };

type Props = {
  jobId: string; clipId: string; sourceUrl: string; start: number; end: number;
  layout: Layout;
  value: Framing; editable: boolean; onSave: (value: Framing) => Promise<boolean>;
};

export function ShortFramingWorkspace(props: Props) {
  const [open, setOpen] = useState(false);
  const [initialLayout, setInitialLayout] = useState(props.layout);
  const [snapshot, setSnapshot] = useState<FrameSnapshot | null>(null);
  return <>
    <label className="flex flex-col gap-1 text-sm font-semibold">基本配置
      <select aria-label="ショート画角" className="min-h-10 border bg-white px-3" value={props.layout}
        onChange={event => { setInitialLayout(event.target.value as Layout); setOpen(true); }}>
        {layouts.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select>
    </label>
    <button type="button" onClick={() => { setInitialLayout(props.layout); setOpen(true); }}
      className="min-h-11 w-full border border-sky-700 bg-sky-50 px-3 text-sm font-semibold text-sky-900">
      画角を見ながら調整
    </button>
    {open ? <FramingDialog {...props} initialLayout={initialLayout} initialFrame={snapshot}
      onFrame={setSnapshot} onClose={() => setOpen(false)} /> : null}
  </>;
}

function FramingDialog({ jobId, clipId, sourceUrl, start, end, value, layout, editable, onSave, onClose, initialLayout, initialFrame, onFrame }: Props & {
  onClose: () => void; initialLayout: Layout; initialFrame: FrameSnapshot | null; onFrame: (frame: FrameSnapshot) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const overview = useRef<HTMLCanvasElement>(null);
  const output = useRef<HTMLCanvasElement>(null);
  const [draft, setDraft] = useState(value);
  const [draftLayout, setDraftLayout] = useState(initialLayout);
  const guides = useRef(new Map<Layout, FramingGuide>());
  const [guide, setGuide] = useState<FramingGuide | null>(null);
  const [frame, setFrame] = useState<HTMLCanvasElement | null>(initialFrame?.image ?? null);
  const [error, setError] = useState("");
  const [sourceError, setSourceError] = useState("");
  const [retry, setRetry] = useState(0);
  const [saving, setSaving] = useState(false);
  const [initialPosition] = useState(initialFrame?.position ?? start);
  const [position, setPosition] = useState(initialPosition);
  const [seeking, setSeeking] = useState(!initialFrame);

  useEffect(() => {
    const element = dialog.current!;
    const bodyOverflow = document.body.style.overflow, rootOverflow = document.documentElement.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = bodyOverflow;
      document.documentElement.style.overflow = rootOverflow;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false, timer: ReturnType<typeof setTimeout>;
    const began = Date.now();
    setGuide(guides.current.get(draftLayout) ?? null);
    setError("");
    if (guides.current.has(draftLayout) && retry === 0) return;
    async function prepare(force = false) {
      try {
        const result = await prepareShortFramingGuide(jobId, clipId, controller.signal, force, draftLayout);
        if (cancelled) return;
        if (result.state === "ready") { guides.current.set(draftLayout, result); setGuide(result); setError(""); }
        else if (result.state === "failed") setError(result.error || "画角を読み込めませんでした。");
        else if (Date.now() - began > 180000) setError("画角の読み込みに時間がかかっています。再試行してください。");
        else timer = setTimeout(() => void prepare(), 700);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "画角を読み込めませんでした。");
      }
    }
    void prepare(retry > 0);
    return () => { cancelled = true; controller.abort(); clearTimeout(timer); };
  }, [jobId, clipId, retry, draftLayout]);

  function captureFrame() {
    const source = video.current;
    if (!source || source.readyState < 2 || source.seeking) return;
    const snapshot = document.createElement("canvas");
    snapshot.width = Math.min(1280, source.videoWidth);
    snapshot.height = Math.round(snapshot.width * source.videoHeight / source.videoWidth);
    snapshot.getContext("2d")!.drawImage(source, 0, 0, snapshot.width, snapshot.height);
    setFrame(snapshot); setSeeking(false); setSourceError("");
    onFrame({ image: snapshot, position: source.currentTime });
  }

  useEffect(() => {
    if (!frame || !overview.current) return;
    const canvas = overview.current;
    canvas.width = frame.width; canvas.height = frame.height;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(frame, 0, 0);
    if (!guide || !output.current) return;
    const geometry = framingGeometry(guide, draft);
    const rect = geometry.source;
    const x = rect.x * canvas.width, y = rect.y * canvas.height;
    const w = rect.width * canvas.width, h = rect.height * canvas.height;
    ctx.fillStyle = "rgba(0,0,0,.58)";
    ctx.beginPath(); ctx.rect(0, 0, canvas.width, canvas.height); ctx.rect(x, y, w, h); ctx.fill("evenodd");
    ctx.strokeStyle = "#38bdf8"; ctx.lineWidth = 4; ctx.strokeRect(x + 2, y + 2, w - 4, h - 4);
    ctx.lineWidth = 1; ctx.setLineDash([8, 6]);
    for (const part of [1 / 3, 2 / 3]) {
      ctx.beginPath(); ctx.moveTo(x + w * part, y); ctx.lineTo(x + w * part, y + h); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x, y + h * part); ctx.lineTo(x + w, y + h * part); ctx.stroke();
    }
    drawSourceBannerGuide(ctx, guide, geometry, canvas.width, canvas.height);
    const dest = output.current;
    dest.width = 540; dest.height = 960;
    const draw = dest.getContext("2d")!;
    draw.scale(.5, .5);
    draw.fillStyle = "#17232b"; draw.fillRect(0, 0, 1080, 1920);
    draw.fillStyle = "#a5b5bf"; draw.font = "36px sans-serif"; draw.textAlign = "center";
    if (guide.contentY) draw.fillText("上帯", 540, guide.contentY / 2);
    const bottom = guide.contentY + guide.contentHeight;
    if (bottom < 1920) draw.fillText("下帯", 540, (bottom + 1920) / 2);
    draw.save(); draw.beginPath(); draw.rect(0, guide.contentY, 1080, guide.contentHeight); draw.clip();
    draw.translate(0, guide.contentY);
    if (geometry.blur) {
      const scale = Math.max(1080 / frame.width, guide.contentHeight / frame.height);
      draw.filter = "blur(24px)";
      draw.drawImage(frame, (1080 - frame.width * scale) / 2, (guide.contentHeight - frame.height * scale) / 2,
        frame.width * scale, frame.height * scale);
      draw.filter = "none";
    }
    draw.drawImage(frame, geometry.x, geometry.y, geometry.width, geometry.height);
    draw.restore();
    drawShortBannerGuide(draw);
  }, [frame, guide, draft]);

  function pointAt(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!guide || saving) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    setDraft(current => framingAtPoint(guide, current, (event.clientX - bounds.left) / bounds.width, (event.clientY - bounds.top) / bounds.height));
  }
  const ready = Boolean(frame && guide);
  const changed = JSON.stringify(draft) !== JSON.stringify(value) || draftLayout !== layout;
  return <dialog ref={dialog} aria-label="ショートの画角調整" onCancel={event => { event.preventDefault(); if (!saving) onClose(); }}
    className="fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none overflow-hidden bg-neutral-50 p-3 text-neutral-950 backdrop:bg-black/50">
    <div className="flex h-full min-h-0 flex-col gap-3">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b pb-2">
        <div><h2 className="text-base font-semibold">ショートの画角調整</h2>
          <p className="text-xs text-neutral-600">青い枠が表示範囲、黄色の破線が上下帯の境界。元映像をクリック・ドラッグすると位置が変わります。</p></div>
        <button type="button" autoFocus disabled={saving} onClick={onClose} className="min-h-10 border bg-white px-4">閉じる</button>
      </header>
      <label className="flex shrink-0 flex-wrap items-center gap-3 text-sm font-semibold">基本配置
        <select aria-label="試す基本配置" className="min-h-10 border bg-white px-3" disabled={saving} value={draftLayout}
          onChange={event => { setRetry(0); setDraftLayout(event.target.value as Layout); }}>
          {layouts.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
        <span className="text-xs font-normal text-neutral-600">保存するまで試し表示。基本配置は全ショート共通、位置・倍率はこのショートのみ。</span>
      </label>
      <div role="status" className="shrink-0 text-sm">
        {sourceError || error ? <span className="text-red-700">{sourceError || error} <button type="button" className="underline"
          onClick={() => { setError(""); setSourceError(""); setRetry(n => n + 1); video.current?.load(); }}>再読み込み</button></span>
          : !guide ? "この配置の基準を読み込み中…" : !frame ? "元映像を読み込み中…" : seeking ? "別の場面を読み込み中…" : "構図は即時反映・静止画で確認"}
      </div>
      <video ref={video} src={`${toBrowserApiUrl(sourceUrl)}#t=${initialPosition}`} muted playsInline preload="metadata" className="hidden"
        onLoadedMetadata={event => { event.currentTarget.currentTime = position; }} onLoadedData={captureFrame} onSeeked={captureFrame}
        onError={() => setSourceError("元映像を読み込めませんでした。")}/>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1.8fr)_minmax(0,1fr)] gap-3">
        <section className="flex min-h-0 min-w-0 flex-col gap-2">
          <h3 className="shrink-0 text-sm font-semibold">元映像・切り抜く範囲</h3>
          <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-neutral-950">
            <canvas ref={overview} aria-label="元映像の切り抜き範囲" className="max-h-full max-w-full touch-none cursor-crosshair"
              onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); pointAt(event); }}
              onPointerMove={event => { if (event.buttons === 1) pointAt(event); }} />
          </div>
          <label className="flex shrink-0 items-center gap-2 text-xs">確認する場面
            <input aria-label="画角確認の場面" className="min-w-0 flex-1" type="range" min={start} max={Math.max(start, end - .1)} step={.1} value={position}
              onChange={event => { const next = Number(event.target.value); setPosition(next); setSeeking(true); if (video.current) video.current.currentTime = next; }}/>
            <span>{(position - start).toFixed(1)}秒</span>
          </label>
        </section>
        <section className="flex min-h-0 min-w-0 flex-col gap-2">
          <h3 className="shrink-0 text-sm font-semibold">構図・上下帯の目安</h3>
          <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-neutral-200">
            <canvas ref={output} aria-label="ショート画角の即時プレビュー" className="max-h-full max-w-full" />
          </div>
          <div className="shrink-0 text-xs text-neutral-600">
            <p className="font-semibold text-amber-800">上下各{SHORT_BANNER_GUIDE.top}px／中央の映像枠 {SHORT_BANNER_GUIDE.width}×{SHORT_BANNER_GUIDE.bottom - SHORT_BANNER_GUIDE.top}px</p>
            <p>線と色は目安のみ。{guide ? `書き出し設定：上帯${guide.contentY > 0 ? "ON" : "OFF"}・下帯${guide.contentY + guide.contentHeight < SHORT_BANNER_GUIDE.height ? "ON" : "OFF"}` : "書き出し設定を確認中"}</p>
          </div>
        </section>
      </div>
      <div className="grid shrink-0 grid-cols-3 gap-3">
        {([{ key: "framingOffsetX", label: "左右", min: -100, max: 100, step: 1, left: "左側", right: "右側" },
          { key: "framingOffsetY", label: "上下", min: -100, max: 100, step: 1, left: "上側", right: "下側" },
          { key: "framingZoom", label: "拡大", min: 1, max: 3, step: .05, left: "標準", right: "３倍" }] as const).map(control => <label key={control.key} className="border bg-white p-3 text-sm">
          <span className="flex justify-between font-semibold"><span>{control.label}</span><span>{control.key === "framingZoom" ? `${Math.round(draft[control.key] * 100)}%` : draft[control.key]}</span></span>
          <input aria-label={`画角調整の${control.label}`} className="my-2 block w-full accent-sky-600" type="range"
            min={control.min} max={control.max} step={control.step} disabled={!ready || saving} value={draft[control.key]}
            onChange={event => setDraft(current => ({ ...current, [control.key]: Number(event.target.value) }))}/>
          <span className="flex justify-between text-xs text-neutral-500"><span>{control.left}</span><span>{control.right}</span></span>
        </label>)}
      </div>
      <footer className="flex shrink-0 flex-wrap items-center gap-3 border-t pt-2">
        <button type="button" disabled={!ready || saving} className="min-h-10 border bg-white px-3" onClick={() => setDraft({ framingOffsetX: 0, framingOffsetY: 0, framingZoom: 1 })}>自動値へ戻す</button>
        <p className="min-w-0 flex-1 text-xs text-neutral-600">{editable ? "保存すると基本配置・位置・倍率をこのショートだけに適用して再生成します。" : "完了済みのため試し表示のみ。保存は再編集時に使えます。"}</p>
        <button type="button" disabled={!editable || !ready || !changed || saving} className="min-h-11 bg-sky-700 px-5 font-semibold text-white disabled:bg-neutral-300"
          onClick={async () => { setSaving(true); try { if (await onSave({ ...draft, shortLayout: draftLayout })) onClose(); else setError("画角を保存できませんでした。再度保存してください。"); } finally { setSaving(false); } }}>
          {saving ? "保存中…" : "この画角を保存"}
        </button>
      </footer>
    </div>
  </dialog>;
}
