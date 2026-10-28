"use client";
import { ChoiceEvaluations } from "./ChoiceEvaluations";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getYouTubeConnections, youtubeSyncLabel, type ConnectedYouTubeChannel } from "../../lib/intelligence";
import { adoptProposal, formatLabels, getDashboard, getTrials, metricLabels, overviewMetrics,
  type DashboardData, type DashboardFormat, type ImprovementTrial } from "../../lib/intelligenceDashboard";
import { getProductionAggregates, type ProductionAggregates } from "../../lib/productionPerformance";
import { ChannelAnalysisSettings } from "../ChannelAnalysisSettings";
import { ProductionAggregatesTable } from "../ProductionPerformance";
import { DailyChart } from "./DailyChart";
import { MetricDisplay, ReportSource } from "./MetricDisplay";
import { TrialPanel } from "./TrialPanel";
import { VideoDetail, VideoPerformanceList } from "./VideoPerformance";

export function Overview({ data }: { data: DashboardData }) {
  return <section className="space-y-3" aria-label="期間別の成績">
    <h2 className="text-lg font-bold">{formatLabels[data.format]}の成績</h2>
    <div className="grid gap-3 md:grid-cols-2">{(["current", "previous"] as const).map(period => <article key={period}
      className={`rounded border p-4 ${data[period].source === "youtube_analytics" ? "border-sky-200 bg-sky-50" : "border-violet-200 bg-violet-50"}`}>
      <h3 className="mb-2 font-semibold">{period === "current" ? "直近28日" : "前28日"}</h3><ReportSource report={data[period]} />
      <dl className="mt-4 grid grid-cols-2 gap-4">{overviewMetrics.map(metric => <div key={metric}>
        <dt className="text-xs text-neutral-600">{metricLabels[metric]}</dt>
        <dd className="mt-1 text-xl"><MetricDisplay metric={data[period].metrics[metric]} /></dd></div>)}</dl>
    </article>)}</div><p className="text-xs text-neutral-600">{data.scopeNote}</p>
    <p className="text-xs">形式未確認 {data.unknownFormatCount}本 ／ 期限切れ・利用不可のため一覧対象外 {data.excludedMetadataCount}本</p>
  </section>;
}

function ChannelDashboard({ channel }: { channel: ConnectedYouTubeChannel }) {
  const [format, setFormat] = useState<DashboardFormat>("all");
  const [data, setData] = useState<DashboardData | null>(null);
  const [allData, setAllData] = useState<DashboardData | null>(null);
  const [aggregates, setAggregates] = useState<ProductionAggregates | null>(null);
  const [aggregateError, setAggregateError] = useState("");
  const [trials, setTrials] = useState<ImprovementTrial[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [adopting, setAdopting] = useState(false);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(async () => { setRevision(value => value + 1); }, []);
  const analysisFinished = useCallback(() => { setRevision(value => value + 1); }, []);
  useEffect(() => {
    let active = true;
    Promise.all([getDashboard(channel.id, "all"), getTrials(channel.id)]).then(([all, plans]) => {
      if (active) { setAllData(all); setTrials(plans); setError(""); }
    }).catch(caught => { if (active) setError(caught instanceof Error ? caught.message : "分析データを取得できませんでした。"); });
    getProductionAggregates(channel.id).then(value => { if (active) { setAggregates(value); setAggregateError(""); } })
      .catch(caught => { if (active) setAggregateError(caught instanceof Error ? caught.message : "独自集計を取得できませんでした。"); });
    return () => { active = false; };
  }, [channel.id, revision]);
  useEffect(() => {
    let active = true;
    getDashboard(channel.id, format).then(value => { if (active) { setData(value); setError(""); } })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : "統計を取得できませんでした。"); });
    return () => { active = false; };
  }, [channel.id, format, revision]);
  function selectVideo(id: string) {
    if (!allData?.videos.some(video => video.id === id)) {
      setError("根拠動画は現在の一覧にありません。メタデータの期限・同期状態を確認してください。"); return;
    }
    setSelectedId(id);
    window.requestAnimationFrame(() => { document.getElementById("video-detail")?.focus();
      document.getElementById("video-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }); });
  }
  async function adopt(analysisId: string, proposalId: string) {
    setAdopting(true); setError("");
    try {
      await adoptProposal(channel.id, analysisId, proposalId);
      await refresh(); setNotice("改善試験を作成しました。投稿後に対象動画を選び、初期7日を比較できます。");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "採用できませんでした。"); }
    finally { setAdopting(false); }
  }
  const visible = data?.format === format ? data : null;
  const selected = allData?.videos.find(video => video.id === selectedId);
  return <div className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3"><fieldset className="flex gap-2" aria-label="表示する形式">
      {(["all", "shorts", "long"] as const).map(value => <button type="button" key={value} aria-pressed={format === value}
        className={`rounded border px-5 py-2 ${format === value ? "bg-sky-800 text-white" : "bg-white"}`}
        onClick={() => setFormat(value)}>{formatLabels[value]}</button>)}</fieldset>
      <button className="text-sm underline" type="button" onClick={() => void refresh()}>保存済みデータを読み直す</button></div>
    <p className="text-xs text-neutral-600">{youtubeSyncLabel(channel.latestRun)}。ページ閲覧・形式切替では同期やCodex分析を開始しません。</p>
    {error ? <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-red-800">{error}</p> : null}
    {notice ? <p role="status" className="rounded bg-emerald-50 p-3 text-emerald-900">{notice} <a href="#improvement-trials" className="underline">改善試験へ</a></p> : null}
    {visible ? <><Overview data={visible} /><DailyChart reports={visible.daily} />
      <VideoPerformanceList videos={visible.videos} onSelect={selectVideo} /></> : <p>保存済みの統計を読み込み中…</p>}
    {selected ? <VideoDetail video={selected} aggregates={aggregates} onClose={() => setSelectedId(null)} /> : null}
    <section id="self-analysis" className="rounded border bg-white p-5" aria-label="自己分析と履歴">
      <ChannelAnalysisSettings channelId={channel.id} connected={channel.connectionStatus === "connected"}
        syncActive={["queued", "running"].includes(channel.latestRun?.status ?? "")} full videos={allData?.videos ?? []}
        trials={trials} onAdopt={(analysisId, proposalId) => void adopt(analysisId, proposalId)} onVideo={selectVideo}
        adopting={adopting} onFinished={analysisFinished} />
    </section>
    <TrialPanel trials={trials} videos={allData?.videos ?? []} onRefresh={refresh} onVideo={selectVideo} />
    <section id="production-performance" className="rounded border border-violet-200 bg-violet-50 p-5" aria-label="制作属性の独自集計">
      <h2 className="font-bold">独自集計（制作属性別）</h2>
      <p className="my-2 text-sm">YouTube公式のチャンネル集計ではありません。初期7日の動画ごとの観測値の中央値と同形式の中央値との比です。
        5本未満はデータ不足。平均視聴率・時間は全視聴者の合算平均ではありません。因果効果は未確定です。</p>
      {aggregateError ? <p role="alert">{aggregateError}</p> : null}
      <details><summary>集計表を開く（{aggregates?.groups.length ?? 0}グループ）</summary>
        {aggregates ? <ProductionAggregatesTable data={aggregates} /> : <p>未取得</p>}</details>
    </section>
    <ChoiceEvaluations data={aggregates?.choice_evaluations} videos={allData?.videos ?? []} onVideo={selectVideo} />
  </div>;
}

export function IntelligenceDashboard() {
  const [channels, setChannels] = useState<ConnectedYouTubeChannel[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let active = true;
    getYouTubeConnections().then(result => {
      if (!active) return;
      setChannels(result.channels);
      const id = Number(new URLSearchParams(window.location.search).get("channel"));
      setSelected(result.channels.some(channel => channel.id === id) ? id : result.channels[0]?.id ?? null);
      setLoaded(true);
    }).catch(caught => { if (active) { setError(caught instanceof Error ? caught.message : "チャンネルを取得できませんでした。"); setLoaded(true); } });
    return () => { active = false; };
  }, []);
  const channel = channels.find(item => item.id === selected);
  return <main className="mx-auto max-w-7xl space-y-6 p-4 md:p-8">
    <header className="space-y-3"><div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-2xl font-bold">チャンネル分析・改善試験</h1><Link href="/settings" className="text-sm underline">YouTube連携の設定</Link></div>
      <nav className="flex flex-wrap gap-4 text-sm text-sky-800"><a href="#self-analysis" className="underline">自己分析・提案</a>
        <a href="#improvement-trials" className="underline">改善試験</a><a href="#production-performance" className="underline">独自集計</a>
        <Link href="/upload" className="underline">動画作成へ</Link></nav>
      <label className="block text-sm">チャンネル<select aria-label="チャンネル" className="ml-3 min-w-64 rounded border bg-white p-2"
        value={selected ?? ""} onChange={e => { const id = Number(e.target.value); setSelected(id);
          window.history.replaceState(null, "", `/intelligence?channel=${id}`); }}>
        {channels.map(item => <option key={item.id} value={item.id}>{item.name ?? item.externalId}</option>)}</select></label>
    </header>
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
    {channel ? <ChannelDashboard key={channel.id} channel={channel} /> : <p>{loaded ? "設定画面で自チャンネルを接続してください。" : "チャンネルを読み込み中…"}</p>}
  </main>;
}
