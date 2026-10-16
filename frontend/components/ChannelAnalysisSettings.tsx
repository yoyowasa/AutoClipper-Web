"use client";

import { useCallback, useEffect, useState } from "react";
import { getChannelAnalysis, startChannelAnalysis, analysisStatus,
  type AnalysisHistory, type AnalysisReview, type AnalysisValidationReport, type SyncBeforeAnalysis } from "../lib/channelAnalysis";
import { youtubeSyncTime } from "../lib/intelligence";

const formatLabel = { all: "全体", shorts: "ショート", videoondemand: "通常" };
const surfaceLabel = { shorts_feed: "Shortsフィード", home: "ホーム", up_next: "次の動画", search: "検索", multi_surface: "複数の表示面" };

const validationReasons: Record<string, string> = {
  EVIDENCE_UNKNOWN: "存在しない根拠ID", BASELINE_FORMAT_MISMATCH: "基準動画の形式が不一致",
  BASELINE_FORMAT_UNKNOWN: "基準動画の形式が不明", BASELINE_NOT_FOUND: "基準動画がない",
  PRIMARY_METRIC_INVALID: "評価指標が不正", SCHEMA_INVALID: "項目の形式が不正",
  BASELINE_EVIDENCE_MISSING: "基準動画の根拠が不足", FINDING_FORMAT_MISMATCH: "所見と根拠動画の形式が不一致",
  RECOMMENDATION_LINK_REQUIRED: "推薦面との関係が未指定", DUPLICATE_ITEM: "項目IDが重複",
  NO_VALID_FINDINGS: "有効な所見がない", REVIEW_ID_MISMATCH: "分析IDが不一致",
  CHANNEL_MISMATCH: "チャンネルが不一致", BATCH_MISMATCH: "同期IDが不一致", FRAMEWORK_MISMATCH: "分析基準が不一致",
};

export function AnalysisValidationText({ validation }: { validation?: AnalysisValidationReport | null }) {
  if (!validation || validation.issues.length === 0) return null;
  return <div className="space-y-1 text-sm text-amber-900" aria-label="分析の検証結果">
    <p>{validation.fatal ? "分析全体を保存できませんでした。" : "有効な部分を保存しました。"}
      除外: 所見{validation.excludedFindings}件・提案{validation.excludedProposals}件</p>
    <ul>{Object.entries(validation.reasonCounts).map(([code, count]) =>
      <li key={code}>{validationReasons[code] ?? code}（{code}）: {count}件</li>)}</ul>
    <details><summary>該当項目</summary><ul>{validation.issues.map((issue, index) =>
      <li key={index}>{issue.code}: {issue.loc.join(".") || "全体"}</li>)}</ul></details>
  </div>;
}

export function AnalysisReviewText({ review }: { review: AnalysisReview }) {
  return <div className="space-y-3 text-sm">
    <h5 className="font-semibold">{review.title}</h5><p className="whitespace-pre-wrap">{review.summary}</p>
    <p className="text-xs text-neutral-600">統計・タイトル・制作記録からの分析です。動画本編の視聴や改善効果の検証は行っていません。</p>
    <ul className="list-inside list-disc text-amber-900">{review.limitations.map((value, index) => <li key={index}>{value}</li>)}</ul>
    <h5 className="font-semibold">所見・仮説</h5>
    {review.findings.map(finding => <details key={finding.id} className="border p-3">
      <summary>{formatLabel[finding.format]}：{finding.title}</summary>
      <dl className="mt-2 space-y-1 whitespace-pre-wrap">
        <dt className="font-semibold">観測</dt><dd>{finding.observation}</dd>
        <dt className="font-semibold">仮説</dt><dd>{finding.hypothesis}</dd>
        <dt className="font-semibold">別の説明</dt><dd>{finding.alternatives.join(" ／ ")}</dd>
        <dt className="font-semibold">反対証拠</dt><dd>{finding.counter_evidence}</dd>
        <dt className="font-semibold">次の確認</dt><dd>{finding.next_check}</dd>
      </dl><p className="mt-2 text-xs">確度: {finding.confidence === "low" ? "低" : "中"} ／ 根拠: {finding.evidence_ids.join(", ")}</p>
    </details>)}
    <h5 className="font-semibold">次の動画案（未採用・効果未確認）</h5>
    {review.proposals.map(proposal => <details key={proposal.id} className="border p-3">
      <summary>{formatLabel[proposal.format]}：{proposal.title}</summary>
      <dl className="mt-2 space-y-1 whitespace-pre-wrap">
        <dt className="font-semibold">理由・目標への仮説</dt><dd>{proposal.reason} ／ {proposal.goal_path}</dd>
        <dt className="font-semibold">探す素材</dt><dd>{proposal.material_to_find}</dd>
        <dt className="font-semibold">タイトル案</dt><dd>{proposal.title_candidates.join(" ／ ")}</dd>
        <dt className="font-semibold">冒頭</dt><dd>{proposal.hook}</dd>
        <dt className="font-semibold">予定構成</dt><dd>{proposal.structure.map(step => `${step.start}〜${step.end}秒: ${step.action}`).join("\n")}</dd>
        <dt className="font-semibold">変える1点</dt><dd>{proposal.change_one}</dd>
        <dt className="font-semibold">固定すること</dt><dd>{proposal.keep_fixed}</dd>
        <dt className="font-semibold">確認・不採用条件</dt><dd>{proposal.result_check} ／ {proposal.rejection_condition}</dd>
      </dl>
      {proposal.recommendation_link ? <p className="mt-2">推薦面: {surfaceLabel[proposal.recommendation_link.surface]} ／
        {proposal.recommendation_link.viewer_need}<br />{proposal.recommendation_link.signal_hypothesis}<br />
        未取得の根拠: {proposal.recommendation_link.evidence_gap}</p> : null}
      <p className="mt-2 text-xs">根拠: {proposal.evidence_ids.join(", ")}</p>
    </details>)}
    {review.proposals.length === 0 ? <p>提案できる根拠が不足しています。制約の記録を確認してください。</p> : null}
  </div>;
}

export function ChannelAnalysisSettings({ channelId, connected, syncActive }: {
  channelId: number; connected: boolean; syncActive: boolean;
}) {
  const [data, setData] = useState<AnalysisHistory | null>(null);
  const [mode, setMode] = useState<SyncBeforeAnalysis>("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => { setData(await getChannelAnalysis(channelId)); }, [channelId]);
  useEffect(() => {
    let active = true;
    getChannelAnalysis(channelId).then(value => { if (active) setData(value); })
      .catch(() => { if (active) setError("分析状態を取得できませんでした。"); });
    return () => { active = false; };
  }, [channelId]);
  const active = data?.latestRun?.status === "queued" || data?.latestRun?.status === "running";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => { void refresh().catch(() => setError("分析状態を取得できませんでした。")); }, 2000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  async function start() {
    setBusy(true); setError(null);
    try {
      await startChannelAnalysis(channelId, mode);
      await refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "分析を開始できませんでした。"); }
    finally { setBusy(false); }
  }
  return <section className="mt-4 space-y-3 border-t pt-3" aria-label="Codex自己分析">
    <h4 className="font-semibold">Codex自己分析（gpt-6-astra / high）</h4>
    <label className="block text-sm">分析前の同期
      <select className="ml-2 border p-2" value={mode} disabled={busy || active}
        onChange={event => setMode(event.target.value as SyncBeforeAnalysis)}>
        <option value="auto">24時間以上経過していれば同期（既定）</option>
        <option value="always">同期してから分析</option><option value="never">保存済みの統計で分析</option>
      </select>
    </label>
    <button type="button" disabled={busy || active || syncActive || !connected}
      className="border px-3 py-2 disabled:opacity-40" onClick={() => void start()}>分析する</button>
    <p className="text-sm" aria-live="polite">{analysisStatus(data?.latestRun ?? null)}</p>
    {error || data?.latestRun?.errorMessage ? <p role="alert" className="text-sm text-red-700">{error ?? data?.latestRun?.errorMessage}</p> : null}
    <AnalysisValidationText validation={data?.latestRun?.validation} />
    {data?.latestResult?.review ? <>
      <p className="text-xs">最新の保存済み分析: {youtubeSyncTime(data.latestResult.finishedAt)} ／
        保持期限: {youtubeSyncTime(data.latestResult.expiresAt)}</p>
      {data.latestResult.id !== data.latestRun?.id ? <AnalysisValidationText validation={data.latestResult.validation} /> : null}
      <AnalysisReviewText review={data.latestResult.review} />
    </> : null}
    {data && data.history.length > 0 ? <details className="text-sm"><summary>分析履歴（{data.history.length}件）</summary>
      {data.history.map(run => <details key={run.id} className="mt-2 border p-2">
        <summary>{youtubeSyncTime(run.queuedAt)}：{analysisStatus(run)}</summary>
        <p>{run.model} / {run.reasoning} ／ {run.errorMessage ?? ""}</p>
        <AnalysisValidationText validation={run.validation} />
        {run.review ? <AnalysisReviewText review={run.review} /> : null}
      </details>)}
    </details> : null}
  </section>;
}
