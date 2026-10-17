import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { subtitlePreviewEvents } from "../lib/subtitlePreview";
import { longEditedSubtitleWarning, usableSubtitleWords } from "../lib/subtitleTiming";

const fixture = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../tests/fixtures/subtitle_timing.json"), "utf8"));
for (const test of fixture.cases) {
  const events = subtitlePreviewEvents({ ...fixture.options, ...test.options, segments: test.segments });
  assert.deepEqual(events.map(({ start, end, text }) => ({ start, end, text })), test.expected, test.name);
}
const segment = { start: 0, end: 6, text: "手で直した字幕", originalText: "元の字幕", words: null };
assert.equal(longEditedSubtitleWarning(segment), true);
assert.equal(longEditedSubtitleWarning({ ...segment, end: 5.999 }), false);
assert.equal(longEditedSubtitleWarning({ ...segment, text: segment.originalText }), false);
const words = [{ start: 1, end: 2, word: segment.text }];
assert.equal(longEditedSubtitleWarning({ ...segment, words }), false);
assert.equal(longEditedSubtitleWarning({ ...segment, words }, "未保存の編集"), true);
assert.equal(usableSubtitleWords("手で直した字幕", [...words, { start: 1, end: 0, word: "" }]), false);
console.log("Speech timing, short captions, legacy fallback, clipping, and editor warnings match shared fixtures.");
