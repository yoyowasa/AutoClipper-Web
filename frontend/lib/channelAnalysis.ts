import { request } from "./intelligence";

export type SyncBeforeAnalysis = "auto" | "always" | "never";
export type AnalysisFinding = {
  id: string; format: "all" | "shorts" | "videoondemand"; title: string; evidence_ids: string[];
  observation: string; hypothesis: string; alternatives: string[]; counter_evidence: string;
  next_check: string; confidence: "low" | "medium";
};
export type RecommendationLink = {
  surface: "shorts_feed" | "home" | "up_next" | "search" | "multi_surface"; viewer_need: string;
  stage: "viewer_fit" | "appeal" | "engagement" | "satisfaction" | "topic_demand";
  signal_hypothesis: string; evidence_gap: string; rule_ids: string[];
};
export type AnalysisProposal = {
  id: string; format: "shorts" | "videoondemand"; priority: number; title: string; baseline_video_id: string;
  evidence_ids: string[]; reason: string; goal_path: string; material_to_find: string; title_candidates: string[];
  hook: string; structure: Array<{ start: number; end: number; action: string }>; change_one: string; keep_fixed: string;
  primary_metric: "engagedViews" | "views" | "averageViewPercentage" | "averageViewDuration" | "subscribersGained";
  result_check: string; rejection_condition: string; recommendation_link: RecommendationLink | null;
};
export type AnalysisReview = {
  id: string; channel_id: number; batch_run_id: string; title: string; summary: string; goal_views: 1000000;
  recommendation_framework_version: string | null; reviewed_material: "statistics_and_titles";
  limitations: string[]; findings: AnalysisFinding[]; proposals: AnalysisProposal[];
};
export type AnalysisRun = {
  id: string; status: "queued" | "running" | "success" | "failed" | "expired";
  queuedAt: string; startedAt: string | null; finishedAt: string | null; expiresAt: string;
  errorCode: string | null; errorMessage: string | null; model: string; reasoning: string;
  requestId: string | null; syncBefore: string; syncRunId: string | null; review: AnalysisReview | null;
};
export type AnalysisHistory = { latestRun: AnalysisRun | null; latestResult: AnalysisRun | null; history: AnalysisRun[] };

export const getChannelAnalysis = (id: number) => request<AnalysisHistory>(`/channels/${id}/analysis`);
export const startChannelAnalysis = (id: number, syncBefore: SyncBeforeAnalysis) => request<AnalysisRun>(
  `/channels/${id}/analysis`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ syncBefore }) });

export function analysisStatus(run: AnalysisRun | null): string {
  return run ? { queued: "分析の順番待ち", running: "分析中（同期・生成・検証）", success: "分析完了",
    failed: "分析失敗", expired: "保持期限切れ" }[run.status] : "未分析";
}
