import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { clipRangeType } from "../lib/clipRangeType";
import { ClipBoundaryEditor } from "../components/ClipBoundaryEditor";
import { ManualClipPlanEditor } from "../components/ManualClipPlanEditor";
import { updateClipPlanBoundary, updateManualClipPlanClip } from "../lib/api";
import type { ClipPlanClip, ClipPlanDocument } from "../lib/types";

assert.deepEqual(clipRangeType("short", 100, 75), { type: "normal", error: null });
assert.deepEqual(clipRangeType("normal", 70, 75), { type: "short", error: null });
assert.match(clipRangeType("short", 80, 75).error!, /どちらの種類でも保存できません.*75秒以内.*90秒以上/);
assert.match(clipRangeType("normal", 80, 75).error!, /どちらの種類でも保存できません.*90秒以上.*75秒以内/);
assert.equal(clipRangeType("short", 100, 120).type, "short");
assert.equal(clipRangeType("normal", 100, 120).type, "normal");
assert.match(clipRangeType("short", 100, 75, false).error!, /75秒以内/);
assert.equal(clipRangeType("short", 1800, 75).type, "normal");
assert.match(clipRangeType("normal", 1801, 75).error!, /最長30分/);

const clip = (type: "normal" | "short", duration: number): ClipPlanClip => ({
  id: "clip-one", type, title: "題材", start: 0, end: duration, duration, previewVideoUrl: null,
  transcriptExcerpt: "本文", finalScore: null, ruleScore: null, aiScore: null, selectionReason: null,
  boundaryRefined: false, recommendedStart: 0, recommendedEnd: type === "short" ? 74 : 95,
  manuallyAdjusted: false, hookSceneStart: null, hookSceneEnd: null,
});
for (const [sourceType, duration, label] of [["short", 100, "通常切り抜きとして保存"], ["normal", 70, "ショートとして保存"]] as const) {
  const current = clip(sourceType, duration);
  const boundary = renderToStaticMarkup(createElement(ClipBoundaryEditor, { clip: current, sourceDuration: 2000, onSave: () => {} }));
  assert.ok(boundary.includes(label));
  assert.match(boundary, /保存する種類/);
  assert.match(boundary, /プレビュー映像は保存すると更新されます/);
  assert.match(boundary, /フック映像は外れます/);
  const button = boundary.match(new RegExp('<button[^>]*>' + label + '</button>'))?.[0];
  assert.ok(button && !button.includes('disabled=""'));
  const plan = { clips: [current], sourceDuration: 2000, sourceVideoUrl: "/source", editorVideoUrl: null,
    settings: { shortMaxDuration: 75 } } as unknown as ClipPlanDocument;
  const manual = renderToStaticMarkup(createElement(ManualClipPlanEditor, { plan, selectedClipId: current.id,
    disabled: false, isApproving: false, isDeleting: false, isSaving: false, isUpdatingHookScene: false,
    onApprove: () => {}, onCreate: () => {}, onDelete: () => {}, onHookSceneUpdate: () => {}, onSelect: () => {}, onUpdate: () => {} }));
  assert.ok(manual.includes(label));
  assert.match(manual, /保存する種類/);
  if (sourceType === "short") assert.doesNotMatch(manual, /冒頭へ見せ場を複製/);
}
const invalid = renderToStaticMarkup(createElement(ClipBoundaryEditor,
  { clip: clip("short", 80), sourceDuration: 2000, onSave: () => {} }));
assert.match(invalid, /どちらの種類でも保存できません/);
assert.match(invalid, /<button[^>]*disabled=""[^>]*>この範囲でプレビュー更新<\/button>/);
const locked = renderToStaticMarkup(createElement(ClipBoundaryEditor,
  { clip: clip("short", 100), sourceDuration: 2000, allowTypeChange: false, onSave: () => {} }));
assert.doesNotMatch(locked, /保存する種類/);
assert.match(locked, /75秒以内/);

async function main() {
  const previous = globalThis.fetch;
  const requests: Array<{ path: string; body: unknown }> = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ path: String(url), body: JSON.parse(String(init?.body)) });
    return new Response(JSON.stringify({}), { status: 200 });
  };
  try {
    await updateClipPlanBoundary("job", "clip", { start: 0, end: 100, type: "normal" });
    await updateManualClipPlanClip("job", "clip", { start: 0, end: 70, type: "short" });
    assert.deepEqual(requests.map(r => r.body), [{ start: 0, end: 100, type: "normal" }, { start: 0, end: 70, type: "short" }]);
    assert.equal(requests.length, 2); // Each combined update makes one HTTP request.
    assert.match(requests[0].path, /\/boundary$/);
    assert.match(requests[1].path, /\/clips\/clip$/);
  } finally { globalThis.fetch = previous; }
  console.log("Clip range/type conversion: target rules, Japanese errors, both editors and single-request payloads passed");
}
void main();
