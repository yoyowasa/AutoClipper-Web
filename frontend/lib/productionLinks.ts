import { request } from "./intelligence";

export type ProductionRecordSummary = {
  familyId: string; recordId: string; publicationTitle: string; type: "normal" | "short";
  revision: number; createdAt: string; characterPresetName: string | null; ambiguous: boolean;
  mode: "auto" | "manual" | "manual_unlinked" | null;
};
export type ProductionVideo = { id: string; channelId: number; title: string | null; publishedAt: string | null };
export type ProductionLinks = {
  links: Array<{ familyId: string; recordId: string; mode: "auto" | "manual"; linkedAt: string | null;
    updatedAt: string; record: ProductionRecordSummary | null; video: ProductionVideo }>;
  unlinkedRecords: ProductionRecordSummary[]; unlinkedVideos: ProductionVideo[];
  linkedCount: number; unlinkedRecordCount: number; unlinkedVideoCount: number;
  issues: Array<{ recordId: string; reason: string }>;
};
export const getProductionLinks = () => request<ProductionLinks>("/production-links");
export const reconcileProductionLinks = () => request<ProductionLinks>("/production-links/reconcile", { method: "POST" });
export const setProductionLink = (familyId: string, videoId: string | null) => request<ProductionLinks>(
  `/production-links/${encodeURIComponent(familyId)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ youtubeVideoId: videoId })
  });
