import assert from "node:assert/strict";
import { subtitlePreviewEvents } from "../lib/subtitlePreview";
import { nextNonemptySubtitleStart, sourceTimeAtPlayback, subtitleInsertionConflict } from "../lib/subtitlePauseInsert";
import { remapInsertedSubtitleDraft, subtitleStructureSources } from "../lib/subtitleStructureDrafts";
import { defaultClipTextStyle } from "../lib/clipTextStyle";
import type { SubtitleReviewSegment, SubtitleStructureRequest } from "../lib/types";

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
assert.equal(sourceTimeAtPlayback({ playbackTime: 12.35, clipStart: 100, clipEnd: 150,
  hookSceneDuration: 0, suppressionEnd: 0 }), 112.35);
assert.equal(sourceTimeAtPlayback({ playbackTime: 12.359, clipStart: 100, clipEnd: 150,
  hookSceneDuration: 0, suppressionEnd: 0 }), 112.35);
assert.equal(sourceTimeAtPlayback({ playbackTime: 12.35, clipStart: 100, clipEnd: 150,
  hookSceneDuration: 3, suppressionEnd: 3 }), 109.35);
assert.equal(sourceTimeAtPlayback({ playbackTime: 2.5, clipStart: 100, clipEnd: 150,
  hookSceneDuration: 3, suppressionEnd: 3 }), null);
assert.equal(sourceTimeAtPlayback({ playbackTime: 52.95, clipStart: 100, clipEnd: 150,
  hookSceneDuration: 3, suppressionEnd: 3 }), null);
const gapSegments = [
  { id: "before", start: 100, end: 105, text: "直前" },
  { id: "blank", start: 106, end: 114, text: "" },
  { id: "whitespace", start: 114, end: 115, text: "  " },
  { id: "after", start: 118, end: 122, text: "次の字幕" }
];
assert.equal(nextNonemptySubtitleStart(gapSegments, 105, 125), 118, "empty rows cannot cap the insertion range");
assert.equal(nextNonemptySubtitleStart(gapSegments, 123, 125), 125);
assert.equal(subtitleInsertionConflict(gapSegments, 106, 117), null, "saved empty rows can be replaced by new subtitles");
assert.equal(subtitleInsertionConflict(gapSegments, 106, 119), "overlap", "nonempty caption overlap remains blocked");
assert.equal(subtitleInsertionConflict(gapSegments, 106, 117, new Set(["blank"])), "unsaved",
  "splitting an empty row cannot discard its unsaved edit");
assert.equal(subtitleInsertionConflict(gapSegments, 106, 117, new Set(["before"])), null,
  "unrelated drafts stay editable and do not prevent insertion into a gap");
assert.equal(subtitleInsertionConflict(gapSegments.map((item) => item.id === "blank" ? { ...item, text: "編集中" } : item), 106, 117), "overlap",
  "the live preview still respects the nonempty text currently being edited");
const styledSegment = (id: string, start: number, end: number, text: string): SubtitleReviewSegment => ({
  id, start, end, text, originalText: "", index: 1, confidence: null, edited: true, affectedClipIds: ["clip", "shared"]
});
const emptySource = styledSegment("old_empty", 2, 8, "");
const insertion: SubtitleStructureRequest = { action: "insert_at_time", segments: [], clipId: "clip", start: 4, end: 6, text: "追加" };
const sources = subtitleStructureSources([emptySource, styledSegment("other", 10, 12, "他の字幕")], insertion);
assert.deepEqual(sources, [emptySource], "time insertion targets include the empty rows whose IDs are replaced");
const replacements = [styledSegment("left", 2, 4, ""), styledSegment("inserted", 4, 6, "追加"), styledSegment("right", 6, 8, "")];
const savedStyle = { ...defaultClipTextStyle("subtitle", "normal"), primaryColor: "#0000FF" };
const draftStyle = { ...savedStyle, primaryColor: "#FF0000" };
const otherDraftStyle = { ...savedStyle, primaryColor: "#00FF00" };
const previousClip = { subtitleStyles: [{ start: 2, end: 8, style: savedStyle }] };
const updatedClip = { id: "clip", subtitleStyles: replacements.map((segment) => ({ start: segment.start, end: segment.end, style: savedStyle })) };
const contentDraft = { title: "未保存タイトル", hookText: "未保存フック", subtitleStyles: [
  { start: 2, end: 8, style: draftStyle }, { start: 10, end: 12, style: otherDraftStyle }
] };
const remapped = remapInsertedSubtitleDraft(contentDraft, previousClip, updatedClip, sources, replacements, 4, 6);
assert.equal(remapped.title, contentDraft.title);
assert.equal(remapped.hookText, contentDraft.hookText);
assert.deepEqual(remapped.subtitleStyles.map((item) => [item.start, item.end, item.style.primaryColor]), [
  [10, 12, "#00FF00"], [2, 4, "#FF0000"], [4, 6, "#FF0000"], [6, 8, "#FF0000"]
], "the split ranges inherit an unsaved style while unrelated styles and metadata survive");
assert.equal(contentDraft.subtitleStyles[0].end, 8, "the old draft is not mutated");
const savedDraft = remapInsertedSubtitleDraft({ subtitleStyles: previousClip.subtitleStyles }, previousClip, updatedClip, sources, replacements, 4, 6);
assert.deepEqual(savedDraft.subtitleStyles, updatedClip.subtitleStyles, "unchanged styles use the saved replacement ranges");
assert.deepEqual(remapInsertedSubtitleDraft({ subtitleStyles: [] }, previousClip, updatedClip, sources, replacements, 4, 6).subtitleStyles, [],
  "an unsaved style removal must not reappear after the insertion");
const newlyStyled = remapInsertedSubtitleDraft({ subtitleStyles: [contentDraft.subtitleStyles[0]] }, { subtitleStyles: [] },
  { id: "clip", subtitleStyles: [] }, sources, replacements, 4, 6);
assert.equal(newlyStyled.subtitleStyles.length, 3, "new unsaved style overrides also follow the split ranges");
const sharedDraft = remapInsertedSubtitleDraft({ subtitleStyles: previousClip.subtitleStyles }, previousClip,
  { ...updatedClip, id: "shared" }, sources, replacements, 4, 6);
assert.deepEqual(sharedDraft.subtitleStyles, updatedClip.subtitleStyles, "shared clips receive the same replacement ranges");
const insertionPreview = subtitlePreviewEvents({
  segments: replacements.map((segment) => ({ ...segment, preserveSegmentation: true,
    style: remapped.subtitleStyles.find((item) => item.start === segment.start && item.end === segment.end)?.style })),
  candidateStart: 0, candidateEnd: 12, hookSceneDuration: 0, suppressionEnd: 0,
  maxCharsPerLine: 28, maxLines: 2, minSubtitleDuration: 1, maxSubtitleDuration: 5, minGapBetweenSubtitles: 0.08
});
assert.equal(insertionPreview[0].style, draftStyle, "the immediate inserted-caption preview keeps the individual draft style");
const adjacentSources = [styledSegment("one", 2, 5, ""), styledSegment("two", 5, 8, "")];
const adjacentDraft = { subtitleStyles: [{ start: 2, end: 5, style: draftStyle }, { start: 5, end: 8, style: otherDraftStyle }] };
const adjacentRemap = remapInsertedSubtitleDraft(adjacentDraft, { subtitleStyles: [] }, { id: "clip", subtitleStyles: [] },
  adjacentSources, replacements, 4, 6);
assert.deepEqual(adjacentRemap.subtitleStyles.map((item) => [item.start, item.end, item.style.primaryColor]), [
  [2, 4, "#FF0000"], [4, 6, "#FF0000"], [6, 8, "#00FF00"]
], "multiple empty source rows preserve each remainder's own style and use the first row for the new caption");
console.log("Manual subtitle boundaries and one-line flags survive preview generation.");
