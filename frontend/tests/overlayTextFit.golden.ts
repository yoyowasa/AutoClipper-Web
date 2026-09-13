import { deepStrictEqual, ok, strictEqual } from "node:assert";

import cases from "../../backend/tests/fixtures/overlay_text_fit_cases.json";
import {
  fitOverlayPreviewText,
  overlayTextWidthUnits,
  splitSubtitlePreviewLines
} from "../lib/subtitlePreview";

for (const testCase of cases) {
  const result = fitOverlayPreviewText(testCase.text, testCase.options);
  deepStrictEqual(result.lines, testCase.expected.lines, `${testCase.name}: lines`);
  strictEqual(
    result.effectiveFontSize,
    testCase.expected.effectiveFontSize,
    `${testCase.name}: effectiveFontSize`
  );
  strictEqual(
    result.maxWidthPx,
    testCase.expected.maxWidthPx,
    `${testCase.name}: maxWidthPx`
  );
  strictEqual(result.fits, testCase.expected.fits, `${testCase.name}: fits`);
  strictEqual(
    result.overflowReason,
    testCase.expected.overflowReason,
    `${testCase.name}: overflowReason`
  );
}

const longSubtitle = splitSubtitlePreviewLines(
  "通常字幕の長文でも二行の表示幅を超えないように完成動画と同じ計算で文字サイズを調整します",
  16,
  2
);
const subtitleFit = fitOverlayPreviewText(longSubtitle, {
  outputWidth: 1080,
  fontSize: 76,
  fontSizeScale: 1000 / 1448,
  marginX: 86,
  outlineWidth: 5,
  shadow: 2,
  alignment: 2,
  xPercent: 50,
  maxLines: 2
});

strictEqual(subtitleFit.lines.length, 2, "subtitle: max two lines");
strictEqual(subtitleFit.fits, true, "subtitle: fits at reduced font size");
ok(subtitleFit.effectiveFontSize < 76, "subtitle: font size is reduced");
for (const line of subtitleFit.lines) {
  ok(
    overlayTextWidthUnits(line) *
      subtitleFit.effectiveFontSize *
      (1000 / 1448) <=
      subtitleFit.maxWidthPx,
    "subtitle: rendered line stays inside the ASS width"
  );
}
