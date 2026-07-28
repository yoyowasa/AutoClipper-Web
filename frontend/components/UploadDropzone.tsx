"use client";

import { useRef, useState } from "react";

function formatFileSize(size: number): string {
  const gibibyte = 1024 ** 3;
  const mebibyte = 1024 ** 2;
  if (size >= gibibyte) {
    return `${(size / gibibyte).toFixed(2)} GiB`;
  }
  return `${(size / mebibyte).toFixed(1)} MiB`;
}

type UploadDropzoneProps = {
  file: File | null;
  accept?: string;
  disabled?: boolean;
  purpose?: "new" | "reedit";
  uploadProgress?: number;
  uploadState?: "idle" | "uploading" | "uploaded";
  onFileChange: (file: File | null) => void;
};

export function UploadDropzone({
  file,
  accept = "video/*",
  disabled = false,
  purpose = "new",
  uploadProgress = 0,
  uploadState = "idle",
  onFileChange
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function selectFile(nextFile: File | undefined) {
    onFileChange(nextFile ?? null);
  }

  function clearFile() {
    if (inputRef.current) {
      inputRef.current.value = "";
    }
    onFileChange(null);
  }

  const boundedProgress = Math.max(0, Math.min(100, uploadProgress));
  const isUploading = file !== null && uploadState === "uploading";
  const isUploaded = file !== null && uploadState === "uploaded";
  const panelStyle = isDragging
    ? "border-sky-600 bg-sky-50 ring-2 ring-sky-200"
    : file
      ? isUploading
        ? "border-sky-500 bg-sky-50"
        : "border-emerald-500 bg-emerald-50"
      : "border-dashed border-neutral-300 bg-white";

  return (
    <section
      aria-live="polite"
      className={`flex min-h-64 flex-col items-center justify-center rounded-md border-2 p-6 text-center transition-colors ${panelStyle}`}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) {
          setIsDragging(true);
        }
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setIsDragging(false);
        if (!disabled) {
          selectFile(event.dataTransfer.files[0]);
        }
      }}
    >
      <input
        ref={inputRef}
        className="hidden"
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(event) => selectFile(event.target.files?.[0])}
      />

      {file ? (
        <div className="flex w-full max-w-3xl flex-col gap-5">
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:text-left">
            <div
              className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-full text-xl font-bold text-white ${
                isUploading ? "bg-sky-600" : "bg-emerald-600"
              }`}
            >
              {isUploading ? `${boundedProgress}%` : "✓"}
            </div>
            <div className="min-w-0 flex-1">
              <p
                className={`text-xs font-bold uppercase ${
                  isUploading ? "text-sky-800" : "text-emerald-800"
                }`}
              >
                {isUploaded
                  ? "アップロード完了"
                  : isUploading
                    ? "アップロード中"
                    : "選択完了"}
              </p>
              <h2 className="mt-1 text-2xl font-semibold text-neutral-950">
                {isUploaded
                  ? purpose === "reedit"
                    ? "元の編集データを確認しました"
                    : "動画を受け取りました"
                  : isUploading
                    ? purpose === "reedit"
                      ? "完成MP4を照合しています"
                      : "動画をアップロードしています"
                    : purpose === "reedit"
                      ? "再編集する完成MP4を選択しました"
                      : "動画を選択しました"}
              </h2>
              <p className="mt-1 text-sm text-neutral-600">
                {isUploaded
                  ? purpose === "reedit"
                    ? "元jobの編集画面を開いています"
                    : "切り抜き処理を準備しています"
                  : isUploading
                    ? "この画面を閉じずにお待ちください"
                    : purpose === "reedit"
                      ? "元jobに保存されたタイトル・フック映像・字幕を使用します"
                      : "選択内容を確認し、設定後に処理を開始してください"}
              </p>
            </div>
          </div>

          <div
            className={`border-y py-4 text-left ${
              isUploading ? "border-sky-300" : "border-emerald-300"
            }`}
          >
            <p className="text-xs font-semibold text-neutral-500">選択した動画</p>
            <p className="mt-1 break-all text-base font-semibold text-neutral-950">
              {file.name}
            </p>
            <p className="mt-1 text-sm font-medium text-neutral-600">
              {formatFileSize(file.size)}
            </p>
          </div>

          {isUploading ? (
            <div>
              <div className="flex items-center justify-between text-sm font-semibold text-sky-900">
                <span>アップロード進捗</span>
                <span className="tabular-nums">{boundedProgress}%</span>
              </div>
              <div
                aria-label="アップロード進捗"
                aria-valuemax={100}
                aria-valuemin={0}
                aria-valuenow={boundedProgress}
                className="mt-2 h-3 overflow-hidden bg-white"
                role="progressbar"
              >
                <div
                  className="h-full bg-sky-600 transition-[width] duration-200"
                  style={{ width: `${boundedProgress}%` }}
                />
              </div>
            </div>
          ) : null}

          {uploadState === "idle" ? (
            <div className="flex flex-wrap justify-center gap-3 sm:justify-start">
              <button
                type="button"
                disabled={disabled}
                className="min-h-10 bg-neutral-950 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-300"
                onClick={() => inputRef.current?.click()}
              >
                別の動画を選ぶ
              </button>
              <button
                type="button"
                disabled={disabled}
                className="min-h-10 border border-neutral-400 bg-white px-4 text-sm font-medium text-neutral-800 disabled:cursor-not-allowed disabled:text-neutral-400"
                onClick={clearFile}
              >
                選択を解除
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-md border border-neutral-300 bg-white text-xl">
            MP4
          </div>
          <div className="flex max-w-md flex-col gap-1">
            <h2 className="text-xl font-semibold text-neutral-950">
              {purpose === "reedit" ? "完成MP4を選択" : "動画を選択"}
            </h2>
            <p className="text-sm text-neutral-600">
              {purpose === "reedit"
                ? "AutoClipperで書き出したMP4を選ぶか、ここへドロップしてください"
                : "動画ファイルを選ぶか、ここへドロップしてください"}
            </p>
          </div>
          <button
            type="button"
            disabled={disabled}
            className="min-h-10 bg-neutral-950 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-300"
            onClick={() => inputRef.current?.click()}
          >
            {purpose === "reedit" ? "完成MP4を選ぶ" : "動画ファイルを選ぶ"}
          </button>
        </div>
      )}
    </section>
  );
}
