import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MetricDisplay, ReportSource } from "../components/intelligence/MetricDisplay";
import { chartSegments, DailyChart } from "../components/intelligence/DailyChart";
import { TrialComparison } from "../components/intelligence/TrialPanel";
import { AnalysisReviewText } from "../components/ChannelAnalysisSettings";
import { metricText, trialDraft, getDashboard, getTrials, getEvidenceVideos, adoptProposal, saveTrial, deleteTrial,
  type NativeReport, type ImprovementTrial } from "../lib/intelligenceDashboard";
import type { AnalysisReview } from "../lib/channelAnalysis";

const zero = { value: 0, missingReason: null, observedSubtotal: null };
const missing = { value: null, missingReason: "API_5XX", observedSubtotal: null };
const native: NativeReport = { source: "youtube_analytics", start: "2026-09-01", end: "2026-09-07",
  observedAt: "2026-10-20T00:00:00Z", metrics: { views: zero, engagedViews: missing }, reason: null, expected: null, returned: null, format: "shorts" };
assert.equal(metricText(zero), "0");
assert.equal(metricText(missing), "未取得");
const missingMarkup = renderToStaticMarkup(createElement(MetricDisplay, { metric: missing }));
assert.match(missingMarkup, /未取得/); assert.match(missingMarkup, /APIの一時エラー/);
assert.doesNotMatch(missingMarkup, />0</);
const partial = renderToStaticMarkup(createElement(MetricDisplay, { metric: { ...missing, missingReason: "PARTIAL_COVERAGE", observedSubtotal: 42 } }));
assert.match(partial, /全期間の合計は未取得/); assert.match(partial, /返却された分のみ/); assert.match(partial, /42/);
assert.match(renderToStaticMarkup(createElement(ReportSource, { report: native })), /YouTube公式値/);
assert.match(renderToStaticMarkup(createElement(ReportSource, { report: { ...native, source: "independent_aggregation" } })), /独自集計/);

const days = [0, 2, null, 3, -1].map((value, i) => ({ ...native, start: `2026-09-0${i + 1}`, end: `2026-09-0${i + 1}`,
  metrics: { views: { ...zero, value } } }));
assert.equal(chartSegments(days, "views").length, 2); // Missing day splits, rather than zero-filling the line.
assert.ok(chartSegments(days, "views").flatMap(points => points.split(" ")).every(point => {
  const y = Number(point.split(",")[1]); return y >= 28 && y <= 178;
}));
assert.match(renderToStaticMarkup(createElement(DailyChart, { reports: days })), /日別の値と欠損理由/);
const partialDays = days.map(report => ({ ...report, metrics: { views: { ...missing, observedSubtotal: 5 } } }));
assert.equal(chartSegments(partialDays, "views").length, 0);
assert.equal(chartSegments(partialDays, "views", true).length, 1);
assert.match(renderToStaticMarkup(createElement(DailyChart, { reports: partialDays })), /小計（独自集計・全体値ではありません）/);

const trial: ImprovementTrial = { id: "trial_test", channelId: 1, analysisId: "analysis_test", proposalId: "proposal_one",
  baselineVideoId: "video000001", targetVideoId: "video000002", changeNote: "冒頭に題材語", keepFixed: "尺", primaryMetric: "views",
  rejectionCondition: "増えなければ保留", resultCheck: "7日を比較", status: "active", createdAt: "2026-10-20T00:00:00Z",
  registeredAt: "2026-10-20T00:00:00Z", updatedAt: "2026-10-20T00:00:00Z",
  baseline: { id: "video000001", title: "基準", publishedAt: "2026-08-31T12:00:00Z", format: "shorts", durationBand: "30〜45秒", first7: native },
  target: { id: "video000002", title: "次の動画", publishedAt: "2026-09-10T12:00:00Z", format: "long", durationBand: "3〜6分", first7: native },
  comparisonIssues: ["FORMAT_MISMATCH", "DURATION_MISMATCH"], direction: null, recordedAfterPublication: true,
  causalVerdict: "変更の効果とは断定できません。" };
const comparison = renderToStaticMarkup(createElement(TrialComparison, { trial, onVideo: () => undefined }));
for (const text of ["公開翌日から7暦日", "America/Los_Angeles", "形式が異なります", "尺帯が異なります", "事後記録", "断定できません", "未取得"]) {
  assert.ok(comparison.includes(text), text);
}
assert.equal(trialDraft(trial).expectedUpdatedAt, trial.updatedAt);
assert.equal(trialDraft(trial).rejectionCondition, trial.rejectionCondition);
assert.equal("baseline" in trialDraft(trial), false); // No YouTube values are written back into the user's intent record.

const review: AnalysisReview = { id: "analysis_test", channel_id: 1, batch_run_id: "sync_test", title: "検証", summary: "仮説",
  recommendation_framework_version: null, reviewed_material: "statistics_and_titles", goal_views: 1000000,
  limitations: ["未取得"], findings: [], proposals: [{ id: "proposal_one", format: "shorts", priority: 1, title: "試す",
    baseline_video_id: "video000001", evidence_ids: ["r:1:views"], reason: "仮説", goal_path: "確認", material_to_find: "題材",
    title_candidates: [], hook: "冒頭", structure: [], change_one: "題材語", keep_fixed: "尺", primary_metric: "views",
    result_check: "7日", rejection_condition: "差がなければ保留", recommendation_link: null }] };
const adopted = renderToStaticMarkup(createElement(AnalysisReviewText, { review, adopted: ["proposal_one"], onAdopt: () => undefined,
  renderEvidence: () => createElement("a", { href: "#video-detail" }, "根拠動画") }));
assert.match(adopted, /採用済み/); assert.match(adopted, /disabled=""/); assert.match(adopted, /根拠動画/);

async function main() {
  const original = globalThis.fetch;
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ path: new URL(String(input)).pathname, init });
    return init?.method === "DELETE" ? new Response(null, { status: 204 }) : new Response(JSON.stringify({}), { status: 200 });
  };
  try {
    await getDashboard(1, "shorts"); await getTrials(1); await getEvidenceVideos(1, "analysis_test");
    await adoptProposal(1, "analysis_test", "proposal_one"); await saveTrial(1, trial.id, trialDraft(trial)); await deleteTrial(1, trial.id);
    assert.deepEqual(calls.map(call => call.init?.method), [undefined, undefined, undefined, "POST", "PUT", "DELETE"]);
    assert.ok(calls[3].path.endsWith("/proposals/proposal_one/adopt"));
    assert.equal(JSON.parse(String(calls[4].init?.body)).rejectionCondition, "増えなければ保留");
    assert.ok(calls.every(call => call.init?.cache === "no-store" && call.init?.credentials === "include"));
  } finally { globalThis.fetch = original; }
  console.log("Intelligence dashboard: missing/zero, sources, chart gaps, comparison, adoption and trial APIs passed");
}
void main();
