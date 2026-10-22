"use client";

import { useEffect, useState } from "react";
import { getProductionAggregates, type PerformanceHint, type ProductionAggregates } from "../lib/productionPerformance";

const dimensions: Record<string, string> = { all: "全体", duration: "本編の尺（秒/min=分）", hook_scene: "フック映像",
  hook_text: "フック文言", title_intent: "タイトルintent", post_metadata_source: "投稿文の出所", opening_score: "冒頭点の帯" };
const metrics = { views: "再生数", averageViewPercentage: "平均視聴率(%)", averageViewDuration: "平均視聴時間(秒)",
  likes: "高評価", subscribersGained: "登録者獲得" };
const valueLabel = (value: string) => ({ yes: "あり", no: "なし", unknown: "未設定/不明", all: "全体" })[value] ?? value;
const number = (value: number | null) => value === null ? "—" : value.toLocaleString("ja-JP", { maximumFractionDigits: 2 });

export function ProductionAggregatesTable({ data }: { data: ProductionAggregates }) {
  return <><p>結び付き{data.linked_videos}本 ／ 有効な初期7日・制作情報がない対象{data.excluded_linked_videos}本。
    属性ごとに同じ動画が含まれるため、行の本数は合算しません。</p>
    <p className="text-xs">集計日時: {new Date(data.generated_at).toLocaleString("ja-JP")} ／
      保持期限: {new Date(data.expires_at).toLocaleString("ja-JP")}</p>
    <div className="overflow-x-auto"><table className="w-full border-collapse text-xs"><thead><tr>
      <th>キャラ/形式</th><th>切り口</th><th>本数/状態</th>{Object.values(metrics).map(label => <th key={label}>{label} ／ 同形式比（観測数）</th>)}
    </tr></thead><tbody>{data.groups.map(group => <tr className="border-t" key={group.id}>
      <td>{group.character_preset_name} ／ {group.format === "short" ? "ショート" : "通常"}</td>
      <td>{dimensions[group.dimension] ?? group.dimension}: {valueLabel(group.value)}</td>
      <td>{group.count}本 ／ {group.sufficient ? "観測あり" : "データ不足"}</td>
      {Object.keys(metrics).map(metric => { const value = group.metrics[metric]; return <td key={metric} className="p-2">
        {number(value.median)} ／ {number(value.relative_to_channel_median)}（n={value.count}）</td>; })}
    </tr>)}</tbody></table></div></>;
}

export function PerformanceHintsList({ hints = [] }: { hints?: PerformanceHint[] }) {
  return <section className="space-y-2" aria-label="制作ヒント">
    <h5 className="font-semibold">制作ヒント（独自集計からの参考・効果未検証）</h5>
    {hints.length === 0 ? <p>ヒントはありません。データ不足のグループからは作成しません。</p> : hints.map((hint, index) =>
      <div key={index} className="border p-2"><p>{hint.character_preset_name} ／ {hint.format === "short" ? "ショート" : "通常"} ／
        {hint.target === "selection" ? "選定" : "タイトル・フック"}</p><p className="whitespace-pre-wrap">{hint.text}</p>
        <p className="text-xs">根拠: {hint.evidence_groups.map(group => `${group.group_id}（${group.count}本）`).join("、")} ／
          確度: {hint.confidence === "low" ? "低" : "中"}</p>
        <details className="text-xs"><summary>根拠動画ID</summary>{hint.video_ids.join("、")}</details>
      </div>)}
  </section>;
}

export function ProductionPerformance({ channelId, revision }: { channelId: number; revision?: string | null }) {
  const [data, setData] = useState<ProductionAggregates | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getProductionAggregates(channelId).then(value => { if (active) { setData(value); setError(""); } })
      .catch(() => { if (active) setError("独自集計を取得できませんでした。"); });
    return () => { active = false; };
  }, [channelId, revision]);
  const current = data?.channel_id === channelId ? data : null;
  return <details className="space-y-2 text-sm" aria-label="制作属性の独自集計">
    <summary className="cursor-pointer font-semibold">独自集計（制作属性別・YouTube公式集計とは異なります）</summary>
    <p>初期7日の動画ごとの観測値の中央値と、同じチャンネル・形式の中央値に対する比です。因果効果ではありません。
      平均視聴率・時間の中央値は全視聴者を合算した平均ではありません。欠損・比較先が0の比は「—」。5本未満はデータ不足。
      分析開始時に集計を更新・保存します。</p>
    {error ? <p role="alert">{error}</p> : null}
    {current ? <ProductionAggregatesTable data={current} /> : !error ? <p>集計を取得中…</p> : null}
  </details>;
}
