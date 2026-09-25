"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { toBrowserApiUrl } from "../lib/api";
import { framingGeometry, type Framing, type FramingGuide } from "../lib/shortFraming";
import { prepareShortFramingGuide } from "../lib/shortFramingApi";
import { shortPreviewSourceTime } from "../lib/shortPreviewTime";

// The existing clip remains the playback/audio clock. Only its picture is replaced
// from the original video; no server-side encoding is needed for framing changes.
export function LiveShortFramingPreview({ jobId, clipId, sourceUrl, clockRef, framing, layout, start, end, hookStart, hookEnd }: {
  jobId: string; clipId: string; sourceUrl: string; clockRef: RefObject<HTMLVideoElement | null>;
  framing: Framing; layout: string; start: number; end: number; hookStart: number | null; hookEnd: number | null;
}) {
  const sourceRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [guide, setGuide] = useState<FramingGuide | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [retry, setRetry] = useState(0);
  const { framingOffsetX, framingOffsetY, framingZoom } = framing;

  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const began = Date.now();
    async function load() {
      try {
        const next = await prepareShortFramingGuide(jobId, clipId, abort.signal, false, layout);
        if (abort.signal.aborted) return;
        if (next.state === "ready") setGuide(next);
        else if (next.state === "failed" || Date.now() - began > 180000) setError("画角情報を読み込めませんでした。");
        else timer = setTimeout(() => void load(), 700);
      } catch { if (!abort.signal.aborted) setError("画角情報を読み込めませんでした。"); }
    }
    void load();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [jobId, clipId, layout, retry]);

  useEffect(() => {
    const source = sourceRef.current, canvas = canvasRef.current;
    if (!source || !canvas || !guide) return;
    let animation = 0, cancelled = false, playPending = false, reportedReady = false;
    const context = canvas.getContext("2d")!;
    const geometry = framingGeometry(guide, { framingOffsetX, framingOffsetY, framingZoom });
    function frame() {
      if (cancelled) return;
      animation = requestAnimationFrame(frame);
      const clock = clockRef.current;
      if (!clock || !source || !canvas || source.readyState < 1) return;
      const target = shortPreviewSourceTime(clock.currentTime, start, end, hookStart, hookEnd);
      const drift = Math.abs(source.currentTime - target);
      if (!source.seeking && drift > (clock.paused ? .045 : .25)) source.currentTime = target;
      source.playbackRate = clock.playbackRate;
      if (clock.paused || clock.seeking || clock.ended) source.pause();
      else if (source.paused && !playPending && !source.seeking) {
        playPending = true;
        void source.play().catch(() => {
          if (!cancelled) setError("元動画を再生できません。再読み込みしてください。");
        }).finally(() => { playPending = false; });
      }
      if (source.readyState < 2 || source.seeking || drift > .3 || clock.readyState < 2) return;
      context.setTransform(.5, 0, 0, .5, 0, 0);
      context.fillStyle = "black"; context.fillRect(0, 0, 1080, 1920);
      // Reuse the exact banner images already present in the text-free clip.
      if (guide!.contentY > 0) context.drawImage(clock, 0, 0, clock.videoWidth, clock.videoHeight * guide!.contentY / 1920,
        0, 0, 1080, guide!.contentY);
      const bottom = guide!.contentY + guide!.contentHeight;
      if (bottom < 1920) context.drawImage(clock, 0, clock.videoHeight * bottom / 1920,
        clock.videoWidth, clock.videoHeight * (1920 - bottom) / 1920, 0, bottom, 1080, 1920 - bottom);
      context.save(); context.beginPath(); context.rect(0, guide!.contentY, 1080, guide!.contentHeight); context.clip();
      context.translate(0, guide!.contentY);
      if (geometry.blur) {
        const scale = Math.max(1080 / source.videoWidth, guide!.contentHeight / source.videoHeight);
        context.filter = "blur(24px)";
        context.drawImage(source, (1080 - source.videoWidth * scale) / 2, (guide!.contentHeight - source.videoHeight * scale) / 2,
          source.videoWidth * scale, source.videoHeight * scale);
        context.filter = "none";
      }
      context.drawImage(source, geometry.x, geometry.y, geometry.width, geometry.height);
      context.restore();
      if (!reportedReady) { reportedReady = true; setReady(true); }
    }
    animation = requestAnimationFrame(frame);
    return () => { cancelled = true; cancelAnimationFrame(animation); source.pause(); };
  }, [guide, framingOffsetX, framingOffsetY, framingZoom, clockRef, start, end, hookStart, hookEnd]);

  return <div className="pointer-events-none absolute inset-0 bg-black" aria-label="変更した画角の動画プレビュー">
    <video key={`${sourceUrl}:${retry}`} ref={sourceRef} src={toBrowserApiUrl(sourceUrl)} muted playsInline preload="auto" className="hidden"
      onError={() => setError("元動画を読み込めません。画角プレビューを再読み込みしてください。")} />
    <canvas ref={canvasRef} width={540} height={960} className="h-full w-full" />
    {!ready || error ? <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 p-3 text-center text-xs text-white">
      <span>{error || "変更した画角を読み込み中…"}</span>
      {error ? <button type="button" className="pointer-events-auto mt-3 border px-3 py-2" onClick={() => {
        setGuide(null); setReady(false); setError(""); setRetry(n => n + 1);
      }}>再読み込み</button> : null}
    </div> : null}
  </div>;
}
