"use client";

import { getSubtitleReview, retrySubtitleReviewPreview } from "../../api";
import { sourceTimeAtPlayback } from "../../subtitlePauseInsert";
import { clamp } from "../display";
import type { SubtitleReviewContext } from "./context";

export function useReviewPreviews(context: SubtitleReviewContext) {
  function seekToClipTime(nextTime: number) {
    const { videoRef, selectedClip, suggestionPlaybackEndRef, setPreviewingSuggestionId, clipDuration, setClipTime } = context;
    if (!videoRef.current || !selectedClip) {
      return;
    }
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
    const relativeTime = clamp(nextTime, 0, clipDuration);
    videoRef.current.currentTime = relativeTime;
    setClipTime(relativeTime);
  }

  function playFromClipStart() {
    const { videoRef, selectedClip, suggestionPlaybackEndRef, setPreviewingSuggestionId, setClipTime } = context;
    if (!videoRef.current || !selectedClip) {
      return;
    }
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
    videoRef.current.currentTime = 0;
    setClipTime(0);
    void videoRef.current.play();
  }

  function seekToSubtitle(start: number) {
    const { videoRef, selectedClip, hookSceneDuration, hookSuppressionEnd, clipDuration, setClipTime, setIsPlaying } = context;
    const video = videoRef.current;
    if (!video || !selectedClip) {
      return;
    }
    const absoluteTime = clamp(
      start,
      selectedClip.start,
      Math.max(selectedClip.start, selectedClip.end - 0.05)
    );
    const relativeTime = clamp(
      Math.max(
        absoluteTime - selectedClip.start + hookSceneDuration,
        hookSuppressionEnd
      ),
      0,
      clipDuration
    );
    video.pause();
    video.currentTime = relativeTime;
    setClipTime(relativeTime);
    setIsPlaying(false);
  }

  function togglePlayback() {
    const { videoRef, selectedClip, suggestionPlaybackEndRef, setPreviewingSuggestionId, clipTime, clipDuration, seekToClipTime } = context;
    const video = videoRef.current;
    if (!video || !selectedClip) {
      return;
    }
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
    if (video.paused) {
      if (clipTime >= clipDuration - 0.05) {
        seekToClipTime(0);
      }
      void video.play();
      return;
    }
    video.pause();
  }

  function skipBy(seconds: number) {
    const { seekToClipTime, clipTime } = context;
    seekToClipTime(clipTime + seconds);
  }

  function currentSourceTime(): number | null {
    const { videoRef, selectedClip, setClipTime, hookSceneDuration, hookSuppressionEnd } = context;
    const video = videoRef.current;
    if (!video || !selectedClip) return null;
    video.pause();
    const playbackTime = video.currentTime;
    setClipTime(playbackTime);
    return sourceTimeAtPlayback({
      playbackTime, clipStart: selectedClip.start, clipEnd: selectedClip.end,
      hookSceneDuration, suppressionEnd: hookSuppressionEnd,
    });
  }

  function handleVideoTimeUpdate() {
    const { videoRef, selectedClip, selectedPlayerReady, suggestionPlaybackEndRef, setPreviewingSuggestionId, setClipTime, clipDuration } = context;
    const video = videoRef.current;
    if (!video || !selectedClip || !selectedPlayerReady) {
      return;
    }
    const suggestionPlaybackEnd = suggestionPlaybackEndRef.current;
    if (
      suggestionPlaybackEnd !== null &&
      video.currentTime >= suggestionPlaybackEnd - 0.03
    ) {
      suggestionPlaybackEndRef.current = null;
      setPreviewingSuggestionId(null);
      video.pause();
      video.currentTime = suggestionPlaybackEnd;
      setClipTime(suggestionPlaybackEnd);
      return;
    }
    if (video.currentTime < -0.05) {
      video.currentTime = 0;
      setClipTime(0);
      return;
    }
    if (video.currentTime >= clipDuration) {
      video.pause();
      video.currentTime = clipDuration;
      setClipTime(clipDuration);
      return;
    }
    setClipTime(clamp(video.currentTime, 0, clipDuration));
  }

  function handleVideoSeeking() {
    const { videoRef, selectedPlayerReady, clipDuration } = context;
    const video = videoRef.current;
    if (!video || !selectedPlayerReady) {
      return;
    }
    if (video.currentTime < 0) {
      video.currentTime = 0;
    } else if (video.currentTime > clipDuration) {
      video.currentTime = clipDuration;
    }
  }

  function retryVideoLoad() {
    const { videoRef, selectedClip, setPreviewLoadFailedClipIds, setVideoLoadSeconds, setIsPlayerReady, setIsBuffering } = context;
    const video = videoRef.current;
    if (!video) {
      return;
    }
    if (selectedClip) {
      setPreviewLoadFailedClipIds((current) => {
        const next = new Set(current);
        next.delete(selectedClip.id);
        return next;
      });
    }
    setVideoLoadSeconds(0);
    setIsPlayerReady(false);
    setIsBuffering(true);
    video.load();
  }

  function handleVideoError() {
    const { selectedClip, setPreviewLoadFailedClipIds, setIsPlayerReady, setIsBuffering, suggestionPlaybackEndRef, setPreviewingSuggestionId } = context;
    if (selectedClip) {
      setPreviewLoadFailedClipIds((current) => new Set(current).add(selectedClip.id));
    }
    setIsPlayerReady(false);
    setIsBuffering(false);
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
  }

  function toggleMuted() {
    const { videoRef, setIsMuted } = context;
    const video = videoRef.current;
    if (!video) {
      return;
    }
    const nextMuted = !video.muted;
    video.muted = nextMuted;
    setIsMuted(nextMuted);
  }

  function changeVolume(nextVolume: number) {
    const { videoRef, setVolume, setIsMuted } = context;
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.volume = nextVolume;
    video.muted = nextVolume === 0;
    setVolume(nextVolume);
    setIsMuted(nextVolume === 0);
  }

  function changePlaybackRate(nextRate: number) {
    const { videoRef, setPlaybackRate } = context;
    if (videoRef.current) {
      videoRef.current.playbackRate = nextRate;
    }
    setPlaybackRate(nextRate);
  }

  async function toggleFullscreen() {
    const { playerShellRef } = context;
    if (!playerShellRef.current) {
      return;
    }
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    await playerShellRef.current.requestFullscreen();
  }

  async function retrySelectedPreview() {
    const {
      selectedClip,
      retryingPreviewClipId,
      beginReviewMutation,
      setRetryingPreviewClipId,
      setError,
      jobId,
      isCurrentReviewMutation,
      setReview,
      endReviewMutation
    } = context;
    if (
      !selectedClip ||
      selectedClip.previewState !== "failed" ||
      retryingPreviewClipId !== null
    ) {
      return;
    }
    const mutationGeneration = beginReviewMutation();
    setRetryingPreviewClipId(selectedClip.id);
    setError(null);
    try {
      const queued = await retrySubtitleReviewPreview(jobId, selectedClip.id);
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(queued);
      }
      const refreshed = await getSubtitleReview(jobId);
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(refreshed);
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "完成表示プレビューを再生成できませんでした"
      );
    } finally {
      endReviewMutation();
      setRetryingPreviewClipId(null);
    }
  }
  return { seekToClipTime, playFromClipStart, seekToSubtitle, togglePlayback, skipBy, currentSourceTime, handleVideoTimeUpdate, handleVideoSeeking, retryVideoLoad, handleVideoError, toggleMuted, changeVolume, changePlaybackRate, toggleFullscreen, retrySelectedPreview };
}
