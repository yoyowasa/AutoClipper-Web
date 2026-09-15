import assert from "node:assert/strict";
import { EMPTY_HEATMAP_MESSAGE, heatmapContentIssue, readHeatmapContentIssue } from "../lib/heatmapFileStatus";

const empty = JSON.stringify({ heatmap_available: false, heatmap: [] });
assert.equal(heatmapContentIssue(empty), EMPTY_HEATMAP_MESSAGE);
assert.equal(heatmapContentIssue(JSON.stringify({ heatmap_available: true, heatmap: [{ value: 0 }] })), EMPTY_HEATMAP_MESSAGE);
assert.equal(heatmapContentIssue('\uFEFF' + JSON.stringify({ heatmap_available: true, heatmap: [{ value: .5 }] })), null);
assert.match(heatmapContentIssue('{broken')!, /JSONの形式/);
assert.match(heatmapContentIssue('{"unrelated":true}')!, /人気度JSONの形式ではありません/);
async function main() {
  assert.equal(await readHeatmapContentIssue(new File([empty], "sample.mp4.heatmap.json")), EMPTY_HEATMAP_MESSAGE);
  console.log("heatmap content checks passed");
}
void main();
