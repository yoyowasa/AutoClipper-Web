import type { ClipTextStyle, PostTitleCandidate, SubtitleReviewClip } from "../types";
import { youtubeTagsText } from "../youtubePosting";
import { hashtagsFromText } from "./posting";

export type ClipContentDraft = {
  // Browser-only intent: full server snapshots are never evidence of a user edit.
  _editedFields?: string[];
  subtitleStyles: NonNullable<SubtitleReviewClip["subtitleStyles"]>;
  publicationTitle: string;
  titleCandidates: PostTitleCandidate[];
  recommendedTitleId: string | null;
  selectedTitleId: string | null;
  youtubeDescription: string;
  youtubeHashtagsText: string;
  youtubeTagsText: string;
  descriptionEvidenceSegmentIds: string[];
  postMetadataSource: string | null;
  postMetadataRevisionHash: string | null;
  title: string;
  hookText: string;
  hookDurationSeconds: number;
  hookSceneStart: number | null;
  hookSceneEnd: number | null;
  thumbnailKicker: string;
  thumbnailLine1: string;
  thumbnailLine2: string;
  thumbnailFrameSeconds: number | null;
  titleStyle: ClipTextStyle | null;
  hookStyle: ClipTextStyle | null;
  subtitleStyle: ClipTextStyle | null;
};

export function contentDraftForClip(clip: SubtitleReviewClip): ClipContentDraft {
  return {
    publicationTitle: clip.publicationTitle ?? clip.title,
    titleCandidates: clip.titleCandidates ?? [],
    recommendedTitleId: clip.recommendedTitleId ?? null,
    selectedTitleId: clip.selectedTitleId ?? null,
    youtubeDescription: clip.youtubeDescription ?? "",
    youtubeHashtagsText: (clip.youtubeHashtags ?? []).join(" "),
    youtubeTagsText: youtubeTagsText(clip.youtubeTags ?? []),
    descriptionEvidenceSegmentIds: clip.descriptionEvidenceSegmentIds ?? [],
    postMetadataSource: clip.postMetadataSource ?? null,
    postMetadataRevisionHash: clip.postMetadataRevisionHash ?? null,
    title: clip.title,
    hookText: clip.hookText,
    hookDurationSeconds: clip.hookDurationSeconds,
    hookSceneStart: clip.hookSceneStart,
    hookSceneEnd: clip.hookSceneEnd,
    thumbnailKicker: clip.thumbnailKicker ?? "",
    thumbnailLine1: clip.thumbnailLine1 ?? "",
    thumbnailLine2: clip.thumbnailLine2 ?? "",
    thumbnailFrameSeconds: clip.thumbnailFrameSeconds ?? null,
    titleStyle: clip.titleStyle,
    hookStyle: clip.hookStyle,
    subtitleStyle: clip.subtitleStyle,
    subtitleStyles: clip.subtitleStyles ?? []
  };
}

export function stylesEqual(
  left: ClipTextStyle | null,
  right: ClipTextStyle | null
): boolean {
  if (left === right) {
    return true;
  }
  if (!left || !right) {
    return false;
  }
  return (
    left.fontPreset === right.fontPreset &&
    left.fontName === right.fontName &&
    left.bold === right.bold &&
    left.fontSize === right.fontSize &&
    left.primaryColor === right.primaryColor &&
    left.outlineColor === right.outlineColor &&
    left.outlineWidth === right.outlineWidth &&
    (left.outerOutlineWidth ?? 0) === (right.outerOutlineWidth ?? 0) &&
    (left.outerOutlineColor ?? "#FFFFFF") === (right.outerOutlineColor ?? "#FFFFFF") &&
    left.xPercent === right.xPercent &&
    left.yPercent === right.yPercent &&
    left.positionMode === right.positionMode
  );
}

export function isClipContentDirty(
  clip: SubtitleReviewClip,
  drafts: Record<string, ClipContentDraft>
): boolean {
  return contentDraftChangedFields(clip, drafts[clip.id]).length > 0;
}

export function contentFieldEquals(key: string, left: unknown, right: unknown): boolean {
  if (["titleStyle", "hookStyle", "subtitleStyle"].includes(key)) return stylesEqual(left as ClipTextStyle | null, right as ClipTextStyle | null);
  if (key === "youtubeHashtagsText") return JSON.stringify(hashtagsFromText(String(left))) === JSON.stringify(hashtagsFromText(String(right)));
  return JSON.stringify(left) === JSON.stringify(right);
}

export function contentDraftChangedFields(clip: SubtitleReviewClip, draft?: ClipContentDraft): string[] {
  if (!draft) return [];
  const saved = contentDraftForClip(clip);
  return Object.keys(saved).filter(key => !contentFieldEquals(key, draft[key as keyof ClipContentDraft], saved[key as keyof ClipContentDraft]));
}
