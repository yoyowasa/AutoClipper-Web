import type { SubtitleReviewClip, SubtitleReviewDocument } from "../types";

export type LivePreviewReference = {
  url: string; version: string; start: number; end: number; hookDuration: number; framingKey: string;
};

export function editingPreviewAvailable(document: SubtitleReviewDocument | null, clip: SubtitleReviewClip | null): boolean {
  return Boolean(document?.sourceVideoUrl && (document.state === "awaiting_review" ||
    (document.subtitleOnlyAuto && clip?.confirmed && ["render_queued", "rendering"].includes(document.state))));
}
export function livePreviewReference(clip: SubtitleReviewClip, document: SubtitleReviewDocument): LivePreviewReference {
  const original = clip.previewFraming;
  return {
    url: clip.livePreviewVideoUrl ?? "", version: clip.livePreviewSpecHash ?? "", start: clip.start, end: clip.end,
    hookDuration: clip.livePreviewHookDurationSeconds ??
      (clip.hookSceneStart !== null && clip.hookSceneEnd !== null ? clip.hookSceneEnd - clip.hookSceneStart : 0),
    framingKey: JSON.stringify([original?.framing_offset_x ?? clip.framingOffsetX,
      original?.framing_offset_y ?? clip.framingOffsetY, original?.framing_zoom ?? clip.framingZoom,
      original?.short_layout ?? clip.shortLayout ?? document.shortLayout])
  };
}

export function livePlaybackSource(clip: SubtitleReviewClip, document: SubtitleReviewDocument, retained?: LivePreviewReference) {
  const reference = clip.livePreviewVideoUrl ? livePreviewReference(clip, document) : retained;
  if (reference && reference.start === clip.start && reference.end === clip.end) {
    return { url: reference.url, version: reference.version, mediaStart: reference.start, mediaOffset: reference.hookDuration, framingKey: reference.framingKey };
  }
  return { url: document.sourceVideoUrl, version: "", mediaStart: 0, mediaOffset: 0, framingKey: null };
}
