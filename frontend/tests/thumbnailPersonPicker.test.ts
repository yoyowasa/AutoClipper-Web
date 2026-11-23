import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ThumbnailFramePicker } from "../components/ThumbnailFramePicker";
import { ThumbnailPersonPicker } from "../components/ThumbnailPersonPicker";
import { regenerateExportThumbnail, renderThumbnailPreview, thumbnailCandidatePeople } from "../lib/api";
import type { ThumbnailPerson } from "../lib/types";

const people: ThumbnailPerson[] = [
  { index: 0, x: .5, y: .3, width: .15, height: .18, closeAvailable: false },
  { index: 1, x: .2, y: .32, width: .1, height: .12, closeAvailable: true },
];
const picker = (selectedIndex: number, list = people) => renderToStaticMarkup(createElement(ThumbnailPersonPicker, {
  imageUrl: "/api/exports/exp/thumbnail/candidates/frame_00/image", people: list, selectedIndex, onSelect: () => {} }));

// A still with only the automatic face needs no chooser.
assert.equal(picker(0, people.slice(0, 1)), "");
const html = picker(1);
assert.match(html, /中心にする人物/);
assert.match(html, /人物1（自動）/);
assert.match(html, /aria-label="人物2を中心にする"/);
assert.match(html, /left:15(\.0+\d*)?%;top:26%;width:10%;height:12%/);
assert.equal((html.match(/aria-pressed="true"/g) ?? []).length, 2);  // the box and the button for person 2

// The close-up button follows the chosen person, not the automatic face.
const frame = (closeAvailable?: boolean) => renderToStaticMarkup(createElement(ThumbnailFramePicker, {
  candidates: [{ id: "frame_00", second: 1, score: 1, closeAvailable: false, imageUrl: "/x" }], selectedId: "frame_00",
  cropMode: "standard", closeAvailable, onSelect: () => {}, onCropChange: () => {} }));
assert.match(frame(), /disabled=""[^>]*>顔のアップ/);
assert.doesNotMatch(frame(true), /disabled=""[^>]*>顔のアップ/);

async function main() {
  const originalFetch = globalThis.fetch;
  const calls: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    if (String(input).includes("/thumbnail/preview")) return new Response(new Blob(["jpg"]), { headers: { "X-Thumbnail-Text-Regions": "{}" } });
    return new Response(JSON.stringify({ people, exportId: "exp", status: "generating", revision: 1 }), {
      headers: { "Content-Type": "application/json" } });
  };
  try {
    assert.deepEqual(await thumbnailCandidatePeople("exp", "frame_00"), people);
    assert.ok(calls[0].url.endsWith("/api/exports/exp/thumbnail/candidates/frame_00/people"));
    await regenerateExportThumbnail("exp", { frameSeconds: 0, subjectAnchorX: 1, frameCandidateId: "frame_00", subjectFaceIndex: 1 });
    assert.equal(JSON.parse(String(calls[1].init?.body)).subjectFaceIndex, 1);
    await renderThumbnailPreview("exp", { frameKey: "k", frameCandidateId: "frame_00", subjectFaceIndex: 1,
      text: { heading: "", upper: "a", lower: "" }, textStyles: {} as never, design: "raden",
      subjectPlacement: { scale: 1, offsetX: 0, offsetY: 0 } }, new AbortController().signal);
    assert.equal(JSON.parse(String(calls[2].init?.body)).subjectFaceIndex, 1);
  } finally { globalThis.fetch = originalFetch; }
  console.log("thumbnailPersonPicker ok");
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
