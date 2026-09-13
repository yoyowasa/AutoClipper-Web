import assert from "node:assert/strict";
import { matchingSubtitleCorrections } from "../lib/subtitleBulkCorrection";
import type { SubtitleReviewSegment } from "../lib/types";

const segments = [
  { id: "a", start: 0, text: "アカネとアカネ", affectedClipIds: ["normal", "short"] },
  { id: "b", start: 3, text: "アカネさん", affectedClipIds: ["short"] },
  { id: "c", start: 8, text: "あかねです", affectedClipIds: ["other"] },
] as SubtitleReviewSegment[];
const matches = matchingSubtitleCorrections(segments, { b: "アカネさんの未保存文", c: "別の未保存文" }, "アカネ", "あかね");
assert.equal(matches.reduce((total, item) => total + item.count, 0), 3);
assert.equal(matches.length, 2); // Shared subtitle counted once, not once per clip.
assert.equal(matches[1].before, "アカネさん");
assert.equal(matches[1].text, "あかねさんの未保存文");
assert.equal(matches[1].current, "アカネさんの未保存文"); // Undo keeps the user's draft.
assert.deepEqual(matchingSubtitleCorrections(segments, {}, "", "a"), []);
assert.deepEqual(matchingSubtitleCorrections(segments, {}, "アカネ", "アカネ"), []);
assert.deepEqual(matchingSubtitleCorrections(segments, {}, "アカネ", ""), []);
const literal = matchingSubtitleCorrections([{ ...segments[0], text: "[a]. [a]." }], {}, "[a].", "$&");
assert.equal(literal[0].text, "$& $&"); // Neither regex nor replacement tokens.
console.log("Bulk correction: exact matches, shared segments, unsaved drafts and literal text verified");
