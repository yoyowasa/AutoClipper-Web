import assert from "node:assert/strict";

import {
  descriptionWithHashtags,
  hashtagsFromText,
  parseYouTubeSourceFromFilename,
  postMetadataApplyPayload,
  tagsFromText,
  youtubeTagsText
} from "../lib/youtubePosting";

const detected = parseYouTubeSourceFromFilename(
  "【雑談】たのしい休肝日計画【儒烏風亭らでん #ReGLOSS】 [z8eCi7kAEVI].mp4"
);
assert.deepEqual(detected, {
  title: "【雑談】たのしい休肝日計画【儒烏風亭らでん #ReGLOSS】",
  url: "https://www.youtube.com/watch?v=z8eCi7kAEVI"
});
assert.equal(parseYouTubeSourceFromFilename("local-video.mp4"), null);
assert.deepEqual(hashtagsFromText("#ReGLOSS ReGLOSS #切り抜き"), [
  "#ReGLOSS",
  "#切り抜き"
]);
assert.deepEqual(tagsFromText("らでん,ReGLOSS、らでん\n休肝日"), [
  "らでん",
  "ReGLOSS",
  "休肝日"
]);
assert.equal(
  descriptionWithHashtags("元配信：\nタイトル", ["#ReGLOSS", "#shortsfunny"]),
  "元配信：\nタイトル\n\n#ReGLOSS #shortsfunny"
);
assert.equal(youtubeTagsText(["らでん", "ReGLOSS"]), "らでん,ReGLOSS");

console.log("youtube posting helpers: ok");

for (const clipType of ["normal", "short"]) {
  const draft = {
    titleCandidates: [{ id: "chosen", title: `${clipType}公開タイトル`, intent: "factual" as const, reason: "最新字幕", evidenceSegmentIds: ["seg-edited"] }],
    recommendedTitleId: "chosen",
    selectedTitleId: "chosen",
    youtubeDescription: " 修正後の字幕から生成した説明欄 ",
    youtubeHashtagsText: "#切り抜き #ReGLOSS",
    youtubeTagsText: "らでん,ReGLOSS",
    descriptionEvidenceSegmentIds: ["seg-edited"],
    postMetadataSource: "codex",
    postMetadataRevisionHash: "new-subtitle-revision"
  };
  // A proposal generated from unsaved subtitles must survive their joint save.
  const payload = postMetadataApplyPayload(draft);
  assert.deepEqual(payload.titleCandidates, draft.titleCandidates);
  assert.equal(payload.selectedTitleId, "chosen");
  assert.equal(payload.postMetadataSource, "codex");
  assert.equal(payload.postMetadataRevisionHash, "new-subtitle-revision");
  assert.deepEqual(payload.descriptionEvidenceSegmentIds, ["seg-edited"]);
  assert.equal(payload.youtubeDescription, "修正後の字幕から生成した説明欄");
  const manual = postMetadataApplyPayload({ ...draft, postMetadataSource: "manual", selectedTitleId: null });
  assert.deepEqual(manual.titleCandidates, draft.titleCandidates);
  assert.equal(manual.postMetadataRevisionHash, "new-subtitle-revision");
}

console.log("posting metadata save payload: ok");
