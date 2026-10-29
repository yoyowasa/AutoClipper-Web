import { request } from "./intelligence";
export type PolicyCohort = { id: string; kind: string; role: string; band: string; count: number;
  rate: number | null; median: number | null; observed_at: string | null; video_ids: string[];
  first7_count?: number; first7_median?: number | null };
export type ChoicePolicy = { id: string; character: string; format: string; currentId: string;
  versions: { id: string; previousId: string | null; createdAt: string; values: { weights: Record<string, number> } }[];
  decisions: { id: string; action: string; reason: string; fromId: string; toId: string; analysisId: string; createdAt: string;
    evidence: { key?: string; before?: PolicyCohort | null; after?: PolicyCohort | null; groups?: string[]; minimum?: number;
      cohorts?: PolicyCohort[]; omitted_cohorts?: number } | null }[] };
export const getChoicePolicies = (id: number) => request<ChoicePolicy[]>(`/channels/${id}/choice-policies`);
export const restoreChoicePolicy = (channel: number, policy: ChoicePolicy) => request<void>(
  `/channels/${channel}/choice-policies/${encodeURIComponent(policy.id)}/rollback`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expectedVersion: policy.currentId }),
  });
export const policyReason: Record<string, string> = {
  OBSERVATIONAL_CRITERIA_MET: "承認された30日観測の更新基準を満たしました（因果効果は未確認）",
  INSUFFICIENT_OR_UNCONFIRMED: "データ不足、または更新基準未達のため保留",
  MIXED_PROVENANCE: "手動・出所未記録の選択が含まれるため保留",
  VERSION_30_DAY_PENDING: "現在の版の30日評価待ち",
  UPDATE_BUDGET_LIMIT: "1回1項目の更新上限のため、次の分析まで保留",
  VERSION_NOT_WORSE: "現在の版は悪化基準に該当せず、新しい更新は保留",
  EVIDENCE_EXPIRED: "比較根拠の保持期限が切れたため保留",
  EVALUATION_FAILED: "更新判定に失敗したため版を変更せず保留（分析結果は保存済み）",
  EARLY_7_DAY_DECLINE: "7日の途中評価に悪化の兆し（警告のみ、版は変更しません）",
  REGRESSION_30_DAY: "30日評価が悪化基準を下回り、自動で直前の版へ戻しました",
  MANUAL_ROLLBACK: "人の操作で直前の版へ戻しました",
};
