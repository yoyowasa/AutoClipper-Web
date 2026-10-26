import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AutomaticReviewStatus } from "../components/subtitleReview/AutomaticReviewStatus";
import { SubtitleReviewScreen } from "../components/subtitleReview/SubtitleReviewScreen";
import { ReviewRenderControls } from "../components/subtitleReview/ReviewActions";
import { automaticReviewStopReasons, loadReviewWithRenderStatus, reviewNeedsPolling } from "../lib/subtitleReview/automaticStatus";
import type { SubtitleReviewClip, SubtitleReviewDocument } from "../lib/types";
import type { SubtitleReviewContext, SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";

Object.assign(globalThis, { React });
const normal = { id: "cand_normal_001", type: "normal", start: 100, end: 200, confirmed: true,
  segmentIds: ["seg_001"], automaticDecisionState: "ready", previewState: "ready" } as SubtitleReviewClip;
const short = { ...normal, id: "cand_short_002", type: "short", start: 300, end: 350,
  segmentIds: [], automaticDecisionState: "generating", previewState: "queued" } as SubtitleReviewClip;
const review = { jobId: "job-test", subtitleOnlyAuto: true, state: "awaiting_review", totalClipCount: 2,
  confirmedClipCount: 2, clips: [normal, short], segments: [{ id: "seg_001", start: 110, end: 115 }] } as SubtitleReviewDocument;
const model = (value: SubtitleReviewDocument) => ({ review: value, jobId: value.jobId, selectedClip: normal }) as SubtitleReviewContext;
const render = (value: SubtitleReviewDocument, error?: string) => renderToStaticMarkup(React.createElement(AutomaticReviewStatus, {
  review: value, error, selectedClip: normal
}));

for (const state of ["awaiting_review", "render_queued", "rendering"] as const) {
  const value = { ...review, state };
  const html = renderToStaticMarkup(React.createElement(SubtitleReviewScreen, { model: model(value) }));
  assert.match(html, /書き出し準備中（完成したら表示します）/);
  assert.equal((html.match(/role="status"/g) ?? []).length, 1);
  assert.doesNotMatch(html, /字幕確定|準備完了|文言を自動決定中|正式プレビューを作成中|cand_|subtitle-review-grid/);
  assert.match(html, /詳細編集（任意）/, "optional corrections remain reachable");
  assert.ok(reviewNeedsPolling(value), "stay on this screen and poll through rendering");
}
const completed = { ...review, state: "completed" } as SubtitleReviewDocument;
assert.match(render(completed), /完成しました →/);
assert.match(render(completed), /href="\/results\/job-test"[^>]*>投稿セットへ/);
assert.equal(reviewNeedsPolling(completed), false);
assert.match(render(completed, "過去の保存エラー"), /投稿セットへ/);
assert.equal(render({ ...review, confirmedClipCount: 1 }), "", "no per-clip progress list before all subtitles are confirmed");
assert.equal(render({ ...review, subtitleOnlyAuto: false }), "");
assert.equal(renderToStaticMarkup(React.createElement(ReviewRenderControls, {
  context: { review } as SubtitleReviewViewContext
})), "", "old bottom progress list is removed");
assert.match(renderToStaticMarkup(React.createElement(ReviewRenderControls, {
  context: { review: { ...review, subtitleOnlyAuto: false }, rawDirtySegmentIds: new Set() } as SubtitleReviewViewContext
})), /プレビュー更新完了を待っています/, "manual flow retains render controls");

const failed = { ...review, clips: [normal, { ...short, automaticDecisionState: "failed",
  automaticDecisionError: `${short.id}（元動画 300.0〜350.0秒）: タイトル案の根拠を確認できませんでした。` }] } as SubtitleReviewDocument;
const errorMarkup = render(failed);
assert.match(errorMarkup, /role="alert"/);
assert.match(errorMarkup, /ショート1（元動画 5:00.0〜5:50.0）: タイトル案の根拠/);
assert.doesNotMatch(errorMarkup, /cand_|書き出し準備中|通常1/);
const gateFailed = { ...review, automaticStopReasons: [`完成動画の検証で停止: ${short.id}: 画角が表示範囲に収まりません`] };
assert.match(render(gateFailed), /ショート1（元動画 5:00.0〜5:50.0）: 画角/);
assert.doesNotMatch(render(gateFailed), /cand_|書き出し準備中/);
assert.match(render(review, "空の字幕です: seg_001"), /通常1の字幕（元動画 1:50.0〜1:55.0）/);
assert.doesNotMatch(render(review, "空の字幕です: seg_001"), /seg_001|書き出し準備中/);
const previewFailed = { ...review, clips: [normal, { ...short, automaticDecisionState: "ready", previewState: "failed",
  previewError: "映像を読み込めませんでした" }] } as SubtitleReviewDocument;
assert.match(render(previewFailed), /ショート1（元動画 5:00.0〜5:50.0）: 正式プレビューの作成に失敗/);
assert.deepEqual(automaticReviewStopReasons({ ...failed, state: "completed" }), [], "stale errors do not obscure completion");
assert.deepEqual(automaticReviewStopReasons({ ...failed, clips: [normal, { ...failed.clips[1], automaticDecisionState: "generating" }] }), [],
  "a stale error does not mark an active retry as stopped");
assert.doesNotMatch(render({ ...review, automaticStopReasons: ["cand_short_unknown で停止"] }), /cand_/);

async function verifyPolling() {
  const originalFetch = globalThis.fetch;
  const requests: string[] = [];
  let current = review;
  let jobStatus = "rendering_shorts";
  let statusFetchFails = false;
  globalThis.fetch = async input => {
    const path = new URL(String(input)).pathname;
    requests.push(path);
    if (!path.endsWith("subtitle-review") && statusFetchFails) throw new Error("Temporary network failure");
    return new Response(JSON.stringify(path.endsWith("subtitle-review") ? current : {
      status: jobStatus, error: { message: `${short.id} の動画を書き出せませんでした` }
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    await loadReviewWithRenderStatus(review.jobId);
    assert.deepEqual(requests.splice(0), ["/api/jobs/job-test/subtitle-review"]);
    current = { ...review, state: "rendering" };
    assert.match(render(await loadReviewWithRenderStatus(review.jobId)), /書き出し準備中/);
    assert.deepEqual(requests.splice(0), ["/api/jobs/job-test/subtitle-review", "/api/jobs/job-test"]);
    statusFetchFails = true;
    assert.equal((await loadReviewWithRenderStatus(review.jobId)).state, "rendering", "transient status errors keep the review usable");
    statusFetchFails = false;
    jobStatus = "failed";
    const stopped = render(await loadReviewWithRenderStatus(review.jobId));
    assert.match(stopped, /書き出しで停止: ショート1（元動画 5:00.0〜5:50.0）/);
    assert.doesNotMatch(stopped, /cand_|書き出し準備中/);
    current = completed;
    assert.match(render(await loadReviewWithRenderStatus(review.jobId)), /投稿セットへ/);
    current = { ...review, subtitleOnlyAuto: false, state: "rendering" };
    requests.length = 0;
    await loadReviewWithRenderStatus(review.jobId);
    assert.deepEqual(requests, ["/api/jobs/job-test/subtitle-review"], "no extra polling request in manual flow");
  } finally { globalThis.fetch = originalFetch; }
}
void verifyPolling().then(() => console.log("Automatic review: compact pending/completed states, named stop reasons and completion polling passed"));
