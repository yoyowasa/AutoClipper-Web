import type { SubtitleReviewClipFramingUpdateRequest } from "./types";

export type Framing = SubtitleReviewClipFramingUpdateRequest;
export type FramingGuide = {
  state: "queued" | "ready" | "failed";
  key: string;
  width: number;
  height: number;
  contentHeight: number;
  contentY: number;
  strategy: string;
  center: [number, number];
  error?: string | null;
};
export const clampFraming = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));
// Python round uses ties-to-even, including the renderer's scale and crop positions.
function round(n: number) {
  const floor = Math.floor(n);
  return n - floor === 0.5 ? floor + (floor % 2) : Math.round(n);
}
const even = (n: number) => { const value = Math.max(2, round(n)); return value + value % 2; };

export function framingGeometry(guide: FramingGuide, framing: Framing) {
  const w = 1080, h = guide.contentHeight;
  const tw = even(w * framing.framingZoom), th = even(h * framing.framingZoom);
  const blur = guide.strategy === "blur_background";
  const tracking = guide.strategy.endsWith("tracking_crop");
  const scale = (blur ? Math.min : Math.max)(tw / guide.width, th / guide.height);
  const width = round(guide.width * scale), height = round(guide.height * scale);
  const offsets = [framing.framingOffsetX, framing.framingOffsetY];
  const crop = [width, height].map((size, axis) => {
    const target = axis === 0 ? w : h;
    return tracking
      ? clampFraming(round(size * clampFraming(guide.center[axis] + offsets[axis] / 200, 0, 1) - target / 2), 0, size - target)
      : (size - target) * (0.5 + offsets[axis] / 200);
  });
  return { width, height, x: -crop[0], y: -crop[1], blur,
    source: {
      x: clampFraming(crop[0] / width, 0, 1), y: clampFraming(crop[1] / height, 0, 1),
      width: Math.min(w / width, 1), height: Math.min(h / height, 1),
    } };
}

export function framingAtPoint(guide: FramingGuide, framing: Framing, x: number, y: number): Framing {
  const geometry = framingGeometry(guide, framing);
  const values = [x, y].map((point, axis) => {
    const size = axis === 0 ? geometry.width : geometry.height;
    const target = axis === 0 ? 1080 : guide.contentHeight;
    // A fitting foreground has no crop to move by clicking. Sliders still position it.
    if (size <= target) return axis === 0 ? framing.framingOffsetX : framing.framingOffsetY;
    return clampFraming(guide.strategy.endsWith("tracking_crop")
      ? (point - guide.center[axis]) * 200
      : ((point * size - target / 2) / (size - target) - 0.5) * 200, -100, 100);
  });
  return { ...framing, framingOffsetX: Math.round(values[0]), framingOffsetY: Math.round(values[1]) };
}
