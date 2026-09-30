import assert from "node:assert/strict";
import { DEFAULT_SETTINGS } from "../components/SettingsPanel";
import { allocationLabel, allocationSettingsError, isAIAllocation, remainingClipSlots } from "../lib/clipAllocation";
import { manualRangeValidationError } from "../lib/manualClipRanges";
import type { ClipPlanDocument } from "../lib/types";

assert.equal(DEFAULT_SETTINGS.clipAllocationMode, "ai");
for (const [total, valid] of [[0, false], [1, true], [36, true], [37, false]] as const) {
  assert.equal(allocationSettingsError({ ...DEFAULT_SETTINGS, totalClipCount: total }) === null, valid);
}
assert.notEqual(allocationSettingsError({ ...DEFAULT_SETTINGS, totalClipCount: null }), null);
assert.notEqual(allocationSettingsError({ ...DEFAULT_SETTINGS, totalClipCount: 2, minNormalClipCount: 2, minShortCount: 1 }), null);
assert.equal(allocationSettingsError({ ...DEFAULT_SETTINGS, totalClipCount: 36, minNormalClipCount: 12, minShortCount: 24 }), null);
const legacy = { ...DEFAULT_SETTINGS, clipAllocationMode: "fixed" as const, totalClipCount: null, normalClipCount: 2, shortCount: 3 };
assert.equal(isAIAllocation(legacy), false);
const clips = [{ id: "n", type: "normal" }, { id: "s", type: "short" }];
const ai = { settings: { ...DEFAULT_SETTINGS, totalClipCount: 10 }, requestedTotal: 10, clips } as ClipPlanDocument;
assert.equal(allocationLabel(ai), "10本中2本（通常1・ショート1）");
assert.equal(remainingClipSlots(ai, ["n", "stale"]), 9);
assert.equal(remainingClipSlots({ ...ai, settings: legacy }, ["s"]), 4);
const manual = { ...DEFAULT_SETTINGS, totalClipCount: 3, normalClipCount: 0, shortCount: 0,
  normalClipTimeRanges: [{ startSeconds: 0, endSeconds: 90 }], shortClipTimeRanges: [{ startSeconds: 0, endSeconds: 30 }] };
assert.equal(manualRangeValidationError(manual), null);
assert.equal(allocationSettingsError(manual), null);
assert.notEqual(allocationSettingsError({ ...manual, totalClipCount: 1 }), null);
console.log("total allocation settings, manual ranges, legacy counts and shortage display passed");
