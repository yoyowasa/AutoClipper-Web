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
  compact?: boolean;
  disabled?: boolean;
  purpose?: "new" | "reedit";
  uploadProgress?: number;
  uploadState?: "idle" | "uploading" | "uploaded";
  onFileChange: (file: File | null) => void;
};

export function UploadDropzone({
  file,
  accept = "video/*",
  compact = false,
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
      className={`flex flex-col items-center justify-center text-center transition-colors ${
        compact ? "min-h-52 border p-4" : "min-h-64 rounded-md border-2 p-6"
      } ${panelStyle}`}
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
        <div className={`flex w-full max-w-3xl flex-col ${compact ? "gap-3" : "gap-5"}`}>
          <div
            className={`flex flex-col items-center sm:flex-row sm:text-left ${
              compact ? "gap-3" : "gap-4"
            }`}
          >
            <div
              className={`flex shrink-0 items-center justify-center font-bold text-white ${
                compact ? "h-11 w-11 text-xs" : "h-16 w-16 rounded-full text-xl"
              } ${isUploading ? "bg-sky-600" : "bg-emerald-600"}`}
            >
              {isUploading ? `${boundedProgress}%` : "MP4"}
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
              <h2
                className={`mt-1 font-semibold text-neutral-950 ${
                  compact ? "text-sm" : "text-2xl"
                }`}
              >
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
              <p className={`mt-1 text-neutral-600 ${compact ? "text-xs" : "text-sm"}`}>
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
            className={`border-y text-left ${compact ? "py-2" : "py-4"} ${
              isUploading ? "border-sky-300" : "border-emerald-300"
            }`}
          >
            <p className="text-xs font-semibold text-neutral-500">選択した動画</p>
            <p
              className={`mt-1 break-all font-semibold text-neutral-950 ${
                compact ? "text-xs" : "text-base"
              }`}
            >
              {file.name}
            </p>
            <p
              className={`mt-1 font-medium text-neutral-600 ${
                compact ? "text-xs" : "text-sm"
              }`}
            >
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
                className={`bg-neutral-950 px-4 font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-300 ${
                  compact ? "min-h-9 text-xs" : "min-h-10 text-sm"
                }`}
                onClick={() => inputRef.current?.click()}
              >
                別の動画を選ぶ
              </button>
              <button
                type="button"
                disabled={disabled}
                className={`border border-neutral-400 bg-white px-4 font-medium text-neutral-800 disabled:cursor-not-allowed disabled:text-neutral-400 ${
                  compact ? "min-h-9 text-xs" : "min-h-10 text-sm"
                }`}
                onClick={clearFile}
              >
                選択を解除
              </button>
            </div>
          ) : null}
        </div>
      ) : (
        <div className={`flex flex-col items-center ${compact ? "gap-3" : "gap-4"}`}>
          <div
            className={`flex items-center justify-center border border-neutral-300 bg-white ${
              compact ? "h-11 w-11 text-sm font-bold" : "h-14 w-14 rounded-md text-xl"
            }`}
          >
            MP4
          </div>
          <div className="flex max-w-md flex-col gap-1">
            <h2 className={`font-semibold text-neutral-950 ${compact ? "text-base" : "text-xl"}`}>
              {purpose === "reedit" ? "完成MP4を選択" : "動画を選択"}
            </h2>
            <p className={compact ? "text-xs text-neutral-600" : "text-sm text-neutral-600"}>
              {purpose === "reedit"
                ? "AutoClipperで書き出したMP4を選ぶか、ここへドロップしてください"
                : "動画ファイルを選ぶか、ここへドロップしてください"}
            </p>
          </div>
          <button
            type="button"
            disabled={disabled}
            className={`bg-neutral-950 px-4 font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-300 ${
              compact ? "min-h-9 text-xs" : "min-h-10 text-sm"
            }`}
            onClick={() => inputRef.current?.click()}
          >
            {purpose === "reedit" ? "完成MP4を選ぶ" : "動画ファイルを選ぶ"}
          </button>
        </div>
      )}
    </section>
  );
}
