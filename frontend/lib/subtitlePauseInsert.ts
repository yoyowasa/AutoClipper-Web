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
