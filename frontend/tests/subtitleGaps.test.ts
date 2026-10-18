import assert from "node:assert/strict";
import { createElement, isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewPreview } from "../components/subtitleReview/ReviewPreview";
import { useReviewPreviews } from "../lib/subtitleReview/hooks/useReviewPreviews";
import { ReviewClipList } from "../components/subtitleReview/ReviewClipList";
import { ReviewSubtitleSegments } from "../components/subtitleReview/ReviewSubtitleSegments";
import { ReviewContentEditor } from "../components/subtitleReview/ReviewContentEditor";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import type { SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../lib/types";

// Backend compatibility fields may still arrive; the frontend must ignore them.
const gap = {
  id: "gap_middle", start: 12, end: 18, sourceStart: 109, sourceEnd: 115, acknowledged: false
};
const acknowledgedGap = { ...gap, id: "gap_checked", start: 25, end: 29, acknowledged: true };
function segment(id: string, start: number, end: number): SubtitleReviewSegment {
  return { id, index: 0, start, end, originalText: id, text: id,
    confidence: null, edited: false, affectedClipIds: ["clip"] };
}
const segments = [segment("first", 100, 109), segment("second", 115, 120)];
const events: string[] = [];
let playbackTime = 0;
const player = {
  pause() { events.push("pause"); },
  get currentTime() { return playbackTime; },
  set currentTime(value: number) { playbackTime = value; events.push(`seek:${value}`); }
};
function elements(node: ReactNode): Array<Record<string, unknown>> {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<{ children?: ReactNode }>(node)) return [];
  return [node.props, ...elements(node.props.children)];
}
const legacyGaps = [gap, acknowledgedGap];

const clip = {
  id: "clip", type: "normal", title: "タイトル", publicationTitle: "投稿タイトル",
  start: 100, end: 200, duration: 100, hookText: "", hookDurationSeconds: 3,
  hookSceneStart: null, hookSceneEnd: null, titleStyle: null, hookStyle: null, subtitleStyle: null,
  previewState: "ready", previewVideoUrl: "/preview.mp4", previewSpecHash: "spec",
  segmentIds: segments.map(item => item.id), confirmed: false, editedSegmentCount: 0, gaps: legacyGaps
} as unknown as SubtitleReviewClip;
const context = {
  selectedClip: clip, selectedClipId: clip.id, activeClipType: "normal", normalClips: [clip], shortClips: [], visibleClips: [clip],
  review: { clips: [clip], state: "awaiting_review", renderRevision: 1, totalClipCount: 1, confirmedClipCount: 0, editedSegmentCount: 0 } as SubtitleReviewDocument,
  clipContentDrafts: {}, selectedClipContentDraft: contentDraftForClip(clip), selectedSegments: [...segments].reverse(),
  drafts: {}, dirtySegmentIds: new Set(), subtitleListRef: { current: null }, segmentRowRefs: { current: {} },
  isEditable: true, allConfirmed: false, allPreviewsReady: true, bodyDuration: 100, clipDuration: 103,
  hookSceneDuration: 3, hookSuppressionEnd: 3, selectedHookDurationIsValid: true,
  // Supply the pre-change gap inputs so this fixture also detects the old rows/counts.
  selectedGaps: legacyGaps, selectedSubtitleTimeline: [
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

const previewContext = {
  ...context, review: { ...context.review, sourceVideoUrl: "/source.mp4" },
  retainedLivePreviews: {}, selectedPlayerReady: true, selectedPlayerVideoUrl: "/preview.mp4",
  selectedPlayerPreviewVersion: "spec", selectedPreviewReady: true, isPlayerReady: true,
  isShowingLivePreview: false, clipTime: 0, isPlaying: false, playbackRate: 1, volume: 1, isMuted: false,
  videoRef: { current: player }, suggestionPlaybackEndRef: { current: null },
  setPreviewingSuggestionId: () => {}, setClipTime: (time: number) => { events.push(`clock:${time}`); },
  setIsPlaying: (playing: boolean) => { events.push(`playing:${playing}`); },
  openPausedSubtitleDraft: () => { events.push("insert"); }
} as unknown as SubtitleReviewViewContext;
function PreviewControlsHarness() {
  Object.assign(previewContext, useReviewPreviews(previewContext));
  return null;
}
renderToStaticMarkup(createElement(PreviewControlsHarness));
for (const type of ["normal", "short"] as const) {
  for (const isShowingLivePreview of [false, true]) {
    const selectedClip = { ...clip, type };
    const active = { ...previewContext, selectedClip, isShowingLivePreview };
    const markup = renderToStaticMarkup(createElement(ReviewPreview, { context: active }));
    assert.doesNotMatch(markup, /字幕なし（音あり）|橙色|bg-amber/);
    assert.match(markup, /clip再生位置/);
    assert.match(markup, /停止位置に字幕を追加/);
    assert.match(markup, /5秒戻る|1秒進む|再生速度/);
    for (const gaps of [undefined, [], legacyGaps.map(item => ({ ...item, acknowledged: true }))]) {
      assert.equal(renderToStaticMarkup(createElement(ReviewPreview, { context: {
        ...active, selectedClip: { ...selectedClip, gaps }
      } as SubtitleReviewViewContext })), markup, "legacy gap data does not affect the preview");
    }
  }
}
const controls = elements(ReviewPreview({ context: previewContext }));
const seek = controls.find(props => props["aria-label"] === "clip再生位置");
(seek?.onChange as (event: { target: { value: string } }) => void)({ target: { value: "12" } });
assert.equal(playbackTime, 12, "ordinary playback seeking remains available");
previewContext.seekToSubtitle(115);
assert.equal(playbackTime, 18, "subtitle-row seeking still uses source time and hook duration");
assert.deepEqual(events.slice(-4), ["pause", "seek:18", "clock:18", "playing:false"]);
const insert = controls.find(props => props.children === "停止位置に字幕を追加");
(insert?.onClick as () => void)();
assert.equal(events.at(-1), "insert", "paused subtitle insertion remains connected");
console.log("Subtitle gaps: no markers or labels; legacy responses, playback seeking and subtitle editing preserved");
