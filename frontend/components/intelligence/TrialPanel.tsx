"use client";
import { useState } from "react";
import { deleteTrial, saveTrial, trialDraft, metricLabels, missingLabel, type DashboardVideo,
  type ImprovementTrial, type TrialDraft } from "../../lib/intelligenceDashboard";
import { MetricDisplay, ReportSource } from "./MetricDisplay";
import { youtubeSyncTime } from "../../lib/intelligence";

export function TrialComparison({ trial, onVideo }: { trial: ImprovementTrial; onVideo: (id: string) => void }) {
  return <div className="space-y-2 text-sm">
    <p className="font-semibold">主要指標: {metricLabels[trial.primaryMetric]} ／ 公開翌日から7暦日（America/Los_Angeles）</p>
    <div className="grid gap-3 md:grid-cols-2">{(["baseline", "target"] as const).map(key => {
      const video = trial[key]; return <div key={key} className="rounded border bg-sky-50 p-3">
        <h4 className="font-semibold">{key === "baseline" ? "基準動画" : "変更した動画"}</h4>
        {video ? <><button className="my-1 text-left text-sky-800 underline" onClick={() => onVideo(video.id)}>
          {video.title ?? video.id}</button><p>{video.durationBand === "unknown" ? "尺帯未確認" : video.durationBand}</p><ReportSource report={video.first7} />
          <dl className="mt-3 space-y-2">{[trial.primaryMetric, ...["views", "engagedViews", "averageViewPercentage",
            "averageViewDuration", "subscribersGained"].filter(metric => metric !== trial.primaryMetric)].map(metric => <div key={metric}
            className="flex justify-between gap-3"><dt>{metricLabels[metric]}</dt><dd><MetricDisplay metric={video.first7.metrics[metric]} /></dd></div>)}</dl>
        </> : <p>未取得・未指定</p>}</div>;
    })}</div>
    {trial.comparisonIssues.map(code => <p key={code} className="text-amber-900">{missingLabel(code)}（{code}）</p>)}
    {trial.direction ? <p>観測値は{({ increase: "増加", decrease: "減少", same: "同値" })[trial.direction]}。効果は未確定です。</p> : null}
    {trial.recordedAfterPublication ? <p className="text-amber-900">事後記録: 変更内容・判定条件は対象動画の公開後に登録または編集されています。</p> : null}
    <p className="text-neutral-600">{trial.causalVerdict}</p>
  </div>;
}

function TrialEditor({ trial, videos, onSaved, onCancel }: {
  trial: ImprovementTrial; videos: DashboardVideo[]; onSaved: () => Promise<void>; onCancel: () => void;
}) {
  const [draft, setDraft] = useState<TrialDraft>(() => trialDraft(trial));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save() {
    setBusy(true); setError("");
    try { await saveTrial(trial.channelId, trial.id, draft); await onSaved(); onCancel(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "保存できませんでした。"); }
    finally { setBusy(false); }
  }
  return <form className="mt-4 space-y-3 border-t pt-4" onSubmit={e => { e.preventDefault(); void save(); }}>
    <label className="block text-sm">基準動画<select className="block w-full border p-2" value={draft.baselineVideoId}
      onChange={e => setDraft({ ...draft, baselineVideoId: e.target.value })}>
      {!videos.some(video => video.id === draft.baselineVideoId) ? <option value={draft.baselineVideoId}>未取得: {draft.baselineVideoId}</option> : null}
      {videos.map(video => <option key={video.id} value={video.id}>{video.title ?? video.id}</option>)}</select></label>
    <label className="block text-sm">変更を入れて投稿した動画（制作記録との結び付きが必要）
      <select className="block w-full border p-2" value={draft.targetVideoId ?? ""}
        onChange={e => setDraft({ ...draft, targetVideoId: e.target.value || null })}>
        <option value="">投稿後に選ぶ</option>
        {draft.targetVideoId && !videos.some(video => video.id === draft.targetVideoId && video.production) ?
          <option value={draft.targetVideoId}>未取得・結び付きなし: {draft.targetVideoId}</option> : null}
        {videos.filter(video => video.production && video.id !== draft.baselineVideoId).map(video =>
          <option key={video.id} value={video.id}>{video.title ?? video.id}</option>)}</select></label>
    {(["changeNote", "keepFixed", "rejectionCondition", "resultCheck"] as const).map(key => <label key={key} className="block text-sm">
      {{ changeNote: "変える1点", keepFixed: "固定すること", rejectionCondition: "反証・不採用の条件", resultCheck: "結果の確認方法" }[key]}
      <textarea className="block w-full border p-2" rows={2} maxLength={key === "resultCheck" ? 1200 : 1000}
        required={key === "changeNote" || key === "rejectionCondition"} value={draft[key]}
        onChange={e => setDraft({ ...draft, [key]: e.target.value })} /></label>)}
    <div className="flex gap-3"><label>主要指標<select className="ml-2 border p-2" value={draft.primaryMetric}
      onChange={e => setDraft({ ...draft, primaryMetric: e.target.value as TrialDraft["primaryMetric"] })}>
      {["views", "engagedViews", "averageViewPercentage", "averageViewDuration", "subscribersGained"].map(metric =>
        <option key={metric} value={metric}>{metricLabels[metric]}</option>)}</select></label>
      <label>状態<select className="ml-2 border p-2" value={draft.status}
        onChange={e => setDraft({ ...draft, status: e.target.value as TrialDraft["status"] })}>
        <option value="active">試験中</option><option value="closed">終了</option></select></label></div>
    <p className="text-xs text-neutral-600">変える内容・基準・指標・判定条件を変更すると、試験の登録日時を更新します。</p>
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
    <div className="flex gap-3"><button disabled={busy} className="bg-sky-800 px-4 py-2 text-white disabled:opacity-40">改善試験を保存</button>
      <button type="button" disabled={busy} onClick={onCancel} className="border px-4 py-2">キャンセル</button></div>
  </form>;
}

export function TrialPanel({ trials, videos, onRefresh, onVideo }: {
  trials: ImprovementTrial[]; videos: DashboardVideo[]; onRefresh: () => Promise<void>; onVideo: (id: string) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove(trial: ImprovementTrial) {
    if (!window.confirm("この改善試験の記録を削除します。動画・分析・制作記録は残ります。")) return;
    setBusy(true); setError("");
    try { await deleteTrial(trial.channelId, trial.id); await onRefresh(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "削除できませんでした。"); }
    finally { setBusy(false); }
  }
  return <section id="improvement-trials" className="space-y-4 rounded border bg-white p-5" aria-label="改善試験">
    <h2 className="text-lg font-bold">改善試験（{trials.length}件）</h2>
    <p className="text-sm">分析の提案を採用し、次の1本で変えることを記録します。投稿後に対象動画を結び付けて比較します。</p>
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
    {trials.length === 0 ? <p>採用した提案はありません。</p> : trials.map(trial => <article key={trial.id} className="space-y-3 rounded border p-4">
      <h3 className="font-semibold">{trial.changeNote} <span className="text-xs">（{trial.status === "active" ? "試験中" : "終了"}）</span></h3>
      <p className="text-sm">固定すること: {trial.keepFixed || "未指定"}<br />反証・不採用の条件: {trial.rejectionCondition}<br />
        確認方法: {trial.resultCheck || "未指定"}</p><p className="text-xs">登録: {youtubeSyncTime(trial.registeredAt)}</p>
      <TrialComparison trial={trial} onVideo={onVideo} />
      <div className="flex gap-3"><button type="button" className="border px-3 py-2" onClick={() => setEditing(trial.id)}>編集・対象動画を選ぶ</button>
        <button type="button" className="border px-3 py-2 text-red-700 disabled:opacity-40" disabled={busy}
          onClick={() => void remove(trial)}>試験を削除</button></div>
      {editing === trial.id ? <TrialEditor key={trial.updatedAt} trial={trial} videos={videos} onSaved={onRefresh}
        onCancel={() => setEditing(null)} /> : null}
    </article>)}
  </section>;
}
