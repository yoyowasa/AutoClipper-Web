import { strictEqual } from "node:assert";
import cases from "../../backend/tests/fixtures/render_text_decisions.json";
import { fitOverlayPreviewText, splitSubtitlePreviewLines } from "../lib/subtitlePreview";
import { resolvedClipTextStyle } from "../lib/clipTextStyle";
import type { ClipTextStyle, ResolvedClipTextStyle } from "../lib/types";

// The same requested style and corrected text used by ClipTextOverlay, compared
// with the effective style actually written to ASS and the production record.
for (const item of cases) {
  const expected = item.expected;
  const style = resolvedClipTextStyle(
    item.style as ClipTextStyle, expected as ResolvedClipTextStyle, "subtitle", item.kind as "short" | "normal"
  );
  const fit = fitOverlayPreviewText(splitSubtitlePreviewLines(item.text, item.maxCharsPerLine, 2), {
    outputWidth: item.width, fontSize: style.fontSize, fontSizeScale: item.fontSizeScale,
    marginX: style.marginX, outlineWidth: style.outlineWidth + (style.outerOutlineWidth ?? 0),
    shadow: style.shadow, alignment: style.alignment, xPercent: style.xPercent, maxLines: 2
  });
  strictEqual(fit.effectiveFontSize, expected.effectiveFontSize, item.name);
  strictEqual(fit.fits, expected.fits, item.name);
  strictEqual(fit.maxWidthPx, expected.maxWidthPx, item.name);
  strictEqual(style.xPercent, expected.xPercent, item.name);
  strictEqual(style.yPercent, expected.yPercent, item.name);
}
