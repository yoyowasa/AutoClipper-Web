"use client";

import { useCallback, useEffect, useState } from "react";
import { ChannelAnalysisSettings } from "./ChannelAnalysisSettings";
import { automationLabel, getYouTubeConnections, startYouTubeConnection, syncYouTubeChannel, youtubeSyncLabel, youtubeSyncTime,
  type YouTubeConnections } from "../lib/intelligence";

export function YouTubeConnectionList({ data, busy, onConnect, onSync }: {
  data: YouTubeConnections; busy: boolean; onConnect: (id: string) => void; onSync: (id: number) => void;
}) {
  return <ul className="space-y-3">{data.channels.map(channel => {
    const active = channel.latestRun?.status === "queued" || channel.latestRun?.status === "running";
    return <li key={channel.id} className="border border-neutral-300 bg-white p-4">
      <h3 className="font-semibold">{channel.name ?? "チャンネル（メタデータ未更新）"}</h3>
      <p className="break-all text-xs text-neutral-500">{channel.externalId}</p>
      <p className="mt-2 text-sm">{channel.connectionStatus === "connected" ? "接続済み" : "再接続が必要"}</p>
      <p className="text-sm">最終同期（成功）: {youtubeSyncTime(channel.lastSyncAt)}</p>
      <p className="text-sm" aria-live="polite">{youtubeSyncLabel(channel.latestRun)}</p>
      {channel.latestRun?.missingReportCount ? <p className="text-xs text-amber-800">
        未返却のレポート: {channel.latestRun.missingReportCount}件（NO_ROWS）
      </p> : null}
      {channel.latestRun?.lastReportDate ? <p className="text-xs text-neutral-600">
        Analyticsの最新返却日: {channel.latestRun.lastReportDate}（米国太平洋時間の日次）
      </p> : null}
      {channel.latestRun?.errorMessage || channel.errorMessage ? <p className="mt-1 text-sm text-red-700" role="alert">
        {channel.latestRun?.errorMessage ?? channel.errorMessage}
      </p> : null}
      <div className="mt-3 flex gap-2">
        <button type="button" disabled={busy || active || !data.clientConfigured} className="border px-3 py-2 disabled:opacity-40"
          onClick={() => onConnect(channel.externalId)}>再接続</button>
        <button type="button" disabled={busy || active || channel.connectionStatus !== "connected"}
          className="bg-sky-700 px-3 py-2 text-white disabled:opacity-40" onClick={() => onSync(channel.id)}>同期する</button>
      </div>
      <ChannelAnalysisSettings channelId={channel.id} connected={channel.connectionStatus === "connected"} syncActive={active} />
    </li>;
  })}</ul>;
}

export function YouTubeConnectionSettings() {
  const [data, setData] = useState<YouTubeConnections | null>(null);
  const [channelId, setChannelId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try { setData(await getYouTubeConnections()); }
    catch { setError("YouTube連携の状態を取得できませんでした。"); }
  }, []);
  useEffect(() => {
    let active = true;
    getYouTubeConnections().then(result => { if (active) setData(result); })
      .catch(() => { if (active) setError("YouTube連携の状態を取得できませんでした。"); });
    return () => { active = false; };
  }, []);
  const syncing = data?.channels.some(channel => ["queued", "running"].includes(channel.latestRun?.status ?? "")) ?? false;
  useEffect(() => {
    if (!syncing) return;
    const timer = window.setInterval(() => void refresh(), 1500);
    return () => window.clearInterval(timer);
  }, [syncing, refresh]);
  async function connect(id: string) {
    setBusy(true); setError(null);
    try {
      const result = await startYouTubeConnection(id);
      window.location.assign(result.authorizationUrl);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "接続を開始できませんでした。"); setBusy(false); }
  }
  async function sync(id: number) {
    setBusy(true); setError(null);
    try { await syncYouTubeChannel(id); await refresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "同期を開始できませんでした。"); await refresh(); }
    finally { setBusy(false); }
  }
  return <section className="space-y-4" aria-labelledby="youtube-connection-heading">
    <h2 id="youtube-connection-heading" className="text-xl font-bold">YouTube連携</h2>
    <p className="text-sm">自分が管理するチャンネルの動画・統計を読み取ります。投稿・変更の権限は求めません。</p>
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
    {!data ? <p>接続状態を確認中…</p> : <>
      <p className="text-sm" aria-label="定時同期と分析">{automationLabel(data.automation)}</p>
      {!data.clientConfigured ? <p className="border border-amber-300 bg-amber-50 p-3 text-sm">
        GoogleのDesktopクライアント設定を storage/secrets/google-client.json に配置してください。
      </p> : null}
      <div className="flex flex-wrap items-end gap-3 border border-neutral-300 p-4">
        <label className="min-w-64 flex-1 text-sm">接続する自チャンネルのID（UCから始まる24文字）
          <input className="mt-1 block w-full border border-neutral-400 p-2" value={channelId} maxLength={24}
            onChange={event => setChannelId(event.target.value.trim())} placeholder="YouTube Studioで確認したチャンネルID" />
        </label>
        <button type="button" disabled={busy || !data.clientConfigured || !/^UC[A-Za-z0-9_-]{22}$/.test(channelId)}
          className="bg-sky-700 px-4 py-2 text-white disabled:opacity-40" onClick={() => void connect(channelId)}>接続する</button>
      </div>
      <p className="text-xs text-neutral-600">Googleで同じチャンネルを選び、YouTubeとAnalyticsの読み取りを両方許可してください。</p>
      <YouTubeConnectionList data={data} busy={busy} onConnect={id => void connect(id)} onSync={id => void sync(id)} />
      {data.channels.length === 0 ? <p className="text-sm">接続済みのチャンネルはありません。</p> : null}
      <p className="text-xs text-neutral-600">統計は最大{data.extendedStorage ? "36か月" : "30日"}保持し、
        タイトルなどは30日以内に更新できなければ削除します。利用条件の確認日: {data.reviewedAt}。
        <a href={data.policyReference} target="_blank" rel="noreferrer" className="ml-1 underline">YouTubeの利用条件</a>
      </p>
    </>}
  </section>;
}
