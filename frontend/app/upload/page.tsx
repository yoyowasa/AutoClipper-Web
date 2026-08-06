"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  SettingsPanel,
  settingsForRuntimeProfile
} from "../../components/SettingsPanel";
import { UploadDropzone } from "../../components/UploadDropzone";
import { UploadActionBar } from "../../components/UploadActionBar";
import { createJob, reopenCompletedVideo, uploadVideo } from "../../lib/api";
import { manualRangeValidationError } from "../../lib/manualClipRanges";
import type { ClipSettings } from "../../lib/types";

type UploadMode = "new" | "reedit";
type SubmissionStage = "idle" | "uploading" | "creating_job" | "opening_reedit";

function actionLabelForStage(
  stage: SubmissionStage,
  mode: UploadMode,
  progress: number,
  hasFile: boolean
): string {
  if (stage === "uploading") {
    return mode === "reedit" ? `完成MP4を照合中 ${progress}%` : `アップロード中 ${progress}%`;
  }
  if (stage === "creating_job") {
    return "処理を準備中";
  }
  if (stage === "opening_reedit") {
    return "再編集画面を開いています";
  }
  if (hasFile) {
    return mode === "reedit" ? "この完成MP4を再編集" : "この動画で処理を開始";
  }
  return mode === "reedit" ? "完成MP4を選択してください" : "動画を選択してください";
}

function UploadForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedProfile = searchParams.get("runtimeProfile");
  const runtimeProfile =
    requestedProfile === "gpu" ? "gpu" : requestedProfile === "cpu" ? "cpu" : null;
  const [uploadMode, setUploadMode] = useState<UploadMode>("new");
  const [file, setFile] = useState<File | null>(null);
  const [heatmapFile, setHeatmapFile] = useState<File | null>(null);
  const [settings, setSettings] = useState<ClipSettings>(() =>
    settingsForRuntimeProfile(runtimeProfile)
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionStage, setSubmissionStage] = useState<SubmissionStage>("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [manualRangeRevealKey, setManualRangeRevealKey] = useState(0);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("No file selected");
      return;
    }
    if (uploadMode === "new") {
      if (settings.heatmapIntervalMode && !heatmapFile) {
        setError("JSON区間モードをONにするには人気区間JSONを選択してください。");
        return;
      }
      if (heatmapFile && heatmapFile.name !== `${file.name}.heatmap.json`) {
        setError(`人気区間JSONは ${file.name}.heatmap.json を選択してください。`);
        return;
      }
      const rangeError = manualRangeValidationError(settings);
      if (rangeError) {
        setError(rangeError);
        setManualRangeRevealKey((current) => current + 1);
        return;
      }
    } else if (!file.name.toLowerCase().endsWith(".mp4")) {
      setError("再編集にはAutoClipperで書き出したMP4を選択してください。");
      return;
    }

    setIsSubmitting(true);
    setSubmissionStage("uploading");
    setUploadProgress(0);
    setError(null);

    try {
      if (uploadMode === "reedit") {
        const reopened = await reopenCompletedVideo(file, setUploadProgress);
        setSubmissionStage("opening_reedit");
        const query = new URLSearchParams({ source: "reupload" });
        if (reopened.matchedClipId) {
          query.set("clipId", reopened.matchedClipId);
        }
        router.push(`/jobs/${reopened.jobId}/subtitles?${query.toString()}`);
        return;
      }
      const uploaded = await uploadVideo(file, setUploadProgress, heatmapFile);
      setSubmissionStage("creating_job");
      const job = await createJob(uploaded.videoId, settings);
      router.push(`/jobs/${job.jobId}`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : uploadMode === "reedit"
            ? "完成MP4から再編集を開始できませんでした"
            : "Upload failed"
      );
      setSubmissionStage("idle");
      setIsSubmitting(false);
    }
  }

  function changeUploadMode(nextMode: UploadMode) {
    if (isSubmitting || nextMode === uploadMode) {
      return;
    }
    setUploadMode(nextMode);
    setFile(null);
    setHeatmapFile(null);
    setSettings((current) => ({ ...current, heatmapIntervalMode: false }));
    setSubmissionStage("idle");
    setUploadProgress(0);
    setError(null);
  }

  const actionLabel = actionLabelForStage(
    submissionStage,
    uploadMode,
    uploadProgress,
    file !== null
  );
  const submitDisabled =
    !file ||
    isSubmitting ||
    (uploadMode === "new" && settings.heatmapIntervalMode && !heatmapFile);

  return (
    <main className="top-workspace min-h-screen bg-[#f1f1ef] text-[#1d1d1b] sm:p-3 xl:p-4">
      <form
        className="flex min-h-screen w-full min-w-0 flex-col border-[#cfcfcb] bg-white sm:border xl:h-[calc(100vh-2rem)] xl:min-h-0 xl:overflow-hidden"
        data-runtime-profile={runtimeProfile ?? "default"}
        data-testid="top-workspace"
        onSubmit={handleSubmit}
      >
        <header className="sticky top-0 z-20 flex min-h-12 flex-wrap items-center justify-between gap-3 border-t-2 border-[#252523] bg-[#fbfbfa] px-3 py-2 sm:px-4 xl:static">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <h1 className="text-lg font-bold tracking-tight text-[#161614]">AutoClipper</h1>
            <span className="border-l border-[#cfcfcb] pl-3 text-xs font-bold text-[#3e3e3a]">
              動画作成
            </span>
            <span
              className={`border px-2 py-1 text-[10px] font-bold ${
                file
                  ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                  : "border-sky-200 bg-sky-50 text-sky-800"
              }`}
            >
              {file ? "設定確認中" : "動画選択待ち"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-[11px] font-semibold text-[#6d6d68] sm:inline">
              {runtimeProfile === "gpu"
                ? "GPU recommended"
                : runtimeProfile === "cpu"
                  ? "CPU compatible"
                  : "Runtime 自動判定"}
            </span>
            <button
              className="min-h-10 bg-sky-700 px-4 text-xs font-bold text-white hover:bg-sky-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:cursor-not-allowed disabled:bg-[#d2d2cf] xl:hidden"
              disabled={submitDisabled}
              type="submit"
            >
              {actionLabel}
            </button>
          </div>
        </header>

        {error ? (
          <div
            className="border-y border-red-300 bg-red-50 px-4 py-2 text-xs font-semibold text-red-800"
            role="alert"
          >
            {error}
          </div>
        ) : null}

        <div className="grid min-h-0 min-w-0 flex-1 xl:grid-cols-[340px_minmax(0,1fr)]">
          <section
            className="min-w-0 border-t border-[#d5d5d2] bg-[#fbfbfa] xl:min-h-0 xl:overflow-y-auto xl:border-r"
            data-testid="top-source-panel"
          >
            <div className="flex min-h-12 items-center justify-between border-b border-[#d5d5d2] bg-white px-3">
              <div>
                <h2 className="text-sm font-bold text-[#1b1b1b]">入力動画</h2>
                <p className="mt-0.5 text-[11px] text-[#6d6d68]">処理する動画の用途を選択</p>
              </div>
              <span className="border border-[#d5d5d2] bg-[#f5f5f3] px-2 py-1 text-[10px] font-bold text-[#686863]">
                {uploadMode === "reedit" ? "再編集" : "新規作成"}
              </span>
            </div>

            <div
              aria-label="動画の利用方法"
              className="grid grid-cols-2 border-b border-[#d5d5d2] bg-white p-1"
              role="group"
            >
              <button
                aria-pressed={uploadMode === "new"}
                className={`min-h-10 px-2 text-xs font-bold ${
                  uploadMode === "new"
                    ? "bg-[#161614] text-white"
                    : "bg-white text-[#5e5e59] hover:bg-[#f1f1ef]"
                }`}
                type="button"
                onClick={() => changeUploadMode("new")}
              >
                新しい動画を作成
              </button>
              <button
                aria-pressed={uploadMode === "reedit"}
                className={`min-h-10 px-2 text-xs font-bold ${
                  uploadMode === "reedit"
                    ? "bg-[#161614] text-white"
                    : "bg-white text-[#5e5e59] hover:bg-[#f1f1ef]"
                }`}
                type="button"
                onClick={() => changeUploadMode("reedit")}
              >
                完成動画を再編集
              </button>
            </div>

            <div className="p-3">
              <UploadDropzone
                compact
                accept={uploadMode === "reedit" ? ".mp4,video/mp4" : "video/*"}
                disabled={isSubmitting}
                file={file}
                purpose={uploadMode}
                uploadProgress={uploadProgress}
                uploadState={
                  submissionStage === "creating_job" || submissionStage === "opening_reedit"
                    ? "uploaded"
                    : submissionStage
                }
                onFileChange={(nextFile) => {
                  setFile(nextFile);
                  const keepHeatmap = Boolean(
                    heatmapFile &&
                      nextFile &&
                      heatmapFile.name === `${nextFile.name}.heatmap.json`
                  );
                  if (!keepHeatmap) {
                    setHeatmapFile(null);
                    setSettings((current) => ({ ...current, heatmapIntervalMode: false }));
                  }
                }}
              />
            </div>

            {uploadMode === "new" ? (
              <section className="border-t border-[#d5d5d2] bg-white p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-xs font-bold text-[#282825]">人気区間JSON</h3>
                      <span className="bg-[#eef7fa] px-1.5 py-0.5 text-[10px] font-bold text-sky-800">
                        任意
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] leading-4 text-[#73736e]">
                      Downloaderが生成した
                      {file ? ` ${file.name}.heatmap.json` : " sidecar"} を追加できます。
                    </p>
                  </div>
                  <label
                    className={`shrink-0 px-3 py-2 text-xs font-bold ${
                      !file || isSubmitting
                        ? "cursor-not-allowed bg-[#e1e1de] text-[#8c8c87]"
                        : "cursor-pointer bg-[#161614] text-white hover:bg-[#30302d]"
                    }`}
                    htmlFor="heatmap-sidecar-input"
                  >
                    JSONを選ぶ
                  </label>
                  <input
                    accept=".json,application/json"
                    className="hidden"
                    disabled={!file || isSubmitting}
                    id="heatmap-sidecar-input"
                    type="file"
                    onChange={(event) => {
                      const selectedHeatmap = event.target.files?.[0] ?? null;
                      setHeatmapFile(selectedHeatmap);
                      if (!selectedHeatmap) {
                        setSettings((current) => ({ ...current, heatmapIntervalMode: false }));
                      }
                      event.currentTarget.value = "";
                      setError(null);
                    }}
                  />
                </div>
                {heatmapFile ? (
                  <div className="mt-3 flex items-center justify-between gap-2 border-t border-[#e1e1de] pt-3">
                    <p className="min-w-0 break-all text-[11px] font-semibold text-emerald-800">
                      {heatmapFile.name}
                    </p>
                    <button
                      className="shrink-0 border border-[#bfc0bd] bg-white px-2 py-1.5 text-[11px] font-bold text-[#5e5e59] hover:bg-[#f1f1ef]"
                      disabled={isSubmitting}
                      type="button"
                      onClick={() => {
                        setHeatmapFile(null);
                        setSettings((current) => ({ ...current, heatmapIntervalMode: false }));
                      }}
                    >
                      外す
                    </button>
                  </div>
                ) : (
                  <p className="mt-2 text-[10px] leading-4 text-[#85857f]">
                    未選択時は従来の字幕・音声・映像評価を使います。値は動画内の相対値0〜1です。
                  </p>
                )}
                <div className="mt-3 border-t border-[#e1e1de] pt-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-[#282825]">JSON区間モード</p>
                      <p className="mt-1 text-[11px] leading-4 text-[#73736e]">
                        {settings.heatmapIntervalMode
                          ? "人気区間を起点に候補を作り、既存の品質条件で絞り込みます。"
                          : "既存候補を字幕・音声・映像で評価し、JSON値を最大+10点の補助に使います。"}
                      </p>
                    </div>
                    <div
                      aria-label="JSON区間モード"
                      className="grid shrink-0 grid-cols-2 border border-[#bfc0bd]"
                      role="group"
                    >
                      <button
                        aria-pressed={!settings.heatmapIntervalMode}
                        className={`min-h-9 px-3 text-xs font-bold ${
                          !settings.heatmapIntervalMode
                            ? "bg-[#161614] text-white"
                            : "bg-white text-[#5e5e59] hover:bg-[#f1f1ef]"
                        }`}
                        disabled={isSubmitting}
                        type="button"
                        onClick={() =>
                          setSettings((current) => ({ ...current, heatmapIntervalMode: false }))
                        }
                      >
                        OFF
                      </button>
                      <button
                        aria-pressed={settings.heatmapIntervalMode}
                        className={`min-h-9 px-3 text-xs font-bold ${
                          settings.heatmapIntervalMode
                            ? "bg-emerald-700 text-white"
                            : "bg-white text-[#5e5e59] hover:bg-[#f1f1ef] disabled:cursor-not-allowed disabled:bg-[#e1e1de] disabled:text-[#8c8c87]"
                        }`}
                        disabled={!heatmapFile || isSubmitting}
                        type="button"
                        onClick={() =>
                          setSettings((current) => ({ ...current, heatmapIntervalMode: true }))
                        }
                      >
                        ON
                      </button>
                    </div>
                  </div>
                  {!heatmapFile ? (
                    <p className="mt-2 text-[10px] leading-4 text-[#85857f]">
                      ONにするには動画に対応する人気区間JSONを選択してください。
                    </p>
                  ) : null}
                  {settings.heatmapIntervalMode &&
                  (settings.normalClipTimeRanges.length > 0 ||
                    settings.shortClipTimeRanges.length > 0) ? (
                    <p className="mt-2 text-[10px] leading-4 text-amber-700">
                      時間を手動指定した種類は手動区間を優先し、それ以外をJSON区間から作成します。
                    </p>
                  ) : null}
                </div>
              </section>
            ) : null}
          </section>

          <section
            className="flex min-w-0 flex-col border-t border-[#d5d5d2] bg-white xl:min-h-0 xl:overflow-hidden"
            data-testid="top-settings-panel"
          >
            <div className="flex min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[#d5d5d2] bg-[#fbfbfa] px-3">
              <div>
                <h2 className="text-sm font-bold text-[#1b1b1b]">
                  {uploadMode === "new" ? "生成設定" : "再編集データの復元"}
                </h2>
                <p className="mt-0.5 text-[11px] text-[#6d6d68]">
                  {uploadMode === "new"
                    ? "出力本数・切り抜き方針・字幕を設定"
                    : "完成MP4から元jobを照合して編集画面を開きます"}
                </p>
              </div>
              <span className="text-[10px] font-semibold text-sky-700">
                {uploadMode === "new" ? "必要な項目だけ調整" : "元データを変更せず復元"}
              </span>
            </div>

            <div className="min-h-0 flex-1 xl:overflow-y-auto">
              {uploadMode === "new" ? (
                <SettingsPanel
                  disabled={isSubmitting}
                  revealManualRanges={manualRangeRevealKey}
                  settings={settings}
                  workspace
                  onChange={setSettings}
                />
              ) : (
                <div className="grid gap-3 p-3 lg:grid-cols-2">
                  <section className="border border-[#cfcfcb] bg-white p-4">
                    <h3 className="text-sm font-bold text-[#20201e]">元jobの編集データを復元します</h3>
                    <p className="mt-2 text-xs leading-6 text-[#555550]">
                      選択した完成MP4自体へ文字を重ねません。同じPCに残っている元動画・切り抜き範囲・
                      文字起こしを開き、タイトル・冒頭フック文字・冒頭フック映像・字幕を変更して再レンダリングします。
                    </p>
                  </section>
                  <section className="border border-amber-200 bg-amber-50 p-4">
                    <h3 className="text-sm font-bold text-amber-900">再編集に必要なもの</h3>
                    <p className="mt-2 text-xs leading-6 text-amber-900">
                      元jobまたは元動画を削除済みの場合、完成MP4だけでは焼き込み済み文字を消せないため再編集できません。
                    </p>
                  </section>
                </div>
              )}
            </div>

            <UploadActionBar
              actionLabel={actionLabel}
              disabled={submitDisabled}
              file={file}
              isSubmitting={isSubmitting}
              mode={uploadMode}
              settings={settings}
            />
          </section>
        </div>
      </form>
    </main>
  );
}

export default function UploadPage() {
  return (
    <Suspense fallback={null}>
      <UploadForm />
    </Suspense>
  );
}
