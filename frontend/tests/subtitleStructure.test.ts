import assert from "node:assert/strict";
import { subtitlePreviewEvents } from "../lib/subtitlePreview";

const events = subtitlePreviewEvents({
  segments: [
    { start: 1, end: 1.2, text: "前半", preserveSegmentation: true, singleLine: true },
    { start: 1.2, end: 9, text: "後半".repeat(30), preserveSegmentation: true, singleLine: true }
  ],
  candidateStart: 0, candidateEnd: 10, hookSceneDuration: 2, suppressionEnd: 0,
  maxCharsPerLine: 16, maxLines: 2, minSubtitleDuration: 1,
  maxSubtitleDuration: 5, minGapBetweenSubtitles: 0.08
});
assert.equal(events.length, 2);
assert.deepEqual(events.map(({ start, end }) => [start, end]), [[3, 3.2], [3.2, 11]]);
assert.ok(events.every(event => event.singleLine && event.preserveSegmentation));
assert.equal(events[1].text, "後半".repeat(30));
console.log("Manual subtitle boundaries and one-line flags survive preview generation.");
