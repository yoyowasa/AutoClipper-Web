import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FinalInspectionAttention, finalInspectionProblems } from "../components/FinalInspectionAttention";

Object.assign(globalThis, { React });
assert.deepEqual(finalInspectionProblems({}), []);
assert.deepEqual(finalInspectionProblems({ finalInspection: [{ reason: "invalid" }] }), []);
const details = { finalInspection: [{ clipLabel: "ショート2", reason: "ショート2：字幕が帯と重なっています。（完成動画 2.0秒）", repairCount: 2 }] };
const html = renderToStaticMarkup(React.createElement(FinalInspectionAttention, { details }));
assert.match(html, /完成検査で停止しました/);
assert.match(html, /ショート2/);
assert.match(html, /完成動画 2.0秒/);
assert.match(html, /自動修復 2回/);
assert.match(html, /もう一度確定して書き出せます/);
assert.doesNotMatch(html, /cand_/);
assert.equal(renderToStaticMarkup(React.createElement(FinalInspectionAttention, { details: {} })), "");
console.log("Incomplete clips show display names, time, reason and bounded repair count without exposing IDs.");
