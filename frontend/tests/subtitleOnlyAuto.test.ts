import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { automaticApplyPayload } from "../lib/subtitleReview/automaticConfirmation";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import { postMetadataApplyPayload } from "../lib/youtubePosting";
import { ReviewRenderControls, ReviewClipActions } from "../components/subtitleReview/ReviewActions";
import type { SubtitleReviewClip } from "../lib/types";
import type { SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";

Object.assign(globalThis, { React });

const clip = { id: "normal", type: "normal", title: "初期値", publicationTitle: null, segmentIds: ["s1"],
  hookText: "", hookDurationSeconds: 3, hookSceneStart: null, hookSceneEnd: null,
  titleStyle: null, hookStyle: null, subtitleStyle: null, confirmed: false } as SubtitleReviewClip;
const draft = contentDraftForClip(clip);
const values = { ...draft };
delete (values as Partial<typeof values>).youtubeHashtagsText;
delete (values as Partial<typeof values>).youtubeTagsText;
const full = { ...values, ...postMetadataApplyPayload(draft), segments: [{ segmentId: "s1", text: "訂正済みの字幕" }] };
assert.deepEqual(automaticApplyPayload(clip, full), { segments: full.segments }, "default values are not manual choices");
const edited = automaticApplyPayload(clip, { ...full, title: "手動のタイトル" });
assert.equal(edited.title, "手動のタイトル");
assert.ok(!("thumbnailLine1" in edited), "a title choice must not mark thumbnail copy as manual");
const hook = automaticApplyPayload(clip, { ...full, hookSceneStart: 1, hookSceneEnd: 3 });
assert.equal(hook.hookSceneStart, 1);
assert.equal(hook.hookSceneEnd, 3);

const context = {
  review: { subtitleOnlyAuto: true, totalClipCount: 1, confirmedClipCount: 0, clips: [clip] },
  selectedClip: clip, selectedClipContentDraft: draft, dirtySegmentIds: new Set(), isEditable: true,
} as unknown as SubtitleReviewViewContext;
const controls = renderToStaticMarkup(React.createElement(ReviewRenderControls, { context }));
assert.ok(!controls.includes("<button"), "no extra render confirmation in subtitle-only flow");
const confirmation = renderToStaticMarkup(React.createElement(ReviewClipActions, { context }));
assert.match(confirmation, /このclipの字幕を確定/);
assert.match(confirmation, /<button(?![^>]*\sdisabled=)[^>]*>この動画の字幕を確定<\/button>/);
clip.confirmed = true;
clip.automaticDecisionState = "failed";
context.isEditable = false;
assert.match(renderToStaticMarkup(React.createElement(ReviewClipActions, { context })),
  /<button(?![^>]*\sdisabled=)[^>]*>自動処理を再試行<\/button>/);
console.log("Subtitle-only auto: subtitle payload, explicit overrides, no render button, retry and empty title confirmation passed");
