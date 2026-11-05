import { defaultClipTextStyle, resolvedClipTextStyle } from "../lib/clipTextStyle";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewTextStyles } from "../components/subtitleReview/ReviewStyleFraming";
import { ReviewSubtitleSegments } from "../components/subtitleReview/ReviewSubtitleSegments";
import { ReviewClipActions } from "../components/subtitleReview/ReviewActions";
import { useSubtitleEditing as createSubtitleEditing } from "../lib/subtitleReview/hooks/useSubtitleEditing";
import { useReviewConfirmation as createReviewConfirmation } from "../lib/subtitleReview/hooks/useReviewConfirmation";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import type { SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../lib/types";
import type { SetStateAction } from "react";
Object.assign(globalThis, { React });

function fixture(type: "normal" | "short") {
  const clip = { id: "selected", type, title: "自動のタイトル", confirmed: true, automaticDecisionState: "ready",
    start: 0, end: type === "normal" ? 120 : 70, segmentIds: ["s0", "s1", "s2", "s3"], subtitleStyles: [] } as unknown as SubtitleReviewClip;
  const other = { ...clip, id: "other" };
  const segments = clip.segmentIds.map((id, index) => ({ id, index, start: index * 3 + 1, end: index * 3 + 2,
    text: `保存前${index}`, affectedClipIds: [clip.id, other.id] })) as SubtitleReviewSegment[];
  const review = { jobId: "job-save-button", state: "awaiting_review", subtitleOnlyAuto: true, clips: [clip, other], segments } as SubtitleReviewDocument;
  const state = { drafts: Object.fromEntries(segments.map(s => [`selected::${s.id}`, `修正${s.index}`])),
    dirty: new Set(segments.map(s => `selected::${s.id}`)), review, error: null as string | null };
  const draft = contentDraftForClip(clip);
  const context = { jobId: review.jobId, review, selectedClip: clip, selectedSegments: segments,
    selectedClipContentDraft: draft, selectedClipHasDirtySegments: true, selectedClipHasDirtyContent: false,
    dirtySegmentIds: new Set(clip.segmentIds), rawDrafts: state.drafts, rawDirtySegmentIds: state.dirty,
    isEditable: false, isSubtitleEditable: true, hasReviewMutationInFlight: false, reviewMutationCountRef: { current: 0 },
    locallyUpdatedReviewRef: { current: null },
    setDrafts: (next: SetStateAction<Record<string, string>>) => { state.drafts = typeof next === "function" ? next(state.drafts) : next; },
    setDirtySegmentIds: (next: SetStateAction<Set<string>>) => { state.dirty = typeof next === "function" ? next(state.dirty) : next; },
    setReview: (value: SubtitleReviewDocument) => { state.review = value; }, setShowSavedPreview: () => {},
    setError: (value: string | null) => { state.error = value; },
    beginReviewMutation: () => { context.reviewMutationCountRef.current++; return 1; },
    endReviewMutation: () => { context.reviewMutationCountRef.current--; }, isCurrentReviewMutation: () => true,
    setIsSavingConfirmedSubtitles: (value: boolean) => { context.hasReviewMutationInFlight = value; },
    setConfirmingClipId: () => { throw Error("caption save must not re-apply the whole clip"); },
  } as unknown as SubtitleReviewViewContext;
  Object.assign(context, createSubtitleEditing(context));
  return { clip, other, segments, state, context, draft };
}

async function main() {
  const previousFetch = globalThis.fetch;
  try {
    for (const type of ["normal", "short"] as const) {
      const { context, clip, other, segments, state, draft } = fixture(type);
      state.dirty.clear();
      context.dirtySegmentIds.clear();
      context.selectedClipHasDirtySegments = false;
      context.selectedClipHasDirtyContent = true;
      draft.subtitleStyles = [{ start: segments[0].start, end: segments[0].end, style: { ...defaultClipTextStyle("subtitle", type), fontName: "Arial", primaryColor: "#FF0000" } }];
      context.clipContentDrafts = { [clip.id]: draft };
      context.setClipContentDrafts = next => {
        context.clipContentDrafts = typeof next === "function" ? next(context.clipContentDrafts) : next;
      };
      context.drafts = {};
      context.hookSuppressionEnd = 0;
      context.hookSceneDuration = 0;
      context.clipDuration = clip.end;
      context.subtitleListRef = { current: null };
      context.segmentRowRefs = { current: {} };
      const rows = renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context }));
      assert.match(rows, /<button(?![^>]*disabled=)[^>]*>個別書式を編集<\/button>/);
      assert.match(rows, /<button(?![^>]*disabled=)[^>]*>この字幕の書式<\/button>/);
      context.isSubtitleEditable = false;
      assert.match(renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context })), /<button(?=[^>]*disabled=)[^>]*>個別書式を編集<\/button>/);
      context.isSubtitleEditable = true;
      assert.match(renderToStaticMarkup(React.createElement(ReviewClipActions, { context })), /<button(?![^>]*disabled=)[^>]*>字幕の変更を保存<\/button>/);
      // The actual workspace style editor permits cue styles only; shared style/title remain locked.
      context.styledSegmentId = segments[0].id;
      context.selectedTextStyleTarget = "subtitle";
      context.selectedClipTextStyles = { title: null, hook: null, subtitle: null };
      context.selectedResolvedClipTextStyles = context.selectedDefaultResolvedClipTextStyles = { title: resolvedClipTextStyle(null, null, "title", type), hook: resolvedClipTextStyle(null, null, "hook", type), subtitle: resolvedClipTextStyle(null, null, "subtitle", type) };
      const cueMarkup = renderToStaticMarkup(React.createElement(ReviewTextStyles, { context }));
      assert.match(cueMarkup, /<select(?![^>]*disabled=)/);
      context.selectedTextStyleTarget = "title";
      const titleMarkup = renderToStaticMarkup(React.createElement(ReviewTextStyles, { context }));
      assert.match(titleMarkup, /<select(?=[^>]*disabled=)/);
      globalThis.fetch = async (url, init) => {
        assert.match(String(url), /\/subtitle-review\/segments$/);
        assert.deepEqual(JSON.parse(String(init?.body)), { clipId: clip.id, segments: [], beforeSubtitleStyles: [], subtitleStyles: draft.subtitleStyles });
        return new Response(JSON.stringify({ ...state.review, clips: [{ ...clip, subtitleStyles: draft.subtitleStyles }, other] }), { status: 200 });
      };
      await createReviewConfirmation(context).confirmSelectedClip();
      assert.equal(state.error, null);
      assert.deepEqual(state.review.clips[0].subtitleStyles, draft.subtitleStyles);
      assert.deepEqual(state.review.clips[1], other);
      assert.ok(state.review.clips.every(c => c.confirmed));
      assert.ok(!context.clipContentDrafts[clip.id]._editedFields?.includes("subtitleStyles"));
    }
  } finally { globalThis.fetch = previousFetch; }
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
