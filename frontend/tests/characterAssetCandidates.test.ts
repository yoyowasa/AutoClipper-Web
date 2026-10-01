import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CandidateCard, CharacterAssetCandidatesPanel } from "../components/CharacterAssetCandidatesPanel";
import {
  adoptCandidate, candidateNeedsReview, deleteCharacterPreset, groupedCandidates, harvestCandidates, rejectCandidate,
  type CharacterAssetCandidate
} from "../lib/characterAssetCandidates";
import type { CharacterAssetList } from "../lib/characterAssets";
import { applyCharacter, captureCharacter, newCharacter } from "../lib/characterPresets";
import { DEFAULT_SETTINGS } from "../components/SettingsPanel";

const candidate: CharacterAssetCandidate = {
  id: "candidate_1", presetId: "preset", videoId: "video", sourceSecond: 10, imageUrl: "/api/character-asset-candidates/candidate_1/image",
  faceBox: { x: .2, y: .1, w: .3, h: .2 }, suggestedEmotion: "joy", usable: true, issues: [], score: .8,
  sameCharacter: null, status: "pending", warnings: [], createdAt: "now"
};
const questionable = { ...candidate, id: "questionable", sameCharacter: false };
assert.equal(candidateNeedsReview(questionable), true);
assert.equal(candidateNeedsReview({ ...candidate, usable: false }), true);
assert.equal(candidateNeedsReview({ ...candidate, status: "rejected" }), true);
const groups = groupedCandidates([
  candidate, { ...candidate, id: "stronger", score: .95 }, questionable,
  { ...candidate, id: "adopted", status: "adopted" }, { ...candidate, id: "unknown", suggestedEmotion: null, score: null }
], false);
assert.deepEqual(groups.find(group => group.emotion === "joy")?.candidates.map(item => item.id), ["stronger", "candidate_1"]);
assert.equal(groups.find(group => group.emotion === "unclassified")?.candidates[0].id, "unknown");
assert.equal(groupedCandidates([questionable], true)[0].candidates[0].id, "questionable");
const assets: CharacterAssetList = {
  emotions: { joy: [], anger: [], sorrow: [], fun: [] }, minSidePixels: 300, maxPerEmotion: 5, maxImageBytes: 20 * 1024 * 1024
};
function cardHtml(value: CharacterAssetCandidate, list = assets) {
  return renderToStaticMarkup(createElement(CandidateCard, {
    candidate: value, assets: list, disabled: false, onAdopt: () => {}, onReject: () => {}
  }));
}
assert.match(cardHtml(candidate), /表情を変えて採用/);
assert.match(cardHtml({ ...candidate, suggestedEmotion: null, score: null }), /判定なし/);
assert.match(cardHtml({ ...candidate, suggestedEmotion: "neutral" }), /disabled=""[^>]*>採用/);
assets.emotions.joy = Array.from({ length: 5 }, (_, index) => ({
  id: `asset_${index}`, presetId: "preset", emotion: "joy", slot: index + 1, imageUrl: "image", width: 300, height: 400,
  faceBox: null, hasAlpha: true, warnings: [], createdAt: "now"
}));
const full = cardHtml(candidate);
assert.match(full, /入れ替える素材枠/);
assert.match(full, /disabled=""[^>]*>採用/);
assert.match(renderToStaticMarkup(createElement(CharacterAssetCandidatesPanel, {
  presetId: "preset", onAssetsChange: () => {}, onBusyChange: () => {}
})), /動画から素材を集める/);
const cleared = newCharacter({ ...DEFAULT_SETTINGS, characterPresetId: "old", autoHarvestCharacterAssets: false });
assert.equal(cleared.characterPresetId, "");
assert.equal(cleared.autoHarvestCharacterAssets, true);
const snapshot = captureCharacter({ ...DEFAULT_SETTINGS, autoHarvestCharacterAssets: false });
assert.equal(snapshot.autoHarvestCharacterAssets, false);
assert.equal(applyCharacter(cleared, { id: "new", name: "新キャラ", settings: snapshot }).characterPresetId, "new");

async function main() {
  const originalFetch = globalThis.fetch;
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(init?.method === "DELETE" || String(input).endsWith("/reject") ? null : "{}", {
      status: init?.method === "DELETE" || String(input).endsWith("/reject") ? 204 : 200,
      headers: { "Content-Type": "application/json" }
    });
  };
  try {
    await harvestCandidates("preset", "video");
    assert.deepEqual(JSON.parse(String(calls[0].init?.body)), { videoId: "video" });
    assert.ok(calls[0].url.endsWith("/asset-harvests"));
    await adoptCandidate("preset", "candidate", "anger", 3);
    assert.deepEqual(JSON.parse(String(calls[1].init?.body)), { emotion: "anger", replaceSlot: 3 });
    await rejectCandidate("preset", "candidate");
    assert.ok(calls[2].url.endsWith("/asset-candidates/candidate/reject"));
    await deleteCharacterPreset("preset", { assets: 5, candidates: 48 });
    assert.equal(calls[3].init?.method, "DELETE");
    assert.deepEqual(JSON.parse(String(calls[3].init?.body)), { assets: 5, candidates: 48 });
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "枠を選んでください。" }), { status: 422 });
    await assert.rejects(adoptCandidate("preset", "candidate", "joy"), /枠を選んで/);
  } finally { globalThis.fetch = originalFetch; }
  console.log("character harvesting, human adoption, replacement and deletion contracts passed");
}
void main().catch(reason => { console.error(reason); process.exitCode = 1; });
