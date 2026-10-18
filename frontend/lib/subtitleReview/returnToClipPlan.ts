import type { SubtitleReviewDocument } from "../types";

export function returnToClipPlanMessage(review: SubtitleReviewDocument, hasDrafts: boolean): string {
  // Legacy reviews did not track saves; never claim their changes were not saved.
  const saved = review.hasSavedReviewChanges !== false || review.editedSegmentCount > 0
    || review.clips.some(clip => clip.confirmed || clip.titleEdited);
  return saved
    ? "字幕確認での修正（字幕・タイトル・フック・画角など）はすべて破棄されます。切り抜き確認に戻りますか？"
    : `字幕確認でまだ修正を保存していません。${hasDrafts ? "入力中の下書きは破棄されます。" : ""}切り抜き確認に戻りますか？`;
}
