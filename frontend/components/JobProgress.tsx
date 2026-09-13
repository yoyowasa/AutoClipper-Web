import type { JobStatusResponse } from "../lib/types";
import { automationGateDisplay } from "../lib/automationQuality";
import { InitialSelectionStatusBanner } from "./InitialSelectionStatusBanner";
import { StatusBadge } from "./StatusBadge";

const errorLabels: Record<string, string> = {
  media_stream_duration_mismatch: "動画ファイルが不完全です",
  audio_extraction_failed: "動画の音声を読み込めません",
  transcript_unusable: "文字起こし結果を利用できません",
  transcription_quality_fallback_failed: "文字起こしの再試行に失敗しました",
  heatmap_interval_mode_unavailable: "人気度JSONを参照できません",
  heatmap_interval_mode_no_candidates: "字幕内容から候補を作成できません",
  codex_initial_selection_failed: "Codex初期選定に失敗しました",
  codex_initial_selection_unavailable: "Codex初期選定を開始できません",
  no_usable_selection: "選定基準を満たす候補がありません",
  no_usable_selection_retry_exhausted: "再処理は終了しています",
  no_usable_output: "切り抜き動画を生成できませんでした",
  quality_gate_render_failed: "完成動画の自動確認で問題を検出しました",
  quality_gate_record_failed: "自動確認の判定記録を保存できませんでした",
};

export function JobProgress({ job }: { job: JobStatusResponse }) {
  const stoppedAtSelection =
    job.status === "failed" &&
    (job.error?.code === "no_usable_selection" ||
      job.error?.code === "no_usable_selection_retry_exhausted");
  const displayedProgress = stoppedAtSelection ? 72 : job.progress;
  const detailNumber = (key: string) => {
    const value = job.details[key];
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  };
  const correctionProgress = detailNumber("stageProgress");
  const correctionCompleted = detailNumber("correctionBatchesCompleted");
  const correctionTotal = detailNumber("correctionBatchesTotal");
  const correctionRetries = detailNumber("correctionRetryCount");
  const correctionTargetsCompleted = detailNumber("correctionTargetsCompleted");
  const correctionTargetsTotal = detailNumber("correctionTargetsTotal");
  const transcriptSegmentCount = detailNumber("transcriptSegmentCount");
  const automationGate = automationGateDisplay(job.details);
  const exceptionOnlyAutomation = automationGate.active;
  const automationGateAttentionCount =
    automationGate.attentionClips ??
    (automationGate.attentionClipIds.length > 0 ? automationGate.attentionClipIds.length : null);
  const automationGateToneClass =
    automationGate.tone === "passed"
      ? "border-emerald-200 text-emerald-900"
      : automationGate.tone === "attention"
        ? "border-amber-200 text-amber-900"
        : "border-sky-200 text-sky-900";
  const automationGateReasonClass =
    automationGate.tone === "passed"
      ? "text-emerald-800"
      : automationGate.tone === "attention"
        ? "text-amber-800"
        : "text-sky-800";
  const heatmapStatus =
    typeof job.details.heatmapStatus === "string" ? job.details.heatmapStatus : null;
  const heatmapSegmentCount = detailNumber("heatmapSegmentCount") ?? 0;
  const heatmapIntervalModeRequested = job.details.heatmapIntervalModeRequested === true;
  const heatmapIntervalModeApplied = job.details.heatmapIntervalModeApplied === true;
  const heatmapSelectionBehavior =
    typeof job.details.heatmapSelectionBehavior === "string"
      ? job.details.heatmapSelectionBehavior
      : null;
  const heatmapModeUnavailable =
    heatmapIntervalModeRequested &&
    !heatmapIntervalModeApplied &&
    heatmapSelectionBehavior !== "manual_ranges";
  let heatmapLabel: string | null = null;
  if (heatmapIntervalModeApplied) {
    heatmapLabel = `字幕選定で人気度JSONを参考（${heatmapSegmentCount}区間）`;
  } else if (heatmapIntervalModeRequested && heatmapSelectionBehavior === "manual_ranges") {
    heatmapLabel = "手動指定区間を優先（人気度JSONは境界に不使用）";
  } else if (heatmapModeUnavailable) {
    heatmapLabel = "人気度JSONを参照できないため字幕内容だけで選定";
  } else if (heatmapStatus === "applied") {
    heatmapLabel = `人気度JSONあり・現在は字幕内容だけで選定（${heatmapSegmentCount}区間）`;
  } else if (heatmapStatus === "unavailable") {
    heatmapLabel = "人気度JSONなし（内容のみで選定）";
  } else if (heatmapStatus === "invalid_fallback") {
    heatmapLabel = "人気度JSON不一致（内容のみで選定）";
  } else if (heatmapStatus === "not_provided") {
    heatmapLabel = "人気度JSONなし（内容のみで選定）";
  }
  const showCorrectionProgress =
    job.status === "correcting_subtitles" &&
    correctionProgress !== null &&
    correctionCompleted !== null &&
    correctionTotal !== null;
  const currentStep =
    job.status === "awaiting_manual_edit"
      ? "元動画から切り抜く範囲を指定してください"
      : job.status === "awaiting_clip_review"
      ? exceptionOnlyAutomation
        ? "自動処理を止め、問題のある切り抜き予定だけ確認へ戻しました"
        : "切り抜き予定を確認してください"
      : job.status === "awaiting_subtitle_review"
        ? exceptionOnlyAutomation
          ? "自動処理を止め、問題のあるタイトル・字幕だけ確認へ戻しました"
          : "字幕を確認してください"
        : job.currentStep;

  return (
    <section className="rounded-md border border-neutral-300 bg-white p-5">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm text-neutral-500">Job</p>
            <h1 className="mt-1 break-all text-2xl font-semibold text-neutral-950">{job.id}</h1>
          </div>
          <StatusBadge status={job.status} />
        </div>

        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-neutral-700">{currentStep}</p>
            {job.error ? (
              <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                <p className="font-medium">{errorLabels[job.error.code] ?? job.error.code}</p>
                <p className="mt-1">{job.error.message}</p>
              </div>
            ) : null}
          </div>
          <p className="text-2xl font-semibold tabular-nums text-neutral-950">
            {displayedProgress}%
          </p>
        </div>

        <div className="h-3 overflow-hidden rounded-md bg-neutral-100">
          <div
            className="h-full rounded-md bg-neutral-950 transition-all"
            style={{ width: `${displayedProgress}%` }}
          />
        </div>

        {heatmapLabel ? (
          <p
            className={`text-xs ${
              heatmapModeUnavailable
                ? "text-red-700"
                : heatmapStatus === "applied"
                  ? "text-emerald-700"
                  : "text-neutral-600"
            }`}
            data-testid="heatmap-status"
          >
            {heatmapLabel}
          </p>
        ) : null}

        <InitialSelectionStatusBanner
          currentStep={job.currentStep}
          details={job.details}
          jobStatus={job.status}
        />

        {automationGate.visible ? (
          <div
            className={`border-t pt-4 text-xs ${automationGateToneClass}`}
            data-testid="automation-gate-summary"
          >
            <p className="font-semibold">
              {automationGate.title}
              {automationGate.stageLabel ? `: ${automationGate.stageLabel}` : ""}
            </p>
            {automationGate.autoPassedClips !== null || automationGateAttentionCount !== null ? (
              <p className="mt-1 tabular-nums">
                自動通過 {automationGate.autoPassedClips ?? 0}件 ・ 要確認{" "}
                {automationGateAttentionCount ?? 0}件
              </p>
            ) : null}
            {automationGate.reasonLabels.length > 0 ? (
              <p className={`mt-1 break-words ${automationGateReasonClass}`}>
                理由: {automationGate.reasonLabels.join(" / ")}
              </p>
            ) : null}
          </div>
        ) : null}

        {showCorrectionProgress ? (
          <div className="border-t border-neutral-200 pt-4" data-testid="subtitle-correction-progress">
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <p className="font-medium text-neutral-800">字幕校正</p>
              <p className="tabular-nums text-neutral-700">
                {correctionCompleted}/{correctionTotal} batches ({correctionProgress}%)
              </p>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-md bg-neutral-100">
              <div
                aria-label="Subtitle correction progress"
                className="h-full rounded-md bg-sky-600 transition-all"
                style={{ width: `${Math.max(0, Math.min(100, correctionProgress))}%` }}
              />
            </div>
            {correctionRetries && correctionRetries > 0 ? (
              <p className="mt-2 text-xs text-amber-700">API retry: {correctionRetries}</p>
            ) : null}
            {correctionTargetsTotal !== null && transcriptSegmentCount !== null ? (
              <p className="mt-2 text-xs text-neutral-600">
                対象segment {correctionTargetsCompleted ?? 0}/{correctionTargetsTotal} ・ 全segment{" "}
                {transcriptSegmentCount}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
