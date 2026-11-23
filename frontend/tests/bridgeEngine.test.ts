import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { BridgeEngineForm } from "../components/BridgeEngineSettingsPanel";
import { choose, laneStatus, type BridgeEngineState } from "../lib/bridgeEngine";

Object.assign(globalThis, { React });
const catalog = {
  codex: [{ id: "gpt-6.1-sol", efforts: ["low", "medium", "high"] }, { id: "gpt-6.2-sol", efforts: ["low", "ultra"] }],
  claude: [{ id: "claude-opus-5-5", efforts: ["low", "medium", "max"] }, { id: "claude-sonnet-5-5", efforts: ["low", "high"] }],
};
const saved = {
  normal: { engine: "codex" as const, model: "gpt-6.1-sol", effort: "medium" },
  analysis: { engine: "claude" as const, model: "claude-opus-5-5", effort: "medium" },
};
const state: BridgeEngineState = { saved, active: saved, catalog, catalogSource: "bridge", bridgeState: "ready" };

// Switching the engine picks that engine's default model; a model without the effort falls back to a valid one.
assert.deepEqual(choose(catalog, saved.normal, { engine: "claude" }), { engine: "claude", model: "claude-opus-5-5", effort: "medium" });
assert.deepEqual(choose(catalog, saved.normal, { model: "gpt-6.2-sol" }), { engine: "codex", model: "gpt-6.2-sol", effort: "low" });
assert.deepEqual(choose(catalog, saved.analysis, { model: "claude-sonnet-5-5", effort: "high" }),
  { engine: "claude", model: "claude-sonnet-5-5", effort: "high" });
assert.deepEqual(choose(catalog, saved.normal, { model: "unknown" }), saved.normal);

assert.equal(laneStatus(state, "normal"), "使用中");
assert.match(laneStatus({ ...state, saved: { ...saved, normal: { ...saved.normal, effort: "high" } } }, "normal"),
  /反映待ち（今は Codex gpt-6.1-sol・medium）/);
assert.match(laneStatus({ ...state, active: null, bridgeState: null }, "analysis"), /中継が起動していません/);
assert.match(laneStatus({ ...state, active: null, bridgeState: "error" }, "analysis"), /エラー/);

const html = renderToStaticMarkup(React.createElement(BridgeEngineForm, {
  state, draft: { ...saved, analysis: { engine: "claude", model: "claude-sonnet-5-5", effort: "high" } }, busy: false,
  onChange: () => {}, onSave: () => {} }));
assert.match(html, /通常の作業/);
assert.match(html, /自己分析/);
assert.match(html, /<option value="claude-sonnet-5-5" selected="">/);
assert.match(html, /<option value="high" selected="">/);
assert.doesNotMatch(html, /<button type="button" disabled=""/);
const unchanged = renderToStaticMarkup(React.createElement(BridgeEngineForm, {
  state, draft: saved, busy: false, onChange: () => {}, onSave: () => {} }));
assert.match(unchanged, /<button type="button" disabled=""/);
console.log("bridgeEngine ok");
