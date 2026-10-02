"use client";

import { useEffect, useState } from "react";
import { toBrowserApiUrl } from "../lib/api";
import { postingDirectorySupported, postingSetSaver, restorePostingSetDirectory } from "../lib/postingSetSave";

export function SavePostingSetButton({ exportId, filename, available }: {
  exportId: string; filename: string; available: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [folder, setFolder] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void restorePostingSetDirectory().then(() => { if (active) setFolder(postingSetSaver.directoryName); });
    return () => { active = false; };
  }, []);
  async function save(chooseNewDirectory = false) {
    setBusy(true);
    setMessage(null);
    const directorySupported = postingDirectorySupported();
    try {
      const result = await postingSetSaver.save({
        manifestUrl: toBrowserApiUrl(`/api/exports/${exportId}/posting-set`),
        zipUrl: toBrowserApiUrl(`/api/exports/${exportId}/posting-set.zip`),
        zipFilename: filename.replace(/\.mp4$/iu, ".zip")
      }, chooseNewDirectory);
      if (result === "saved") {
        setFolder(postingSetSaver.directoryName);
        setMessage(directorySupported ? "動画・サムネ・投稿文を保存しました" : "投稿セットのZIPをダウンロードします");
      }
    } catch (error) {
      setMessage(`${error instanceof Error ? error.message : "保存に失敗しました"}（途中まで保存されたファイルが残る場合があります）`);
    } finally {
      setBusy(false);
    }
  }
  return <span className="inline-flex flex-col items-start gap-1">
    <button type="button" onClick={() => void save()} disabled={busy || !available}
      className="inline-flex min-h-10 items-center rounded-md bg-sky-700 px-4 text-sm font-semibold text-white disabled:bg-neutral-300">
      {busy ? "投稿セットを保存中" : "投稿セットを保存"}
    </button>
    {!available && <span className="text-xs text-neutral-600">サムネ完成後に3ファイルを保存できます</span>}
    {folder && <span className="text-xs text-neutral-600">保存先: {folder} <button type="button" className="underline"
      disabled={busy} onClick={() => void save(true)}>保存先を変更して保存</button></span>}
    {message && <span role="status" className="max-w-80 text-xs text-neutral-700">{message}</span>}
  </span>;
}
