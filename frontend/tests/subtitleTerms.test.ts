import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SubtitleTermList } from "../components/SubtitleTermRules";
import { switchSubtitleTerm, termStatus, type CharacterSubtitleTerms, type SubtitleTerm } from "../lib/subtitleTerms";

Object.assign(globalThis, { React });
const term = (patch: Partial<SubtitleTerm> = {}): SubtitleTerm => ({ src: "ラデン", dst: "らでん", count: 15, jobs: 1, kept: 0,
  reversed: 0, active: true, disabled: false, ...patch });
const items: CharacterSubtitleTerms[] = [{ id: "c1", character: "儒烏風亭らでん", terms: [term(), term({ src: "ソピ", dst: "そぴ", count: 2,
  active: false })] }];
const render = (value: CharacterSubtitleTerms[]) => renderToStaticMarkup(React.createElement(SubtitleTermList, {
  items: value, busy: false, onSwitch: () => {} }));
assert.match(render(items), /儒烏風亭らでん/);
assert.match(render(items), /ラデン.*→.*らでん.*修正15回／1本/);
assert.match(render(items), /次の動画から自動で置換/);
assert.match(render(items), /学習中（3回、または1本で5回/);
assert.match(render([]), /学習した語はまだありません/);
assert.equal(termStatus(term({ disabled: true })), "使わない設定");
assert.match(termStatus(term({ active: false, reversed: 2 })), /元に戻された/);
assert.match(termStatus(term({ active: false, count: 3, kept: 5 })), /残す例が多い/);
assert.match(render([{ ...items[0], terms: [term({ disabled: true, active: false })] }]), /また使う/);
let sent: { url: string; body: string } | undefined;
globalThis.fetch = async (url, init) => {
  sent = { url: String(url), body: String(init?.body) };
  return new Response(null, { status: 204 });
};
switchSubtitleTerm("c1", term(), true).then(() => {
  assert.match(sent!.url, /api\/subtitle-terms\/c1\/disable$/);
  assert.deepEqual(JSON.parse(sent!.body), { src: "ラデン", dst: "らでん" });
  return switchSubtitleTerm("c1", term({ disabled: true }), false);
}).then(() => {
  assert.match(sent!.url, /api\/subtitle-terms\/c1\/enable$/);
  console.log("Subtitle terms: per-character list, status labels, disable/enable requests passed");
}).catch(error => { console.error(error); process.exitCode = 1; });
