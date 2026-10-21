import { request } from "./intelligence";

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
};
export const getProductionAggregates = (id: number) => request<ProductionAggregates>(`/channels/${id}/production-aggregates`);
