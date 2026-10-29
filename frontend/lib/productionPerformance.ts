import { request } from "./intelligence";
import type { VideoGoal } from "./intelligenceDashboard";

export type PerformanceHint = {
  character_preset_name: string; format: "normal" | "short"; target: "selection" | "title_hook";
  text: string; evidence_groups: Array<{ group_id: string; count: number }>; video_ids: string[];
  confidence: "low" | "medium";
};
export type AggregateMetric = {
  count: number; median: number | null; baseline_count: number; baseline_median: number | null;
  relative_to_channel_median: number | null; missing_reason: string | null;
};
export type ProductionAggregateGroup = {
  id: string; character_preset_name: string; format: "normal" | "short"; dimension: string; value: string;
  count: number; sufficient: boolean; status: "available" | "insufficient_data";
  metrics: Record<string, AggregateMetric>; video_ids: string[];
};
export type ProductionAggregates = {
  source: "independent_aggregation"; label: string; channel_id: number; generated_at: string; expires_at: string;
  minimum_group_videos: number; linked_videos: number; excluded_linked_videos: number;
  excluded_reasons?: Record<string, number>;
  groups: ProductionAggregateGroup[];
  choice_evaluations?: ChoiceEvaluations | null;
};
export type ChoiceObservation = {
  record_id: string; record_family_id: string; choice_id: string; video_id: string; kind: string; role: string;
  source: string; policy_version: string | null; value_hash: string; selected_ids: string[]; evaluation: VideoGoal;
  values: Record<string, unknown> | null; values_omitted: boolean;
};
export type ChoiceEvaluationGroup = {
  id: string; character_preset_name: string; format: string; kind: string; role: string; source: string;
  policy_version: string | null; count: number; judged_count: number; sufficient: boolean; effect: "unconfirmed";
  option_values: Record<string, unknown>;
  implementation_version?: string | null;
  target_views: number | null; median_views: number | null; reached_count: number; attainment_rate: number | null;
  video_ids: string[]; observations: ChoiceObservation[];
};
export type ChoiceEvaluations = {
  source: "independent_aggregation"; label: string; minimum_group_videos: number; window_days: 30; interim_days: 7;
  linked_videos: number; excluded_reasons: Record<string, number>; groups: ChoiceEvaluationGroup[];
};
export const getProductionAggregates = (id: number) => request<ProductionAggregates>(`/channels/${id}/production-aggregates`);
