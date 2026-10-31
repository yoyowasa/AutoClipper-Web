import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewSubtitleSegments } from "../components/subtitleReview/ReviewSubtitleSegments";
import type { SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";
Object.assign(globalThis, { React });
import type { Dispatch, SetStateAction } from "react";
import { useSubtitleEditing as actions } from "../lib/subtitleReview/hooks/useSubtitleEditing";
import { subtitleStructureSources } from "../lib/subtitleStructureDrafts";
import { subtitleEditTargets, segmentDraftKey } from "../lib/subtitleReview/sharedSegments";
import { reviewDraftFingerprint, rebaseUnchangedContent } from "../lib/subtitleReview/draftStorage";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import type { SubtitleReviewContext } from "../lib/subtitleReview/hooks/context";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../lib/types";

function state<T>(value: T) {
  const cell = { value, set: (() => {}) as Dispatch<SetStateAction<T>> };
  cell.set = next => { cell.value = typeof next === "function" ? (next as (old: T) => T)(cell.value) : next; };
  return cell;
}

async function main() {
  const clip = { id: "short", type: "short", start: 0, end: 70, title: "元のタイトル", confirmed: false,
    segmentIds: ["s1", "s2"], subtitleStyles: [] } as unknown as SubtitleReviewClip;
  const other = { ...clip, id: "normal", confirmed: true };
  const segments = [{ id: "s1", start: 1, end: 3, text: "元の字幕", affectedClipIds: ["short", "normal"] },
    { id: "s2", start: 5, end: 6, text: "後の字幕", affectedClipIds: ["short"] }] as SubtitleReviewSegment[];
  const review = { jobId: "job-238", state: "awaiting_review", subtitleOnlyAuto: true, clips: [other, clip], segments } as SubtitleReviewDocument;
  const error = state<string | null>(null), dirty = state(new Set(["s1", "s2", "normal::s1"]));
  const drafts = state<Record<string, string>>({ s1: "未保存の手直し", s2: "離れた行の手直し", "normal::s1": "別clipの下書き" });
  const persisted = state(review), content = state({ [clip.id]: contentDraftForClip(clip) });
  const context = { review, selectedClip: clip, selectedSegments: segments, isEditable: true, isSubtitleEditable: true,
    jobId: review.jobId, drafts: drafts.value, rawDrafts: drafts.value, dirtySegmentIds: dirty.value, rawDirtySegmentIds: dirty.value,
    setDrafts: drafts.set, setDirtySegmentIds: dirty.set, setReview: persisted.set, setClipContentDrafts: content.set,
    locallyUpdatedReviewRef: { current: null }, subtitleListRef: { current: null }, segmentRowRefs: { current: {} },
    beginReviewMutation: () => 1, isCurrentReviewMutation: () => true, endReviewMutation: () => {},
    setIsSavingStructure: () => {}, setIsSavingBulkCorrection: () => {}, setShowSavedPreview: () => {},
    setError: error.set, setStyledSegmentId: () => {}, setSegmentCursor: () => {}, setBulkCorrectionSelection: () => {},
    pausedSubtitleDraft: { clipId: clip.id, start: 2, end: 2.5, text: "追加した字幕" }, setPausedSubtitleDraft: () => {},
    hookSceneDuration: 0, hookSuppressionEnd: 0,
  } as unknown as SubtitleReviewContext;
  const oldFetch = globalThis.fetch;
  const calls: { url: string; body: Record<string, unknown> }[] = [];
  Object.assign(globalThis, { requestAnimationFrame: (callback: () => void) => callback() });
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), body: JSON.parse(String(init?.body)) });
    const body = JSON.parse(String(init?.body));
    const response = init?.method === "PATCH" ? { ...review, segments: review.segments.map(segment => ({ ...segment,
      text: body.segments.find((item: { segmentId: string; text: string }) => item.segmentId === segment.id)?.text ?? segment.text
    })) } : review;
    return new Response(JSON.stringify(response), { status: 200 });
  };
  try {
    Object.assign(context, actions(context));
    await context.savePausedSubtitleDraft();
    assert.equal(error.value, null);
    assert.equal(calls.length, 1);
    assert.match(calls[0].url, /segment-structure$/);
    assert.equal(calls[0].body.action, "insert_at_time");
    assert.deepEqual(calls[0].body.edits, [
      { segmentId: "s1", before: "元の字幕", text: "未保存の手直し" },
      { segmentId: "s2", before: "後の字幕", text: "離れた行の手直し" }
    ]);
    assert.equal(clip.confirmed, false);
    assert.equal(drafts.value["normal::s1"], "別clipの下書き");
    assert.deepEqual([...dirty.value], ["normal::s1"]);
    assert.deepEqual(subtitleStructureSources(segments, {
      action: "insert_at_time", segments: [], clipId: clip.id, start: 2, end: 2.5, text: "追加"
    }).map(row => row.id), ["s1"], "nonempty overlap is remapped too");

    clip.confirmed = true;
    const another = { ...clip, id: "unconfirmed", confirmed: false };
    review.clips.push(another);
    assert.deepEqual(subtitleEditTargets(review, [{ affectedClipIds: [clip.id, another.id] }], clip.id).map(item => item.id), [clip.id]);
    const key = segmentDraftKey(clip, "s1");
    context.rawDirtySegmentIds = new Set([key, "normal::s1"]);
    context.rawDrafts = { [key]: "確定後の訂正", "normal::s1": "別clipの下書き" };
    dirty.set(new Set(context.rawDirtySegmentIds)); drafts.set({ ...context.rawDrafts });
    context.isEditable = false;
    await actions(context).saveConfirmedSubtitles();
    assert.equal(calls.length, 2);
    assert.match(calls[1].url, /subtitle-review\/segments$/);
    assert.equal(calls[1].body.clipId, clip.id);
    assert.deepEqual(calls[1].body.segments, [{ segmentId: "s1", before: "元の字幕", text: "確定後の訂正" }]);
    assert.deepEqual([...dirty.value], ["normal::s1"]);
    assert.ok(clip.confirmed, "neither unconfirm nor apply was called");
    const screenContext = { ...context, review, selectedClipContentDraft: contentDraftForClip(clip),
      clipDuration: 70, currentSourceTime: () => 2, rawDrafts: {}, dirtySegmentIds: new Set<string>() } as SubtitleReviewViewContext;
    const screen = renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context: screenContext, showStyleControls: false }));
    assert.match(screen, /<textarea(?=[^>]*aria-label="追加する字幕")(?![^>]*\sdisabled=)[^>]*>/);
    assert.match(screen, /<button(?![^>]*\sdisabled=)[^>]*>字幕を追加<\/button>/);
    assert.match(screen, /確定の解除は不要/);
    assert.doesNotMatch(screen, /次の未確定clipにも反映/);
    screenContext.isSubtitleEditable = false;
    screenContext.isSubtitleTextEditable = true;
    screenContext.hasReviewMutationInFlight = true;
    const savingScreen = renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context: screenContext, showStyleControls: false }));
    assert.match(savingScreen, /<textarea(?=[^>]*aria-label="字幕 0:01.0")(?![^>]*\sdisabled=)[^>]*>/,
      "a pending caption save must not disable the typing field");
    screenContext.isSubtitleEditable = true;
    screenContext.hasReviewMutationInFlight = false;
    clip.confirmed = false;
    screenContext.isEditable = true;
    const shared = renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context: screenContext, showStyleControls: false }));
    assert.match(shared, /次の未確定clipにも反映/);
    clip.confirmed = true;
    const fingerprint = reviewDraftFingerprint(review, clip);
    const before = contentDraftForClip(clip);
    clip.title = "背景で更新されたタイトル";
    const after = contentDraftForClip(clip);
    assert.equal(reviewDraftFingerprint(review, clip), fingerprint, "automatic metadata does not erase caption drafts");
    const rebased = rebaseUnchangedContent({ ...before, youtubeDescription: "手入力を残す" }, before, after);
    assert.equal(rebased.title, after.title);
    assert.equal(rebased.youtubeDescription, "手入力を残す");
    segments[0].text = "他の保存操作";
    assert.notEqual(reviewDraftFingerprint(review, clip), fingerprint, "server caption changes still invalidate stale drafts");
  } finally { globalThis.fetch = oldFetch; }
  console.log("Anytime subtitles: atomic overlap/drafts, confirmed scoped autosave, independent drafts and background content rebasing passed");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
