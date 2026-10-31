import assert from "node:assert/strict";
import { nextCaptionSave, reconcileCaptionSave, captionRowKey } from "../lib/subtitleReview/captionAutosave";
import { useSubtitleEditing as actions } from "../lib/subtitleReview/hooks/useSubtitleEditing";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../lib/types";
import type { SubtitleReviewContext } from "../lib/subtitleReview/hooks/context";

const clip = { id: "short", confirmed: true, segmentIds: ["shared", "second"] } as SubtitleReviewClip;
const other = { ...clip, id: "normal" };
const row = { id: "shared", index: 1, start: 10, end: 12, text: "保存前", affectedClipIds: [clip.id, other.id] } as SubtitleReviewSegment;
const second = { ...row, id: "second", index: 2, start: 12, end: 14, text: "次の行", affectedClipIds: [clip.id] };
const before = { jobId: "job-typing", subtitleOnlyAuto: true, clips: [clip, other], segments: [row, second] } as SubtitleReviewDocument;
const dirty = new Set(["short::shared"]);
for (let position = 0; position < "日本語を変換しながら文章を途切れずに入力する。".length; position++) {
  assert.equal(nextCaptionSave(before, dirty, { clipId: clip.id, composing: false }), null, "no request while textarea owns focus");
  assert.equal(nextCaptionSave(before, dirty, { clipId: null, composing: true }), null, "IME owns its composition, even across focus events");
}
assert.equal(nextCaptionSave(before, dirty, { clipId: null, composing: false })?.id, clip.id);
assert.equal(nextCaptionSave(before, dirty, { clipId: null, composing: false }, clip.id), null, "insertion saves drafts atomically");
assert.equal(nextCaptionSave({ ...before, subtitleOnlyAuto: false }, dirty, { clipId: null, composing: false }), null);
const fork = { ...row, id: "short-copy", text: "送信した文", affectedClipIds: [clip.id] };
const after = { ...before, clips: [{ ...clip, segmentIds: [fork.id, second.id] }, other], segments: [row, fork, second] };
const sent = [{ segmentId: row.id, text: fork.text }];
const newer = { "short::shared": "送信した文にさらに続きを入力中", "normal::shared": "別clipの下書き", "short::second": "次の行の下書き" };
let result = reconcileCaptionSave(before, after, clip.id, sent, newer, new Set(Object.keys(newer)));
assert.equal(result.drafts["short::short-copy"], newer["short::shared"]);
assert.equal(result.drafts["normal::shared"], newer["normal::shared"]);
assert.equal(result.drafts["short::second"], newer["short::second"]);
assert.ok(result.dirty.has("short::short-copy"));
assert.ok(!result.dirty.has("short::shared"));
assert.equal(captionRowKey(clip.id, row), captionRowKey(clip.id, fork), "COW cannot unmount the input or cancel composition");
assert.notEqual(captionRowKey(clip.id, row), captionRowKey(clip.id, { ...fork, end: 11 }), "real structure edits replace the row");
result = reconcileCaptionSave(before, after, clip.id, sent, { "short::shared": "保存前" }, new Set());
assert.equal(result.drafts["short::short-copy"], "保存前", "undo made while HTTP was pending is still an unsaved change");
assert.ok(result.dirty.has("short::short-copy"));
result = reconcileCaptionSave(before, after, clip.id, sent, { "short::shared": "送信した文" }, dirty);
assert.deepEqual(result.drafts, {});
assert.equal(result.dirty.size, 0);

async function delayedResponse() {
  const refs = { drafts: { current: { "short::shared": "送信した文" } as Record<string, string> }, dirty: { current: new Set(dirty) } };
  const status: { saving: boolean; error: string | null; review: SubtitleReviewDocument } = { saving: false, error: null, review: before };
  let release: (value: Response) => void = () => {};
  const oldFetch = globalThis.fetch;
  globalThis.fetch = () => new Promise<Response>(resolve => { release = resolve; });
  const context = { jobId: before.jobId, review: before, selectedClip: clip, rawDrafts: refs.drafts.current, rawDirtySegmentIds: refs.dirty.current,
    subtitleDraftsRef: refs.drafts, subtitleDirtyRef: refs.dirty, beginReviewMutation: () => 1, isCurrentReviewMutation: () => true,
    endReviewMutation: () => {}, reviewMutationCountRef: { current: 0 }, locallyUpdatedReviewRef: { current: null },
    setIsSavingConfirmedSubtitles: (value: boolean) => { status.saving = value; }, setShowSavedPreview: () => {},
    setError: (value: string | null) => { status.error = value; },
    setDrafts: (value: Record<string, string>) => { refs.drafts.current = value; },
    setDirtySegmentIds: (value: Set<string>) => { refs.dirty.current = value; },
    setReview: (value: SubtitleReviewDocument) => { status.review = value; },
  } as unknown as SubtitleReviewContext;
  try {
    const pending = actions(context).saveConfirmedSubtitles();
    assert.ok(status.saving);
    refs.drafts.current = { ...newer };
    refs.dirty.current = new Set(Object.keys(newer));
    release(new Response(JSON.stringify(after), { status: 200 }));
    await pending;
    assert.equal(status.error, null);
    assert.equal(status.saving, false);
    assert.equal(refs.drafts.current["short::short-copy"], newer["short::shared"]);
    assert.equal(status.review.clips[0].confirmed, true);
    assert.ok(refs.dirty.current.has("short::short-copy"));
  } finally { globalThis.fetch = oldFetch; }
  console.log("Caption typing: focus/IME gating, delayed replies, COW IDs, continued typing, undo and independent drafts passed");
}
void delayedResponse().catch(error => { console.error(error); process.exitCode = 1; });
