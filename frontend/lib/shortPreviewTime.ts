export function shortPreviewSourceTime(time: number, start: number, end: number, hookStart: number | null, hookEnd: number | null) {
  const hookDuration = hookStart !== null && hookEnd !== null ? Math.max(0, hookEnd - hookStart) : 0;
  return Math.min(end, Math.max(start, hookDuration > 0 && time < hookDuration
    ? hookStart! + time : start + Math.max(0, time - hookDuration)));
}
