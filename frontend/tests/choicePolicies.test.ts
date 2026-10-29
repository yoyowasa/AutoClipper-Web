import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChoicePolicyItems } from "../components/intelligence/ChoicePolicyHistory";
import { restoreChoicePolicy, policyReason, type ChoicePolicy } from "../lib/choicePolicies";

Object.assign(globalThis, { React });
const cohort = { id: "group", kind: "framing", role: "", band: "60〜75秒", count: 5,
  rate: 1, median: 1400000, observed_at: "2026-10-29T00:00:00Z", video_ids: ["video000001"] };
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
assert.match(render([policy]), /判定済み5本.*到達率100%.*1,400,000/);
assert.match(render([policy]), /根拠動画1/);
assert.match(render([{ ...policy, decisions: [{ ...policy.decisions[0], reason: "MIXED_PROVENANCE", evidence: null }] }]), /手動・出所未記録/);
assert.match(render([{ ...policy, decisions: [{ ...policy.decisions[0], evidence: null }] }]), /保持期限/);
assert.match(render([]), /版はまだありません/);
assert.match(policyReason.EARLY_7_DAY_DECLINE, /警告のみ/);
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
