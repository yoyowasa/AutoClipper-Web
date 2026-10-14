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
    id: "short-01", type: "short", title: "画面タイトル", publicationTitle: "投稿タイトル",
    hookText: "題材のフック", hookDurationSeconds: 3, hookSceneStart: null, hookSceneEnd: null,
    titleStyle: null, hookStyle: null, subtitleStyle: null, previewState: "queued"
  } as SubtitleReviewClip;
  const segment = { id: "seg-01", text: "保存された字幕" } as SubtitleReviewSegment;
  const review = { clips: [clip], segments: [segment] } as SubtitleReviewDocument;
  const error = state<string | null>(null);
  const drafts = state<Record<string, string>>({ "seg-01": "編集中の字幕", "other-clip": "残す字幕" });
  const dirty = state(new Set(["seg-01", "other-clip"]));
  const savedReview = state<SubtitleReviewDocument | null>(review);
  const contentDrafts = state({ [clip.id]: contentDraftForClip(clip) });
  const destinations: string[] = [];
  const context = {
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

    // Hook scene updates remain blocked while subtitle edits are unsaved.
    const content = createContentActions(context);
    context.dirtySegmentIds = new Set(["seg-01"]);
    await content.saveHookScene(100, 103);
    assert.equal(calls.length, 3);
    context.dirtySegmentIds = new Set();
    await content.saveHookScene(100, 103);
    assert.deepEqual(calls[3].body, { start: 100, end: 103 });
    assert.equal(calls[3].path, "/api/jobs/job-test/subtitle-review/clips/short-01/hook-scene");

    // Bulk correction uses one batch request and only clears the submitted row's dirty flag.
    dirty.set(new Set(["seg-01", "other-clip"]));
    await createSubtitleActions(context).saveBulkCorrection([{ segmentId: "seg-01", before: "保存された字幕", text: "修正済み" }]);
    assert.equal(calls[4].path, "/api/jobs/job-test/subtitle-review/segments");
    assert.deepEqual(calls[4].body, { segments: [{ segmentId: "seg-01", before: "保存された字幕", text: "修正済み" }] });
    assert.deepEqual([...dirty.value], ["other-clip"]);

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
