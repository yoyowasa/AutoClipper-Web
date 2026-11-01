import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
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
      const markup = () => renderToStaticMarkup(React.createElement(ReviewClipActions, { context }));
      assert.match(markup(), /未保存の変更 4件/);
      for (const status of ["awaiting_review", "render_queued", "rendering", "completed"] as const) {
        context.review.state = status;
        assert.match(markup(), /<button(?![^>]*\sdisabled=)[^>]*>字幕の変更を保存<\/button>/, `${type}/${status}`);
      }
      context.hasReviewMutationInFlight = true;
      assert.match(markup(), /<button(?=[^>]*\sdisabled=)[^>]*>字幕の変更を保存<\/button>/);
      context.hasReviewMutationInFlight = false;
      context.isSubtitleEditable = false;
      assert.match(markup(), /<button(?=[^>]*\sdisabled=)[^>]*>字幕の変更を保存<\/button>/);
      context.isSubtitleEditable = true;
      draft.title = "別の内容の下書きは送らない";
      context.selectedClipHasDirtyContent = true;
      let requests = 0;
      let release: (value: Response) => void = () => {};
      globalThis.fetch = async (url, init) => {
        requests++;
        assert.match(String(url), /\/subtitle-review\/segments$/);
        assert.equal(init?.method, "PATCH");
        assert.deepEqual(JSON.parse(String(init?.body)), { clipId: clip.id,
          segments: segments.map(s => ({ segmentId: s.id, before: s.text, text: `修正${s.index}` })) });
        return new Promise<Response>(resolve => { release = resolve; });
      };
      const actions = createReviewConfirmation(context);
      const saving = actions.confirmSelectedClip();
      await actions.confirmSelectedClip();
      assert.equal(requests, 1, "button/blur/repeated clicks cannot start concurrent caption saves");
      const forks = segments.map(s => ({ ...s, id: `${s.id}-copy`, text: `修正${s.index}`, affectedClipIds: [clip.id] }));
      release(new Response(JSON.stringify({ ...context.review, clips: [{ ...clip, segmentIds: forks.map(s => s.id) }, other],
        segments: [...segments.map(s => ({ ...s, affectedClipIds: [other.id] })), ...forks] }), { status: 200 }));
      await saving;
      assert.equal(state.error, null);
      assert.equal(state.dirty.size, 0);
      assert.deepEqual(state.drafts, {});
      assert.ok(state.review.clips.every(c => c.confirmed));
      assert.deepEqual(state.review.segments.filter(s => s.affectedClipIds.includes(other.id)).map(s => s.text), segments.map(s => s.text));
      assert.equal(context.selectedClipContentDraft, draft, "unrelated content drafts are preserved");

      const failed = fixture(type);
      globalThis.fetch = async () => new Response(JSON.stringify({ detail: "字幕を保存できませんでした。" }), { status: 409 });
      await createReviewConfirmation(failed.context).confirmSelectedClip();
      assert.match(failed.state.error ?? "", /字幕を保存できません/);
      assert.equal(failed.state.dirty.size, 4);
      assert.equal(Object.keys(failed.state.drafts).length, 4, "failed saves retain all four edits");
      assert.ok(failed.clip.confirmed);
      assert.match(renderToStaticMarkup(React.createElement(ReviewClipActions, { context: failed.context })),
        /<button(?![^>]*\sdisabled=)[^>]*>字幕の変更を保存<\/button>/, "explicit save remains available after failure");
      globalThis.fetch = async () => new Response(JSON.stringify({ ...failed.context.review,
        segments: failed.segments.map(s => ({ ...s, text: `修正${s.index}` })) }), { status: 200 });
      await createReviewConfirmation(failed.context).confirmSelectedClip();
      assert.equal(failed.state.error, null);
      assert.equal(failed.state.dirty.size, 0, "manual retry can save the retained edits");
    }
  } finally { globalThis.fetch = previousFetch; }
  console.log("Confirmed caption save button: enabled with four edits, caption-only PATCH, COW, serialization, failure retention and both formats passed");
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
