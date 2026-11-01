"use client";

import { useEffect, useRef } from "react";
import { toBrowserApiUrl } from "../../lib/api";
import { draftPlaybackClock } from "../../lib/subtitleReview/draftPlayback";
import { livePlaybackSource } from "../../lib/subtitleReview/livePlaybackSource";
import type { SubtitleReviewContext } from "../../lib/subtitleReview/hooks/context";

export function DraftReviewPlayer({ context }: { context: SubtitleReviewContext }) {
  const { review, selectedClip, selectedClipContentDraft, videoRef, setIsPlayerReady, setIsBuffering,
    setIsPlaying, setClipTime, handleVideoTimeUpdate, handleVideoSeeking, handleVideoError, togglePlayback, playbackRate, volume, isMuted,
    retainedLivePreviews, pendingPlayerResumeRef, playerMediaKey } = context;
  const nativeRef = useRef<HTMLVideoElement>(null);
  const playbackRef = useRef<ReturnType<typeof draftPlaybackClock> | null>(null);
  const hookStart = selectedClipContentDraft?.hookSceneStart ?? null;
  const hookEnd = selectedClipContentDraft?.hookSceneEnd ?? null;
  const start = selectedClip?.start ?? 0, end = selectedClip?.end ?? 0;
  const clipId = selectedClip?.id;
  const media = selectedClip && review ? livePlaybackSource(selectedClip, review, retainedLivePreviews[selectedClip.id]) : null;
  const mediaStart = media?.mediaStart ?? 0, mediaOffset = media?.mediaOffset ?? 0, mediaUrl = media?.url;
  useEffect(() => {
    const element = nativeRef.current;
    if (!element || !clipId) return;
    const playback = draftPlaybackClock(element, { start, end, hookStart, hookEnd, mediaStart, mediaOffset });
    playbackRef.current = playback;
    videoRef.current = playback.clock;
    element.pause(); playback.seek(0); setClipTime(0); setIsPlaying(false);
    let frame = 0;
    const tick = () => { playback.advance(); frame = requestAnimationFrame(tick); };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame); element.pause();
      if (videoRef.current === playback.clock) videoRef.current = null;
    };
    // Hook edits update the virtual clock below; they do not replace the media
    // controller or pause the video. Real media/range changes still rebuild it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clipId, start, end, mediaStart, mediaOffset, mediaUrl, videoRef, setClipTime, setIsPlaying]);
  useEffect(() => {
    const playback = playbackRef.current;
    if (!playback) return;
    playback.updateRange({ start, end, hookStart, hookEnd, mediaStart, mediaOffset });
    setClipTime(playback.clock.currentTime);
  }, [clipId, start, end, hookStart, hookEnd, mediaStart, mediaOffset, mediaUrl, setClipTime]);
  useEffect(() => {
    const element = nativeRef.current;
    if (element) { element.playbackRate = playbackRate; element.volume = volume; element.muted = isMuted; }
  }, [playbackRate, volume, isMuted]);
  if (!review || !selectedClip) return null;
  return <video ref={nativeRef} src={toBrowserApiUrl(mediaUrl ?? review.sourceVideoUrl)}
    className="h-full w-full cursor-pointer bg-black object-contain" playsInline preload="metadata"
    onClick={togglePlayback} onError={handleVideoError}
    onLoadedMetadata={() => {
      const resume = pendingPlayerResumeRef.current;
      playbackRef.current?.seek(resume?.key === playerMediaKey ? resume.time : 0);
      if (resume?.key === playerMediaKey) {
        pendingPlayerResumeRef.current = null;
        if (resume.playing) void playbackRef.current?.clock.play().catch(() => setIsPlaying(false));
      }
      setIsPlayerReady(true);
    }}
    onCanPlay={() => { setIsPlayerReady(true); setIsBuffering(false); }}
    onLoadStart={() => { setIsPlayerReady(false); setIsBuffering(true); }}
    onPause={() => setIsPlaying(false)} onPlay={() => setIsPlaying(true)} onPlaying={() => setIsBuffering(false)}
    onSeeking={handleVideoSeeking} onWaiting={() => setIsBuffering(true)}
    onSeeked={() => { setIsPlayerReady(true); setIsBuffering(false); }}
    onTimeUpdate={() => { playbackRef.current?.advance(); handleVideoTimeUpdate(); }} />;
}
