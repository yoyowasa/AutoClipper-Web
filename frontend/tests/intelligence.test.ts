import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { YouTubeConnectionList } from "../components/YouTubeConnectionSettings";
import { getYouTubeConnections, startYouTubeConnection, syncYouTubeChannel, youtubeSyncLabel, youtubeSyncTime,
  type YouTubeConnections } from "../lib/intelligence";

const data: YouTubeConnections = { clientConfigured: true, derivedAllowed: true, extendedStorage: true,
  reviewedAt: "2026-10-15", policyReference: "https://developers.google.com/youtube/terms/derived-metrics-policy",
  channels: [{ id: 1, externalId: "UC" + "a".repeat(22), name: "自チャンネル", connectionStatus: "connected", errorMessage: null,
    lastSyncAt: "2026-10-14T12:00:00", latestRun: { id: "sync_test", status: "failed", queuedAt: "2026-10-15T00:00:00",
      finishedAt: "2026-10-15T00:00:01", errorCode: "QUOTA_EXCEEDED", errorMessage: "利用枠を超えました。",
      requestedStart: null, requestedEnd: null, lastReportDate: null, fetchedCount: 0, truncated: false, missingReportCount: 0 } }] };
const markup = renderToStaticMarkup(createElement(YouTubeConnectionList, { data, busy: false, onConnect: () => {}, onSync: () => {} }));
assert.match(markup, /接続済み/);
assert.match(markup, /同期失敗/);
assert.match(markup, /利用枠を超えました/);
assert.match(markup, /2026\/10\/14 21:00:00/, "last successful sync stays visible after a failed attempt, in JST");
const reconnect = structuredClone(data);
reconnect.channels[0].connectionStatus = "reconnect_required";
reconnect.channels[0].latestRun = null;
const reconnectMarkup = renderToStaticMarkup(createElement(YouTubeConnectionList, { data: reconnect, busy: false,
  onConnect: () => {}, onSync: () => {} }));
assert.match(reconnectMarkup, /再接続が必要/);
assert.match(reconnectMarkup, /disabled=""[^>]*>同期する/);
assert.equal(youtubeSyncLabel(null), "未同期");
assert.equal(youtubeSyncLabel({ ...data.channels[0].latestRun!, status: "success" }), "同期完了（Analyticsは未返却）");
assert.equal(youtubeSyncTime(null), "未同期");

async function main() {
  const previous = globalThis.fetch;
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ path: new URL(String(input)).pathname, init });
    return new Response(JSON.stringify(data), { status: 200 });
  };
  try {
    assert.deepEqual(await getYouTubeConnections(), data);
    await startYouTubeConnection(data.channels[0].externalId);
    await syncYouTubeChannel(1);
    assert.deepEqual(calls.map(call => call.path), ["/api/intelligence/channels", "/api/intelligence/oauth/start",
      "/api/intelligence/channels/1/sync"]);
    assert.equal(calls[1].init?.credentials, "include", "OAuth state is bound to the browser's HttpOnly cookie");
    assert.deepEqual(JSON.parse(String(calls[1].init?.body)), { channelExternalId: data.channels[0].externalId });
    assert.equal(calls[2].init?.method, "POST");
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "再接続が必要です。" }), { status: 409 });
    await assert.rejects(syncYouTubeChannel(1), /再接続が必要/);
  } finally { globalThis.fetch = previous; }
  console.log("YouTube connections: native sync status, reconnect, JST timestamps, API paths and OAuth cookie passed");
}
void main();
