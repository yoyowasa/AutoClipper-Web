"use client";

import Image from "next/image";
import { useState } from "react";

import { SaveFileButton } from "./SaveFileButton";
import { formatDuration, formatScore } from "../lib/format";
import { toBrowserApiUrl } from "../lib/api";
import type { PostTitleIntent, ResultExportItem } from "../lib/types";
import { descriptionWithHashtags, youtubeTagsText } from "../lib/youtubePosting";

const INTENT_LABELS: Record<PostTitleIntent, string> = {
  factual: "事実重視",
  engagement: "興味喚起",
  concise: "短く強い"
};

function normalizedHashtags(values: string[]): string[] {
  return values
    .map((value) => value.trim())
    .filter(Boolean)
    .map((value) => (value.startsWith("#") ? value : `#${value}`));
}

function postCopyText(item: ResultExportItem): string {
  return [
    item.title.trim(),
    descriptionWithHashtags(
      item.youtubeDescription ?? "",
      normalizedHashtags(item.youtubeHashtags ?? [])
    )
  ]
    .filter(Boolean)
    .join("\n\n");
}

function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : formatScore(value);
}

function formatTime(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${value.toFixed(2)}s`;
}

function resolutionText(item: ResultExportItem): string {
  const width = item.resolution?.width;
  const height = item.resolution?.height;
  return width && height ? `${width}x${height}` : "unknown";
}

function readableToken(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  return value.replaceAll("_", " ");
}

function scoreSourceLabel(item: ResultExportItem): string {
  if (item.openaiScoreSource) {
    return readableToken(item.openaiScoreSource);
  }
  if (item.aiScore !== null) {
    return "AI";
  }
  return "rule";
}

function thumbnailStatusLabel(
  status: ResultExportItem["thumbnailStatus"],
  hasPublishedUrl: boolean
): string {
  if (status === "failed") {
    return "サムネ生成失敗";
  }
  if (status === "generating") {
    return "サムネだけ再生成中";
  }
  if (status === "ready") {
    return hasPublishedUrl ? "サムネ完成" : "サムネ情報不整合";
  }
  if (status === "not_generated" || status === null) {
    return "サムネ未生成";
  }
  return "サムネ状態不明";
}

export function ResultVideoCard({
  item,
  auditAvailable = false,
  onReedit,
  onRegenerateThumbnail,
  isReediting = false,
  isRegeneratingThumbnail = false,
  thumbnailPriority = false,
  suggestedFilename
}: {
  item: ResultExportItem;
  auditAvailable?: boolean;
  onReedit?: (item: ResultExportItem) => void;
  onRegenerateThumbnail?: (
    item: ResultExportItem,
    cropMode: "standard" | "close"
  ) => void;
  isReediting?: boolean;
  isRegeneratingThumbnail?: boolean;
  thumbnailPriority?: boolean;
  suggestedFilename: string;
}) {
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [failedThumbnailUrl, setFailedThumbnailUrl] = useState<string | null>(null);
  const warnings = item.auditWarnings ?? [];
  const titleCandidates = item.titleCandidates ?? [];
  const youtubeDescription = item.youtubeDescription ?? "";
  const youtubeHashtags = normalizedHashtags(item.youtubeHashtags ?? []);
  const youtubeTags = item.youtubeTags ?? [];
  const hasPostMetadata = Boolean(
    titleCandidates.length > 0 ||
      youtubeDescription ||
      youtubeHashtags.length > 0 ||
      youtubeTags.length > 0
  );
  const scoreSource = scoreSourceLabel(item);
  const showOverlayStatus =
    item.overlayTitleExpected !== null || item.overlayTitleRendered !== null;
  const thumbnailUrl = item.thumbnailUrl
    ? toBrowserApiUrl(item.thumbnailUrl)
    : null;
  const thumbnailIsDisplayable = Boolean(
    thumbnailUrl && failedThumbnailUrl !== thumbnailUrl
  );
  const thumbnailFilename =
    item.thumbnailFilename ?? suggestedFilename.replace(/\.mp4$/iu, ".jpg");
  const thumbnailIsPng = thumbnailFilename.toLowerCase().endsWith(".png");
  const thumbnailLabel = thumbnailStatusLabel(
    item.thumbnailStatus,
    thumbnailIsDisplayable
  );
  const thumbnailHasError =
    item.thumbnailStatus === "failed" ||
    (item.thumbnailStatus === "ready" && !thumbnailIsDisplayable);

  async function copyField(field: string, value: string) {
    if (!value.trim()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopyStatus(field);
    } catch {
      setCopyStatus("error");
    }
  }

  return (
    <article className="rounded-md border border-neutral-300 bg-white p-5 shadow-sm shadow-neutral-200/60">
      <div className="flex min-h-40 flex-col justify-between gap-5">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-neutral-300 bg-neutral-50 px-2 py-1 text-xs font-medium uppercase text-neutral-600">
              {item.type}
            </span>
            <span className="text-sm text-neutral-500">{formatDuration(item.duration)}</span>
            <span className="text-sm text-neutral-500">score {formatNumber(item.finalScore ?? item.score)}</span>
            {item.belowQualityThreshold ? (
              <span className="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-900">
                below threshold
              </span>
            ) : null}
            {item.boundaryRefined ? (
              <span className="rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-900">
                boundary refined
              </span>
            ) : null}
          </div>
          <h2 className="break-words text-lg font-semibold leading-snug text-neutral-950">{item.title}</h2>
          {thumbnailIsDisplayable && thumbnailUrl ? (
            <section className="overflow-hidden rounded-md border border-neutral-200 bg-neutral-50">
              <Image
                alt={`${item.title} のサムネイル`}
                className={`h-auto w-full bg-neutral-950 object-contain ${
                  item.type === "short" ? "aspect-[9/16] max-h-[34rem]" : "aspect-video"
                }`}
                height={item.type === "short" ? 1920 : 720}
                priority={thumbnailPriority}
                src={thumbnailUrl}
                unoptimized
                width={item.type === "short" ? 1080 : 1280}
                onError={() => setFailedThumbnailUrl(thumbnailUrl)}
              />
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-200 px-3 py-2">
                <span className="text-xs font-semibold text-neutral-600">
                  {thumbnailLabel}
                </span>
                {item.thumbnailDownloadUrl ? (
                  <SaveFileButton
                    className="inline-flex min-h-9 items-center rounded-md border border-neutral-400 bg-white px-3 text-xs font-semibold text-neutral-900"
                    description="YouTube thumbnail"
                    extension={thumbnailIsPng ? ".png" : ".jpg"}
                    label="サムネを保存"
                    mimeType={thumbnailIsPng ? "image/png" : "image/jpeg"}
                    suggestedName={thumbnailFilename}
                    url={toBrowserApiUrl(item.thumbnailDownloadUrl)}
                  />
                ) : null}
              </div>
            </section>
          ) : item.thumbnailStatus ? (
            <div
              className={`rounded-md border px-3 py-2 text-xs font-semibold ${
                thumbnailHasError
                  ? "border-red-200 bg-red-50 text-red-700"
                  : "border-neutral-200 bg-neutral-50 text-neutral-600"
              }`}
            >
              {thumbnailLabel}
            </div>
          ) : null}
          {item.type === "normal" && onRegenerateThumbnail ? (
            <section className="border border-amber-300 bg-amber-50 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-neutral-950">
                    サムネだけ再生成
                  </h3>
                  <p className="mt-1 text-xs text-neutral-600">
                    承認済みの文字とデザインは維持し、人物の場面と寄り方を切り替えます。完成動画は変更しません。
                  </p>
                </div>
                {item.thumbnailStatus === "generating" ? (
                  <span className="text-xs font-semibold text-amber-800" role="status">
                    生成中
                  </span>
                ) : null}
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <button
                  className="min-h-11 bg-amber-600 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
                  disabled={isRegeneratingThumbnail || item.thumbnailStatus === "generating"}
                  type="button"
                  onClick={() => onRegenerateThumbnail(item, "standard")}
                >
                  {item.thumbnailStatus === "generating"
                    ? "再生成中"
                    : "別場面（上半身）"}
                </button>
                <button
                  className="min-h-11 bg-neutral-950 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
                  disabled={isRegeneratingThumbnail || item.thumbnailStatus === "generating"}
                  type="button"
                  onClick={() => onRegenerateThumbnail(item, "close")}
                >
                  {item.thumbnailStatus === "generating"
                    ? "再生成中"
                    : "別場面（顔寄り）"}
                </button>
              </div>
            </section>
          ) : null}
          <div className="grid gap-2 text-xs text-neutral-600 sm:grid-cols-2">
            <span>title: {readableToken(item.titleSource)}</span>
            <span>score source: {scoreSource}</span>
            <span>rule {formatNumber(item.ruleScore)}</span>
            <span>AI {formatNumber(item.aiScore)}</span>
            <span>resolution {resolutionText(item)}</span>
            {showOverlayStatus ? (
              <span>
                overlay title: {item.overlayTitleRendered ? "rendered" : item.overlayTitleExpected ? "missing" : "off"}
              </span>
            ) : null}
          </div>
          {warnings.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {warnings.map((warning) => (
                <span
                  key={warning}
                  className="rounded-md border border-red-200 bg-red-50 px-2 py-1 text-xs font-medium text-red-800"
                >
                  {readableToken(warning)}
                </span>
              ))}
            </div>
          ) : !auditAvailable ? (
            <span className="text-xs font-medium text-neutral-500">Audit not available</span>
          ) : (
            <span className="text-xs font-medium text-emerald-700">No audit warnings</span>
          )}
        </div>

        <details className="rounded-md border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-700">
          <summary className="cursor-pointer font-medium text-neutral-900">Details</summary>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            <div>
              <dt className="font-medium text-neutral-500">Range</dt>
              <dd>
                {formatTime(item.refinedStart ?? item.start)} - {formatTime(item.refinedEnd ?? item.end)}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-500">Original range</dt>
              <dd>
                {formatTime(item.originalStart)} - {formatTime(item.originalEnd)}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-500">Selection</dt>
              <dd>{readableToken(item.selectionReason)}</dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-500">Quality warning</dt>
              <dd>{readableToken(item.qualityWarning)}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="font-medium text-neutral-500">Subtitle path</dt>
              <dd className="break-all">{item.subtitlePath ?? "n/a"}</dd>
            </div>
          </dl>
        </details>

        {hasPostMetadata ? (
          <details className="rounded-md border border-sky-200 bg-sky-50/50 p-3 text-xs text-neutral-700">
            <summary className="cursor-pointer font-semibold text-sky-950">
              YouTube投稿用セット
            </summary>
            {item.postMetadataSource ? (
              <p className="mt-2 text-[11px] text-neutral-500">
                生成元: {item.postMetadataSource}
              </p>
            ) : null}
            {titleCandidates.length > 0 ? (
              <div className="mt-3 grid gap-2">
                {titleCandidates.map((candidate) => (
                  <div
                    className={`border bg-white p-2 ${
                      item.selectedTitleId === candidate.id
                        ? "border-sky-700"
                        : "border-neutral-200"
                    }`}
                    key={candidate.id}
                  >
                    <div className="flex flex-wrap items-center gap-1 text-[10px] font-semibold">
                      <span className="bg-neutral-100 px-1.5 py-0.5 text-neutral-700">
                        {INTENT_LABELS[candidate.intent]}
                      </span>
                      {item.recommendedTitleId === candidate.id ? (
                        <span className="bg-emerald-100 px-1.5 py-0.5 text-emerald-800">
                          推奨
                        </span>
                      ) : null}
                      {item.selectedTitleId === candidate.id ? (
                        <span className="bg-sky-100 px-1.5 py-0.5 text-sky-800">
                          採用
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 break-words font-medium text-neutral-950">
                      {candidate.title}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
            {youtubeDescription ? (
              <p className="mt-3 whitespace-pre-wrap leading-5 text-neutral-700">
                {youtubeDescription}
              </p>
            ) : null}
            {youtubeHashtags.length > 0 ? (
              <p className="mt-2 break-words font-medium text-sky-800">
                {youtubeHashtags.join(" ")}
              </p>
            ) : null}
            {youtubeTags.length > 0 ? (
              <p className="mt-2 break-words text-neutral-600">
                タグ: {youtubeTagsText(youtubeTags)}
              </p>
            ) : null}
            <div className="mt-3 grid grid-cols-2 gap-1 sm:grid-cols-4">
              <button
                className="min-h-9 border border-neutral-400 bg-white px-2 text-[11px] font-semibold"
                type="button"
                onClick={() => void copyField("title", item.title)}
              >
                {copyStatus === "title" ? "コピー済み" : "タイトル"}
              </button>
              <button
                className="min-h-9 border border-neutral-400 bg-white px-2 text-[11px] font-semibold disabled:text-neutral-400"
                disabled={!youtubeDescription.trim() && youtubeHashtags.length === 0}
                type="button"
                onClick={() =>
                  void copyField(
                    "description",
                    descriptionWithHashtags(youtubeDescription, youtubeHashtags)
                  )
                }
              >
                {copyStatus === "description" ? "コピー済み" : "説明欄"}
              </button>
              <button
                className="min-h-9 border border-neutral-400 bg-white px-2 text-[11px] font-semibold disabled:text-neutral-400"
                disabled={youtubeTags.length === 0}
                type="button"
                onClick={() => void copyField("tags", youtubeTagsText(youtubeTags))}
              >
                {copyStatus === "tags" ? "コピー済み" : "タグ"}
              </button>
              <button
                className="min-h-9 border border-neutral-400 bg-white px-2 text-[11px] font-semibold"
                type="button"
                onClick={() => void copyField("all", postCopyText(item))}
              >
                {copyStatus === "all" ? "コピー済み" : "全部"}
              </button>
            </div>
            {copyStatus === "error" ? (
              <p className="mt-2 font-semibold text-red-700" role="status">
                コピーできませんでした
              </p>
            ) : null}
          </details>
        ) : null}

        <div className="flex flex-wrap gap-2">
          {onReedit && item.candidateId ? (
            <button
              className="inline-flex min-h-10 items-center bg-sky-700 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
              disabled={isReediting}
              type="button"
              onClick={() => onReedit(item)}
            >
              {isReediting ? "再編集画面を準備中" : "この動画だけ再編集"}
            </button>
          ) : null}
          <SaveFileButton
            className="inline-flex min-h-10 items-center rounded-md bg-neutral-950 px-4 text-sm font-medium text-white"
            url={toBrowserApiUrl(item.downloadUrl)}
            suggestedName={suggestedFilename}
            mimeType="video/mp4"
            extension=".mp4"
            description="MP4 video"
            label="MP4を保存"
          />
          <a
            className="inline-flex min-h-10 items-center rounded-md border border-neutral-300 px-4 text-sm font-medium text-neutral-800"
            href={toBrowserApiUrl(item.videoUrl)}
            target="_blank"
          >
            Open
          </a>
          {item.metadataUrl ? (
            <a
              className="inline-flex min-h-10 items-center rounded-md border border-neutral-300 px-4 text-sm font-medium text-neutral-800"
              href={toBrowserApiUrl(item.metadataUrl)}
              target="_blank"
            >
              Metadata
            </a>
          ) : null}
          {item.subtitleUrl ? (
            <a
              className="inline-flex min-h-10 items-center rounded-md border border-neutral-300 px-4 text-sm font-medium text-neutral-800"
              href={toBrowserApiUrl(item.subtitleUrl)}
              target="_blank"
            >
              Subtitle
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}
