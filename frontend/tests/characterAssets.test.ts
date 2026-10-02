import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CharacterAssetsManager } from "../components/CharacterAssetsManager";
import {
  CHARACTER_EMOTIONS, characterAssetSlots, deleteCharacterAsset, getCharacterAssets, uploadCharacterAsset, visibleCharacterAssetWarnings,
  type CharacterAsset, type CharacterAssetList
} from "../lib/characterAssets";

const asset: CharacterAsset = {
  id: "asset_1", presetId: "preset", emotion: "joy", slot: 2, imageUrl: "/api/character-assets/asset_1/image",
  width: 400, height: 300, hasAlpha: true, faceBox: { x: .1, y: .2, w: .3, h: .4 }, warnings: [], createdAt: "now"
};
assert.deepEqual(CHARACTER_EMOTIONS.map(item => item.value), ["joy", "anger", "sorrow", "fun"]);
assert.deepEqual(characterAssetSlots([asset], 5), [undefined, asset, undefined, undefined, undefined]);
const html = renderToStaticMarkup(createElement(CharacterAssetsManager, { presetId: "preset", onBusyChange: () => {} }));
assert.equal((html.match(/type="file"/g) ?? []).length, 20);
assert.equal((html.match(/ multiple=""/g) ?? []).length, 20);
assert.match(html, /grid-cols-4/);
assert.match(html, /使用が認められた素材だけ/);
assert.match(html, /胸から上が写った画像を登録してください/);
assert.match(html, /高さを人物枠に合わせます/);
const legacyWarnings = ["顔を検出できません（配置を手で調整してください）", "背景付き（切り抜きモデル未導入）", "素材の解像度が足りず粗くなります"];
assert.deepEqual(visibleCharacterAssetWarnings(legacyWarnings), legacyWarnings.slice(1));
assert.equal(legacyWarnings.length, 3); // Saved warnings are preserved; only their display changes.
assert.deepEqual(visibleCharacterAssetWarnings(), []);
for (const label of ["喜", "怒", "哀", "楽"]) {
  for (let slot = 1; slot <= 5; slot += 1) assert.ok(html.includes(`${label}の素材${slot}をアップロード`));
}

async function main() {
  const originalFetch = globalThis.fetch;
  const list: CharacterAssetList = {
    emotions: { joy: [asset], anger: [], sorrow: [], fun: [] }, minSidePixels: 300, maxImageBytes: 20 * 1024 * 1024, maxPerEmotion: 5
  };
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(init?.method === "DELETE" ? null : JSON.stringify(init?.method === "POST" ? asset : list), {
      status: init?.method === "DELETE" ? 204 : 200, headers: { "Content-Type": "application/json" }
    });
  };
  try {
    assert.deepEqual(await getCharacterAssets("preset"), list);
    const file = new File(["test png"], "a.png", { type: "image/png" });
    assert.deepEqual(await uploadCharacterAsset("preset", "joy", file), asset);
    assert.ok(calls[1].url.endsWith("/api/character-presets/preset/assets"));
    assert.equal(calls[1].init?.headers, undefined); // Browser supplies the multipart boundary.
    const form = calls[1].init?.body as FormData;
    assert.equal(form.get("emotion"), "joy");
    assert.equal((form.get("file") as File).name, "a.png");
    assert.equal(await deleteCharacterAsset("preset", asset.id), undefined);
    assert.ok(calls[2].url.endsWith("/assets/asset_1"));
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: "同じ表情は5枚までです。" }), { status: 422 });
    await assert.rejects(uploadCharacterAsset("preset", "joy", file), /5枚まで/);
  } finally { globalThis.fetch = originalFetch; }
  console.log("Character assets: four emotions, twenty multi-upload slots, multipart API, deletion and errors passed");
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
