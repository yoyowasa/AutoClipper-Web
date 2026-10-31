import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewSubtitleSegments } from "../components/subtitleReview/ReviewSubtitleSegments";
import { useSubtitleEditing as actions } from "../lib/subtitleReview/hooks/useSubtitleEditing";
import { bulkEditableSegments, clipSegmentDrafts } from "../lib/subtitleReview/sharedSegments";
import { matchingSubtitleCorrections, subtitleUndoUpdates } from "../lib/subtitleBulkCorrection";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import type { SubtitleReviewContext, SubtitleReviewViewContext } from "../lib/subtitleReview/hooks/context";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../lib/types";
import type { SetStateAction } from "react";
Object.assign(globalThis, { React });

async function main() {
  const clip = { id: "short", type: "short", start: 0, end: 70, title: "開いているショート", confirmed: true,
    segmentIds: ["shared", "short-only"], subtitleStyles: [] } as unknown as SubtitleReviewClip;
  const other = { ...clip, id: "normal", type: "normal", title: "保護する通常", segmentIds: ["shared", "other-only"] } as SubtitleReviewClip;
  const unconfirmed = { ...other, id: "unconfirmed", title: "別の未確定", confirmed: false };
  const segments = [{ id: "shared", index: 0, start: 1, end: 3, text: "アカネです", affectedClipIds: [clip.id, other.id, unconfirmed.id] },
    { id: "short-only", index: 1, start: 5, end: 6, text: "アカネの話", affectedClipIds: [clip.id] },
    { id: "other-only", index: 2, start: 60, end: 62, text: "アカネの続き", affectedClipIds: [other.id, unconfirmed.id] }] as SubtitleReviewSegment[];
  const review = { jobId: "job-bulk", state: "awaiting_review", subtitleOnlyAuto: true, clips: [other, clip, unconfirmed], segments } as SubtitleReviewDocument;
  let drafts: Record<string, string> = { "short::shared": "アカネを手直し中", "normal::shared": "他clipの下書き", shared: "未確定側の下書き" };
  let dirty = new Set(Object.keys(drafts));
  const context = { review, jobId: review.jobId, selectedClip: clip, selectedSegments: segments.slice(0, 2),
    isEditable: false, isSubtitleEditable: true, isSubtitleTextEditable: true, hasReviewMutationInFlight: false,
    rawDrafts: drafts, rawDirtySegmentIds: dirty, drafts: clipSegmentDrafts(clip, segments, drafts), dirtySegmentIds: new Set(["shared"]),
    setDrafts: (next: SetStateAction<Record<string, string>>) => { drafts = typeof next === "function" ? next(drafts) : next; },
    setDirtySegmentIds: (next: SetStateAction<Set<string>>) => { dirty = typeof next === "function" ? next(dirty) : next; },
    setShowSavedPreview: () => {}, selectedClipContentDraft: contentDraftForClip(clip), hookSceneDuration: 0, hookSuppressionEnd: 0,
    segmentRowRefs: { current: {} }, bulkCorrectionSelection: { segmentId: "shared", source: "アカネ", replacement: "あかね" },
  } as unknown as SubtitleReviewViewContext;
  const eligible = bulkEditableSegments(review, clip.id);
  assert.deepEqual(eligible.map(row => row.id), ["shared", "short-only"]);
  assert.ok(eligible.every(row => row.affectedClipIds.length === 1 && row.affectedClipIds[0] === clip.id));
  const matches = matchingSubtitleCorrections(eligible, clipSegmentDrafts(clip, eligible, drafts), "アカネ", "あかね");
  assert.deepEqual(matches.map(row => row.current), ["アカネを手直し中", "アカネの話"]);
  const render = () => renderToStaticMarkup(React.createElement(ReviewSubtitleSegments, { context, showStyleControls: false }));
  const markup = render();
  assert.match(markup, /<input(?=[^>]*aria-label="一括修正の正しい表記")(?![^>]*\sdisabled=)[^>]*>/);
  assert.match(markup, /<button(?![^>]*\sdisabled=)[^>]*>2か所をまとめて下書きへ反映<\/button>/);
  assert.match(markup, /開いているclipだけを修正/);
  assert.match(markup, /修正前：アカネを手直し中/);
  assert.doesNotMatch(markup, /対象clip：[^<]*保護する通常/);
  context.isSubtitleEditable = false;
  context.hasReviewMutationInFlight = true;
  assert.match(render(), /<input(?=[^>]*aria-label="一括修正の正しい表記")(?![^>]*\sdisabled=)[^>]*>/,
    "caption autosave must not disable the local bulk draft editor");
  context.isSubtitleTextEditable = false;
  assert.match(render(), /<input(?=[^>]*aria-label="一括修正の正しい表記")(?=[^>]*\sdisabled=)[^>]*>/,
    "other blocking mutations retain their lock");
  context.isSubtitleTextEditable = true;
  context.hasReviewMutationInFlight = false;
  await actions(context as SubtitleReviewContext).saveBulkCorrection([
    ...matches, { segmentId: "other-only", before: "アカネの続き", text: "触ってはいけない" }
  ]);
  assert.equal(drafts["short::shared"], "あかねを手直し中");
  assert.equal(drafts["short::short-only"], "あかねの話");
  assert.equal(drafts["normal::shared"], "他clipの下書き");
  assert.equal(drafts.shared, "未確定側の下書き");
  assert.equal(drafts["short::other-only"], undefined);
  assert.ok(dirty.has("short::short-only"));
  assert.ok(clip.confirmed && other.confirmed);
  assert.deepEqual(bulkEditableSegments(review).map(row => row.id), ["shared", "other-only"], "global bulk still excludes confirmed clips");
  assert.deepEqual(bulkEditableSegments({ ...review, subtitleOnlyAuto: false }, clip.id).map(row => row.id), ["shared", "other-only"], "legacy scope stays unchanged");
  const undo = [{ segmentId: "shared", before: "あかねです", text: "アカネです", index: 0, start: 1, end: 3 }];
  const fork = { ...segments[0], id: "forked", text: "あかねです", affectedClipIds: [clip.id] };
  assert.deepEqual(subtitleUndoUpdates([fork], undo), [{ segmentId: "forked", before: "あかねです", text: "アカネです" }]);
  assert.deepEqual(subtitleUndoUpdates([{ ...fork, end: 2 }], undo), [], "changed structure cannot inherit an old undo");
  assert.deepEqual(subtitleUndoUpdates([fork, { ...fork, id: "ambiguous" }], undo), [], "ambiguous replacement is never guessed");
  console.log("Bulk captions: confirmed scope, enabled controls, existing drafts, other clip protection and legacy scope passed");
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
