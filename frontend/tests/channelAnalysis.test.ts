import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AnalysisReviewText, AnalysisValidationText, ChannelAnalysisSettings } from "../components/ChannelAnalysisSettings";
import { analysisStatus, getChannelAnalysis, startChannelAnalysis, type AnalysisReview } from "../lib/channelAnalysis";

const review: AnalysisReview = {
  id: "analysis_test", channel_id: 1, batch_run_id: "sync_test", title: "観測と次の確認", summary: "まだ仮説です。",
  goal_views: 1000000, recommendation_framework_version: "youtube_official_2026_09_24",
  reviewed_material: "statistics_and_titles", limitations: ["表示機会は未取得"],
  findings: [{ id: "finding", format: "all", title: "初期実績", evidence_ids: ["r:1:views"],
    observation: "観測した事実", hypothesis: "未検証の説明", alternatives: ["公開時期", "視聴者"],
    counter_evidence: "母数不足", next_check: "次に比較", confidence: "low" }],
  proposals: [{ id: "proposal", format: "shorts", priority: 1, title: "題材を先に", baseline_video_id: "video000001",
    evidence_ids: ["r:1:views"], reason: "比較するため", goal_path: "改善の仮説", material_to_find: "成立する場面",
    title_candidates: ["題材のタイトル"], hook: "題材の冒頭", structure: [{ start: 0, end: 3, action: "題材" },
      { start: 3, end: 20, action: "展開" }], change_one: "冒頭", keep_fixed: "尺", primary_metric: "views",
    result_check: "7日で確認", rejection_condition: "差がなければ保留", recommendation_link: { surface: "shorts_feed",
      viewer_need: "題材が分かる", stage: "appeal", signal_hypothesis: "反応の仮説", evidence_gap: "未取得の根拠",
      rule_ids: ["shorts_response"] } }],
};
const markup = renderToStaticMarkup(createElement(AnalysisReviewText, { review }));
for (const value of ["観測した事実", "未検証の説明", "公開時期", "母数不足", "次に比較", "題材を先に", "7日で確認",
  "差がなければ保留", "Shortsフィード", "r:1:views", "未採用・効果未確認"]) assert.ok(markup.includes(value), value);
assert.doesNotMatch(markup, /<button/); // Adoption and improvement trials are a later integration task.
assert.match(renderToStaticMarkup(createElement(AnalysisReviewText, { review: { ...review, proposals: [] } })), /根拠が不足/);
const settings = renderToStaticMarkup(createElement(ChannelAnalysisSettings, { channelId: 1, connected: false, syncActive: false }));
assert.match(settings, /24時間以上/);
assert.match(settings, /disabled=""/);
assert.match(settings, /分析する/);
assert.equal(analysisStatus(null), "未分析");
const validation = { excludedFindings: 1, excludedProposals: 2, fatal: false,
  reasonCounts: { BASELINE_FORMAT_UNKNOWN: 1, SCHEMA_INVALID: 2 },
  issues: [{ code: "SCHEMA_INVALID", loc: ["proposals", 0, "structure"] }] };
const diagnostic = renderToStaticMarkup(createElement(AnalysisValidationText, { validation }));
for (const value of ["有効な部分を保存", "所見1件・提案2件", "BASELINE_FORMAT_UNKNOWN", "基準動画の形式が不明",
  "SCHEMA_INVALID", "proposals.0.structure"]) assert.ok(diagnostic.includes(value), value);
assert.match(renderToStaticMarkup(createElement(AnalysisValidationText,
  { validation: { ...validation, fatal: true } })), /分析全体を保存できません/);
assert.equal(renderToStaticMarkup(createElement(AnalysisValidationText, {})), "");

async function main() {
  const previous = globalThis.fetch;
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ path: new URL(String(input)).pathname, init });
    return new Response(JSON.stringify({ latestRun: null, latestResult: null, history: [] }), { status: 200 });
  };
  try {
    await getChannelAnalysis(1);
    for (const mode of ["auto", "always", "never"] as const) await startChannelAnalysis(1, mode);
    assert.ok(calls.every(call => call.path === "/api/intelligence/channels/1/analysis"));
    assert.deepEqual(calls.map(call => call.init?.method), [undefined, "POST", "POST", "POST"]);
    assert.deepEqual(calls.slice(1).map(call => JSON.parse(String(call.init?.body))),
      [{ syncBefore: "auto" }, { syncBefore: "always" }, { syncBefore: "never" }]);
    assert.ok(calls.every(call => call.init?.credentials === "include" && call.init?.cache === "no-store"));
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "このチャンネルは分析中です。" }), { status: 409 });
    await assert.rejects(startChannelAnalysis(1, "auto"), /分析中/);
  } finally { globalThis.fetch = previous; }
  console.log("Channel analysis: evidence, hypotheses, proposals, limits, sync modes and API errors passed");
}
void main();
