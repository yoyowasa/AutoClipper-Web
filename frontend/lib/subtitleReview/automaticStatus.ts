import { getJobStatus, getSubtitleReview } from "../api";
import type { SubtitleReviewClip, SubtitleReviewDocument } from "../types";
import { clipLabel, formatTime } from "./display";

export function automaticReviewIsConfirmed(review: SubtitleReviewDocument): boolean {
  return Boolean(review.subtitleOnlyAuto && (review.state !== "awaiting_review" ||
    (review.totalClipCount > 0 && review.confirmedClipCount === review.totalClipCount)));
}

function clipReference(clip: SubtitleReviewClip, review: SubtitleReviewDocument): string {
  return `${clipLabel(clip, review.clips).replace(" ", "")}（元動画 ${formatTime(clip.start)}〜${formatTime(clip.end)}）`;
}

export function reviewFailureMessage(review: SubtitleReviewDocument, message: string, clip?: SubtitleReviewClip): string {
  let result = message;
  for (const item of review.clips) {
    result = result.replaceAll(`${item.id}（元動画 ${item.start.toFixed(1)}〜${item.end.toFixed(1)}秒）`, clipReference(item, review));
    result = result.replaceAll(item.id, clipReference(item, review));
  }
  for (const segment of review.segments) {
    if (result.includes(segment.id)) {
      const names = review.clips.filter(item => item.segmentIds.includes(segment.id))
        .map(item => clipLabel(item, review.clips).replace(" ", "")).join("・");
      result = result.replaceAll(segment.id, `${names}の字幕（元動画 ${formatTime(segment.start)}〜${formatTime(segment.end)}）`);
    }
  }
  result = result.replace(/\bcand_[A-Za-z0-9_-]+\b/g, "対象clip");
  if (clip && !result.includes(clipLabel(clip, review.clips).replace(" ", ""))) {
    result = `${clipReference(clip, review)}: ${result}`;
  }
  return result;
}

export function automaticReviewStopReasons(review: SubtitleReviewDocument): string[] {
  if (!review.subtitleOnlyAuto || review.state === "completed") return [];
  const reasons = (review.automaticStopReasons ?? []).map(reason => reviewFailureMessage(review, reason));
  for (const clip of review.clips) {
    if (clip.automaticDecisionState === "failed") {
      reasons.push(reviewFailureMessage(review, clip.automaticDecisionError || "自動決定に失敗しました。", clip));
    } else if (clip.confirmed && clip.previewState === "failed") {
      reasons.push(reviewFailureMessage(review, `正式プレビューの作成に失敗しました。${clip.previewError ?? ""}`, clip));
    }
  }
  return [...new Set(reasons)];
}

export function reviewNeedsPolling(review: SubtitleReviewDocument | null): boolean {
  if (review?.pendingSubtitleClipIds?.length) return true;
  if (!review || (review.subtitleOnlyAuto && review.state === "completed")) return false;
  return Boolean(
    (review.subtitleOnlyAuto && (review.state !== "awaiting_review" || review.confirmedClipCount > 0)) ||
    review.clips.some(clip => clip.automaticDecisionState === "queued" || clip.automaticDecisionState === "generating" ||
      clip.previewState === "queued" || clip.previewState === "rendering" ||
      (review.state === "awaiting_review" && !clip.livePreviewVideoUrl && clip.previewState !== "failed"))
  );
}

export async function loadReviewWithRenderStatus(jobId: string): Promise<SubtitleReviewDocument> {
  const review = await getSubtitleReview(jobId);
  if (review.subtitleOnlyAuto && (review.state === "render_queued" || review.state === "rendering")) {
    // A terminated worker can leave the review in rendering while the job is failed.
    // Keep the usable review on a transient status-fetch failure; the next poll retries it.
    const job = await getJobStatus(jobId).catch(() => null);
    if (job?.status === "failed") {
      review.automaticStopReasons = [...(review.automaticStopReasons ?? []),
        `書き出しで停止: ${job.error?.message || "処理が中断されました。処理状況を確認してください。"}`];
    }
  }
  return review;
}
