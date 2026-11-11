import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChoicePolicyItems } from "../components/intelligence/ChoicePolicyHistory";
import { restoreChoicePolicy, policyReason, type ChoicePolicy } from "../lib/choicePolicies";

Object.assign(globalThis, { React });
const cohort = { id: "group", kind: "framing", role: "", count: 5,
  rate: 1, median: 1400000, first7_count: 3, first7_median: 600, observed_at: "2026-10-29T00:00:00Z", video_ids: ["video000001"] };
const policy: ChoicePolicy = { id: "scope", character: "キャラ", format: "short", currentId: "policy_new",
  versions: [{ id: "policy_new", previousId: "policy_before", createdAt: "2026-10-29T00:00:00Z", values: { weights: {} } }],
  decisions: [{ id: "decision", action: "update", reason: "OBSERVATIONAL_CRITERIA_MET", fromId: "policy_before",
    toId: "policy_new", analysisId: "analysis", createdAt: "2026-10-29T00:00:00Z", evidence: { before: cohort, after: cohort } }] };
const render = (items: ChoicePolicy[]) => renderToStaticMarkup(React.createElement(ChoicePolicyItems, {
  items, busy: false, restore: () => {},
}));
assert.match(render([policy]), /現在の版.*policy_new/);
assert.match(render([policy]), /直前の版に戻す/);
assert.match(render([policy]), /因果効果は未確認/);
assert.match(render([policy]), /30日: 判定済み5本.*1,400,000.*7日: 3本.*600/);
assert.doesNotMatch(render([policy]), /到達率|警告用/);
assert.match(render([{ ...policy, decisions: [{ ...policy.decisions[0], evidence: { before: { ...cohort, band: "60〜75秒" }, after: cohort } }] }]), /60〜75秒 ／ 30日/);
const provisional = { ...policy.decisions[0], reason: "PROVISIONAL_7_DAY_CRITERIA_MET", evidence: { basis: "first7" as const,
  before_count: 9, after_count: 4, before_median: 310, after_median: 552.5, before: cohort, after: { ...cohort, source: "mixed" } } };
const provisionalHtml = render([{ ...policy, decisions: [provisional] }]);
assert.match(provisionalHtml, /仮更新しました/);
assert.match(provisionalHtml, /仮判定（7日の成績）.*9本 中央値310再生.*4本 中央値552.5再生/);
assert.match(provisionalHtml, /出所: 複数の出所/);
assert.match(render([{ ...policy, decisions: [{ ...policy.decisions[0], evidence: { basis: "first30", before_count: 5, after_count: 5,
  before_median: 1000000, after_median: 1400000 } }] }]), /確定（30日の成績）.*5本 中央値1,000,000再生/);
assert.match(render([policy]), /根拠動画1/);
assert.match(render([{ ...policy, decisions: [{ ...policy.decisions[0], reason: "MIXED_PROVENANCE", evidence: null }] }]), /旧基準/);
const manual = { ...cohort, source: "manual" };
assert.match(render([{ ...policy, decisions: [{ ...policy.decisions[0], evidence: { before: cohort, after: manual } }] }]), /出所: 手動/);
const corrected = { ...policy.decisions[0], reason: "HUMAN_CORRECTIONS", evidence: { source: "human_corrections", key: "text_style.subtitle.regular", count: 5,
  corrections: [{ record_id: "exp_1", video_id: "video000001", kind: "text_style", role: "subtitleStyle", before: { bold: true }, after: { bold: false },
    applied_at: "2026-10-29T00:00:00" }] } };
const humanHtml = render([{ ...policy, decisions: [corrected] }]);
assert.match(humanHtml, /人の修正 5本/);
assert.match(humanHtml, /bold=true.*→.*bold=false/);
assert.match(policyReason.HUMAN_CORRECTIONS, /人の修正が5本以上/);
assert.match(render([{ ...policy, decisions: [{ ...policy.decisions[0], evidence: null }] }]), /保持期限/);
assert.match(render([]), /版はまだありません/);
assert.match(policyReason.EARLY_7_DAY_DECLINE, /旧基準/);
assert.match(policyReason.REGRESSION_7_DAY, /自動で直前の版/);
assert.match(policyReason.VERSION_RESULT_PENDING, /成績待ち/);
assert.match(policyReason.REGRESSION_30_DAY, /自動で直前の版/);
let sent: { url: string; body: string } | undefined;
globalThis.fetch = async (url, init) => {
  sent = { url: String(url), body: String(init?.body) };
  return new Response(null, { status: 204 });
};
restoreChoicePolicy(1, policy).then(() => {
  assert.match(sent!.url, /channels\/1\/choice-policies\/scope\/rollback$/);
  assert.deepEqual(JSON.parse(sent!.body), { expectedVersion: "policy_new" });
  console.log("Version history, safe hold/revert reasons, evidence and stale-version protection passed");
}).catch(error => { console.error(error); process.exitCode = 1; });
