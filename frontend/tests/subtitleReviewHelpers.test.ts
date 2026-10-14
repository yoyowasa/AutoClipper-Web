import assert from "node:assert/strict";

import { contentDraftForClip, isClipContentDirty, stylesEqual } from "../lib/subtitleReview/drafts";
import { hashtagsFromText, normalizeYoutubeHashtags, postCopyText } from "../lib/subtitleReview/posting";
import { limitToTwoTextLines, normalizeReviewTitle } from "../lib/subtitleReview/text";
import type { ClipTextStyle, SubtitleReviewClip } from "../lib/types";

const style: ClipTextStyle = {
  fontPreset: null, fontName: "Noto Sans JP", bold: false, fontSize: 54,
  primaryColor: "#FFFFFF", outlineColor: "#000000", outlineWidth: 3,
  xPercent: 50, yPercent: 80, positionMode: "explicit"
};
const clip: SubtitleReviewClip = {
  id: "clip-01", type: "short", title: "画面の文言", publicationTitle: "公開用タイトル",
  titleCandidates: [{ id: "title-01", title: "公開用タイトル", intent: "factual", reason: "字幕の内容", evidenceSegmentIds: ["seg-01"] }],
  recommendedTitleId: "title-01", selectedTitleId: "title-01",
  youtubeDescription: "投稿用の説明", youtubeHashtags: ["#題材", "#切り抜き"], youtubeTags: ["題材", "切り抜き"],
  descriptionEvidenceSegmentIds: ["seg-01"], postMetadataSource: "codex", postMetadataRevisionHash: "saved-revision",
  originalTitle: "元の文言", titleEdited: true, overlayTitleExpected: true,
  hookText: "冒頭のフック", hookDurationSeconds: 2.5, hookSceneStart: 101, hookSceneEnd: 103,
  thumbnailKicker: "小見出し", thumbnailLine1: "上の文言", thumbnailLine2: "下の文言", thumbnailFrameSeconds: 5,
  titleStyle: style, hookStyle: null, subtitleStyle: style,
  subtitleStyles: [{ start: 101, end: 103, style }],
  framingOffsetX: 0, framingOffsetY: 0, framingZoom: 1,
  resolvedTitleStyle: null, resolvedHookStyle: null, resolvedSubtitleStyle: null,
  resolvedDefaultTitleStyle: null, resolvedDefaultHookStyle: null, resolvedDefaultSubtitleStyle: null,
  subtitleMaxCharsPerLine: null, subtitleMaxLines: null, subtitleMinDurationSeconds: null,
  subtitleMaxDurationSeconds: null, subtitleMinGapSeconds: null, previewWidth: null, previewHeight: null,
  start: 100, end: 175, duration: 75, previewState: "ready", previewSpecHash: "preview-spec", previewError: null,
  previewVideoUrl: "/preview.mp4", livePreviewSpecHash: null, livePreviewVideoUrl: null,
  segmentIds: ["seg-01"], confirmed: false, editedSegmentCount: 0
};

const snapshot = structuredClone(clip);
const draft = contentDraftForClip(clip);
assert.equal(draft.publicationTitle, "公開用タイトル");
assert.equal(draft.title, "画面の文言");
assert.equal(draft.youtubeHashtagsText, "#題材 #切り抜き");
assert.equal(draft.youtubeTagsText, "題材,切り抜き");
assert.equal(draft.selectedTitleId, "title-01");
assert.equal(draft.postMetadataRevisionHash, "saved-revision");
assert.deepEqual(draft.subtitleStyles, clip.subtitleStyles);
assert.deepEqual(clip, snapshot, "building a draft must not change the saved clip");

const emptyClip = {
  ...clip, publicationTitle: null, titleCandidates: [], recommendedTitleId: null, selectedTitleId: null,
  youtubeDescription: "", youtubeHashtags: [], youtubeTags: [], descriptionEvidenceSegmentIds: [],
  postMetadataSource: null, postMetadataRevisionHash: null, thumbnailKicker: "", thumbnailLine1: "", thumbnailLine2: "",
  thumbnailFrameSeconds: null, subtitleStyles: undefined
};
const emptyDraft = contentDraftForClip(emptyClip);
assert.equal(emptyDraft.publicationTitle, clip.title, "missing publication title uses the overlay title");
assert.deepEqual(emptyDraft.titleCandidates, []);
assert.equal(emptyDraft.selectedTitleId, null);
assert.equal(emptyDraft.youtubeHashtagsText, "");
assert.equal(emptyDraft.youtubeTagsText, "");
assert.equal(emptyDraft.postMetadataSource, null);
assert.equal(emptyDraft.thumbnailFrameSeconds, null);
assert.deepEqual(emptyDraft.subtitleStyles, []);
assert.equal(isClipContentDirty(emptyClip, { [clip.id]: emptyDraft }), false);

assert.equal(stylesEqual(null, null), true);
assert.equal(stylesEqual(style, null), false);
assert.equal(stylesEqual(null, style), false);
assert.equal(stylesEqual(style, structuredClone(style)), true);
assert.equal(stylesEqual(style, { ...style, outerOutlineWidth: 0, outerOutlineColor: "#FFFFFF" }), true);
for (const changed of [
  { ...style, fontSize: 60 }, { ...style, fontName: "Another font" }, { ...style, bold: true },
  { ...style, primaryColor: "#FF0000" }, { ...style, outlineColor: "#111111" }, { ...style, outlineWidth: 4 },
  { ...style, outerOutlineWidth: 1 }, { ...style, outerOutlineColor: "#FF0000" },
  { ...style, xPercent: 40 }, { ...style, yPercent: 60 }, { ...style, positionMode: "layout" as const }
]) {
  assert.equal(stylesEqual(style, changed), false, "different saved text styling must be detected");
}

assert.equal(isClipContentDirty(clip, {}), false);
assert.equal(isClipContentDirty(clip, { [clip.id]: structuredClone(draft) }), false);
assert.equal(isClipContentDirty(clip, { "other-clip": { ...draft, title: "別の文言" } }), false);
for (const changed of [
  { ...draft, title: "修正した画面の文言" }, { ...draft, publicationTitle: "修正した公開用タイトル" },
  { ...draft, titleCandidates: [] }, { ...draft, selectedTitleId: null }, { ...draft, recommendedTitleId: null },
  { ...draft, youtubeDescription: "新しい説明" }, { ...draft, youtubeHashtagsText: "#別の題材" },
  { ...draft, descriptionEvidenceSegmentIds: [] }, { ...draft, postMetadataSource: "manual" },
  { ...draft, postMetadataRevisionHash: "edited-revision" }, { ...draft, hookText: "新しいフック" },
  { ...draft, hookDurationSeconds: 3 }, { ...draft, hookSceneStart: 102 }, { ...draft, hookSceneEnd: 104 },
  { ...draft, thumbnailKicker: "新しい小見出し" }, { ...draft, thumbnailLine1: "新しい上行" },
  { ...draft, thumbnailLine2: "新しい下行" }, { ...draft, thumbnailFrameSeconds: 6 },
  { ...draft, titleStyle: { ...style, fontSize: 60 } }, { ...draft, hookStyle: style },
  { ...draft, subtitleStyle: { ...style, outlineWidth: 4 } }, { ...draft, subtitleStyles: [] }
]) {
  assert.equal(isClipContentDirty(clip, { [clip.id]: changed }), true, "unsaved content must be detected");
}
assert.equal(isClipContentDirty(clip, { [clip.id]: { ...draft, youtubeHashtagsText: "題材, #題材、切り抜き" } }), false);
assert.equal(isClipContentDirty(clip, { [clip.id]: { ...draft, youtubeHashtagsText: "#切り抜き #題材" } }), true);
// Characterize the existing comparison scope; this refactor does not add tag-only detection.
assert.equal(isClipContentDirty(clip, { [clip.id]: { ...draft, youtubeTagsText: "違うタグ" } }), false);

const hashtags = [" 題材, #題材、切り抜き ", "#Tag tag", "", " \n "];
assert.deepEqual(normalizeYoutubeHashtags(hashtags), ["#題材", "#切り抜き", "#Tag", "#tag"]);
assert.deepEqual(hashtags, [" 題材, #題材、切り抜き ", "#Tag tag", "", " \n "], "formatting must not mutate input");
assert.deepEqual(hashtagsFromText("\t題材、題材 #切り抜き\n"), ["#題材", "#切り抜き"]);
assert.deepEqual(hashtagsFromText(""), []);
assert.deepEqual(normalizeYoutubeHashtags(Array.from({ length: 15 }, (_, i) => `tag${i}`)),
  Array.from({ length: 12 }, (_, i) => `#tag${i}`));
assert.equal(postCopyText(" タイトル ", " 説明 ", ["題材 #題材", "切り抜き"]), "タイトル\n\n説明\n\n#題材 #切り抜き");

assert.equal(limitToTwoTextLines(""), "");
assert.equal(limitToTwoTextLines("  1行だけ  "), "  1行だけ  ");
assert.equal(limitToTwoTextLines("上\n下"), "上\n下");
assert.equal(limitToTwoTextLines("上\n下\n補足"), "上\n下 補足");
for (const separator of ["\r\n", "\r", "\u2028", "\u2029", "\\N"]) {
  assert.equal(limitToTwoTextLines(`上${separator}下${separator}補足`), "上\n下 補足");
}
assert.equal(limitToTwoTextLines("\n下\n補足"), "\n下 補足");
assert.equal(normalizeReviewTitle("  上   の  行 \r\n 下\tの 行 \n補足 "), "上 の 行\n下 の 行 補足");

console.log("Subtitle review helpers: drafts, dirty checks, styling, hashtags and two-line text passed");
