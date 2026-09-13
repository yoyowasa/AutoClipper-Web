import assert from "node:assert/strict";

import {
  clampEndBoundary,
  clampStartBoundary,
  combineBoundaryTime,
  splitBoundaryTime
} from "../lib/clipBoundaryTime";

assert.deepEqual(splitBoundaryTime(5153.25), {
  hours: "1",
  minutes: "25",
  seconds: "53.25"
});
assert.equal(
  combineBoundaryTime({ hours: "1", minutes: "25", seconds: "53.25" }),
  5153.25
);
assert.equal(
  combineBoundaryTime({ hours: "0", minutes: "60", seconds: "0" }),
  null
);
assert.equal(clampStartBoundary(110, 100), 99);
assert.equal(clampStartBoundary(-5, 100), 0);
assert.equal(clampEndBoundary(90, 100, 200), 101);
assert.equal(clampEndBoundary(220, 100, 200), 200);

console.log("clip boundary time helpers: ok");
