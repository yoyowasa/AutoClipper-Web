import type { JobStatus, JobStatusDetails } from "./types";

export type InitialSelectionDisplayState =
  | "pending"
  | "running"
  | "retrying"
  | "success"
  | "fallback"
  | "unknown"
  | "failed";

export type InitialSelectionStatusDisplay = {
  state: InitialSelectionDisplayState;
  tone: "neutral" | "info" | "success" | "warning" | "danger";
  title: string;
  description: string;
  detail: string | null;
};

function detailNumber(details: JobStatusDetails, key: string): number | null {
  const value = details[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function detailText(details: JobStatusDetails, key: string): string | null {
  const value = details[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function selectionCountText(details: JobStatusDetails): string | null {
  const requestedNormal = detailNumber(details, "codexInitialSelectionRequestedNormalCount");
  const requestedShort = detailNumber(details, "codexInitialSelectionRequestedShortCount");
  const selectedNormal = detailNumber(details, "codexInitialSelectionSelectedNormalCount");
  const selectedShort = detailNumber(details, "codexInitialSelectionSelectedShortCount");
  if (
    requestedNormal === null &&
    requestedShort === null &&
    selectedNormal === null &&
    selectedShort === null
  ) {
    return null;
  }
  return `通常 ${selectedNormal ?? 0}/${requestedNormal ?? "-"}・ショート ${
    selectedShort ?? 0
  }/${requestedShort ?? "-"}`;
}

export function initialSelectionStatusDisplay(
  details: JobStatusDetails,
  jobStatus?: JobStatus,
  currentStep?: string
): InitialSelectionStatusDisplay | null {
  if (details.initialSelectionProvider !== "codex") {
    return null;
  }

  const rawStatus = detailText(details, "codexInitialSelectionStatus")?.toLowerCase() ?? null;
  const fallbackUsed = details.codexInitialSelectionFallbackUsed === true;
  const error =
    detailText(details, "codexInitialSelectionErrorMessage") ??
    detailText(details, "codexInitialSelectionError");
  const errorCode = detailText(details, "codexInitialSelectionErrorCode");
  const fallbackReason = detailText(details, "codexInitialSelectionFallbackReason");
  const hostErrorCode = detailText(details, "codexInitialSelectionHostErrorCode");
  const diagnosticCodes = [...new Set([errorCode, hostErrorCode].filter(Boolean))];
  const errorDetail = [error, diagnosticCodes.length > 0 ? diagnosticCodes.join(" / ") : null]
    .filter(Boolean)
    .join(" — ") || null;
  const retryCount =
    detailNumber(details, "codexInitialSelectionRetryCount") ??
    detailNumber(details, "codexInitialSelectionAttemptCount") ??
    detailNumber(details, "codexInitialSelectionAttempt");
  const retrying =
    rawStatus === "retrying" ||
    rawStatus === "restarting" ||
    (typeof currentStep === "string" && currentStep.includes("再試行")) ||
    (retryCount !== null &&
      retryCount > 1 &&
      (rawStatus === "queued" || rawStatus === "running" || rawStatus === "selecting"));

  if (fallbackUsed || rawStatus === "fallback") {
    return {
      state: "fallback",
      tone: "warning",
      title: "ローカル仮選定",
      description:
        "Codex選定に失敗したため、表示中はローカル仮選定です。おすすめ結果ではありません。",
      detail: errorDetail ?? fallbackReason
    };
  }

  if (retrying) {
    return {
      state: "retrying",
      tone: "info",
      title: "Codex接続を再試行中",
      description: "接続状態を確認して自動で再試行しています。候補はまだ確定していません。",
      detail: retryCount !== null ? `試行 ${retryCount}回目` : error
    };
  }

  if (error || rawStatus === "failed") {
    return {
      state: "failed",
      tone: "danger",
      title: "Codex内容選定に失敗しました",
      description: "Codexのおすすめ候補は作成されていません。",
      detail: errorDetail
    };
  }

  if (rawStatus === "ready" || rawStatus === "completed" || rawStatus === "success") {
    return {
      state: "success",
      tone: "success",
      title: "Codex内容選定",
      description: "Codexが動画全体の文脈から候補を選定しました。",
      detail: selectionCountText(details)
    };
  }

  if (
    rawStatus === "queued" ||
    rawStatus === "running" ||
    rawStatus === "selecting" ||
    jobStatus === "selecting_clips" ||
    jobStatus === "reselecting_clips"
  ) {
    return {
      state: "running",
      tone: "info",
      title: "Codex内容選定中",
      description: "動画全体の文脈を確認して候補を選んでいます。",
      detail: null
    };
  }

  if (
    details.codexInitialSelectionSummaryAvailable === false &&
    jobStatus &&
    [
      "preparing_clip_review",
      "awaiting_clip_review",
      "preparing_subtitle_review",
      "awaiting_subtitle_review",
      "rendering_normal_clips",
      "rendering_shorts",
      "packaging_zip",
      "completed",
      "failed"
    ].includes(jobStatus)
  ) {
    return {
      state: "unknown",
      tone: "warning",
      title: "選定方法を確認できません",
      description:
        "Codex選定の記録がないため、表示中の候補をおすすめ結果として確認できません。",
      detail: null
    };
  }

  return {
    state: "pending",
    tone: "neutral",
    title: "Codex内容選定待ち",
    description: "文字起こし完了後にCodexで候補を選定します。",
    detail: null
  };
}
