import type { SubtitleReviewClip, SubtitleReviewDocument } from "../types";

export function canEditManualFraming(review: SubtitleReviewDocument, clip: SubtitleReviewClip): boolean {
  return !review.subtitleOnlyAuto || (clip.confirmed && clip.automaticDecisionState === "ready"
    && (review.state === "awaiting_review" || review.state === "completed"));
}
