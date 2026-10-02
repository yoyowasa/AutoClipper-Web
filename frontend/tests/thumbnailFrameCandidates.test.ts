import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ThumbnailFramePicker } from "../components/ThumbnailFramePicker";
import { prepareThumbnailCandidates, prepareThumbnailPreview, regenerateExportThumbnail } from "../lib/api";
import type { ThumbnailFrameCandidate } from "../lib/types";

const candidates: ThumbnailFrameCandidate[] = [
  { id: "frame_00", second: 3.5, score: 10, closeAvailable: false, imageUrl: "/api/exports/exp/thumbnail/candidates/frame_00/image" },
  { id: "frame_01", second: 9, score: 8, closeAvailable: true, imageUrl: "/api/exports/exp/thumbnail/candidates/frame_01/image" }
];
function markup(id: string) {
  return renderToStaticMarkup(createElement(ThumbnailFramePicker, {
    candidates, selectedId: id, cropMode: "standard", onSelect: () => {}, onCropChange: () => {}
  }));
}
assert.match(markup("frame_00"), /保存済みの人物候補/);
assert.match(markup("frame_00"), /半身/);
assert.match(markup("frame_00"), /disabled=""[^>]*>顔のアップ/);
assert.ok(!markup("frame_01").includes('disabled=""'));
assert.match(markup("frame_01"), /frame_01\/image/);
assert.equal((markup("frame_01").match(/<img /g) ?? []).length, 2);

async function main() {
  const originalFetch = globalThis.fetch;
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(JSON.stringify({ state: "ready", candidates, frameKey: "test", status: "generating" }), {
      headers: { "Content-Type": "application/json" }
    });
  };
  try {
    const state = await prepareThumbnailCandidates("exp");
    assert.deepEqual(state.candidates, candidates);
    assert.ok(calls[0].url.endsWith("/thumbnail/candidates/prepare") && calls[0].init?.method === "POST");
    await prepareThumbnailPreview("exp", new AbortController().signal, false, { subjectSource: "video", frameCandidateId: "frame_01" });
    assert.equal(new URL(calls[1].url).searchParams.get("frameCandidateId"), "frame_01");
    await regenerateExportThumbnail("exp", { frameSeconds: 0, subjectAnchorX: 1, frameCandidateId: "frame_01", cropMode: "close" });
    const body = JSON.parse(String(calls[2].init?.body));
    assert.equal(body.frameCandidateId, "frame_01");
    assert.equal(body.cropMode, "close");
  } finally { globalThis.fetch = originalFetch; }
  console.log("Cached thumbnail candidates: gallery, close eligibility and selection requests passed");
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
