import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewSubtitleSegments } from "../components/subtitleReview/ReviewSubtitleSegments";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import { hasSpeakerColor, paintSubtitles, readRememberedColors, speakerColorOf, speakerColors, subtitlesBetween,
  writeRememberedColors } from "../lib/subtitleReview/speakerColors";
import type { SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment, SubtitleStyleOverride } from "../lib/types";
Object.assign(globalThis, { React });

const segments = [0, 1, 2, 3].map((index) => ({ id: `s${index}`, index, start: index * 3 + 1, end: index * 3 + 2,
  text: `字幕${index}`, affectedClipIds: ["clip"] })) as SubtitleReviewSegment[];
const pink = { primaryColor: "#FF66AA", outlineColor: "#330011" };
const blue = { primaryColor: "#3366FF" };

// A colour is only the colour part of a per-subtitle style.
assert.deepEqual(speakerColorOf({ primaryColor: "#ff66aa", outlineColor: "#330011", fontSize: 90, fontName: "Arial" }), pink);
assert.equal(speakerColorOf({ fontSize: 90 }), null);
assert.equal(speakerColorOf({ primaryColor: "red" }), null);

// One click paints one subtitle and keeps its other per-subtitle settings; a second click returns it to the common colour.
const sized: SubtitleStyleOverride[] = [{ start: 1, end: 2, style: { fontSize: 90 }, layoutAdjustment: { fontSize: 80 } }];
const painted = paintSubtitles(sized, [segments[0]], pink, true);
assert.deepEqual(painted, [{ start: 1, end: 2, style: { fontSize: 90, ...pink }, styleVersion: 2, layoutAdjustment: { fontSize: 80 } }]);
assert.equal(hasSpeakerColor(painted, segments[0], pink), true);
assert.deepEqual(paintSubtitles(painted, [segments[0]], pink, true).map((item) => item.style), [{ fontSize: 90 }]);
assert.deepEqual(paintSubtitles(paintSubtitles([], [segments[1]], pink, true), [segments[1]], pink, true), []);
// Another colour replaces the colour instead of mixing with it.
assert.deepEqual(paintSubtitles(painted, [segments[0]], blue, true)[0].style, { fontSize: 90, ...blue });

// Shift+click paints from the last painted subtitle to the clicked one, whichever comes first, and never toggles off.
assert.deepEqual(subtitlesBetween(segments, "s3", "s1").map((item) => item.id), ["s1", "s2", "s3"]);
assert.deepEqual(subtitlesBetween(segments, null, "s2").map((item) => item.id), ["s2"]);
assert.deepEqual(subtitlesBetween(segments, "gone", "s2").map((item) => item.id), ["s2"]);
const ranged = paintSubtitles(painted, subtitlesBetween(segments, "s0", "s2"), pink);
assert.deepEqual(ranged.map((item) => [item.start, hasSpeakerColor(ranged, item, pink)]).sort(), [[1, true], [4, true], [7, true]]);

// Colours used in the job come first, then remembered ones; duplicates collapse and four buttons is the limit.
assert.deepEqual(speakerColors([[{ start: 4, end: 5, style: blue }, { start: 1, end: 2, style: pink }], [{ start: 1, end: 2, style: pink }]],
  [{ primaryColor: "#00FF00" }, blue]), [pink, blue, { primaryColor: "#00FF00" }]);
assert.equal(speakerColors([], ["1", "2", "3", "4", "5"].map((n) => ({ primaryColor: `#00000${n}` }))).length, 4);

// Remembered per character in the browser; broken or foreign data is ignored.
const saved = new Map<string, string>();
const storage = { getItem: (key: string) => saved.get(key) ?? null, setItem: (key: string, value: string) => { saved.set(key, value); },
  removeItem: (key: string) => { saved.delete(key); } };
writeRememberedColors(storage, "キャラA", [pink, blue]);
assert.deepEqual(readRememberedColors(storage, "キャラA"), [pink, blue]);
assert.deepEqual(readRememberedColors(storage, "キャラB"), []);
saved.set([...saved.keys()][0], JSON.stringify([{ primaryColor: "javascript:alert(1)" }, "x", pink]));
assert.deepEqual(readRememberedColors(storage, "キャラA"), [pink]);
saved.set([...saved.keys()][0], "{broken");
assert.deepEqual(readRememberedColors(storage, "キャラA"), []);
writeRememberedColors(storage, "キャラA", []);
assert.equal(saved.size, 0);
assert.deepEqual(readRememberedColors(undefined, "キャラA"), []);

// The rows show one button per colour, mark the subtitle that has it, and follow the caption edit lock.
const clip = { id: "clip", type: "short", title: "題", confirmed: false, start: 0, end: 70, segmentIds: segments.map((s) => s.id),
  subtitleStyles: [{ start: 1, end: 2, style: pink }] } as unknown as SubtitleReviewClip;
const other = { ...clip, id: "other", subtitleStyles: [{ start: 4, end: 5, style: blue }] } as unknown as SubtitleReviewClip;
const review = { jobId: "job", state: "awaiting_review", characterPresetName: "キャラA", clips: [clip, other], segments } as SubtitleReviewDocument;
let update: { subtitleStyles?: SubtitleStyleOverride[] } | null = null;
const context = { jobId: "job", review, selectedClip: clip, selectedSegments: segments, selectedClipContentDraft: contentDraftForClip(clip),
  clipContentDrafts: {}, dirtySegmentIds: new Set<string>(), rawDrafts: {}, drafts: {}, isSubtitleEditable: true,
  hookSuppressionEnd: 0, hookSceneDuration: 0, clipDuration: 70, subtitleListRef: { current: null }, segmentRowRefs: { current: {} },
  updateClipContentDraft: (_id: string, value: { subtitleStyles?: SubtitleStyleOverride[] }) => { update = value; },
} as unknown as SubtitleReviewViewContext;
const html = renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context }));
assert.equal((html.match(/aria-label="色1にする"/g) ?? []).length, 4);
assert.equal((html.match(/aria-label="色2にする"/g) ?? []).length, 4);
assert.equal((html.match(/aria-label="色1にする" aria-pressed="true"/g) ?? []).length, 1);
assert.match(html, /background-color:#FF66AA;border-color:#330011/);
assert.match(html, /Shift＋クリック/);
assert.equal(update, null);
context.isSubtitleEditable = false;
assert.match(renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context })), /<button[^>]*disabled=""[^>]*aria-label="色1にする"/);
const none = { ...context, review: { ...review, clips: [{ ...clip, subtitleStyles: [] }] }, selectedClipContentDraft: contentDraftForClip({ ...clip, subtitleStyles: [] }) };
const empty = renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context: none as unknown as SubtitleReviewViewContext }));
assert.doesNotMatch(empty, /色1にする/);
assert.match(empty, /その色のボタンが各字幕に出ます/);
assert.doesNotMatch(renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context, showStyleControls: false })), /色1にする/);
console.log("Speaker colours: one-click paint/toggle, Shift range, kept settings, job-first palette, per-character memory and row buttons passed");
