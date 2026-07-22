"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import {
  SettingsPanel,
  settingsForRuntimeProfile
} from "../../components/SettingsPanel";
import { UploadDropzone } from "../../components/UploadDropzone";
import { createJob, uploadVideo } from "../../lib/api";
import type { ClipSettings } from "../../lib/types";

type SubmissionStage = "idle" | "uploading" | "creating_job";

function UploadForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedProfile = searchParams.get("runtimeProfile");
  const runtimeProfile =
    requestedProfile === "gpu" ? "gpu" : requestedProfile === "cpu" ? "cpu" : null;
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

    setIsSubmitting(true);
    setSubmissionStage("uploading");
    setUploadProgress(0);
    setError(null);

    try {
      const uploaded = await uploadVideo(file, setUploadProgress);
      setSubmissionStage("creating_job");
      const job = await createJob(uploaded.videoId, settings);
      router.push(`/jobs/${job.jobId}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed");
      setSubmissionStage("idle");
      setIsSubmitting(false);
    }
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
              ? `アップロード中 ${uploadProgress}%`
              : submissionStage === "creating_job"
                ? "アップロード完了"
                : "処理を開始"}
          </button>
        </header>

        <UploadDropzone disabled={isSubmitting} file={file} onFileChange={setFile} />

        {submissionStage !== "idle" ? (
          <section
            aria-live="polite"
            className={`border px-5 py-4 ${
              submissionStage === "creating_job"
                ? "border-emerald-300 bg-emerald-50"
                : "border-sky-300 bg-sky-50"
            }`}
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-neutral-950">
                  {submissionStage === "creating_job"
                    ? "動画のアップロードが完了しました"
                    : "動画をアップロードしています"}
                </p>
                <p className="mt-1 text-sm text-neutral-600">
                  {submissionStage === "creating_job"
                    ? "切り抜き処理を準備しています"
                    : `${file?.name ?? "動画"} - ${uploadProgress}%`}
                </p>
              </div>
              <span className="text-2xl font-semibold tabular-nums text-neutral-950">
                {submissionStage === "creating_job" ? "完了" : `${uploadProgress}%`}
              </span>
            </div>
            <div
              aria-label="アップロード進捗"
              aria-valuemax={100}
              aria-valuemin={0}
              aria-valuenow={submissionStage === "creating_job" ? 100 : uploadProgress}
              className="mt-4 h-2 overflow-hidden bg-white"
              role="progressbar"
            >
              <div
                className={`h-full transition-[width] duration-200 ${
                  submissionStage === "creating_job" ? "bg-emerald-600" : "bg-sky-600"
                }`}
                style={{
                  width: `${submissionStage === "creating_job" ? 100 : uploadProgress}%`
                }}
              />
            </div>
          </section>
        ) : null}

        <SettingsPanel disabled={isSubmitting} settings={settings} onChange={setSettings} />

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
