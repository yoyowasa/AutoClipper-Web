"use client";

import { useState, useSyncExternalStore } from "react";

import {
  browserFileSaveSupported,
  saveBrowserFile
} from "../lib/browserFileSave";

type SaveStatus = "idle" | "saving" | "saved" | "error";

function subscribeToBrowserCapabilities(): () => void {
  return () => undefined;
}

function browserFileSaveServerSnapshot(): null {
  return null;
}

export function SaveFileButton({
  className,
  url,
  suggestedName,
  mimeType,
  extension,
  description,
  label
}: {
  className: string;
  url: string;
  suggestedName: string;
  mimeType: string;
  extension: string;
  description: string;
  label: string;
}) {
  const supported = useSyncExternalStore(
    subscribeToBrowserCapabilities,
    browserFileSaveSupported,
    browserFileSaveServerSnapshot
  );
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  async function saveFile() {
    setStatus("saving");
    setError(null);
    try {
      const result = await saveBrowserFile({
        url,
        suggestedName,
        mimeType,
        extension,
        description
      });
      setStatus(result === "saved" ? "saved" : "idle");
    } catch (caught) {
      setStatus("error");
      setError(
        caught instanceof Error
          ? caught.message
          : "保存処理に失敗しました"
      );
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        className={className}
        data-save-picker-supported={
          supported === null ? "checking" : supported ? "true" : "false"
        }
        disabled={status === "saving" || supported === false}
        type="button"
        onClick={() => void saveFile()}
      >
        {status === "saving"
          ? "保存中"
          : status === "saved"
            ? "保存完了"
            : label}
      </button>
      {supported === false ? (
        <span className="max-w-64 text-xs text-red-700" role="status">
          このChromeでは保存先を選ぶ機能を利用できません
        </span>
      ) : null}
      {status === "error" && error ? (
        <span className="max-w-64 text-xs text-red-700" role="status">
          {error}
        </span>
      ) : null}
    </span>
  );
}
