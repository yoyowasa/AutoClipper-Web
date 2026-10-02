import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ThumbnailAssetPicker } from "../components/ThumbnailAssetPicker";
import { ResultThumbnailEditor } from "../components/ResultThumbnailEditor";
import { thumbnailTextDefaults } from "../lib/thumbnailStyle";
import { getThumbnailAssets, prepareThumbnailPreview, renderThumbnailPreview, regenerateExportThumbnail } from "../lib/api";
import type { ResultExportItem, ThumbnailSubjectSelection } from "../lib/types";

const selection: ThumbnailSubjectSelection = { subjectSource: "asset", characterAssetId: "asset_example", emotion: "joy" };
const picker = renderToStaticMarkup(createElement(ThumbnailAssetPicker, {
  exportId: "exp_example", value: selection, onChange: () => {}
}));
assert.match(picker, /動画のコマ/);
assert.match(picker, />素材</);
for (const label of ["喜", "怒", "哀", "楽"]) assert.ok(picker.includes(`disabled="" class="min-h-9 border border-neutral-400 text-sm aria-pressed:bg-sky-100 disabled:text-neutral-400">${label}`));
const warning = "表情を自動で選べませんでした（仮に喜を使用）";
const editor = renderToStaticMarkup(createElement(ResultThumbnailEditor, {
  item: { id: "exp_example", thumbnailRenderRevision: 1, thumbnailSubjectSource: "asset", thumbnailCharacterAssetId: "asset_example",
    thumbnailEmotion: "joy", thumbnailWarnings: [warning, "素材の解像度が足りず粗くなります"], thumbnailEmotionReason: "自動選択に失敗しました。" } as ResultExportItem,
  onRender: () => {}, onDraftChange: () => {}, styles: thumbnailTextDefaults(), setStyles: () => {}, regions: null
}));
assert.ok(editor.includes(warning) && editor.includes("表情の選択理由"));
assert.ok(!editor.includes("素材の解像度が足りず粗くなります")); // The live preview supplies the current scale warning.
assert.match(editor, /文言に合う表情を選び直す/);
assert.match(editor, /顔を検出できなかった素材も、大きさ・左右・上下で調整/);

async function main() {
  const originalFetch = globalThis.fetch;
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    if (String(input).endsWith("/preview")) return new Response(new Blob(["jpeg"]), { headers: {
      "X-Thumbnail-Text-Regions": "{}", "X-Thumbnail-Warnings": JSON.stringify(["素材の解像度が足りず粗くなります"])
        .replace(/[\u007f-\uffff]/g, character => `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`)
    } });
    return new Response(JSON.stringify({ state: "ready", frameKey: "key", emotions: { joy: [], anger: [], sorrow: [], fun: [] } }), {
      headers: { "Content-Type": "application/json" }
    });
  };
  try {
    await getThumbnailAssets("exp_example");
    assert.ok(calls[0].url.endsWith("/thumbnail/assets"));
    await prepareThumbnailPreview("exp_example", new AbortController().signal, false, selection);
    const query = new URL(calls[1].url).searchParams;
    assert.equal(query.get("subjectSource"), "asset");
    assert.equal(query.get("characterAssetId"), selection.characterAssetId);
    const draft = { ...selection, frameKey: "key", text: { heading: "", upper: "見どころ", lower: "" },
      textStyles: thumbnailTextDefaults(), design: "raden" as const, subjectPlacement: { scale: 1.5, offsetX: -20, offsetY: 15 } };
    const preview = await renderThumbnailPreview("exp_example", draft, new AbortController().signal);
    assert.deepEqual(preview.warnings, ["素材の解像度が足りず粗くなります"]);
    assert.deepEqual(JSON.parse(String(calls[2].init?.body)), draft);
    await regenerateExportThumbnail("exp_example", { frameSeconds: 4, subjectAnchorX: 1, ...draft });
    const saved = JSON.parse(String(calls[3].init?.body));
    assert.equal(saved.characterAssetId, selection.characterAssetId);
    assert.deepEqual(saved.subjectPlacement, draft.subjectPlacement);
    await regenerateExportThumbnail("exp_example", { frameSeconds: 4, subjectAnchorX: 1, subjectSource: "asset", selectWithCodex: true });
    const auto = JSON.parse(String(calls[4].init?.body));
    assert.equal(auto.selectWithCodex, true);
    assert.equal(auto.characterAssetId, undefined);
    assert.equal(auto.emotion, undefined);
    await prepareThumbnailPreview("exp_example", new AbortController().signal, false, { subjectSource: "video" });
    assert.equal(new URL(calls[5].url).searchParams.get("subjectSource"), "video");
    assert.equal(new URL(calls[5].url).searchParams.has("characterAssetId"), false);
  } finally { globalThis.fetch = originalFetch; }
  console.log("Thumbnail assets: source/emotion controls, fallback notices, preview warnings and selection payloads passed");
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
