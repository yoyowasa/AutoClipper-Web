import assert from "node:assert/strict";
import { applyCharacter, captureCharacter, newCharacter } from "../lib/characterPresets";
import { DEFAULT_SETTINGS } from "../components/SettingsPanel";

const original = { ...DEFAULT_SETTINGS, youtubeSourceTitle: "現在の動画", youtubeSourceUrl: "https://www.youtube.com/watch?v=12345678901" };
const a = { ...original, channelName: "チャンネルA", youtubePostingProfile: {
  performerName: "キャラA", affiliation: "グループA", baseHashtags: ["#キャラA"], shortHashtags: ["#shorts"], baseTags: ["キャラA"]
}, normalTitleSuffix: "【キャラA】", shortTopBannerAssetId: "a".repeat(64) };
const b = newCharacter(a);
assert.equal(b.normalClipCount, 0);
assert.equal(b.shortTopBannerEnabled, false);
assert.deepEqual(b.youtubePostingProfile.baseTags, []);
assert.equal(b.normalTitleSuffix, "");
const snapshot = captureCharacter(a);
assert.equal("youtubeSourceTitle" in snapshot, false);
assert.equal("youtubeSourceUrl" in snapshot, false);
const restored = applyCharacter(b, { name: "チャンネルA／キャラA", settings: snapshot });
assert.equal(restored.youtubePostingProfile.performerName, "キャラA");
assert.equal(restored.shortTopBannerAssetId, "a".repeat(64));
assert.equal(restored.youtubeSourceTitle, "現在の動画");
assert.equal(restored.normalTitleSuffix, "【キャラA】");
restored.youtubePostingProfile.baseTags.push("変更");
assert.deepEqual(snapshot.youtubePostingProfile?.baseTags, ["キャラA"]);
console.log("character preset switching keeps source fields and isolates character settings");
