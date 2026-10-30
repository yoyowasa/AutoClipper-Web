import type { PublicationSummary, PublicationDecision } from "./types";

export const publicationReasons: Record<string,string> = {
  WEAK_SCORE: "内容の強さの採点が見送り基準を下回っています",
  LOW_CONTENT_DENSITY: "字幕から確認できる内容が尺に対して少ないため見送ります",
  MODEL_REJECTED: "既存の選定で採用に適さないと判定されています",
  QUALITY_EVIDENCE_MISSING: "必須条件の検査記録が足りず、投稿可否を判定できません",
  EXISTING_GATE_REJECTED: "既存の必須条件を満たしていません。範囲・内容の確認が必要です",
  SCORE_MISSING: "採点が記録されていないため、投稿可否を判定できません",
  TRANSCRIPT_MISSING: "内容の根拠となる字幕が足りず、投稿可否を判定できません",
  RANGE_INVALID: "元動画の範囲・尺の条件に合っていません",
  SELECTION_REASON_MISSING: "選定理由が記録されていないため、投稿可否を判定できません",
};
export function publicationSummary(details?: Record<string,unknown>): PublicationSummary | null {
  const value = details?.publication;
  if (!value || typeof value !== "object") return null;
  const row = value as Partial<PublicationSummary>;
  if (!["publish","partial","no_publication","needs_review"].includes(row.outcome ?? "") ||
      !Array.isArray(row.decisions) || typeof row.selectedCount !== "number") return null;
  return row as PublicationSummary;
}
export function withheld(clip: {publicationDecision?: string | null}) {
  return clip.publicationDecision === "skip" || clip.publicationDecision === "unknown";
}
export function publicationLabel(decision: PublicationDecision) {
  return `${decision.type === "normal" ? "通常" : "ショート"} ${Math.floor(decision.start/60)}:${String(Math.floor(decision.start%60)).padStart(2,"0")}〜${Math.floor(decision.end/60)}:${String(Math.floor(decision.end%60)).padStart(2,"0")}`;
}
