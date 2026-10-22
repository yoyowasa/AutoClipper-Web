import { request } from "./intelligence";
import type { AnalysisProposal } from "./channelAnalysis";

export type DashboardFormat = "all" | "shorts" | "long";
export type MetricValue = { value: number | null; missingReason: string | null; observedSubtotal: number | null };
export type NativeReport = {
  source: "youtube_analytics" | "independent_aggregation"; start: string | null; end: string | null;
  observedAt: string | null; metrics: Record<string, MetricValue>; reason: string | null;
  expected: number | null; returned: number | null; format: string;
};
export type ProductionSummary = {
  recordId: string; revision: number; characterPresetName: string | null; type: "short" | "normal";
  bodyDurationSeconds: number; completedDurationSeconds: number; publicationTitle: string;
  hookText: string | null; hookSceneStart: number | null; hookSceneEnd: number | null;
  postMetadataSource: string | null; titleCandidates: { selectedId: string | null; recommendedId: string | null;
    intent: string | null; candidates: Array<{ id: string; title: string; intent: string | null }> };
  selection: { reason?: string; selectionReason?: string; openingScore?: number | null; topicKey?: string | null };
  thumbnail: { source: string };
  performanceHints?: Array<{ analysisId: string; generatedAt: string; target: string; text: string }>;
};
export type DashboardVideo = {
  id: string; title: string | null; publishedAt: string | null; durationSeconds: number | null; format: string;
  durationBand: string; current: NativeReport; first7: NativeReport; production: ProductionSummary | null;
  productionMissing: string | null; aggregateGroupIds: string[];
};
export type DashboardData = {
  channelId: number; format: DashboardFormat; lastReportDate: string | null; syncRunId: string | null;
  current: NativeReport; previous: NativeReport; daily: NativeReport[]; videos: DashboardVideo[];
  excludedMetadataCount: number; unknownFormatCount: number; scopeNote: string;
};
export type TrialVideo = Pick<DashboardVideo, "id" | "title" | "publishedAt" | "format" | "durationBand" | "first7">;
export type ImprovementTrial = {
  id: string; channelId: number; analysisId: string; proposalId: string; baselineVideoId: string; targetVideoId: string | null;
  changeNote: string; keepFixed: string; primaryMetric: AnalysisProposal["primary_metric"]; rejectionCondition: string;
  resultCheck: string; status: "active" | "closed"; createdAt: string; registeredAt: string; updatedAt: string;
  baseline: TrialVideo | null; target: TrialVideo | null; comparisonIssues: string[];
  direction: "increase" | "decrease" | "same" | null; recordedAfterPublication: boolean; causalVerdict: string;
};
export type TrialDraft = Pick<ImprovementTrial, "baselineVideoId" | "targetVideoId" | "changeNote" | "keepFixed" |
  "primaryMetric" | "rejectionCondition" | "resultCheck" | "status"> & { expectedUpdatedAt: string };

export const getDashboard = (id: number, format: DashboardFormat) => request<DashboardData>(`/channels/${id}/dashboard?format=${format}`);
export const getTrials = (id: number) => request<ImprovementTrial[]>(`/channels/${id}/trials`);
export const getEvidenceVideos = (id: number, analysisId: string) => request<{ evidenceVideos: Record<string, string[]> }>(
  `/channels/${id}/analysis/${encodeURIComponent(analysisId)}/evidence-videos`);
export const adoptProposal = (id: number, analysisId: string, proposalId: string) => request<ImprovementTrial>(
  `/channels/${id}/analysis/${encodeURIComponent(analysisId)}/proposals/${encodeURIComponent(proposalId)}/adopt`, { method: "POST" });
export const saveTrial = (id: number, trialId: string, draft: TrialDraft) => request<ImprovementTrial>(
  `/channels/${id}/trials/${encodeURIComponent(trialId)}`, { method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft) });
export const deleteTrial = (id: number, trialId: string) => request<void>(
  `/channels/${id}/trials/${encodeURIComponent(trialId)}`, { method: "DELETE" });

export const metricLabels: Record<string, string> = { views: "再生数", engagedViews: "エンゲージビュー",
  estimatedMinutesWatched: "視聴時間（分）", subscribersGained: "登録者獲得", averageViewPercentage: "平均視聴率（%）",
  averageViewDuration: "平均視聴時間（秒）", likes: "高評価" };
export const overviewMetrics = ["views", "engagedViews", "estimatedMinutesWatched", "subscribersGained"];
export const formatLabels: Record<string, string> = { all: "全体", shorts: "ショート", long: "通常", live: "ライブ", unknown: "形式未確認" };
const reasons: Record<string, string> = {
  NO_ROWS: "APIから値が返っていません", UNAVAILABLE: "値を取得できていません", NO_SYNC: "同期結果がありません",
  PARTIAL_COVERAGE: "日別値に未返却があるため、全期間の合計は未取得", NO_VIDEOS: "この期間の対象動画がありません",
  API_5XX: "APIの一時エラー", FIRST7_NOT_READY: "公開翌日から7暦日がまだ返却されていません",
  PUBLICATION_UNAVAILABLE: "公開日時が未取得", MULTIPLE_CONTENT_TYPES: "複数の形式が返り比較できません",
  FORMAT_MISMATCH: "動画の形式が異なります", FORMAT_UNCONFIRMED: "公式の形式が確認できていません",
  DURATION_MISMATCH: "動画の尺帯が異なります", DURATION_UNCONFIRMED: "動画の尺帯が確認できていません",
  BASELINE_UNAVAILABLE: "基準動画が未取得・期限切れです", TARGET_NOT_SELECTED: "対象動画を選んでください",
  TARGET_UNAVAILABLE: "対象動画が未取得・期限切れです", TARGET_NOT_LINKED: "対象動画の制作記録の結び付けがありません",
  WAITING_FOR_FIRST7: "初期7日レポートの返却待ちです", METRIC_UNAVAILABLE: "主要指標が未取得です",
  DERIVED_NOT_ALLOWED: "独自集計の利用が無効です", NOT_LINKED: "制作記録との結び付けなし", RECORD_UNAVAILABLE: "制作記録を読めません",
};
export const missingLabel = (reason: string | null | undefined) => reason ? (reasons[reason] ?? reason) : "値を取得できていません";
export const numberLabel = (value: number) => value.toLocaleString("ja-JP", { maximumFractionDigits: 2 });
export function metricText(metric?: MetricValue): string {
  return metric?.value !== null && metric?.value !== undefined ? numberLabel(metric.value) : "未取得";
}
export function trialDraft(trial: ImprovementTrial): TrialDraft {
  return { baselineVideoId: trial.baselineVideoId, targetVideoId: trial.targetVideoId, changeNote: trial.changeNote,
    keepFixed: trial.keepFixed, primaryMetric: trial.primaryMetric, rejectionCondition: trial.rejectionCondition,
    resultCheck: trial.resultCheck, status: trial.status, expectedUpdatedAt: trial.updatedAt };
}
