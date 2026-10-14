"use client";

import { SubtitleReviewScreen } from "../../../../components/subtitleReview/SubtitleReviewScreen";
import { useSubtitleReviewDocument } from "../../../../lib/subtitleReview/hooks/useSubtitleReviewDocument";

export default function SubtitleReviewPage() {
  const model = useSubtitleReviewDocument();
  return <SubtitleReviewScreen model={model} />;
}
