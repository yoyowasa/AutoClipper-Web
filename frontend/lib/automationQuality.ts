import type {
  AutomationGateOutcome,
  AutomationGateStage,
  AutomationGateState,
  AutomationMode,
  JobStatusDetails
} from "./types";

const AUTOMATION_GATE_STAGE_LABELS: Record<AutomationGateStage, string> = {
  selection: "切り抜き予定",
  content: "タイトル・字幕",
  post_render: "完成動画"
};

const AUTOMATION_GATE_REASON_LABELS: Record<string, string> = {
  invalid_clip_range_or_duration: "切り抜き範囲または長さに問題があります",
  missing_title: "タイトルがありません",
  missing_transcript_coverage: "文字起こしが不足しています",
  requested_clip_shortfall: "指定した本数を確保できませんでした",
  candidate_hard_gate_failed: "選定の必須条件を満たしていません",
  unresolved_candidate_risk_flags: "未解決の候補リスクがあります",
  duplicate_short_moment: "ショートの場面が重複しています",
  selection_gate_evaluation_failed: "切り抜き予定を自動判定できませんでした",
  selection_gate_record_unavailable: "切り抜き予定の判定記録を確認できません",
  invalid_subtitle_structure: "字幕の構造に問題があります",
  preview_render_failed: "確認用プレビューを作成できませんでした",
  preview_not_ready_or_unverifiable: "プレビューを確認できません",
  human_review_or_current_preview_incomplete: "字幕またはプレビューの確認が未完了です",
  title_hook_evidence_inconsistent: "タイトル・フックと根拠字幕が一致していません",
  title_hook_evidence_unavailable_or_stale: "タイトル・フックの根拠が未生成または古くなっています",
  asr_alignment_evidence_insufficient: "音声と字幕の一致を自動確認できませんでした",
  overlay_layout_outside_safe_area: "文字が表示できる範囲からはみ出しています",
  overlay_layout_evidence_incomplete: "文字配置を自動確認できませんでした",
  content_gate_evaluation_failed: "タイトル・字幕を自動判定できませんでした",
  content_gate_record_unavailable: "タイトル・字幕の判定記録を確認できません",
  auto_resume_after_clip_review_failed: "範囲確認後の自動処理を再開できませんでした",
  exports_not_inspected: "完成動画を自動確認できませんでした",
  export_count_mismatch: "完成動画の本数が予定と一致しません",
  render_failures_not_inspected: "書き出し失敗の有無を確認できません",
  render_failures_present: "書き出しに失敗した動画があります",
  rendered_media_artifact_missing: "完成動画または字幕ファイルが不足しています",
  visual_evidence_not_inspected: "完成ショートの画角と帯を自動確認できませんでした",
  post_render_visual_contract_failed: "完成ショートの画角・帯・文字表示に問題があります",
  post_render_visual_evidence_insufficient: "完成ショートの画角を安全と判定できませんでした",
  post_render_gate_evaluation_failed: "完成動画を自動判定できませんでした",
  quality_gate_record_failed: "自動判定の記録を保存できませんでした"
};

const AUTOMATION_MODES = new Set<AutomationMode>(["manual", "shadow", "guarded", "auto"]);
const GATE_STATES = new Set<AutomationGateState>([
  "passed",
  "needs_attention",
  "fallback_manual",
  "evaluating"
]);
const GATE_STAGES = new Set<AutomationGateStage>(["selection", "content", "post_render"]);
const GATE_OUTCOMES = new Set<AutomationGateOutcome>(["pass", "fail", "unknown"]);

export type AutomationGateDisplay = {
  active: boolean;
  visible: boolean;
  mode: AutomationMode | null;
  state: AutomationGateState | null;
  outcome: AutomationGateOutcome | null;
  stage: AutomationGateStage | null;
  stageLabel: string | null;
  autoPassedClips: number | null;
  attentionClips: number | null;
  attentionClipIds: string[];
  reasonCodes: string[];
  reasonLabels: string[];
  tone: "passed" | "attention" | "evaluating";
  title: string;
};

function readSetValue<T extends string>(value: unknown, values: Set<T>): T | null {
  return typeof value === "string" && values.has(value as T) ? (value as T) : null;
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readStrings(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return [
    ...new Set(value.filter((item): item is string => typeof item === "string" && item.length > 0))
  ];
}

export function isExceptionOnlyAutomationMode(value: unknown): value is "guarded" | "auto" {
  return value === "guarded" || value === "auto";
}

export function automationGateReasonLabel(code: string): string {
  return AUTOMATION_GATE_REASON_LABELS[code] ?? `確認理由: ${code}`;
}

export function automationGateDisplay(
  details: JobStatusDetails | null | undefined
): AutomationGateDisplay {
  const effectiveMode = readSetValue(details?.automationEffectiveMode, AUTOMATION_MODES);
  const requestedMode = readSetValue(details?.automationMode, AUTOMATION_MODES);
  const mode = effectiveMode ?? requestedMode;
  const active = isExceptionOnlyAutomationMode(mode);
  const state = readSetValue(details?.automationGateState, GATE_STATES);
  const stage = readSetValue(details?.automationGateStage, GATE_STAGES);
  const outcome = readSetValue(details?.automationGateOutcome, GATE_OUTCOMES);
  const autoPassedClips = readNumber(details?.automationGateAutoPassedClips);
  const attentionClips = readNumber(details?.automationGateAttentionClips);
  const attentionClipIds = readStrings(details?.automationGateAttentionClipIds);
  const reasonCodes = readStrings(details?.automationGateReasonCodes);
  const needsAttention =
    state === "needs_attention" ||
    state === "fallback_manual" ||
    outcome === "fail" ||
    (attentionClips !== null && attentionClips > 0) ||
    attentionClipIds.length > 0;
  const passed = state === "passed" || (outcome === "pass" && !needsAttention);
  const evaluating = state === "evaluating";
  const tone = passed ? "passed" : needsAttention ? "attention" : "evaluating";
  const title = passed
    ? "自動品質確認を通過"
    : state === "fallback_manual"
      ? "判定不能のため人の確認へ戻しました"
      : needsAttention
        ? "問題だけ人の確認へ戻しました"
        : evaluating
          ? "自動品質確認中"
          : "自動品質確認";
  const visible =
    active &&
    (state !== null ||
      stage !== null ||
      outcome !== null ||
      autoPassedClips !== null ||
      attentionClips !== null ||
      attentionClipIds.length > 0 ||
      reasonCodes.length > 0);

  return {
    active,
    visible,
    mode,
    state,
    outcome,
    stage,
    stageLabel: stage ? AUTOMATION_GATE_STAGE_LABELS[stage] : null,
    autoPassedClips,
    attentionClips,
    attentionClipIds,
    reasonCodes,
    reasonLabels: reasonCodes.map(automationGateReasonLabel),
    tone,
    title
  };
}
