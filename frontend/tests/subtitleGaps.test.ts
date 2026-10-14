import assert from "node:assert/strict";
import { createElement, isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SubtitleGapMarkers } from "../components/SubtitleGapMarkers";
import { seekAndPauseAtSubtitleGap, subtitleGapLabel } from "../lib/subtitleGaps";
import { ReviewClipList } from "../components/subtitleReview/ReviewClipList";
import { ReviewSubtitleSegments } from "../components/subtitleReview/ReviewSubtitleSegments";
import { ReviewContentEditor } from "../components/subtitleReview/ReviewContentEditor";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import type { SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewGap, SubtitleReviewSegment } from "../lib/types";

const gap: SubtitleReviewGap = {
  id: "gap_middle", start: 12, end: 18, sourceStart: 109, sourceEnd: 115, acknowledged: false
};
const acknowledgedGap: SubtitleReviewGap = { ...gap, id: "gap_checked", start: 25, end: 29, acknowledged: true };
function segment(id: string, start: number, end: number): SubtitleReviewSegment {
  return { id, index: 0, start, end, originalText: id, text: id,
    confidence: null, edited: false, affectedClipIds: ["clip"] };
}
const segments = [segment("first", 100, 109), segment("second", 115, 120)];
assert.equal(subtitleGapLabel(gap), "字幕なし（音あり）0:12〜0:18");

const events: string[] = [];
let playbackTime = 0;
const player = {
  pause() { events.push("pause"); },
  get currentTime() { return playbackTime; },
  set currentTime(value: number) { playbackTime = value; events.push(`seek:${value}`); }
};
const onSelect = (selected: SubtitleReviewGap) => { seekAndPauseAtSubtitleGap(player, selected, 30); };
function buttons(node: ReactNode): Array<{ onClick?: () => void }> {
  if (Array.isArray(node)) return node.flatMap(buttons);
  if (!isValidElement<{ children?: ReactNode; onClick?: () => void }>(node)) return [];
  return [...(node.type === "button" ? [node.props] : []), ...buttons(node.props.children)];
}
const markerProps = { gaps: [gap, acknowledgedGap], duration: 30, onSelect };
const markerMarkup = renderToStaticMarkup(createElement(SubtitleGapMarkers, markerProps));
assert.equal((markerMarkup.match(/<button/g) ?? []).length, 2, "all gaps remain visible regardless of acknowledgement");
assert.match(markerMarkup, /left:40%;width:20%/);
assert.match(markerMarkup, /left:83\.33333333333334%;width:13\.333333333333334%/);
assert.doesNotMatch(markerMarkup, /確認済みにする|確認を保存中|[0-9]+か所/);
const unconfirmedMarkup = renderToStaticMarkup(createElement(SubtitleGapMarkers, {
  ...markerProps, gaps: markerProps.gaps.map(item => ({ ...item, acknowledged: false }))
}));
assert.equal(markerMarkup, unconfirmedMarkup, "confirmation flags do not change marker appearance");
for (const [index, second] of [12, 25].entries()) {
  buttons(SubtitleGapMarkers(markerProps))[index].onClick?.();
  assert.deepEqual(events.slice(-2), ["pause", `seek:${second}`]);
  assert.equal(playbackTime, second, "paused subtitle insertion continues to use the selected gap's position");
}
assert.equal(SubtitleGapMarkers({ ...markerProps, gaps: undefined }), null, "old responses without gaps remain usable");
assert.equal(SubtitleGapMarkers({ ...markerProps, gaps: [] }), null);
assert.equal(SubtitleGapMarkers({ ...markerProps, duration: 0 }), null);
assert.equal(seekAndPauseAtSubtitleGap(player, { ...gap, start: -5 }, 30), 0);
assert.equal(seekAndPauseAtSubtitleGap(player, { ...gap, start: 40 }, 30), 30);
assert.deepEqual(markerProps.gaps, [gap, acknowledgedGap], "display and seeking do not change saved confirmation flags");

const clip = {
  id: "clip", type: "normal", title: "タイトル", publicationTitle: "投稿タイトル",
  start: 100, end: 200, duration: 100, hookText: "", hookDurationSeconds: 3,
  hookSceneStart: null, hookSceneEnd: null, titleStyle: null, hookStyle: null, subtitleStyle: null,
  previewState: "ready", previewVideoUrl: "/preview.mp4", previewSpecHash: "spec",
  segmentIds: segments.map(item => item.id), confirmed: false, editedSegmentCount: 0, gaps: markerProps.gaps
} as SubtitleReviewClip;
const context = {
  selectedClip: clip, selectedClipId: clip.id, activeClipType: "normal", normalClips: [clip], shortClips: [], visibleClips: [clip],
  review: { clips: [clip], state: "awaiting_review", renderRevision: 1, totalClipCount: 1, confirmedClipCount: 0, editedSegmentCount: 0 } as SubtitleReviewDocument,
  clipContentDrafts: {}, selectedClipContentDraft: contentDraftForClip(clip), selectedSegments: [...segments].reverse(),
  drafts: {}, dirtySegmentIds: new Set(), subtitleListRef: { current: null }, segmentRowRefs: { current: {} },
  isEditable: true, allConfirmed: false, allPreviewsReady: true, bodyDuration: 100, clipDuration: 103,
  hookSceneDuration: 3, hookSuppressionEnd: 3, selectedHookDurationIsValid: true,
  // Supply the pre-change gap inputs so this fixture also detects the old rows/counts.
  selectedGaps: markerProps.gaps, selectedSubtitleTimeline: [
    { kind: "segment", segment: segments[0], segmentIndex: 1, start: 3 },
    { kind: "gap", gap, start: gap.start },
    { kind: "segment", segment: segments[1], segmentIndex: 0, start: 18 }
  ]
} as unknown as SubtitleReviewViewContext;
const clipMarkup = renderToStaticMarkup(createElement(ReviewClipList, { context }));
const segmentMarkup = renderToStaticMarkup(createElement(ReviewSubtitleSegments, { context }));
assert.doesNotMatch(clipMarkup, /字幕なし/);
assert.doesNotMatch(segmentMarkup, /字幕なし|確認済みにする|確認を保存中/);
assert.match(clipMarkup, /未確認/, "clip confirmation status remains visible");
assert.match(segmentMarkup, /この動画を確定/, "saving and clip confirmation remain available");
assert.equal((segmentMarkup.match(/<textarea/g) ?? []).length, 2);
assert(segmentMarkup.indexOf('>first</textarea>') < segmentMarkup.indexOf('>second</textarea>'),
  "subtitle rows keep their chronological display order");
assert.deepEqual(context.selectedSegments.map(item => item.id), ["second", "first"], "rendering does not reorder saved segments");
const emptyMarkup = renderToStaticMarkup(createElement(ReviewSubtitleSegments, { context: { ...context, selectedSegments: [] } }));
assert.match(emptyMarkup, /このclipに表示対象の字幕はありません/);
assert.doesNotMatch(emptyMarkup, /字幕なし|確認済みにする/);
const dirtyEditorMarkup = renderToStaticMarkup(createElement(ReviewContentEditor, { context: {
  ...context, autoGeneratingSuggestionClipIds: new Set<string>(), hasDirtyClipContent: true,
  dirtySegmentIds: new Set(["first"])
} }));
assert.doesNotMatch(dirtyEditorMarkup, /フック映像の変更前に|右下のOK/);
assert.match(dirtyEditorMarkup, /フック映像設定/, "dirty text must keep the hook editor available");
const staleClip = { ...clip, previewState: "stale" as const, previewDeferred: true };
const staleMarkup = renderToStaticMarkup(createElement(ReviewClipList, { context: {
  ...context, visibleClips: [staleClip]
} }));
assert.match(staleMarkup, /確定すると正式プレビューを作成/);
assert.doesNotMatch(staleMarkup, /完成表示プレビューを更新中/);
console.log("Subtitle gaps: marker-only display, confirmation-independent rendering, seek/pause and subtitle editing preserved");
