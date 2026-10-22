import { formatLabels, metricLabels, missingLabel, overviewMetrics, type DashboardVideo } from "../../lib/intelligenceDashboard";
import type { ProductionAggregates } from "../../lib/productionPerformance";
import { ProductionAggregatesTable } from "../ProductionPerformance";
import { MetricDisplay, ReportSource } from "./MetricDisplay";
import { youtubeSyncTime } from "../../lib/intelligence";

export function VideoPerformanceList({ videos, onSelect }: { videos: DashboardVideo[]; onSelect: (id: string) => void }) {
  return <section className="rounded border bg-white p-4" aria-label="動画別の寄与">
    <h2 className="text-lg font-bold">動画別の寄与（{videos.length}本）</h2>
    <p className="my-2 text-xs">各動画のYouTube公式値です。全体と取得範囲が異なるため、合算や構成比への置き換えはしていません。</p>
    <div className="max-h-[32rem] overflow-auto"><table className="w-full text-left text-sm"><thead className="bg-sky-50"><tr>
      <th className="p-2">動画</th><th>直近28日の再生</th><th>初期7日の再生</th><th>初期7日のエンゲージビュー</th></tr></thead>
      <tbody>{videos.map(video => <tr key={video.id} className="border-t align-top"><td className="max-w-md p-2">
        <button type="button" className="text-left text-sky-800 underline" onClick={() => onSelect(video.id)}>
          {video.title ?? video.id}</button><p className="mt-1 text-xs text-neutral-600">{formatLabels[video.format]} ／
          {video.durationBand === "unknown" ? "尺帯未確認" : video.durationBand}
          {video.production ? " ／ 制作記録あり" : ""}</p></td>
        <td className="p-2"><MetricDisplay metric={video.current.metrics.views} /></td>
        <td className="p-2"><MetricDisplay metric={video.first7.metrics.views} /></td>
        <td className="p-2"><MetricDisplay metric={video.first7.metrics.engagedViews} /></td></tr>)}</tbody></table></div>
    {videos.length === 0 ? <p>この形式の動画は未取得です。</p> : null}
  </section>;
}

export function VideoDetail({ video, aggregates, onClose }: {
  video: DashboardVideo; aggregates: ProductionAggregates | null; onClose: () => void;
}) {
  const production = video.production;
  const groups = aggregates?.groups.filter(group => video.aggregateGroupIds.includes(group.id)) ?? [];
  return <section id="video-detail" tabIndex={-1} className="scroll-mt-4 rounded border-2 border-sky-300 bg-white p-5"
    aria-label="動画詳細"><div className="flex justify-between gap-4"><h2 className="text-lg font-bold">{video.title ?? video.id}</h2>
      <button type="button" onClick={onClose} className="shrink-0 underline">詳細を閉じる</button></div>
    <p className="my-2 text-sm">{formatLabels[video.format]} ／ {video.durationSeconds ?? "未取得"}秒 ／
      公開: {video.publishedAt ? youtubeSyncTime(video.publishedAt) : "未取得"} <a className="ml-3 text-sky-800 underline"
        href={`https://www.youtube.com/watch?v=${encodeURIComponent(video.id)}`} target="_blank" rel="noreferrer">YouTubeで開く</a></p>
    <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th>指標</th>
      <th className="p-2">直近28日<ReportSource report={video.current} /></th>
      <th className="p-2">初期7日（公開翌日から）<ReportSource report={video.first7} /></th></tr></thead>
      <tbody>{[...overviewMetrics, "averageViewPercentage", "averageViewDuration", "likes"].map(metric => <tr key={metric} className="border-t">
        <th className="p-2">{metricLabels[metric]}</th><td className="p-2"><MetricDisplay metric={video.current.metrics[metric]} /></td>
        <td className="p-2"><MetricDisplay metric={video.first7.metrics[metric]} /></td></tr>)}</tbody></table></div>
    <h3 className="mt-5 font-semibold">結び付いた制作記録（自前データ）</h3>
    {!production ? <p className="text-sm">{missingLabel(video.productionMissing)}</p> : <div className="space-y-2 text-sm">
      <p>{production.characterPresetName ?? "キャラ未設定"} ／ {production.recordId}（revision {production.revision}）</p>
      <p>本編 {production.bodyDurationSeconds}秒 ／ 完成 {production.completedDurationSeconds}秒 ／
        フック映像 {production.hookSceneStart !== null && production.hookSceneEnd !== null ?
          `${production.hookSceneEnd - production.hookSceneStart}秒` : "なし"}</p>
      <p>フック文言: {production.hookText || "なし"}</p><p>intent: {production.titleCandidates.intent ?? "未設定"} ／
        投稿文の出所: {production.postMetadataSource ?? "未設定"} ／ 冒頭点: {production.selection.openingScore ?? "未記録"}</p>
      <p>選定理由: {production.selection.selectionReason ?? production.selection.reason ?? "未記録"}</p>
      <p>サムネ素材: {({ video_frame: "動画のコマ", character_asset: "予備素材", unknown: "未記録" })[production.thumbnail.source]
        ?? production.thumbnail.source}</p>
      <details><summary>タイトル候補と使用した制作ヒント</summary><ul className="list-inside list-disc">
        {production.titleCandidates.candidates.map(item => <li key={item.id}>{item.title}
          {item.id === production.titleCandidates.selectedId ? "（選択）" : ""}
          {item.id === production.titleCandidates.recommendedId ? "（推薦）" : ""}</li>)}</ul>
        {(production.performanceHints ?? []).map((hint, i) => <p key={i}>{hint.target}: {hint.text}（{hint.analysisId}）</p>)}</details>
    </div>}
    {aggregates && production ? <details className="mt-4 rounded border border-violet-200 bg-violet-50 p-3 text-sm">
      <summary>該当する独自集計グループ（{groups.length}件）</summary>
      {groups.length ? <ProductionAggregatesTable data={{ ...aggregates, groups }} /> : <p>該当グループは未集計です。</p>}
    </details> : null}
  </section>;
}
