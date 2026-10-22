import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { DEFAULT_SETTINGS, SettingsPanel, settingsForRuntimeProfile } from "../components/SettingsPanel";
import { JobProgress } from "../components/JobProgress";
import type { JobStatusResponse } from "../lib/types";

import {
  automationGateDisplay,
  automationGateReasonLabel,
  isExceptionOnlyAutomationMode
} from "../lib/automationQuality";

assert.equal(isExceptionOnlyAutomationMode("guarded"), true);
assert.equal(isExceptionOnlyAutomationMode("auto"), true);
assert.equal(isExceptionOnlyAutomationMode("shadow"), false);

for (const profile of ["cpu", "gpu", null]) {
  const settings = settingsForRuntimeProfile(profile);
  assert.equal(settings.automationMode, "auto");
  assert.equal(settings.requireSubtitleReview, true);
  assert.equal(settings.requireClipPlanReview, true);
  assert.equal(settings.burnSubtitles, true);
}
const settingsHtml = renderToStaticMarkup(createElement(SettingsPanel, { settings: DEFAULT_SETTINGS, onChange: () => {} }));
assert.ok(settingsHtml.includes("字幕確認で必ず止まります"));
assert.ok(settingsHtml.includes("clipごとの確定時に正式プレビュー"));
assert.ok(!settingsHtml.includes("完成まで自動"));
const humanReview = automationGateDisplay({
  automationEffectiveMode: "auto", humanSubtitleReviewRequired: true,
  automationGateStage: "content", automationGateState: "needs_attention",
  automationGateReasonCodes: ["human_subtitle_review_required", "preview_not_ready_or_unverifiable"]
});
assert.equal(humanReview.title, "字幕を確認・修正して確定してください");
assert.deepEqual(humanReview.reasonLabels, ["字幕を確認・修正し、各clipを確定してください", "正式プレビューの完成待ち（clip確定後に作成）"]);
const progress = renderToStaticMarkup(createElement(JobProgress, { job: {
  id: "isolated", status: "awaiting_subtitle_review", progress: 80, currentStep: "字幕確認", error: null, details: {
    humanSubtitleReviewRequired: true, automationEffectiveMode: "auto", automationGateStage: "content",
    subtitleReviewConfirmedClips: 0, subtitleReviewTotalClips: 1
  }
} satisfies JobStatusResponse }));
assert.ok(progress.includes("字幕を確認・修正し、各clipを確定してください"));
assert.ok(!progress.includes("問題のあるタイトル・字幕だけ"));
assert.ok(!progress.includes("自動通過"));

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
