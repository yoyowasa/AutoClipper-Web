import type { ClipTextStyle, PostTitleCandidate, SubtitleReviewClip } from "../types";
import { youtubeTagsText } from "../youtubePosting";
import { hashtagsFromText, normalizeYoutubeHashtags } from "./posting";

export type ClipContentDraft = {
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
  const draft = drafts[clip.id];
  return Boolean(
    draft &&
      (draft.title !== clip.title ||
        draft.publicationTitle !== (clip.publicationTitle ?? clip.title) ||
        JSON.stringify(draft.titleCandidates) !== JSON.stringify(clip.titleCandidates ?? []) ||
        draft.recommendedTitleId !== (clip.recommendedTitleId ?? null) ||
        draft.selectedTitleId !== (clip.selectedTitleId ?? null) ||
        draft.youtubeDescription !== (clip.youtubeDescription ?? "") ||
        JSON.stringify(hashtagsFromText(draft.youtubeHashtagsText)) !==
          JSON.stringify(normalizeYoutubeHashtags(clip.youtubeHashtags ?? [])) ||
        JSON.stringify(draft.descriptionEvidenceSegmentIds) !==
          JSON.stringify(clip.descriptionEvidenceSegmentIds ?? []) ||
        draft.postMetadataSource !== (clip.postMetadataSource ?? null) ||
        draft.postMetadataRevisionHash !== (clip.postMetadataRevisionHash ?? null) ||
        draft.hookText !== clip.hookText ||
        draft.hookDurationSeconds !== clip.hookDurationSeconds ||
        draft.hookSceneStart !== clip.hookSceneStart ||
        draft.hookSceneEnd !== clip.hookSceneEnd ||
        draft.thumbnailKicker !== (clip.thumbnailKicker ?? "") ||
        draft.thumbnailLine1 !== (clip.thumbnailLine1 ?? "") ||
        draft.thumbnailLine2 !== (clip.thumbnailLine2 ?? "") ||
        draft.thumbnailFrameSeconds !== (clip.thumbnailFrameSeconds ?? null) ||
        !stylesEqual(draft.titleStyle, clip.titleStyle) ||
        !stylesEqual(draft.hookStyle, clip.hookStyle) ||
        !stylesEqual(draft.subtitleStyle, clip.subtitleStyle) ||
        JSON.stringify(draft.subtitleStyles) !== JSON.stringify(clip.subtitleStyles ?? []))
  );
}
