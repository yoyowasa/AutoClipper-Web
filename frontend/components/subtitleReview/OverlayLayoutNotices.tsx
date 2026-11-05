"use client";

import { useEffect, useState } from "react";
import { clipLabel, formatTime } from "../../lib/subtitleReview/display";
import type { OverlayLayoutNotice, SubtitleReviewClip } from "../../lib/types";
import type { SubtitleReviewContext } from "../../lib/subtitleReview/hooks/context";

export function OverlayLayoutNotices({ context, onOpen }: { context: SubtitleReviewContext; onOpen: () => void }) {
  const [pending, setPending] = useState<{ clip: SubtitleReviewClip; notice: OverlayLayoutNotice } | null>(null);
  useEffect(() => {
    if (!pending || context.selectedClip?.id !== pending.clip.id) return;
    const { clip, notice } = pending;
    const hook = clip.hookSceneStart != null && clip.hookSceneEnd != null ? clip.hookSceneEnd - clip.hookSceneStart : 0;
    const sourceTime = clip.start + notice.start - hook;
    const segment = context.review?.segments.find(s => clip.segmentIds.includes(s.id) && s.end > sourceTime && s.start <= sourceTime + .05);
    context.setWorkspaceTab("style");
    context.setSelectedTextStyleTarget(notice.role.startsWith("subtitle:") ? "subtitle" : notice.role === "title" ? "title" : "hook");
    context.setStyledSegmentId(notice.role.startsWith("subtitle:") ? segment?.id ?? null : null);
    const video = context.videoRef.current;
    const seek = () => {
      context.seekToClipTime(notice.start);
      video?.pause();
      context.setIsPlaying(false);
      requestAnimationFrame(() => setPending(null));
    };
    if (video && video.readyState < 1) {
      video.addEventListener("loadedmetadata", seek, { once: true });
      return () => video.removeEventListener("loadedmetadata", seek);
    }
    seek();
  }, [pending, context]);
  const review = context.review;
  if (!review) return null;
  const rows = review.clips.flatMap(clip => (clip.overlayLayoutNotices ?? []).map(notice => ({ clip, notice })));
  if (!rows.length) return null;
  const button = ({ clip, notice }: typeof rows[number], index: number) => <button type="button" key={`${clip.id}:${index}`}
      className={`block w-full py-1 text-left underline ${notice.failed ? "text-red-800" : "text-sky-800"}`}
      onClick={() => { onOpen(); context.selectClip(clip); setPending({ clip, notice }); }}>
      {clipLabel(clip, review.clips)}・{formatTime(notice.start)}〜{formatTime(notice.end)}「{notice.text}」：
      {notice.failed ? `${notice.boundary}へ${notice.overflowPx.toFixed(1)}pxはみ出し（自動修復できませんでした）` : <>
        {notice.fontSizeAfter < notice.fontSizeBefore ? `文字を${notice.fontSizeAfter}pxに縮小` : ""}
        {notice.shiftPx ? `${notice.fontSizeAfter < notice.fontSizeBefore ? "・" : ""}${notice.shiftPx < 0 ? "上" : "下"}へ${Math.abs(notice.shiftPx).toFixed(1)}px移動` : ""}
      </>}
    </button>;
  return <section aria-label="文字の自動調整と検査結果" className="border border-neutral-300 bg-white p-3 text-sm">
    {rows.filter(row => row.notice.failed).map(button)}
    {rows.some(row => !row.notice.failed) && <details><summary className="cursor-pointer">
      文字を自動調整しました（{rows.filter(row => !row.notice.failed).length}件）
    </summary>{rows.filter(row => !row.notice.failed).map(button)}</details>}
  </section>;
}
