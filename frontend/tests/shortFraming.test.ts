import assert from "node:assert/strict";
import { framingAtPoint, framingGeometry, type FramingGuide } from "../lib/shortFraming";

const base: FramingGuide = { state: "ready", key: "test", width: 1920, height: 1080,
  contentHeight: 1200, contentY: 360, strategy: "center_crop", center: [.75, .4] };
const standard = { framingOffsetX: 0, framingOffsetY: 0, framingZoom: 1 };
const center = framingGeometry(base, standard);
assert.equal(center.width, 2133);
assert.equal(center.height, 1200);
assert.equal(center.x, -(2133 - 1080) / 2);
const left = framingGeometry(base, { ...standard, framingOffsetX: -100 });
assert.equal(Math.abs(left.x), 0);
const right = framingGeometry(base, { ...standard, framingOffsetX: 100 });
assert.equal(right.x, -(2133 - 1080));
const zoomed = framingGeometry(base, { ...standard, framingZoom: 2 });
assert.ok(zoomed.source.width < center.source.width);
assert.ok(zoomed.source.height < center.source.height);
const tracking = { ...base, strategy: "face_tracking_crop" };
assert.equal(framingGeometry(tracking, standard).x, -Math.min(1053, Math.round(2133 * .75 - 540)));
assert.equal(Math.abs(framingGeometry(tracking, { ...standard, framingOffsetX: -100 }).x), 0);
const clicked = framingAtPoint(base, { ...standard, framingZoom: 2 }, .7, .6);
const positioned = framingGeometry(base, clicked);
assert.ok(Math.abs(positioned.source.x + positioned.source.width / 2 - .7) < .01);
assert.ok(Math.abs(positioned.source.y + positioned.source.height / 2 - .6) < .01);
const blur = framingGeometry({ ...base, strategy: "blur_background" }, standard);
assert.equal(blur.width, 1080);
assert.equal(blur.height, 608);
assert.equal(blur.source.width, 1);
assert.equal(blur.source.height, 1);
assert.equal(blur.y, (1200 - 608) / 2);
// Offsets also place a fitting foreground within a blurred background.
assert.equal(framingGeometry({ ...base, strategy: "blur_background" }, { ...standard, framingOffsetY: 100 }).y, 1200 - 608);
for (const contentHeight of [1200, 1560, 1920]) {
  const framed = framingGeometry({ ...base, width: 720, height: 1280, contentHeight }, standard);
  assert.ok(framed.width >= 1080 && framed.height >= contentHeight);
  assert.ok(framed.source.x >= 0 && framed.source.y >= 0);
}
console.log("short framing geometry passed");
