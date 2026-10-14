import assert from "node:assert/strict";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import { readReviewDraft, reviewDraftFingerprint, writeReviewDraft, reviewDraftKey, type StoredReviewDraft } from "../lib/subtitleReview/draftStorage";
import { livePlaybackSource, livePreviewReference } from "../lib/subtitleReview/livePlaybackSource";
import { draftPlaybackClock, sourceVideoForClock } from "../lib/subtitleReview/draftPlayback";
import type { SubtitleReviewClip, SubtitleReviewDocument } from "../lib/types";

const clip = { id: "clip", type: "short", title: "タイトル", publicationTitle: "投稿タイトル", start: 100, end: 175,
  confirmed: false, hookText: "", hookDurationSeconds: 3, hookSceneStart: null, hookSceneEnd: null,
  framingOffsetX: 0, framingOffsetY: 0, framingZoom: 1, titleStyle: null, hookStyle: null, subtitleStyle: null,
  segmentIds: ["segment"] } as SubtitleReviewClip;
const document = { renderRevision: 1, clips: [clip], segments: [{ id: "segment", start: 100, end: 105, text: "字幕" }] } as SubtitleReviewDocument;
const fingerprint = reviewDraftFingerprint(document, clip);
const values = new Map<string, string>();
const storage = { getItem: (key: string) => values.get(key) ?? null,
  setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
const draft: StoredReviewDraft = { version: 1, fingerprint,
  content: { ...contentDraftForClip(clip), title: "新しいタイトル", hookSceneStart: 100, hookSceneEnd: 103 },
  framing: { framingOffsetX: 20, framingOffsetY: 0, framingZoom: 1.2 }, segments: { segment: "編集中の字幕" } };
writeReviewDraft("job", clip.id, draft, storage);
assert.deepEqual(readReviewDraft("job", clip.id, fingerprint, storage), draft, "reload restores every part of a clip draft");
assert.equal(readReviewDraft("other-job", clip.id, fingerprint, storage), null);
assert.equal(readReviewDraft("job", "other-clip", fingerprint, storage), null);
assert.equal(reviewDraftFingerprint({ ...document, updatedAt: "new poll" }, { ...clip, previewState: "ready", previewSpecHash: "new hash" }), fingerprint,
  "preview completion must not discard a draft");
const changed = reviewDraftFingerprint(document, { ...clip, title: "サーバーの変更" });
assert.equal(readReviewDraft("job", clip.id, changed, storage), null, "external server edits invalidate the old draft");
assert.equal(values.size, 0);
writeReviewDraft("job", clip.id, draft, storage);
writeReviewDraft("job", clip.id, null, storage);
assert.equal(values.size, 0, "confirmed drafts are removed");
values.set(reviewDraftKey("job", clip.id), "invalid json");
assert.equal(readReviewDraft("job", clip.id, fingerprint, storage), null);
const unavailable = { getItem() { throw new Error("disabled"); }, setItem() { throw new Error("quota"); }, removeItem() { throw new Error("disabled"); } };
assert.equal(readReviewDraft("job", clip.id, fingerprint, unavailable), null);
assert.doesNotThrow(() => writeReviewDraft("job", clip.id, draft, unavailable));
assert.doesNotThrow(() => writeReviewDraft("job", clip.id, null, unavailable));

const events: string[] = [];
class VideoStub {
  currentTime = 0;
  paused = true;
  pause() { this.paused = true; events.push("pause"); }
  play() { this.paused = false; events.push("play"); return Promise.resolve(); }
}
const video = new VideoStub() as unknown as HTMLVideoElement;
const playback = draftPlaybackClock(video, { start: 100, end: 175, hookStart: 120, hookEnd: 123 });
playback.seek(0);
assert.equal(video.currentTime, 120);
assert.equal(playback.clock.duration, 78);
assert.equal(playback.clock.currentTime, 0);
playback.clock.currentTime = 2;
assert.equal(video.currentTime, 122);
video.currentTime = 123;
playback.advance();
assert.equal(video.currentTime, 100, "the drafted hook is followed by the original body");
assert.equal(playback.clock.currentTime, 3);
playback.clock.currentTime = 12;
assert.equal(video.currentTime, 109, "clip-relative seeks map to source time");
void playback.clock.play();
assert.equal(video.paused, false, "browser methods remain bound to the native element");
video.currentTime = 176;
playback.advance();
assert.equal(video.currentTime, 175);
assert.equal(video.paused, true);
assert.equal(playback.clock.currentTime, 78);
const pausedCount = events.length;
playback.advance();
assert.equal(events.length, pausedCount, "the completed body does not repeatedly pause/seek");
assert.equal(sourceVideoForClock(playback.clock), video, "canvas drawing uses a native element, not a proxy");
const noHook = draftPlaybackClock(video, { start: 100, end: 175, hookStart: null, hookEnd: null });
noHook.seek(5);
assert.equal(video.currentTime, 105);
assert.equal(noHook.clock.duration, 75);
console.log("Review drafts: storage restoration/isolation/invalidation/failures and immediate hook/body playback passed");

const encodedClip = { ...clip, livePreviewVideoUrl: "/bare.mp4", livePreviewSpecHash: "bare", hookSceneStart: 110, hookSceneEnd: 112 };
const base = livePlaybackSource(encodedClip, document);
assert.deepEqual([base.url, base.mediaStart, base.mediaOffset], ["/bare.mp4", 100, 2]);
const retained = livePreviewReference(encodedClip, document);
const pending = { ...encodedClip, hookSceneStart: 120, hookSceneEnd: 123, livePreviewVideoUrl: null };
assert.deepEqual(livePlaybackSource(pending, document, retained), base, "reuse the old bare media's own timing while a new preview is pending");
const encodedPlayback = draftPlaybackClock(video, { start: 100, end: 175, hookStart: 120, hookEnd: 123, mediaStart: 100, mediaOffset: 2 });
encodedPlayback.seek(0);
assert.equal(video.currentTime, 22, "a new hook is taken from the encoded bare body's timeline");
video.currentTime = 25;
encodedPlayback.advance();
assert.equal(video.currentTime, 2);
encodedPlayback.clock.currentTime = 12;
assert.equal(video.currentTime, 11);
assert.equal(encodedPlayback.clock.currentTime, 12);
