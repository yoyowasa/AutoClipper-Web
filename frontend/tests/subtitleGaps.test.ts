import assert from "node:assert/strict";
import { createElement, isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SubtitleGapMarkers, SubtitleGapRow } from "../components/SubtitleGapMarkers";
import { acknowledgeSubtitleReviewGap } from "../lib/api";
import {
  mergeSubtitleGapAcknowledgement,
  seekAndPauseAtSubtitleGap,
  subtitleGapLabel,
  subtitleTimeline,
  unacknowledgedSubtitleGaps
} from "../lib/subtitleGaps";
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
assert.deepEqual(subtitleTimeline(segments, [gap, acknowledgedGap], 100, 3).map((item) =>
  item.kind === "segment" ? [item.kind, item.segment.id, item.segmentIndex, item.start] : [item.kind, item.gap.id, item.start]
), [["segment", "first", 0, 3], ["gap", "gap_middle", 12], ["segment", "second", 1, 18]],
"gap times already include the hook; segment times include it exactly once");
assert.equal(subtitleTimeline([], [gap], 100, 3)[0].kind, "gap", "clips with no captions still show their gap");
assert.equal(subtitleTimeline(segments, undefined, 100, 0).length, 2, "old responses without gaps remain usable");
assert.deepEqual(unacknowledgedSubtitleGaps([gap, acknowledgedGap]), [gap]);
assert.equal(subtitleGapLabel(gap), "字幕なし（音あり）0:12〜0:18");

const events: string[] = [];
let playbackTime = 0;
const player = {
  pause() { events.push("pause"); },
  get currentTime() { return playbackTime; },
  set currentTime(value: number) { playbackTime = value; events.push(`seek:${value}`); }
};
const onSelect = (selected: SubtitleReviewGap) => { seekAndPauseAtSubtitleGap(player, selected, 30); };
let savedGap: SubtitleReviewGap | null = null;
const row = SubtitleGapRow({ gap, editable: true, saving: false, canSeek: true,
  onSelect, onAcknowledge: (selected) => { savedGap = selected; } });
function buttons(node: ReactNode): Array<{ onClick?: () => void }> {
  if (Array.isArray(node)) return node.flatMap(buttons);
  if (!isValidElement<{ children?: ReactNode; onClick?: () => void }>(node)) return [];
  return [...(node.type === "button" ? [node.props] : []), ...buttons(node.props.children)];
}
buttons(row)[0].onClick?.();
assert.deepEqual(events, ["pause", "seek:12"], "clicking the gap pauses and seeks to its clip-relative start");
assert.equal(playbackTime, 12, "the existing paused-caption insertion uses this playback position");
buttons(row)[1].onClick?.();
assert.equal(savedGap, gap);
assert.equal(SubtitleGapRow({ gap: acknowledgedGap, editable: true, saving: false, canSeek: true,
  onSelect, onAcknowledge: () => {} }), null, "confirmed rows disappear");
const rowMarkup = renderToStaticMarkup(row);
assert.match(rowMarkup, /停止位置から字幕を追加/);
assert.match(rowMarkup, /確認済みにする/);
const markerProps = { gaps: [gap, acknowledgedGap], duration: 30, onSelect };
const markerMarkup = renderToStaticMarkup(createElement(SubtitleGapMarkers, markerProps));
assert.equal((markerMarkup.match(/<button/g) ?? []).length, 1, "confirmed marks disappear from the playback bar too");
assert.match(markerMarkup, /left:40%;width:20%/);
buttons(SubtitleGapMarkers(markerProps))[0].onClick?.();
assert.deepEqual(events.slice(-2), ["pause", "seek:12"]);

const current = {
  jobId: "job", updatedAt: "before", segments,
  clips: [{ id: "clip", gaps: [gap], title: "current title", previewState: "ready" } as SubtitleReviewClip]
} as SubtitleReviewDocument;
const updated = {
  ...current, updatedAt: "after", segments: [segment("server", 0, 1)],
  clips: [{ ...current.clips[0], title: "old server title", previewState: "queued", gaps: [{ ...gap, acknowledged: true }] }]
} as SubtitleReviewDocument;
const merged = mergeSubtitleGapAcknowledgement(current, updated, "clip");
assert.equal(merged.segments, current.segments, "confirmation cannot reset subtitle edits");
assert.equal(merged.clips[0].title, "current title");
assert.equal(merged.clips[0].previewState, "ready");
assert.deepEqual(unacknowledgedSubtitleGaps(merged.clips[0].gaps), []);
assert.equal(merged.updatedAt, "after");

async function main() {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    assert.match(String(input), /\/api\/jobs\/job\/subtitle-review\/clips\/clip\/gaps\/gap_middle$/);
    assert.equal(init?.method, "PATCH");
    assert.deepEqual(JSON.parse(String(init?.body)), { acknowledged: true });
    return new Response(JSON.stringify(updated), { headers: { "Content-Type": "application/json" } });
  };
  try {
    assert.deepEqual((await acknowledgeSubtitleReviewGap("job", "clip", gap.id)).clips[0].gaps, updated.clips[0].gaps);
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "空白区間が変わりました。再読み込みしてください。" }), { status: 404 });
    await assert.rejects(acknowledgeSubtitleReviewGap("job", "clip", gap.id), /空白区間が変わりました/);
  } finally { globalThis.fetch = originalFetch; }
  console.log("Subtitle gaps: timeline, playback marks, seek/pause and persisted confirmation passed.");
}
void main().catch((error) => { console.error(error); process.exitCode = 1; });
