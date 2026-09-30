import type { ClipSettings, ClipPlanDocument } from "./types";

export function isAIAllocation(settings: Pick<ClipSettings, "clipAllocationMode" | "totalClipCount">): boolean {
  return settings.totalClipCount != null && (settings.clipAllocationMode ?? "ai") === "ai";
}
export function allocationSettingsError(settings: ClipSettings): string | null {
  if (!isAIAllocation(settings) && settings.clipAllocationMode !== "ai") return null;
  const total = settings.totalClipCount ?? 0, normal = settings.minNormalClipCount ?? 0, short = settings.minShortCount ?? 0;
  if (!Number.isInteger(total) || total < 1 || total > 36) return "合計本数は1〜36本です。";
  if (!Number.isInteger(normal) || normal < 0 || normal > 12) return "通常の最低本数は0〜12本です。";
  if (!Number.isInteger(short) || short < 0 || short > 24) return "ショートの最低本数は0〜24本です。";
  if (normal + short > total) return "形式ごとの最低本数の合計は合計本数以下にしてください。";
  if (settings.normalClipTimeRanges.length + settings.shortClipTimeRanges.length > total) return "手動指定の本数が合計本数を超えています。";
  return null;
}
export function remainingClipSlots(plan: ClipPlanDocument, keptIds: string[]): number {
  if (isAIAllocation(plan.settings)) return Math.max(0, (plan.settings.totalClipCount ?? 0) - plan.clips.filter(c => keptIds.includes(c.id)).length);
  return (["normal", "short"] as const).reduce((total, kind) => {
    const clips = plan.clips.filter(c => c.type === kind);
    const requested = kind === "normal" ? plan.settings.normalClipCount : plan.settings.shortCount;
    return total + Math.max(requested, clips.length) - clips.filter(c => keptIds.includes(c.id)).length;
  }, 0);
}
export function allocationLabel(plan: ClipPlanDocument): string {
  const normal = plan.clips.filter(c => c.type === "normal").length, short = plan.clips.length - normal;
  return `${plan.requestedTotal ?? plan.settings.totalClipCount}本中${plan.clips.length}本（通常${normal}・ショート${short}）`;
}
export const shortageLabels: Record<string, string> = {
  insufficient_strong_candidates: "強い候補が不足", duration_out_of_range: "尺ルールの範囲外",
  low_codex_confidence: "AIの確信度が不足", rejected_by_user_no_content: "内容がないと指定した区間",
  rejected_by_user_weak_highlight: "見どころが弱いと指定した区間", rejected_by_user_missing_context: "文脈不足で未拡張",
  rejected_by_user_missing_context_repeated: "繰り返し文脈不足と指定した区間",
  rejected_by_user_other: "その他の理由で不採用", rejected_by_user_unspecified: "以前の不採用候補とほぼ同じ",
  minimum_normal_shortfall: "通常の最低本数が不足", minimum_short_shortfall: "ショートの最低本数が不足",
  previous_source_usage: "既に使用した区間", quality_below_threshold: "品質の基準未達"
};
