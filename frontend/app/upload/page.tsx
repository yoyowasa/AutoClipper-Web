"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  SettingsPanel,
  settingsForRuntimeProfile
} from "../../components/SettingsPanel";
import { UploadDropzone } from "../../components/UploadDropzone";
import { createJob, reopenCompletedVideo, uploadVideo } from "../../lib/api";
import { manualRangeValidationError } from "../../lib/manualClipRanges";
import type { ClipSettings } from "../../lib/types";

type UploadMode = "new" | "reedit";
type SubmissionStage = "idle" | "uploading" | "creating_job" | "opening_reedit";

function UploadForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedProfile = searchParams.get("runtimeProfile");
  const runtimeProfile =
    requestedProfile === "gpu" ? "gpu" : requestedProfile === "cpu" ? "cpu" : null;
  const [uploadMode, setUploadMode] = useState<UploadMode>("new");
  const [file, setFile] = useState<File | null>(null);
  const [settings, setSettings] = useState<ClipSettings>(() =>
    settingsForRuntimeProfile(runtimeProfile)
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionStage, setSubmissionStage] = useState<SubmissionStage>("idle");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("No file selected");
      return;
    }
    if (uploadMode === "new") {
      const rangeError = manualRangeValidationError(settings);
      if (rangeError) {
        setError(rangeError);
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
      const uploaded = await uploadVideo(file, setUploadProgress);
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
    setSubmissionStage("idle");
    setUploadProgress(0);
    setError(null);
  }

  return (
    <main className="min-h-screen bg-[#f7f7f4] px-6 py-8 text-neutral-950">
      <form
        className="mx-auto flex w-full max-w-5xl flex-col gap-5"
        data-runtime-profile={runtimeProfile ?? "default"}
        onSubmit={handleSubmit}
      >
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-neutral-300 pb-5">
          <div>
            <p className="text-sm font-medium uppercase text-neutral-500">AutoClipper</p>
            <h1 className="mt-2 text-3xl font-semibold">Upload</h1>
            {runtimeProfile ? (
              <p className="mt-2 text-sm text-neutral-600">
                Runtime: {runtimeProfile === "gpu" ? "GPU recommended" : "CPU compatible"}
              </p>
            ) : null}
          </div>
          <button
            className="min-h-11 rounded-md bg-neutral-950 px-5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-neutral-300"
            disabled={!file || isSubmitting}
            type="submit"
          >
            {submissionStage === "uploading"
              ? uploadMode === "reedit"
                ? `完成MP4を照合中 ${uploadProgress}%`
                : `アップロード中 ${uploadProgress}%`
              : submissionStage === "creating_job"
                ? "処理を準備中"
                : submissionStage === "opening_reedit"
                  ? "再編集画面を開いています"
                : file
                  ? uploadMode === "reedit"
                    ? "この完成MP4を再編集"
                    : "この動画で処理を開始"
                  : uploadMode === "reedit"
                    ? "完成MP4を選択してください"
                    : "動画を選択してください"}
          </button>
        </header>

        <div
          aria-label="動画の利用方法"
          className="grid grid-cols-2 border border-neutral-300 bg-white p-1"
          role="tablist"
        >
          <button
            aria-selected={uploadMode === "new"}
            className={`min-h-11 px-4 text-sm font-semibold ${
              uploadMode === "new"
                ? "bg-neutral-950 text-white"
                : "bg-white text-neutral-700"
            }`}
            role="tab"
            type="button"
            onClick={() => changeUploadMode("new")}
          >
            新しい動画を作成
          </button>
          <button
            aria-selected={uploadMode === "reedit"}
            className={`min-h-11 px-4 text-sm font-semibold ${
              uploadMode === "reedit"
                ? "bg-sky-700 text-white"
                : "bg-white text-neutral-700"
            }`}
            role="tab"
            type="button"
            onClick={() => changeUploadMode("reedit")}
          >
            完成動画を再編集
          </button>
        </div>

        <UploadDropzone
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
          onFileChange={setFile}
        />

        {uploadMode === "new" ? (
          <SettingsPanel disabled={isSubmitting} settings={settings} onChange={setSettings} />
        ) : (
          <section className="border-l-4 border-sky-600 bg-sky-50 px-5 py-4 text-sm text-sky-950">
            <h2 className="font-semibold">元jobの編集データを復元します</h2>
            <p className="mt-1 leading-6">
              選択した完成MP4自体へ文字を重ねません。同じPCに残っている元動画・切り抜き範囲・
              文字起こしを開き、タイトル・フック・字幕だけを変更して再レンダリングします。
            </p>
            <p className="mt-2 text-xs text-sky-800">
              元jobまたは元動画を削除済みの場合、完成MP4だけでは焼き込み済み文字を消せないため再編集できません。
            </p>
          </section>
        )}

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}
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
