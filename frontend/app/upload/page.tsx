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
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("No file selected");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const uploaded = await uploadVideo(file);
      const job = await createJob(uploaded.videoId, settings);
      router.push(`/jobs/${job.jobId}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed");
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
            {isSubmitting ? "Starting" : "Start job"}
          </button>
        </header>

        <UploadDropzone disabled={isSubmitting} file={file} onFileChange={setFile} />
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
