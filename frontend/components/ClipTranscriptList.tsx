"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";

import type { ClipPlanTranscriptSegment } from "../lib/types";

type ScrollPosition = {
  top: number;
  atBottom: boolean;
  anchor: string | null;
  offset: number;
};

export function ClipTranscriptPanel({ children }: { children: ReactNode }) {
  const panelRef = useRef<HTMLElement>(null);

  useLayoutEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const resize = () => {
      const top = Math.max(0, panel.getBoundingClientRect().top);
      const height = `${Math.max(180, window.innerHeight - top - 12)}px`;
      if (panel.style.getPropertyValue("--transcript-panel-height") !== height) {
        panel.style.setProperty("--transcript-panel-height", height);
      }
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(document.documentElement);
    window.addEventListener("resize", resize);
    window.addEventListener("scroll", resize, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", resize);
      window.removeEventListener("scroll", resize);
    };
  }, []);

  return (
    <aside
      className="border-b border-neutral-300 bg-white px-5 py-5 lg:sticky lg:top-0 lg:col-start-3 lg:row-span-2 lg:row-start-1 lg:flex lg:h-[var(--transcript-panel-height,calc(100dvh-290px))] lg:min-h-0 lg:flex-col lg:border-b-0"
      ref={panelRef}
    >
      {children}
    </aside>
  );
}

export function ClipTranscriptList({
  segments,
  formatTime
}: {
  segments: ClipPlanTranscriptSegment[];
  formatTime: (value: number) => string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const positionRef = useRef<ScrollPosition | null>(null);

  function rememberPosition() {
    const list = listRef.current;
    if (!list) return;
    const viewportTop = list.getBoundingClientRect().top + list.clientTop;
    const rows = Array.from(list.querySelectorAll<HTMLElement>("[data-transcript-time]"));
    const anchor = rows.find((row) => row.getBoundingClientRect().bottom > viewportTop);
    positionRef.current = {
      top: list.scrollTop,
      atBottom: list.scrollHeight > list.clientHeight &&
        list.scrollHeight - list.clientHeight - list.scrollTop <= 24,
      anchor: anchor?.dataset.transcriptTime ?? null,
      offset: anchor ? anchor.getBoundingClientRect().top - viewportTop : 0
    };
  }

  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const position = positionRef.current;
    if (position?.atBottom) {
      list.scrollTop = list.scrollHeight;
    } else if (position) {
      const anchor = Array.from(list.querySelectorAll<HTMLElement>("[data-transcript-time]"))
        .find((row) => row.dataset.transcriptTime === position.anchor);
      list.scrollTop = anchor
        ? list.scrollTop + anchor.getBoundingClientRect().top -
          list.getBoundingClientRect().top - list.clientTop - position.offset
        : position.top;
    }
    rememberPosition();
  }, [segments]);

  return (
    <>
      <div className="mt-2 flex shrink-0 gap-2">
        {(["先頭へ", "末尾へ"] as const).map((label, index) => (
          <button
            className="min-h-8 border border-neutral-300 bg-white px-3 text-xs hover:bg-neutral-100"
            key={label}
            type="button"
            onClick={() => {
              const list = listRef.current;
              if (list) list.scrollTop = index === 0 ? 0 : list.scrollHeight;
              rememberPosition();
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        aria-label="選択範囲の文字起こし"
        className="mt-2 max-h-80 overflow-y-auto overscroll-y-contain border border-neutral-200 bg-neutral-50 [overflow-anchor:none] [scrollbar-gutter:stable] lg:min-h-0 lg:max-h-none lg:flex-1"
        ref={listRef}
        role="region"
        tabIndex={0}
        onScroll={rememberPosition}
      >
        {segments.map((segment, index) => (
          <div
            className="border-b border-neutral-200 px-3 py-2 last:border-b-0"
            data-transcript-time={`${segment.start}-${segment.end}`}
            key={`${segment.start}-${segment.end}-${index}`}
          >
            <span className="text-xs tabular-nums text-neutral-500">
              {formatTime(segment.start)} - {formatTime(segment.end)}
            </span>
            <p className="mt-1 break-words text-sm leading-6 text-neutral-900">
              {segment.text}
            </p>
          </div>
        ))}
        {segments.length === 0 ? (
          <p className="px-3 py-2 text-sm text-neutral-600">
            この範囲に発話の文字起こしはありません
          </p>
        ) : null}
      </div>
    </>
  );
}
