import { shortPreviewSourceTime } from "../shortPreviewTime";

export type DraftPlaybackRange = {
  start: number; end: number; hookStart: number | null; hookEnd: number | null;
  mediaStart?: number; mediaOffset?: number;
};
const elements = new WeakMap<HTMLVideoElement, HTMLVideoElement>();
export const sourceVideoForClock = (clock: HTMLVideoElement) => elements.get(clock) ?? clock;

// Keep existing clip-relative seek/play controls while the native element plays
// source-relative media. The proxy binds browser methods to the real element.
export function draftPlaybackClock(element: HTMLVideoElement, range: DraftPlaybackRange) {
  let mediaStart = range.mediaStart ?? 0, mediaOffset = range.mediaOffset ?? 0;
  const sourceTime = () => element.currentTime + mediaStart - mediaOffset;
  const mediaTime = (source: number) => source - mediaStart + mediaOffset;
  let hookDuration = range.hookStart !== null && range.hookEnd !== null ? range.hookEnd - range.hookStart : 0;
  let duration = range.end - range.start + hookDuration;
  let part: "hook" | "body" = hookDuration > 0 ? "hook" : "body";
  const seek = (time: number) => {
    const clipped = Math.max(0, Math.min(duration, time));
    part = clipped < hookDuration ? "hook" : "body";
    element.currentTime = mediaTime(shortPreviewSourceTime(clipped, range.start, range.end, range.hookStart, range.hookEnd));
  };
  const clock = new Proxy(element, {
    get(target, property) {
      if (property === "currentTime") return part === "hook"
        ? Math.max(0, sourceTime() - (range.hookStart ?? range.start))
        : hookDuration + Math.max(0, sourceTime() - range.start);
      if (property === "duration") return duration;
      const value = Reflect.get(target, property, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
    set(target, property, value) {
      if (property === "currentTime") { seek(Number(value)); return true; }
      return Reflect.set(target, property, value, target);
    }
  });
  elements.set(clock, element);
  return {
    clock, seek,
    updateRange(next: DraftPlaybackRange) {
      const source = sourceTime(), hookTime = clock.currentTime;
      range = next;
      mediaStart = range.mediaStart ?? 0; mediaOffset = range.mediaOffset ?? 0;
      hookDuration = range.hookStart !== null && range.hookEnd !== null ? range.hookEnd - range.hookStart : 0;
      duration = range.end - range.start + hookDuration;
      // A background hook decision changes the virtual timeline, not the body
      // video. Keep its source position and playback state (no pause/load).
      if (part === "hook" && hookDuration > 0) {
        if (Math.abs(source - (range.hookStart! + Math.min(hookTime, hookDuration))) > 0.001) seek(Math.min(hookTime, hookDuration));
      } else {
        part = "body";
        const nextTime = mediaTime(Math.max(range.start, Math.min(range.end, source)));
        if (Math.abs(element.currentTime - nextTime) > 0.001) element.currentTime = nextTime;
      }
    },
    advance() {
      if (part === "hook" && sourceTime() >= (range.hookEnd ?? range.start)) {
        const ended = element.ended;
        part = "body"; element.currentTime = mediaTime(range.start);
        if (ended) void element.play().catch(() => {});
      } else if (part === "body" && sourceTime() >= range.end) {
        if (!element.paused) element.pause();
        if (sourceTime() > range.end) element.currentTime = mediaTime(range.end);
      }
    }
  };
}
