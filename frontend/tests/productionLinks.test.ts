import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ProductionLinkList } from "../components/ProductionLinkSettings";
import { getProductionLinks, reconcileProductionLinks, setProductionLink, type ProductionLinks } from "../lib/productionLinks";

const record = { familyId: "exp_root", recordId: "exp_new", publicationTitle: "題材の話", type: "short" as const,
  revision: 2, createdAt: "2026-10-01T00:00:00Z", characterPresetName: null, ambiguous: false, mode: "manual_unlinked" as const };
const video = { id: "video000001", channelId: 1, title: "公開動画", publishedAt: "2026-10-02T00:00:00" };
const data: ProductionLinks = { links: [], unlinkedRecords: [record], unlinkedVideos: [video], linkedCount: 0,
  unlinkedRecordCount: 1, unlinkedVideoCount: 1, issues: [] };
function markup(value: ProductionLinks, busy = false) {
  return renderToStaticMarkup(createElement(ProductionLinkList, { data: value, busy, choices: { exp_root: video.id },
    onChoose: () => {}, onLink: () => {}, onUnlink: () => {} }));
}
assert.match(markup(data), /未結び付けの制作記録 1件/);
assert.match(markup(data), /手動で解除済み/);
assert.match(markup(data), /公開動画/);
assert.match(markup(data, true), /disabled=""/);
assert.match(markup({ ...data, unlinkedRecords: [{ ...record, ambiguous: true }] }), /枝分かれ/);
const linked: ProductionLinks = { ...data, unlinkedRecords: [], unlinkedVideos: [], linkedCount: 1,
  unlinkedRecordCount: 0, unlinkedVideoCount: 0, links: [{ familyId: record.familyId, recordId: record.recordId,
    mode: "manual", linkedAt: video.publishedAt, updatedAt: video.publishedAt, record, video }] };
assert.match(markup(linked), /結び付きを外す/);
assert.match(markup(linked), /手動/);
assert.doesNotMatch(markup(linked), /再生数|平均視聴|engaged/);

async function main() {
  const previous = globalThis.fetch;
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ path: new URL(String(input)).pathname, init });
    return new Response(JSON.stringify(data), { status: 200 });
  };
  try {
    assert.deepEqual(await getProductionLinks(), data);
    await setProductionLink("exp_root", video.id);
    await setProductionLink("exp_root", null);
    await reconcileProductionLinks();
    assert.deepEqual(calls.map(call => call.path), ["/api/intelligence/production-links",
      "/api/intelligence/production-links/exp_root", "/api/intelligence/production-links/exp_root",
      "/api/intelligence/production-links/reconcile"]);
    assert.deepEqual(calls.map(call => call.init?.method), [undefined, "PUT", "PUT", "POST"]);
    assert.deepEqual(JSON.parse(String(calls[1].init?.body)), { youtubeVideoId: video.id });
    assert.deepEqual(JSON.parse(String(calls[2].init?.body)), { youtubeVideoId: null });
    assert.ok(calls.every(call => call.init?.credentials === "include" && call.init?.cache === "no-store"));
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "この動画は既に結び付いています。" }), { status: 409 });
    await assert.rejects(setProductionLink("exp_root", video.id), /既に結び付いています/);
  } finally { globalThis.fetch = previous; }
  console.log("Production links: counts, manual links/unlinks, ambiguity, API payloads and errors passed");
}
void main();
