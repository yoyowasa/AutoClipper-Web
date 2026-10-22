import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PerformanceHintsList, ProductionAggregatesTable } from "../components/ProductionPerformance";
import { applyCharacter, captureCharacter } from "../lib/characterPresets";
import { DEFAULT_SETTINGS } from "../components/SettingsPanel";
import { getProductionAggregates, type ProductionAggregates } from "../lib/productionPerformance";

const metric = { count: 0, median: null, baseline_count: 5, baseline_median: 0,
  relative_to_channel_median: null, missing_reason: "BASELINE_ZERO" };
const data: ProductionAggregates = { source: "independent_aggregation", label: "独自集計", channel_id: 1,
  generated_at: "2026-10-21T00:00:00Z", expires_at: "2026-11-20T00:00:00Z", minimum_group_videos: 5,
  linked_videos: 4, excluded_linked_videos: 0, groups: [{ id: "aggregate:test", character_preset_name: "テストキャラ",
    format: "short", dimension: "duration", value: "60-75", count: 4, sufficient: false, status: "insufficient_data",
    metrics: { views: metric, averageViewPercentage: metric, averageViewDuration: metric, likes: metric, subscribersGained: metric },
    video_ids: [] }] };
const table = renderToStaticMarkup(createElement(ProductionAggregatesTable, { data }));
assert.ok(table.includes("データ不足") && table.includes("テストキャラ") && table.includes("60-75"));
assert.ok(table.includes("—") && !table.includes("NaN") && !table.includes("Infinity"));
assert.ok(renderToStaticMarkup(createElement(PerformanceHintsList, {})).includes("ヒントはありません"));
const hints = renderToStaticMarkup(createElement(PerformanceHintsList, { hints: [{ character_preset_name: "テストキャラ", format: "short",
  target: "selection", text: "題材を早めに示す仮説です。", evidence_groups: [{ group_id: "aggregate:test", count: 5 }],
  video_ids: ["video000001"], confidence: "low" }] }));
assert.ok(hints.includes("効果未検証") && hints.includes("5本") && hints.includes("題材を早め"));
const off = { ...DEFAULT_SETTINGS, usePerformanceHints: false };
assert.equal(captureCharacter(off).usePerformanceHints, false);
assert.equal(applyCharacter(off, { name: "旧設定", settings: {} }).usePerformanceHints, true);
assert.equal(applyCharacter(DEFAULT_SETTINGS, { name: "OFF設定", settings: captureCharacter(off) }).usePerformanceHints, false);
async function main() {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    assert.ok(String(input).endsWith("/channels/1/production-aggregates"));
    return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try { assert.equal((await getProductionAggregates(1)).source, "independent_aggregation"); }
  finally { globalThis.fetch = originalFetch; }
  console.log("Production performance: independent medians/missing display, insufficient data, hints and character opt-out passed");
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
