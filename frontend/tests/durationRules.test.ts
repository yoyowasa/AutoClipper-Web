import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as rules from "../lib/durationRules";

const fixture = JSON.parse(fs.readFileSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)),
  "../../backend/tests/fixtures/duration_rules.json"), "utf8").replace(/^\uFEFF/, ""));
for (const [key, value] of Object.entries(fixture)) {
  assert.equal(rules[key as keyof typeof rules], value);
}
for (const [duration, valid] of [[89,false],[90,true],[600,true],[601,false]] as const) {
  assert.equal(rules.validateClipDuration("normal", duration, 75) === null, valid);
}
assert.equal(rules.validateClipDuration("short", 0.1, 1), null);
assert.equal(rules.validateClipDuration("short", 75, 75), null);
assert.match(rules.validateClipDuration("short", 76, 75)!, /75秒以内/);
const defaults = {normalMinDuration:90, normalMaxDuration:600, shortMinDuration:0, shortMaxDuration:75};
for (const maximum of [0,1,180,181]) {
  assert.equal(rules.durationSettingsError({...defaults, shortMaxDuration:maximum}) === null,
    maximum >= 1 && maximum <= 180);
}
assert.notEqual(rules.durationSettingsError({...defaults, normalMinDuration:601}), null);
assert.notEqual(rules.durationSettingsError({...defaults, normalMinDuration:100, normalMaxDuration:90}), null);
assert.notEqual(rules.durationSettingsError({...defaults, shortMinDuration:76}), null);
console.log("shared duration rules: ok");
import { manualRangeValidationError, updateManualRangeTime } from "../lib/manualClipRanges";
import { DEFAULT_SETTINGS } from "../components/SettingsPanel";
const settings = {...DEFAULT_SETTINGS, ...defaults, normalClipCount:0, shortCount:1, normalClipTimeRanges:[],
  shortClipTimeRanges:[{startSeconds:0, endSeconds:1}]};
const halfSecond = updateManualRangeTime(settings, "short", 0, "endSeconds", "seconds", "0.5");
assert.equal(halfSecond.shortClipTimeRanges[0].endSeconds, 0.5);
assert.equal(manualRangeValidationError(halfSecond), null);
assert.match(manualRangeValidationError({...settings, normalClipCount:1,
  normalClipTimeRanges:[{startSeconds:0, endSeconds:89}]})!, /90秒/);
