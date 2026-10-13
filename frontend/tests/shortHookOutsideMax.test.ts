import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ClipBoundaryEditor } from "../components/ClipBoundaryEditor";
import { ClipHookSceneEditor } from "../components/ClipHookSceneEditor";
import { ManualClipPlanEditor } from "../components/ManualClipPlanEditor";
import { SettingsPanel, DEFAULT_SETTINGS } from "../components/SettingsPanel";
import { applySubtitleReviewClip } from "../lib/api";
import { clipBodyDuration, completedClipDuration, validateClipDuration, validateHookSceneDuration } from "../lib/durationRules";
import { manualRangeValidationError } from "../lib/manualClipRanges";
import type { ClipPlanClip, ClipPlanDocument } from "../lib/types";

function clip(duration: number): ClipPlanClip {
  return { id: "short", type: "short", start: 0, end: duration, duration, title: "題材",
    previewVideoUrl: null, transcriptExcerpt: "字幕", finalScore: null, ruleScore: null, aiScore: null,
    selectionReason: null, boundaryRefined: false, recommendedStart: 0, recommendedEnd: duration,
    manuallyAdjusted: false, hookSceneStart: 1, hookSceneEnd: 4 };
}
for (const [body, valid] of [[72.4, true], [75, true], [75.1, false]] as const) {
  assert.equal(validateClipDuration("short", clipBodyDuration(0, body), 75) === null, valid);
  assert.equal(completedClipDuration("short", 0, body, 1, 4), body + 3);
  const boundary = renderToStaticMarkup(createElement(ClipBoundaryEditor, {
    clip: clip(body), sourceDuration: 100, shortMaxDuration: 75, onSave: () => {}
  }));
  assert.equal(/75秒以内/.test(boundary), !valid);
  assert.match(boundary, /本編の上限75秒（フック映像は別に最大3秒）/);
  assert.equal(manualRangeValidationError({ ...DEFAULT_SETTINGS, normalClipCount: 0, shortCount: 1,
    normalClipTimeRanges: [], shortClipTimeRanges: [{ startSeconds: 0, endSeconds: body }] }) === null, valid);
  const plan = { clips: [clip(body)], settings: { ...DEFAULT_SETTINGS, workflowMode: "manual" },
    sourceDuration: 100, sourceVideoUrl: "/video", editorVideoUrl: null } as unknown as ClipPlanDocument;
  const manual = renderToStaticMarkup(createElement(ManualClipPlanEditor, {
    plan, selectedClipId: "short", disabled: false, isApproving: false, isDeleting: false, isSaving: false,
    isUpdatingHookScene: false, onApprove: () => {}, onCreate: () => {}, onDelete: () => {},
    onHookSceneUpdate: () => {}, onSelect: () => {}, onUpdate: () => {}
  }));
  assert.equal(/ショートの本編は75秒以内/.test(manual), !valid);
}
for (const [duration, valid] of [[.49, false], [.5, true], [3, true], [3.1, false]] as const) {
  assert.equal(validateHookSceneDuration(duration) === null, valid);
}
const hook = renderToStaticMarkup(createElement(ClipHookSceneEditor, {
  clip: { ...clip(75), hookSceneStart: null, hookSceneEnd: null }, shortMaxDuration: 75, playheadSourceTime: 0, onSave: () => {}
}));
const saveButton = hook.match(/<button[^>]*>この場面を冒頭へ追加<\/button>/)?.[0];
assert.ok(saveButton);
assert.doesNotMatch(saveButton!, / disabled=/); // No saved hook: initial 2-second hook can be added to a 75-second body.
assert.doesNotMatch(hook, /完成尺が上限.*超え/);
assert.match(hook, /フック映像は別に最大3秒/);
const invalidHook = renderToStaticMarkup(createElement(ClipHookSceneEditor, {
  clip: { ...clip(75), hookSceneEnd: 4.1 }, shortMaxDuration: 75, playheadSourceTime: 0, onSave: () => {}
}));
assert.match(invalidHook, /フック映像は0.5〜3秒/);
const settings = renderToStaticMarkup(createElement(SettingsPanel, { settings: DEFAULT_SETTINGS, onChange: () => {} }));
assert.match(settings, /本編の長さ（フック映像は別に最大3秒）/);
for (const duration of [90, 600, 1800]) {
  assert.equal(validateClipDuration("normal", duration, 75), null);
  assert.equal(completedClipDuration("normal", 0, duration, 1, 4), duration);
}

async function errors() {
  const fetch = globalThis.fetch;
  try {
    for (const [detail, expected] of [
      ["ショートの本編は75秒以内です（フック映像は別に最大3秒）。", /本編は75秒以内/],
      [[{ loc: ["body"], msg: "Value error, フック映像は0.5〜3秒にしてください。" }], /フック映像は0.5〜3秒/],
      [[{ loc: ["body", "hookSceneStart"], msg: "Input should be greater than or equal to 0" }], /0秒以上の有効な時刻/]
    ] as const) {
      globalThis.fetch = async () => new Response(JSON.stringify({ detail }), { status: 422 });
      await assert.rejects(applySubtitleReviewClip("job", "short", {} as Parameters<typeof applySubtitleReviewClip>[2]), expected);
    }
  } finally { globalThis.fetch = fetch; }
  console.log("Short hook: body cap, separate hook cap, editor recovery and Japanese 422 reasons passed");
}
void errors().catch(error => { console.error(error); process.exitCode = 1; });
