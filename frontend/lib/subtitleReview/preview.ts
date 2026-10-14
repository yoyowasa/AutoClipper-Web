import { toApiUrl } from "../api";
import type { SubtitleReviewClip, SubtitleReviewDocument } from "../types";

export function previewVideoSrc(url: string, specHash: string): string {
  const resolved = toApiUrl(url);
  if (!specHash) {
    return resolved;
  }
  const separator = resolved.includes("?") ? "&" : "?";
  return `${resolved}${separator}v=${encodeURIComponent(specHash)}`;
}

export function isPreviewReady(
  clip: SubtitleReviewClip | null,
  reviewState: SubtitleReviewDocument["state"] | null | undefined
): boolean {
  return Boolean(
    clip?.previewState === "ready" &&
      clip.previewVideoUrl &&
      (reviewState !== "awaiting_review" || clip.previewSpecHash)
  );
}

export function shortTitleOutputExpected({
  renderMode,
  storedMode,
  topBannerEnabled,
  titleManuallyReviewed
}: {
  renderMode: string;
  storedMode: SubtitleReviewDocument["shortOverlayTitleMode"];
  topBannerEnabled: boolean;
  titleManuallyReviewed: boolean;
}): boolean {
  if (topBannerEnabled || storedMode === "always") {
    return true;
  }
  if (storedMode === "never") {
    return false;
  }
  if (renderMode === "high_quality") {
    return true;
  }
  return storedMode === "auto" && titleManuallyReviewed;
}
