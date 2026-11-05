import { contentFieldEquals, type ClipContentDraft } from "./drafts";
import type { SubtitleReviewClip } from "../types";

export function cueStylesChanged(clip: SubtitleReviewClip, draft?: ClipContentDraft | null): boolean {
  return Boolean(draft && !contentFieldEquals("subtitleStyles", draft.subtitleStyles, clip.subtitleStyles ?? []));
}
