export function sourceTimeAtPlayback(options: {
  playbackTime: number;
  clipStart: number;
  clipEnd: number;
  hookSceneDuration: number;
  suppressionEnd: number;
}): number | null {
  const { playbackTime, clipStart, clipEnd, hookSceneDuration, suppressionEnd } = options;
  const duration = hookSceneDuration + clipEnd - clipStart;
  if (!Number.isFinite(playbackTime) || playbackTime < suppressionEnd || playbackTime >= duration - 0.1) {
    return null;
  }
  return Math.floor((clipStart + playbackTime - hookSceneDuration) * 100 + 0.000001) / 100;
}

type TimedSubtitle = { id?: string; start: number; end: number; text: string };

export function nextNonemptySubtitleStart(
  segments: readonly TimedSubtitle[], start: number, clipEnd: number
): number {
  return segments.reduce((next, segment) =>
    segment.text.trim() && segment.start > start + 0.01 ? Math.min(next, segment.start) : next,
  clipEnd);
}

export function subtitleInsertionConflict(
  segments: readonly TimedSubtitle[],
  start: number,
  end: number,
  dirtySegmentIds?: ReadonlySet<string>
): "unsaved" | "overlap" | null {
  const overlapping = segments.filter((segment) => segment.start < end - 0.001 && segment.end > start + 0.001);
  // Splitting a saved empty row can replace its ID; never discard an unsaved edit to it.
  if (overlapping.some((segment) => segment.id && dirtySegmentIds?.has(segment.id))) return "unsaved";
  return overlapping.some((segment) => segment.text.trim()) ? "overlap" : null;
}
