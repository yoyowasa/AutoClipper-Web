import assert from "node:assert/strict";
import { rejectionPayload, retainRejectionDrafts } from "../lib/clipRejections";
import { getClipRejections, reselectClipPlan } from "../lib/api";

async function main() {
  const clips = [{ id: "kept" }, { id: "missing" }, { id: "notes" }];
  const payload = rejectionPayload(clips, ["kept"], {
    kept: { reason: "no_content", note: "not sent" },
    notes: { reason: "unspecified", note: "推測して変えない" },
    stale: { reason: "other", note: "not current" }
  });
  assert.deepEqual(payload, [
    { clipId: "missing", reason: "unspecified", note: null },
    { clipId: "notes", reason: "unspecified", note: "推測して変えない" }
  ]);
  const oldPlan = { jobId: "test", revision: 1 };
  const drafts = { notes: { reason: "other" as const, note: "以前の場面" } };
  const next = { ...oldPlan, clips: [{ id: "notes" }] } as Parameters<typeof retainRejectionDrafts>[1];
  assert.deepEqual(retainRejectionDrafts(oldPlan, next, drafts), drafts); // Worker rollback keeps drafts.
  assert.deepEqual(retainRejectionDrafts(oldPlan, { ...next, revision: 2 }, drafts), {}); // Reused IDs are fresh scenes.
  assert.deepEqual(retainRejectionDrafts(oldPlan, { ...next, jobId: "other" }, drafts), {});
  const originalFetch = globalThis.fetch;
  const calls: { url: string; options?: RequestInit }[] = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), options });
    return new Response(JSON.stringify(String(url).endsWith("/rejections") ? [] : { jobId: "test", status: "reselecting_clips" }), { status: 200 });
  };
  try {
    assert.deepEqual(await getClipRejections("test"), []);
    await reselectClipPlan("test", { rejections: payload } as Parameters<typeof reselectClipPlan>[1]);
    assert.equal(calls[0].options?.cache, "no-store");
    assert.equal(calls[0].url.endsWith("/api/jobs/test/clip-plan/rejections"), true);
    assert.deepEqual(JSON.parse(String(calls[1].options?.body)).rejections, payload);
  } finally { globalThis.fetch = originalFetch; }
  console.log("clip rejection payload and history API passed");
}
void main();
