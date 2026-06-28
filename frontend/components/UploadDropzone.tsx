"use client";

import { useRef, useState } from "react";

type UploadDropzoneProps = {
  file: File | null;
  disabled?: boolean;
  onFileChange: (file: File | null) => void;
};

export function UploadDropzone({
  file,
  disabled = false,
  onFileChange
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  function selectFile(nextFile: File | undefined) {
    onFileChange(nextFile ?? null);
  }

  return (
    <section className="rounded-md border border-neutral-300 bg-white p-5">
      <div
        className={`flex min-h-56 flex-col items-center justify-center gap-4 rounded-md border border-dashed p-6 text-center ${
          isDragging ? "border-neutral-900 bg-neutral-100" : "border-neutral-300 bg-neutral-50"
        }`}
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
          accept="video/*"
          disabled={disabled}
          onChange={(event) => selectFile(event.target.files?.[0])}
        />
        <div className="flex h-14 w-14 items-center justify-center rounded-md border border-neutral-300 bg-white text-xl">
          MP4
        </div>
        <div className="flex max-w-md flex-col gap-1">
          <h2 className="text-lg font-semibold text-neutral-950">Upload video</h2>
          <p className="text-sm text-neutral-600">
            {file ? file.name : "No file selected"}
          </p>
        </div>
        <button
          type="button"
          disabled={disabled}
          className="min-h-10 rounded-md bg-neutral-950 px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-neutral-300"
          onClick={() => inputRef.current?.click()}
        >
          Select file
        </button>
      </div>
    </section>
  );
}
