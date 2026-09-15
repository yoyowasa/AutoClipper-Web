"use client";

import { useEffect, useState } from "react";
import { readHeatmapContentIssue } from "../lib/heatmapFileStatus";

export function HeatmapFileNotice({ file }: { file: File }) {
  const [result, setResult] = useState<{ file: File; issue: string | null } | null>(null);
  useEffect(() => {
    let active = true;
    void readHeatmapContentIssue(file).then(issue => { if (active) setResult({ file, issue }); });
    return () => { active = false; };
  }, [file]);
  const ready = result?.file === file;
  return <p role="status" className={`mt-2 text-xs ${ready && result.issue ? "text-amber-800" : "text-neutral-600"}`}>
    {!ready ? "JSONの中身を確認中…" : result.issue ?? "人気度データあり。動画との一致はアップロード時に確認します。"}
  </p>;
}
