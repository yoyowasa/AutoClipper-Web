import assert from "node:assert/strict";
import type { Dispatch, SetStateAction } from "react";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import type { SubtitleReviewContext } from "../lib/subtitleReview/hooks/context";
// These action factories contain no React hooks. Exercise them with an isolated
// render snapshot and mocked HTTP, without loading a live job or changing storage.
import { useReviewConfirmation as createConfirmation } from "../lib/subtitleReview/hooks/useReviewConfirmation";
import { useReviewMutations as createMutations } from "../lib/subtitleReview/hooks/useReviewMutations";
import { useClipContentDraft as createContentActions } from "../lib/subtitleReview/hooks/useClipContentDraft";
import { useSubtitleEditing as createSubtitleActions } from "../lib/subtitleReview/hooks/useSubtitleEditing";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../lib/types";

function state<T>(initial: T): { value: T; set: Dispatch<SetStateAction<T>> } {
  const cell = { value: initial, set: (() => {}) as Dispatch<SetStateAction<T>> };
  cell.set = (next) => { cell.value = typeof next === "function" ? (next as (old: T) => T)(cell.value) : next; };
  return cell;
}

async function main() {
  const clip = {
    id: "short-01", type: "short", start: 100, end: 175, segmentIds: ["seg-01"], title: "画面タイトル", publicationTitle: "投稿タイトル",
    hookText: "題材のフック", hookDurationSeconds: 3, hookSceneStart: null, hookSceneEnd: null,
    titleStyle: null, hookStyle: null, subtitleStyle: null, previewState: "queued"
  } as SubtitleReviewClip;
  const segment = { id: "seg-01", text: "保存された字幕" } as SubtitleReviewSegment;
  const review = { jobId: "job-test", shortMaxDuration: 75, clips: [clip], segments: [segment] } as SubtitleReviewDocument;
  const error = state<string | null>(null);
  const drafts = state<Record<string, string>>({ "seg-01": "編集中の字幕", "other-clip": "残す字幕" });
  const dirty = state(new Set(["seg-01", "other-clip"]));
  const savedReview = state<SubtitleReviewDocument | null>(review);
  const contentDrafts = state({ [clip.id]: contentDraftForClip(clip) });
  const framingDrafts = state({});
  const destinations: string[] = [];
  const context = {
    locallyUpdatedReviewRef: { current: null }, setShortFramingDrafts: framingDrafts.set,
    jobId: "job-test", review, selectedClip: clip, selectedClipContentDraft: { ...contentDraftForClip(clip), publicationTitle: "  投稿タイトル  " },
    selectedSegments: [segment], selectedShortFramingDirty: false, selectedHookDurationIsValid: true,
    hasDirtyShortFraming: false, hasDirtyClipContent: false, isSavingShortBannerSettings: false,
    isEditable: true, allPreviewsReady: false, dirtySegmentIds: dirty.value, drafts: drafts.value,
    reviewMutationCountRef: { current: 0 }, reviewRequestGenerationRef: { current: 0 }, videoRef: { current: null },
    setError: error.set, setDrafts: drafts.set, setDirtySegmentIds: dirty.set, setReview: savedReview.set,
    setClipContentDrafts: contentDrafts.set, setConfirmingClipId: () => {}, setIsFinalizing: () => {},
    setIsReopeningBoundaries: () => {}, setIsUpdatingHookScene: () => {}, setIsSavingBulkCorrection: () => {},
    setShowSavedPreview: () => {}, router: { push: (path: string) => { destinations.push(path); } }
  } as unknown as SubtitleReviewContext;
  Object.assign(context, createMutations(context));
  const confirmation = createConfirmation(context);
  const calls: { path: string; method: string; body: Record<string, unknown> | null }[] = [];
  let failRequest = false;
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    calls.push({ path: new URL(String(input)).pathname, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    return new Response(JSON.stringify(failRequest ? { detail: "フック区間が不正です" } : review), {
      status: failRequest ? 422 : 200, headers: { "Content-Type": "application/json" }
    });
  };
  try {
    // OK saves the selected clip and dirty subtitle rows even before its preview finishes.
    await confirmation.confirmSelectedClip();
    assert.equal(calls[0].path, "/api/jobs/job-test/subtitle-review/clips/short-01/apply");
    assert.equal(calls[0].method, "POST");
    assert.equal(calls[0].body?.publicationTitle, "投稿タイトル");
    assert.deepEqual(calls[0].body?.segments, [{ segmentId: "seg-01", text: "編集中の字幕" }]);
    assert.deepEqual([...dirty.value], ["other-clip"], "another clip's unsaved subtitles remain dirty");
    assert.equal(drafts.value["other-clip"], "残す字幕");
    assert.equal(context.reviewMutationCountRef.current, 0);

    // The same guards still prevent rendering and boundary navigation with unsaved work.
    await confirmation.startRendering();
    await confirmation.returnToBoundaryEditor();
    assert.equal(calls.length, 1);
    assert.deepEqual(destinations, []);
    context.dirtySegmentIds = new Set();
    await confirmation.startRendering();
    assert.match(error.value ?? "", /完成表示プレビュー/);
    assert.equal(calls.length, 1, "finalize still waits for every preview");
    context.allPreviewsReady = true;
    await confirmation.startRendering();
    await confirmation.returnToBoundaryEditor();
    assert.deepEqual(calls.slice(1).map((call) => call.path), [
      "/api/jobs/job-test/subtitle-review/finalize", "/api/jobs/job-test/subtitle-review/reopen-clip-plan"
    ]);
    assert.deepEqual(destinations, ["/jobs/job-test", "/jobs/job-test/clips"]);

    // Hook/frames and bulk text edits remain local, even with existing dirty rows.
    const content = createContentActions(context);
    Object.assign(context, content);
    context.dirtySegmentIds = new Set(["seg-01"]);
    await content.saveHookScene(100, 103);
    await content.saveSelectedShortFraming(clip.id, { framingOffsetX: 20, framingOffsetY: 0, framingZoom: 1.2, shortLayout: "center_crop" });
    assert.equal(calls.length, 3, "drafting never sends hook-scene/framing requests");
    assert.equal(contentDrafts.value[clip.id].hookSceneEnd, 103);
    dirty.set(new Set(["seg-01", "other-clip"]));
    await createSubtitleActions(context).saveBulkCorrection([{ segmentId: "seg-01", before: "保存された字幕", text: "修正済み" }]);
    assert.equal(calls.length, 3, "batch text changes are also drafts");
    context.selectedClipContentDraft = { ...contentDrafts.value[clip.id], title: "新しい画面タイトル" };
    context.selectedShortFramingDirty = true;
    context.selectedShortFramingDraft = { framingOffsetX: 20, framingOffsetY: 0, framingZoom: 1.2, shortLayout: "center_crop" };
    context.drafts = drafts.value;
    context.dirtySegmentIds = dirty.value;
    await confirmation.confirmSelectedClip();
    assert.equal(calls.length, 4, "one apply saves all of the selected clip's edits");
    assert.equal(calls[3].path, "/api/jobs/job-test/subtitle-review/clips/short-01/apply");
    assert.equal(calls[3].body?.title, "新しい画面タイトル");
    assert.deepEqual(calls[3].body?.segments, [{ segmentId: "seg-01", text: "修正済み" }]);
    assert.equal(calls[3].body?.hookSceneStart, 100);
    assert.equal(calls[3].body?.hookSceneEnd, 103);
    assert.deepEqual(calls[3].body?.framing, context.selectedShortFramingDraft);
    assert.deepEqual([...dirty.value], ["other-clip"]);
    assert.deepEqual(framingDrafts.value, {}, "accepted framing drafts are discarded");
    context.selectedClipContentDraft.hookSceneEnd = 103.1;
    await confirmation.confirmSelectedClip();
    assert.equal(calls.length, 4, "invalid hook duration never reaches apply");
    assert.match(error.value ?? "", /0.5〜3秒/);
    context.selectedClipContentDraft.hookSceneEnd = 103;

    failRequest = true;
    await confirmation.confirmSelectedClip();
    assert.match(error.value ?? "", /フック区間が不正/);
    assert.equal(context.reviewMutationCountRef.current, 0, "failed saves release the mutation guard");
  } finally {
    globalThis.fetch = previousFetch;
  }
  console.log("Subtitle review actions: OK payload, preview/dirty guards, navigation, hook/batch saves and 422 recovery passed");
}

main().catch((error: unknown) => { console.error(error); process.exitCode = 1; });
