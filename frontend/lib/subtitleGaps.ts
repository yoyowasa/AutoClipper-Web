import type {
  SubtitleReviewDocument,
  SubtitleReviewGap,
  SubtitleReviewSegment
} from "./types";

export function unacknowledgedSubtitleGaps(gaps?: SubtitleReviewGap[]): SubtitleReviewGap[] {
  return (gaps ?? []).filter((gap) => !gap.acknowledged);
}

export function subtitleGapLabel(gap: SubtitleReviewGap): string {
  const time = (value: number) => {
    const seconds = Math.floor(Math.max(0, value));
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  };
  return `字幕なし（音あり）${time(gap.start)}〜${time(gap.end)}`;
}

type SubtitleTimelineItem =
  | { kind: "segment"; segment: SubtitleReviewSegment; segmentIndex: number; start: number }
  | { kind: "gap"; gap: SubtitleReviewGap; start: number };

export function subtitleTimeline(
  segments: SubtitleReviewSegment[],
  gaps: SubtitleReviewGap[] | undefined,
  clipStart: number,
  hookSceneDuration: number
): SubtitleTimelineItem[] {
  const items: SubtitleTimelineItem[] = segments.map((segment, segmentIndex) => ({
    kind: "segment", segment, segmentIndex,
    start: segment.start - clipStart + hookSceneDuration
  }));
  for (const gap of unacknowledgedSubtitleGaps(gaps)) {
    items.push({ kind: "gap", gap, start: gap.start });
  }
  return items.sort((left, right) => left.start - right.start);
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

// Acknowledging a gap must not replace unsaved subtitle/content drafts or preview state.
export function mergeSubtitleGapAcknowledgement(
  current: SubtitleReviewDocument,
  updated: SubtitleReviewDocument,
  clipId: string
): SubtitleReviewDocument {
  if (current.jobId !== updated.jobId) return current;
  const clip = updated.clips.find((item) => item.id === clipId);
  if (!clip) return current;
  return {
    ...current,
    updatedAt: updated.updatedAt,
    clips: current.clips.map((item) => item.id === clipId ? { ...item, gaps: clip.gaps ?? [] } : item)
  };
}
