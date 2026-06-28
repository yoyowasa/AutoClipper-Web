export function formatDuration(seconds: number): string {
  const totalSeconds = Math.round(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

export function formatScore(score: number): string {
  return Math.round(score).toString();
}
