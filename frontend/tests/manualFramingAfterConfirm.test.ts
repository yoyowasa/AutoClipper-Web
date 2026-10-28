import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { canEditManualFraming } from "../lib/subtitleReview/manualFraming";
import { ReviewShortFraming } from "../components/subtitleReview/ReviewStyleFraming";
import { useClipContentDraft as createContentActions } from "../lib/subtitleReview/hooks/useClipContentDraft";
import type { SubtitleReviewClip, SubtitleReviewDocument } from "../lib/types";
import type { SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";

Object.assign(globalThis, { React });
const clip = { id: "short", type: "short", start: 10, end: 60, confirmed: false,
  automaticDecisionState: "idle", framingOffsetX: 0, framingOffsetY: 0, framingZoom: 1 } as SubtitleReviewClip;
const review = { jobId: "test", subtitleOnlyAuto: true, state: "awaiting_review", clips: [clip] } as SubtitleReviewDocument;
const framing = { framingOffsetX: 10, framingOffsetY: 0, framingZoom: 1.1 };
const context = { jobId: "test", review, selectedClip: clip, selectedShortFramingDraft: framing,
  isEditable: false, hasReviewMutationInFlight: false,
  changeSelectedShortFraming: () => null, saveSelectedShortFraming: async () => true } as unknown as SubtitleReviewViewContext;
for (const state of ["idle", "queued", "generating", "failed", "ready"] as const) {
  clip.automaticDecisionState = state;
  assert.equal(canEditManualFraming(review, clip), false, "unconfirmed clips cannot edit framing");
  assert.equal(renderToStaticMarkup(React.createElement(ReviewShortFraming, { context })), "");
}
clip.confirmed = true;
clip.automaticDecisionState = "generating";
assert.equal(canEditManualFraming(review, clip), false);
clip.automaticDecisionState = "ready";
assert.equal(canEditManualFraming(review, clip), true);
assert.match(renderToStaticMarkup(React.createElement(ReviewShortFraming, { context })), /画角を見ながら調整/);
assert.doesNotMatch(renderToStaticMarkup(React.createElement(ReviewShortFraming, { context })), /自動に戻す/);
clip.manualDecisionFields = ["framing"];
assert.match(renderToStaticMarkup(React.createElement(ReviewShortFraming, { context })), /自動に戻す/);
review.state = "completed";
assert.equal(canEditManualFraming(review, clip), true);
review.state = "rendering";
assert.equal(canEditManualFraming(review, clip), false);
review.subtitleOnlyAuto = false;
clip.confirmed = false;
assert.equal(canEditManualFraming(review, clip), true, "legacy/manual editing eligibility stays unchanged");

async function checkSave() {
  review.subtitleOnlyAuto = true;
  review.state = "awaiting_review";
  const requests: unknown[] = [];
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : null });
    return new Response(JSON.stringify(review), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  const saved: unknown[] = [];
  Object.assign(context, { setShortFramingDrafts: () => {}, setShowSavedPreview: () => {}, setError: () => {},
    setSavingShortFramingClipId: () => {}, beginReviewMutation: () => 1, endReviewMutation: () => {},
    setReview: (value: unknown) => saved.push(value), locallyUpdatedReviewRef: { current: null } });
  try {
    const actions = createContentActions(context);
    assert.equal(await actions.saveSelectedShortFraming(clip.id, framing), false);
    assert.equal(await actions.resetSelectedShortFraming(clip.id), false);
    assert.equal(requests.length, 0);
    clip.confirmed = true;
    assert.equal(await actions.saveSelectedShortFraming(clip.id, framing), true);
    assert.deepEqual(requests, [{ url: "http://localhost:8000/api/jobs/test/subtitle-review/clips/short/framing",
      method: "PATCH", body: framing }]);
    assert.equal(saved.length, 1);
    assert.equal(await actions.resetSelectedShortFraming(clip.id), true);
    assert.deepEqual(requests[1], { url: "http://localhost:8000/api/jobs/test/subtitle-review/clips/short/framing/reset",
      method: "POST", body: null });
    assert.equal(saved.length, 2);
  } finally { globalThis.fetch = previousFetch; }
}
void checkSave().then(() => console.log("Manual framing: confirmation gate, automatic completion, legacy editing and targeted save passed"));
