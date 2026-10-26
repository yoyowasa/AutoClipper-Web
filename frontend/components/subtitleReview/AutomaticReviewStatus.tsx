import Link from "next/link";
import type { SubtitleReviewClip, SubtitleReviewDocument } from "../../lib/types";
import { automaticReviewIsConfirmed, automaticReviewStopReasons, reviewFailureMessage } from "../../lib/subtitleReview/automaticStatus";

export function AutomaticReviewStatus({ review, error, selectedClip }: {
  review: SubtitleReviewDocument; error?: string | null; selectedClip?: SubtitleReviewClip | null;
}) {
  if (!review.subtitleOnlyAuto) return null;
  const reasons = automaticReviewStopReasons(review);
  if (error && review.state !== "completed") reasons.unshift(reviewFailureMessage(review, error, selectedClip ?? undefined));
  if (reasons.length) return <div role="alert" className="border border-red-300 bg-red-50 p-3 text-sm text-red-900">
    {[...new Set(reasons)].map(reason => <p key={reason}>{reason}</p>)}
  </div>;
  if (!automaticReviewIsConfirmed(review)) return null;
  return <p role="status" className="border border-sky-200 bg-sky-50 p-3 text-sm">
    {review.state === "completed"
      ? <>完成しました → <Link className="underline" href={`/results/${review.jobId}`}>投稿セットへ</Link></>
      : "書き出し準備中（完成したら表示します）"}
  </p>;
}
