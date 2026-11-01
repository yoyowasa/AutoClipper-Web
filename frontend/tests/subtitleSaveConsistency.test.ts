import assert from "node:assert/strict";
import { contentDraftForClip, isClipContentDirty } from "../lib/subtitleReview/drafts";
import { remapDraftEvidence } from "../lib/subtitleReview/draftEvidence";
import { rebaseUnchangedContent } from "../lib/subtitleReview/draftStorage";
import { draftPlaybackClock } from "../lib/subtitleReview/draftPlayback";
import { livePlaybackSource, livePreviewReference, editingPreviewAvailable } from "../lib/subtitleReview/livePlaybackSource";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../lib/types";

const row = { id: "shared", index: 253, start: 759.08, end: 761.66, sourceIndices: [253], clipScoped: true } as SubtitleReviewSegment;
const fork = { ...row, id: "normal-copy", text: "保存した字幕", affectedClipIds: ["normal"] };
const before = { id: "normal", title: "元のタイトル", hookText: "フック", hookDurationSeconds: 3,
  hookSceneStart: 759.08, hookSceneEnd: 761.66, start: 659.16, end: 927.46, confirmed: true,
  segmentIds: [row.id], titleStyle: null, hookStyle: null, subtitleStyle: null,
  titleCandidates: [{ id: "suggestion_1", title: "投稿タイトル", evidenceSegmentIds: [row.id] }],
  descriptionEvidenceSegmentIds: [row.id] } as SubtitleReviewClip;
const after = { ...before, segmentIds: [fork.id], titleCandidates: before.titleCandidates!.map(c => ({ ...c, evidenceSegmentIds: [fork.id] })),
  descriptionEvidenceSegmentIds: [fork.id] };
const document = { clips: [after], segments: [row, fork] } as SubtitleReviewDocument;
const base = contentDraftForClip(before), saved = contentDraftForClip(after);
assert.ok(isClipContentDirty(after, { normal: base }), "real COW metadata reproduces phantom unsaved content after caption HTTP 200");
const rebased = remapDraftEvidence(rebaseUnchangedContent(base, base, saved), document, after);
assert.equal(isClipContentDirty(after, { normal: rebased }), false);
// Recover an already persisted stale reference without discarding a real edit.
const manual = { ...base, title: "編集中のタイトル", titleCandidates: [{ ...base.titleCandidates[0], reason: "手で直した理由" }] };
const recovered = remapDraftEvidence(manual, document, after);
assert.equal(recovered.title, manual.title);
assert.equal(recovered.titleCandidates[0].reason, "手で直した理由");
assert.deepEqual(recovered.titleCandidates[0].evidenceSegmentIds, [fork.id]);
assert.deepEqual(recovered.descriptionEvidenceSegmentIds, [fork.id]);
const duplicate = { ...fork, id: "ambiguous" };
assert.deepEqual(remapDraftEvidence(base, { ...document, segments: [row, fork, duplicate] }, { ...after, segmentIds: [fork.id, duplicate.id] })
  .descriptionEvidenceSegmentIds, [row.id], "ambiguous structure changes cannot silently select evidence");

class Video {
  private time = 0;
  seeks = 0;
  pauses = 0;
  paused = false;
  get currentTime() { return this.time; }
  set currentTime(value: number) { this.seeks++; this.time = value; }
  pause() { this.pauses++; this.paused = true; }
  play() { this.paused = false; return Promise.resolve(); }
}
const video = new Video();
const range = { start: 659.16, end: 927.46, hookStart: 759.08, hookEnd: 761.66, mediaStart: 659.16, mediaOffset: 0 };
const playback = draftPlaybackClock(video as unknown as HTMLVideoElement, range);
playback.seek(80);
const physicalTime = video.currentTime, seeks = video.seeks;
playback.updateRange({ ...range, hookStart: 784.26, hookEnd: 787.26 });
assert.equal(video.currentTime, physicalTime, "a background hook decision keeps the source position in the body");
assert.equal(video.seeks, seeks, "even seeking to the same native timestamp can interrupt the browser");
assert.equal(video.pauses, 0);
assert.equal(video.paused, false);
assert.ok(Math.abs(playback.clock.currentTime - 80.42) < 0.001);
playback.seek(1);
playback.updateRange({ ...range, hookStart: 800, hookEnd: 802 });
assert.ok(Math.abs(video.currentTime - (801 - range.start)) < 0.001, "a hook currently being watched follows its changed source");
assert.equal(video.paused, false);

const bodyOnly = { ...after, livePreviewVideoUrl: "/body.mp4", livePreviewSpecHash: "body", livePreviewHookDurationSeconds: 0 };
const original = livePlaybackSource(bodyOnly, document);
assert.equal(original.mediaOffset, 0);
assert.deepEqual(livePlaybackSource({ ...bodyOnly, hookSceneStart: 800, hookSceneEnd: 803 }, document), original);
const legacy = { ...bodyOnly, livePreviewHookDurationSeconds: undefined };
assert.ok(Math.abs(livePreviewReference(legacy, document).hookDuration - 2.58) < 0.001, "historical media still includes its encoded hook");
const changedRange = livePlaybackSource({ ...bodyOnly, start: 660, livePreviewVideoUrl: null },
  { ...document, sourceVideoUrl: "/source" }, livePreviewReference(bodyOnly, document));
assert.equal(changedRange.url, "/source");
assert.equal(changedRange.version, "", "the player key must identify the actual fallback media, not the retained old range");
for (const state of ["awaiting_review", "render_queued", "rendering"] as const) {
  assert.equal(editingPreviewAvailable({ ...document, sourceVideoUrl: "/source", subtitleOnlyAuto: true, state }, after), true,
    "a confirmed caption edit must not unmount the editing player as background rendering starts");
}
assert.equal(editingPreviewAvailable({ ...document, sourceVideoUrl: "/source", subtitleOnlyAuto: true, state: "completed" }, after), false,
  "completed output remains the exact/final viewing mode");
assert.equal(editingPreviewAvailable({ ...document, sourceVideoUrl: "/source", subtitleOnlyAuto: false, state: "rendering" }, after), false,
  "legacy/manual review flow is unchanged");
console.log("Subtitle save consistency: COW content rebase, persisted evidence recovery, real drafts and uninterrupted virtual playback passed");
