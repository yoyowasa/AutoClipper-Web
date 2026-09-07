import { deepStrictEqual, strictEqual, ok } from "node:assert";
import { subtitlePreviewEvents } from "../lib/subtitlePreview";
import { defaultClipTextStyle, resolvedClipTextStyle, assPreviewFontMetrics } from "../lib/clipTextStyle";

const style = { ...defaultClipTextStyle("subtitle", "short"), fontPreset: "keifont" as const,
  fontName: "Keifont", primaryColor: "#FF0000", outerOutlineWidth: 6, outerOutlineColor: "#0000FF" };
const options = { candidateStart: 10, candidateEnd: 18, hookSceneDuration: 0, suppressionEnd: 0,
  maxCharsPerLine: 16, maxLines: 2, minSubtitleDuration: 1.1, maxSubtitleDuration: 4.2,
  minGapBetweenSubtitles: 0.08,
  segments: [{ start: 10, end: 12, text: "いつもの字幕" }, { start: 12, end: 14, text: "ここだけ強調", style },
    { start: 14, end: 18, text: "共通に戻る" }] };
const events = subtitlePreviewEvents(options);
deepStrictEqual(events.map((e) => [e.start, e.end, e.style ?? null]), [[0,1.92,null],[2,3.92,style],[4,8,null]]);
const suppressed = subtitlePreviewEvents({ ...options, hookSceneDuration: 2, suppressionEnd: 5 });
ok(suppressed.every((event) => event.start >= 5));
deepStrictEqual(suppressed[0].style, style);
const resolved = resolvedClipTextStyle(style, null, "subtitle", "short");
strictEqual(resolved.outerOutlineWidth, 6);
strictEqual(resolved.outerOutlineColor, "#0000FF");
strictEqual(assPreviewFontMetrics("Keifont").fontSizeScale, 1024 / 1134);
console.log("Phrase style timing, suppression, and outline contracts passed");
