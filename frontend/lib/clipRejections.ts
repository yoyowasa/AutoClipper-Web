import type { ClipPlanClip, ClipPlanDocument, ClipRejectionReason, ClipRejectionRequest } from "./types";

export const rejectionLabels: Record<ClipRejectionReason, string> = {
  no_content: "内容がない", missing_context: "文脈不足", weak_highlight: "見どころが弱い",
  other: "その他", unspecified: "理由未指定"
};
export type RejectionDraft = { reason: ClipRejectionReason; note: string };
export function rejectionPayload(clips: Pick<ClipPlanClip, "id">[], keptIds: string[], drafts: Record<string, RejectionDraft>): ClipRejectionRequest[] {
  return clips.filter(clip => !keptIds.includes(clip.id)).map(clip => ({
    clipId: clip.id, reason: drafts[clip.id]?.reason ?? "unspecified", note: drafts[clip.id]?.note || null
  }));
}

export function retainRejectionDrafts(
  previous: Pick<ClipPlanDocument, "jobId" | "revision"> | null,
  next: Pick<ClipPlanDocument, "jobId" | "revision" | "clips">,
  drafts: Record<string, RejectionDraft>
): Record<string, RejectionDraft> {
  if (previous?.jobId !== next.jobId || previous.revision !== next.revision) return {};
  return Object.fromEntries(Object.entries(drafts).filter(([id]) => next.clips.some(clip => clip.id === id)));
}
