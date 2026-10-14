"use client";

import { useEffect, useLayoutEffect } from "react";
import type { SubtitleReviewContext } from "./context";

export function usePreviewResumeLayout(context: Pick<SubtitleReviewContext, "currentPlayerMediaRef" | "selectedClipId" | "playerMediaKey" | "pendingPlayerResumeRef" | "clipTime" | "isPlaying">) {
  const { currentPlayerMediaRef, selectedClipId, playerMediaKey, pendingPlayerResumeRef, clipTime, isPlaying } = context;
  useLayoutEffect(() => {
    const previous = currentPlayerMediaRef.current;
    if (previous?.clipId === selectedClipId && previous.key !== playerMediaKey && playerMediaKey) {
      pendingPlayerResumeRef.current = { key: playerMediaKey, time: clipTime, playing: isPlaying };
    } else if (previous?.clipId !== selectedClipId) {
      pendingPlayerResumeRef.current = null;
    }
    currentPlayerMediaRef.current = playerMediaKey ? { clipId: selectedClipId, key: playerMediaKey } : null;
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clipTime, isPlaying, playerMediaKey, selectedClipId]);
}

export function usePlayerLoadTimer(context: Pick<SubtitleReviewContext, "isPlayerReady" | "selectedClip" | "selectedPlayerReady" | "setVideoLoadSeconds">) {
  const { isPlayerReady, selectedClip, selectedPlayerReady, setVideoLoadSeconds } = context;
  useEffect(() => {
    if (isPlayerReady || !selectedClip || !selectedPlayerReady) {
      return;
    }
    const intervalId = window.setInterval(() => {
      setVideoLoadSeconds((current) => current + 1);
    }, 1000);
    return () => window.clearInterval(intervalId);
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlayerReady, selectedClip, selectedPlayerReady]);
}

export function usePlaybackRateSync(context: Pick<SubtitleReviewContext, "videoRef" | "playbackRate">) {
  const { videoRef, playbackRate } = context;
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.playbackRate = playbackRate;
    }
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playbackRate]);
}

export function useVolumeSync(context: Pick<SubtitleReviewContext, "videoRef" | "volume" | "isMuted">) {
  const { videoRef, volume, isMuted } = context;
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.volume = volume;
      videoRef.current.muted = isMuted;
    }
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMuted, volume]);
}

export function useActiveSubtitleScroll(context: Pick<SubtitleReviewContext, "activeSegmentId" | "isPlaying" | "subtitleListRef" | "segmentRowRefs">) {
  const { activeSegmentId, isPlaying, subtitleListRef, segmentRowRefs } = context;
  useEffect(() => {
    if (!activeSegmentId || !isPlaying) {
      return;
    }
    const container = subtitleListRef.current;
    const row = segmentRowRefs.current[activeSegmentId];
    if (!container || !row) {
      return;
    }
    const containerRect = container.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const visibleTop = containerRect.top + 12;
    const visibleBottom = containerRect.bottom - 12;
    if (rowRect.top >= visibleTop && rowRect.bottom <= visibleBottom) {
      return;
    }
    container.scrollBy({
      top: rowRect.top - containerRect.top - container.clientHeight * 0.28,
      behavior: "smooth"
    });
    // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSegmentId, isPlaying]);
}

export function useClipSelectionScroll(context: Pick<SubtitleReviewContext, "subtitleListRef" | "selectedClipId">) {
  const { subtitleListRef, selectedClipId } = context;
      // Preserve original dependencies: these setters/refs are stable useSubtitleReviewState outputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
useEffect(() => { subtitleListRef.current?.scrollTo({ top: 0 }); }, [selectedClipId]);
}
