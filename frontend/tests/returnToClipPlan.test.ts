import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { clearJobReviewDrafts, reviewDraftKey, reviewDraftFingerprint } from "../lib/subtitleReview/draftStorage";
import { returnToClipPlanMessage } from "../lib/subtitleReview/returnToClipPlan";
import { useReviewConfirmation as createConfirmation } from "../lib/subtitleReview/hooks/useReviewConfirmation";
import { ReviewReturnToClipPlanButton } from "../components/subtitleReview/ReviewActions";
import type { SubtitleReviewContext, SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";
import type { SubtitleReviewDocument } from "../lib/types";
import { approveClipPlan } from "../lib/api";

async function main() {
  const entries = new Map([[reviewDraftKey("job", "clip"), "draft"], [reviewDraftKey("job", "removed"), "draft"],
    [reviewDraftKey("job-other", "clip"), "keep"], ["other-preferences", "keep"]]);
  const storage = { get length() { return entries.size; }, key: (index: number) => [...entries.keys()][index] ?? null,
    removeItem: (key: string) => { entries.delete(key); } } as Storage;
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const previousFetch = globalThis.fetch;
  let confirmed = false, requestStatus = 200, requests = 0, mutations = 0;
  let prompt = "", error: string | null = null, documentState: unknown, navigation = "", draftCleared = false;
  Object.defineProperty(globalThis, "window", { configurable: true, value: { localStorage: storage,
    confirm: (message: string) => { prompt = message; return confirmed; } } });
  globalThis.fetch = async (url, init) => {
    requests++;
    assert.match(String(url), /\/api\/jobs\/job\/subtitle-review\/return-to-clip-plan$/);
    assert.equal(init?.method, "POST");
    return new Response(JSON.stringify(requestStatus === 200 ? { status: "awaiting_clip_review" } : { detail: "書き出し中は戻れません。" }),
      { status: requestStatus, headers: { "Content-Type": "application/json" } });
  };
  const review = { jobId: "job", editedSegmentCount: 0, hasSavedReviewChanges: false, clips: [], segments: [] } as unknown as SubtitleReviewDocument;
  documentState = review;
  const context = { review, isEditable: true, hasReviewMutationInFlight: false, jobId: "job",
    dirtySegmentIds: new Set(["dirty"]), hasDirtyClipContent: true, hasDirtyShortFraming: true,
    beginReviewMutation: () => { mutations++; }, endReviewMutation: () => { mutations--; },
    setIsReturningToClipPlan: () => {}, setError: (value: string | null) => { error = value; },
    setReview: (value: unknown) => { documentState = value; }, setDrafts: () => { draftCleared = true; },
    setDirtySegmentIds: () => {}, setClipContentDrafts: () => {}, setShortFramingDrafts: () => {},
    router: { push: (value: string) => { navigation = value; } } } as unknown as SubtitleReviewContext;
  const action = createConfirmation(context);
  try {
    await action.returnToClipPlan();
    assert.match(prompt, /まだ修正を保存していません.*下書きは破棄/);
    assert.equal(requests, 0); // Cancel keeps every draft and makes no mutation.
    assert.equal(entries.size, 4);
    confirmed = true;
    requestStatus = 409;
    await action.returnToClipPlan();
    assert.equal(error, "書き出し中は戻れません。");
    assert.equal(documentState, review);
    assert.equal(entries.size, 4);
    assert.equal(mutations, 0);
    requestStatus = 200;
    await action.returnToClipPlan();
    assert.equal(documentState, null);
    assert.equal(draftCleared, true);
    assert.equal(navigation, "/jobs/job/clips");
    assert.deepEqual([...entries.keys()], [reviewDraftKey("job-other", "clip"), "other-preferences"]);
    assert.equal(mutations, 0);
    context.review = { ...review, returnToClipPlanAllowed: false };
    const before = requests;
    await action.returnToClipPlan();
    assert.equal(requests, before);
    assert.match(error!, /手動ワークフロー/);
    assert.match(returnToClipPlanMessage({ ...review, hasSavedReviewChanges: true }, false), /修正.*すべて破棄/);
    assert.match(returnToClipPlanMessage({ ...review, hasSavedReviewChanges: undefined }, false), /修正.*すべて破棄/);
    const html = renderToStaticMarkup(createElement(ReviewReturnToClipPlanButton,
      { context: context as SubtitleReviewViewContext }));
    assert.match(html, /切り抜き確認に戻る/);
    assert.match(html, /disabled/);
    assert.match(html, /手動ワークフローは対象外/);
    clearJobReviewDrafts("job", { get length() { throw new Error("disabled"); } } as unknown as Storage);
    const clip = { id: "clip", segmentIds: [] } as unknown as SubtitleReviewDocument["clips"][number];
    assert.notEqual(reviewDraftFingerprint(review, clip), reviewDraftFingerprint({ ...review, previewGeneration: "new" }, clip));
    globalThis.fetch = async (url, init) => {
      assert.match(String(url), /\/clip-plan\/approve$/);
      assert.deepEqual(JSON.parse(String(init?.body)), { keptClipIds: ["clip"] });
      return new Response(JSON.stringify({ status: "awaiting_subtitle_review" }));
    };
    await approveClipPlan("job", { keptClipIds: ["clip"] });
  } finally {
    globalThis.fetch = previousFetch;
    if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
    else Reflect.deleteProperty(globalThis, "window");
  }
  console.log("Return to clip plan: confirmation/cancel, single POST, errors, all job drafts and manual exclusion passed");
}
void main();
