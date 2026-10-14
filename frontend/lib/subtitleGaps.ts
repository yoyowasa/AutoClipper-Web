import type { SubtitleReviewGap } from "./types";

export function subtitleGapLabel(gap: SubtitleReviewGap): string {
  const time = (value: number) => {
    const seconds = Math.floor(Math.max(0, value));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  };
  return `字幕なし（音あり）${time(gap.start)}〜${time(gap.end)}`;
}

export function seekAndPauseAtSubtitleGap(
  player: Pick<HTMLVideoElement, "pause" | "currentTime">,
  gap: SubtitleReviewGap,
  clipDuration: number
): number {
  const time = Math.max(0, Math.min(gap.start, clipDuration));
  player.pause();
  player.currentTime = time;
  return time;
}
