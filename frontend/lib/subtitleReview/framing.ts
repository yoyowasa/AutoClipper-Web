import type { SubtitleReviewClipFramingUpdateRequest } from "../types";

export type ShortFramingDrafts = Record<
  string,
  SubtitleReviewClipFramingUpdateRequest
>;

export function shortFramingSignature(
  framing: SubtitleReviewClipFramingUpdateRequest
): string {
  return `${framing.framingOffsetX}:${framing.framingOffsetY}:${framing.framingZoom}`;
}

export function shortFramingEquals(
  left: SubtitleReviewClipFramingUpdateRequest,
  right: SubtitleReviewClipFramingUpdateRequest
): boolean {
  return shortFramingSignature(left) === shortFramingSignature(right);
}
