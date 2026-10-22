"use client";
import { useState } from "react";
import { metricLabels, overviewMetrics, type NativeReport } from "../../lib/intelligenceDashboard";
import { MetricDisplay } from "./MetricDisplay";

export function chartSegments(reports: NativeReport[], metric: string, partial = false): string[] {
  const values = reports.map(report => partial ? report.metrics[metric]?.observedSubtotal ?? null : report.metrics[metric]?.value ?? null);
  const domain = reports.flatMap(report => [report.metrics[metric]?.value, report.metrics[metric]?.observedSubtotal])
    .filter((value): value is number => value !== null && value !== undefined);
  const max = Math.max(1, ...domain);
  const min = Math.min(0, ...domain);
  const segments: string[] = [];
  let current: string[] = [];
  values.forEach((value, i) => {
    if (value === null) { if (current.length) segments.push(current.join(" ")); current = []; }
    else current.push(`${24 + 752 * i / Math.max(1, values.length - 1)},${178 - 150 * (value - min) / (max - min)}`);
  });
  if (current.length) segments.push(current.join(" "));
  return segments;
}

export function DailyChart({ reports }: { reports: NativeReport[] }) {
  const [metric, setMetric] = useState("views");
  const segments = chartSegments(reports, metric);
  const partials = chartSegments(reports, metric, true);
  const domain = reports.flatMap(report => [report.metrics[metric]?.value, report.metrics[metric]?.observedSubtotal])
    .filter((value): value is number => value !== null && value !== undefined);
  return <section className="rounded border bg-white p-4" aria-label="日別推移">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-bold">日別推移</h2>
      <label className="text-sm">表示する指標 <select className="border p-2" value={metric} onChange={e => setMetric(e.target.value)}>
        {overviewMetrics.map(key => <option key={key} value={key}>{metricLabels[key]}</option>)}</select></label></div>
    <p className="mt-2 text-xs text-neutral-600">左28日は前期間、右28日は直近。未取得の日は線をつなぎません。時刻は米国太平洋時間です。</p>
    <p className="text-xs text-neutral-600">青: 取得済みの値。橙の点線: 一部だけ返却された値の小計（独自集計・全体値ではありません）。</p>
    <svg viewBox="0 0 800 205" className="mt-3 w-full" role="img" aria-label={`${metricLabels[metric]}の日別推移`}>
      <rect x="24" y="16" width="376" height="162" fill="#f5f5f5" />
      <line x1="400" y1="16" x2="400" y2="178" stroke="#a3a3a3" strokeDasharray="4 4" />
      <line x1="24" y1="178" x2="776" y2="178" stroke="#d4d4d4" />
      {segments.map((points, index) => <polyline key={index} points={points} fill="none" stroke="#0369a1" strokeWidth="2" />)}
      {segments.flatMap((points, i) => points.split(" ").map((point, j) => {
        const [x, y] = point.split(","); return <circle key={`${i}-${j}`} cx={x} cy={y} r="2" fill="#0369a1" />;
      }))}
      {partials.map((points, index) => <polyline key={`partial-${index}`} points={points} fill="none" stroke="#b45309"
        strokeWidth="2" strokeDasharray="4 4" />)}
      {partials.flatMap((points, i) => points.split(" ").map((point, j) => {
        const [x, y] = point.split(","); return <circle key={`partial-${i}-${j}`} cx={x} cy={y} r="2" fill="#b45309" />;
      }))}
      <text x="28" y="26" fontSize="11">{Math.max(1, ...domain).toLocaleString("ja-JP")}</text>
      <text x="28" y="174" fontSize="11">{Math.min(0, ...domain).toLocaleString("ja-JP")}</text>
      <text x="24" y="199" fontSize="12">{reports[0]?.start}</text><text x="660" y="199" fontSize="12">{reports.at(-1)?.end}</text>
    </svg>
    {segments.length === 0 ? <p>{partials.length ? "全体の日別値は未取得です。返却された分のみ表示しています。" : "日別値は未取得です。"}</p> : null}
    <details className="mt-2 text-sm"><summary>日別の値と欠損理由を表で確認</summary><div className="max-h-72 overflow-auto">
      <table className="w-full text-left"><thead><tr><th>日付</th><th>{metricLabels[metric]}</th></tr></thead><tbody>
        {reports.map((report, i) => <tr key={i} className="border-t"><td className="p-2">{report.start}</td>
          <td><MetricDisplay metric={report.metrics[metric]} /></td></tr>)}</tbody></table></div></details>
  </section>;
}
