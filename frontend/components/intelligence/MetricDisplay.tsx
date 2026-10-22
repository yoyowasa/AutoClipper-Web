import { metricText, missingLabel, numberLabel, type MetricValue, type NativeReport } from "../../lib/intelligenceDashboard";
import { youtubeSyncTime } from "../../lib/intelligence";

export function MetricDisplay({ metric }: { metric?: MetricValue }) {
  const missing = metric?.value === null || metric?.value === undefined;
  return <span><span className={missing ? "text-neutral-500" : "font-semibold tabular-nums"}>{metricText(metric)}</span>
    {missing ? <span className="block text-xs text-amber-800">{missingLabel(metric?.missingReason)}
      {metric?.observedSubtotal !== null && metric?.observedSubtotal !== undefined ?
        <span className="block">返却された分のみ: {numberLabel(metric.observedSubtotal)}</span> : null}</span> : null}</span>;
}

export function ReportSource({ report }: { report: NativeReport }) {
  return <div className="space-y-1 text-xs">
    <span className={`inline-block rounded px-2 py-1 ${report.source === "youtube_analytics" ?
      "bg-sky-100 text-sky-900" : "bg-violet-100 text-violet-900"}`}>
      {report.source === "youtube_analytics" ? "YouTube公式値" : "独自集計（返却済みの日次値）"}</span>
    <p>{report.start ?? "未取得"} 〜 {report.end ?? "未取得"}（America/Los_Angeles）</p>
    {report.expected !== null ? <p>返却済み {report.returned}/{report.expected} 動画×日</p> : null}
    <p>取得日時: {report.observedAt ? youtubeSyncTime(report.observedAt) : "未取得"}</p>
  </div>;
}
