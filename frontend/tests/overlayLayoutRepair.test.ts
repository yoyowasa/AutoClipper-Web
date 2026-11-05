import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewTextStyles } from "../components/subtitleReview/ReviewStyleFraming";
import { OverlayLayoutNotices } from "../components/subtitleReview/OverlayLayoutNotices";
import { resolvedClipTextStyle } from "../lib/clipTextStyle";
import type { SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import type { SubtitleReviewClip } from "../lib/types";
Object.assign(globalThis, { React });
const clip = { id: "clip", type: "short", confirmed: true, start: 100, end: 160, title: "動画", subtitleStyles: [],
  subtitleStyle: { fontSize: 110, yPercent: 72.9167, positionMode: "explicit", primaryColor: "#FFFFFF" },
  segmentIds: ["row"], overlayLayoutNotices: [{ role: "subtitle:event_00001", start: 2, end: 5, text: "確定した字幕",
    failed: true, boundary: "下の帯", overflowPx: 37.6, fontSizeBefore: 110, fontSizeAfter: 110, shiftPx: 0 }] } as unknown as SubtitleReviewClip;
const draft = contentDraftForClip(clip);
let update: unknown;
const context = { selectedClip: clip, selectedSegments: [{ id: "row", start: 102, end: 105 }], styledSegmentId: "row",
  selectedClipContentDraft: draft, selectedTextStyleTarget: "subtitle", isEditable: false, isSubtitleEditable: true,
  selectedClipTextStyles: { title: null, hook: null, subtitle: clip.subtitleStyle },
  selectedResolvedClipTextStyles: { title: null, hook: null, subtitle: resolvedClipTextStyle(null, null, "subtitle", "short") },
  review: { clips: [clip], subtitleOnlyAuto: true }, updateClipContentDraft: (_: string, value: unknown) => { update = value; },
} as unknown as SubtitleReviewViewContext;
const editor = ReviewTextStyles({ context });
assert.equal(typeof editor?.props.onCueStyleChange, "function");
editor?.props.onCueStyleChange({ primaryColor: "#9BFF9B" });
assert.deepEqual(update, { subtitleStyles: [{ start: 102, end: 105, style: { primaryColor: "#9BFF9B" }, styleVersion: 2 }] });
const resolved = resolvedClipTextStyle({ primaryColor: "#9BFF9B" },
  resolvedClipTextStyle(clip.subtitleStyle, null, "subtitle", "short"), "subtitle", "short");
assert.equal(resolved.fontSize, 110);
assert.equal(resolved.yPercent, 72.9167);
assert.equal(resolved.primaryColor, "#9BFF9B");
const markup = renderToStaticMarkup(React.createElement(OverlayLayoutNotices, { context, onOpen: () => {} }));
assert.match(markup, /ショート 1/);
assert.match(markup, /0:02.0/);
assert.match(markup, /確定した字幕/);
assert.match(markup, /下の帯へ37.6px/);
assert.doesNotMatch(markup, />clip</);
clip.overlayLayoutNotices![0] = { ...clip.overlayLayoutNotices![0], failed: false, fontSizeAfter: 78, shiftPx: -10 };
const corrected = renderToStaticMarkup(React.createElement(OverlayLayoutNotices, { context, onOpen: () => {} }));
assert.match(corrected, /文字を78pxに縮小/);
assert.match(corrected, /上へ10.0px移動/);
