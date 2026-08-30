import assert from "node:assert/strict";

import {
  descriptionWithHashtags,
  hashtagsFromText,
  parseYouTubeSourceFromFilename,
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
