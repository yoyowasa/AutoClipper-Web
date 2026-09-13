import assert from "node:assert/strict";

import {
  automationGateDisplay,
  automationGateReasonLabel,
  isExceptionOnlyAutomationMode
} from "../lib/automationQuality";

assert.equal(isExceptionOnlyAutomationMode("guarded"), true);
assert.equal(isExceptionOnlyAutomationMode("auto"), true);
assert.equal(isExceptionOnlyAutomationMode("shadow"), false);

const attention = automationGateDisplay({
  automationEffectiveMode: "auto",
  automationGateState: "needs_attention",
  automationGateStage: "content",
  automationGateOutcome: "fail",
  automationGateAutoPassedClips: 3,
  automationGateAttentionClipIds: ["short-2", "short-2"],
  automationGateReasonCodes: ["invalid_subtitle_structure", "preview_render_failed"]
});
assert.equal(attention.active, true);
assert.equal(attention.visible, true);
assert.equal(attention.title, "問題だけ人の確認へ戻しました");
assert.equal(attention.stageLabel, "タイトル・字幕");
assert.equal(attention.autoPassedClips, 3);
assert.deepEqual(attention.attentionClipIds, ["short-2"]);
assert.deepEqual(attention.reasonLabels, [
  "字幕の構造に問題があります",
  "確認用プレビューを作成できませんでした"
]);

const passed = automationGateDisplay({
  automationEffectiveMode: "guarded",
  automationGateState: "passed",
  automationGateStage: "selection",
  automationGateOutcome: "pass",
  automationGateAutoPassedClips: 5,
  automationGateAttentionClips: 0
});
assert.equal(passed.visible, true);
assert.equal(passed.tone, "passed");
assert.equal(passed.title, "自動品質確認を通過");

const fallback = automationGateDisplay({
  automationMode: "auto",
  automationGateState: "fallback_manual",
  automationGateReasonCodes: ["selection_gate_record_unavailable"]
});
assert.equal(fallback.active, true);
assert.equal(fallback.title, "判定不能のため人の確認へ戻しました");

const effectiveManual = automationGateDisplay({
  automationMode: "auto",
  automationEffectiveMode: "manual",
  automationGateState: "needs_attention"
});
assert.equal(effectiveManual.active, false);
assert.equal(effectiveManual.visible, false);

assert.equal(automationGateReasonLabel("future_reason"), "確認理由: future_reason");
assert.equal(
  automationGateReasonLabel("post_render_visual_evidence_insufficient"),
  "完成ショートの画角を安全と判定できませんでした"
);

console.log("automation quality UI contract: passed");
