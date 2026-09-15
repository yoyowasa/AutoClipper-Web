import { clampFraming, type framingGeometry, type FramingGuide } from "./shortFraming";

// Matches the standard banner slots used by the short renderer.
export const SHORT_BANNER_GUIDE = { width: 1080, height: 1920, top: 360, bottom: 1560 } as const;

export function drawShortBannerGuide(context: CanvasRenderingContext2D) {
  const { width, height, top, bottom } = SHORT_BANNER_GUIDE;
  context.save();
  context.fillStyle = "rgba(15, 23, 42, .72)";
  context.fillRect(0, 0, width, top);
  context.fillRect(0, bottom, width, height - bottom);
  context.strokeStyle = "#fbbf24";
  context.lineWidth = 5;
  context.setLineDash([20, 12]);
  for (const y of [top, bottom]) {
    context.beginPath(); context.moveTo(0, y); context.lineTo(width, y); context.stroke();
  }
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillStyle = "#fef3c7";
  context.font = "bold 46px sans-serif";
  context.fillText("上帯の目安", width / 2, top / 2 - 28);
  context.fillText("下帯の目安", width / 2, (bottom + height) / 2 - 28);
  context.font = "36px sans-serif";
  context.fillText("360px", width / 2, top / 2 + 36);
  context.fillText("360px", width / 2, (bottom + height) / 2 + 36);
  context.restore();
}

export function drawSourceBannerGuide(
  context: CanvasRenderingContext2D, guide: FramingGuide,
  geometry: ReturnType<typeof framingGeometry>, width: number, height: number,
) {
  const rect = geometry.source;
  const x = rect.x * width, y = rect.y * height;
  const w = rect.width * width, h = rect.height * height;
  const sourceY = (outputY: number) => (outputY - guide.contentY - geometry.y) / geometry.height * height;
  const top = sourceY(SHORT_BANNER_GUIDE.top), bottom = sourceY(SHORT_BANNER_GUIDE.bottom);
  context.save();
  context.fillStyle = "rgba(251, 191, 36, .22)";
  context.fillRect(x, y, w, clampFraming(top - y, 0, h));
  const lower = clampFraming(bottom, y, y + h);
  context.fillRect(x, lower, w, y + h - lower);
  context.strokeStyle = "#fbbf24";
  context.lineWidth = 3;
  context.setLineDash([10, 6]);
  for (const boundary of [top, bottom]) {
    if (boundary < y - .5 || boundary > y + h + .5) continue;
    context.beginPath(); context.moveTo(x, boundary); context.lineTo(x + w, boundary); context.stroke();
  }
  context.restore();
}
