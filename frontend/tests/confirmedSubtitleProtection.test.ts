import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Dispatch, SetStateAction } from "react";
import { SubtitleBulkCorrection } from "../components/SubtitleBulkCorrection";
import { useSubtitleEditing as createSubtitleEditing } from "../lib/subtitleReview/hooks/useSubtitleEditing";
import { useReviewMutations as createReviewMutations } from "../lib/subtitleReview/hooks/useReviewMutations";
import { useReviewConfirmation as createReviewConfirmation } from "../lib/subtitleReview/hooks/useReviewConfirmation";
import type { SubtitleReviewContext } from "../lib/subtitleReview/hooks/context";
import { contentDraftForClip } from "../lib/subtitleReview/drafts";
import { readReviewDraft, writeReviewDraft, reviewDraftFingerprint } from "../lib/subtitleReview/draftStorage";
import { bulkEditableSegments, clipSegmentDrafts, clipDirtySegmentIds, sharedSubtitleNotice, segmentDraftKey } from "../lib/subtitleReview/sharedSegments";
import type { SubtitleReviewClip, SubtitleReviewDocument, SubtitleReviewSegment } from "../lib/types";

function state<T>(initial: T) {
  const cell = { value: initial, set: (() => {}) as Dispatch<SetStateAction<T>> };
  cell.set = value => { cell.value = typeof value === "function" ? (value as (old: T) => T)(cell.value) : value; };
  return cell;
}

async function main() {
  const normal = { id: "normal", type: "normal", confirmed: true, title: "確定した通常", segmentIds: ["shared", "normal-only"],
    start: 0, end: 100, hookText: "", hookDurationSeconds: 3, hookSceneStart: null, hookSceneEnd: null } as SubtitleReviewClip;
  const short = { ...normal, id: "short", type: "short", confirmed: false, title: "編集中ショート", publicationTitle: "投稿タイトル",
    end: 70, segmentIds: ["shared"] } as SubtitleReviewClip;
  const short2 = { ...short, id: "short2", title: "共有ショート" };
  const segments = [
    { id: "shared", text: "アカネです", start: 1, end: 2, affectedClipIds: [normal.id, short.id, short2.id] },
    { id: "normal-only", text: "アカネの話", start: 90, end: 91, affectedClipIds: [normal.id] }
  ] as SubtitleReviewSegment[];
  const review = { jobId: "test", state: "awaiting_review", shortMaxDuration: 75, clips: [normal, short, short2], segments } as SubtitleReviewDocument;
  const eligible = bulkEditableSegments(review);
  assert.deepEqual(eligible.map(s => s.id), ["shared"]);
  assert.deepEqual(eligible[0].affectedClipIds, [short.id, short2.id]);
  const markup = renderToStaticMarkup(createElement(SubtitleBulkCorrection, {
    segments: eligible, clips: review.clips, drafts: {}, disabled: false, draftOnly: true,
    selection: { segmentId: "shared", source: "アカネ", replacement: "あかね" }, onSelection: () => {}, onSave: async () => {}
  }));
  assert.match(markup, /確定済みのclipは対象外/);
  assert.match(markup, /編集中ショート/);
  assert.match(markup, /共有ショート/);
  assert.doesNotMatch(markup, /確定した通常/);
  assert.match(sharedSubtitleNotice(review, segments, short.id), /共有ショート/);
  assert.doesNotMatch(sharedSubtitleNotice(review, segments, short.id), /確定した通常/);

  const drafts = state<Record<string, string>>({});
  const dirty = state(new Set<string>());
  const context = { review, selectedClip: short, setDrafts: drafts.set, setDirtySegmentIds: dirty.set, setShowSavedPreview: () => {} } as unknown as SubtitleReviewContext;
  await createSubtitleEditing(context).saveBulkCorrection(segments.map(s => ({ segmentId: s.id, before: s.text, text: "あかねです" })));
  assert.equal(JSON.stringify(drafts.value), JSON.stringify({ shared: "あかねです" }));
  assert.equal(clipSegmentDrafts(normal, segments, drafts.value).shared, "アカネです");
  assert.equal(clipDirtySegmentIds(normal, dirty.value).size, 0);
  assert.equal(clipSegmentDrafts(short2, segments, drafts.value).shared, "あかねです");
  assert.ok(clipDirtySegmentIds(short2, dirty.value).has("shared"));
  context.selectedClip = normal;
  createReviewMutations(context).updateDraft("shared", "直接の修正");
  assert.equal(clipSegmentDrafts(normal, segments, drafts.value).shared, "直接の修正");
  assert.equal(clipSegmentDrafts(short, segments, drafts.value).shared, "あかねです");
  assert.ok(clipDirtySegmentIds(normal, dirty.value).has("shared"));

  // Each clip persists only its own draft view, including explicit confirmed edits.
  const stored = new Map<string, string>();
  const storage = { getItem: (key: string) => stored.get(key) ?? null, setItem: (key: string, value: string) => { stored.set(key, value); },
    removeItem: (key: string) => { stored.delete(key); } };
  for (const clip of [normal, short]) {
    writeReviewDraft("test", clip.id, { version: 1, fingerprint: reviewDraftFingerprint(review, clip),
      content: contentDraftForClip(clip), framing: null, segments: { shared: drafts.value[segmentDraftKey(clip, "shared")] } }, storage);
  }
  assert.equal(readReviewDraft("test", normal.id, reviewDraftFingerprint(review, normal), storage)?.segments.shared, "直接の修正");
  assert.equal(readReviewDraft("test", short.id, reviewDraftFingerprint(review, short), storage)?.segments.shared, "あかねです");

  const previousFetch = globalThis.fetch;
  const previousWindow = globalThis.window;
  const previousAnimationFrame = globalThis.requestAnimationFrame;
  let confirmCalls = 0, requests = 0;
  Object.assign(globalThis, { window: { confirm: () => { confirmCalls++; return false; } } });
  const sharedEdit = { ...segments[0], id: "edited", text: "あかねです", affectedClipIds: [short.id, short2.id] };
  const protectedSegments = [{ ...segments[0], affectedClipIds: [normal.id] }, segments[1]];
  const savedReview = state<SubtitleReviewDocument | null>(null);
  const clipDrafts = state(Object.fromEntries(review.clips.map(clip => [clip.id, contentDraftForClip(clip)])));
  const style = { fontSize: 42 };
  for (const draft of Object.values(clipDrafts.value)) draft.subtitleStyles = [{ start: 1, end: 2, style }];
  globalThis.fetch = async (_input, init) => {
    requests++;
    assert.deepEqual(JSON.parse(String(init?.body)).segments, [{ segmentId: "shared", text: "あかねです" }]);
    return new Response(JSON.stringify({ ...review, clips: [normal,
      { ...short, confirmed: true, segmentIds: [sharedEdit.id] }, { ...short2, segmentIds: [sharedEdit.id] }],
      segments: [...protectedSegments, sharedEdit] }), { headers: { "Content-Type": "application/json" } });
  };
  Object.assign(context, {
    jobId: "test", selectedClip: short, selectedClipContentDraft: contentDraftForClip(short), selectedSegments: [segments[0]],
    drafts: clipSegmentDrafts(short, segments, drafts.value), dirtySegmentIds: clipDirtySegmentIds(short, dirty.value),
    selectedHookDurationIsValid: true, beginReviewMutation: () => 1, isCurrentReviewMutation: () => true,
    locallyUpdatedReviewRef: { current: null }, setError: () => {}, setConfirmingClipId: () => {}, setReview: savedReview.set,
    setShortFramingDrafts: () => {}, setClipContentDrafts: () => {}, endReviewMutation: () => {}
  });
  try {
    await createReviewConfirmation(context).confirmSelectedClip();
    assert.equal(requests, 1);
    assert.equal(confirmCalls, 0, "shared subtitle confirmation must save without a dialog");
    assert.deepEqual(savedReview.value?.clips[0], normal);
    assert.deepEqual(savedReview.value?.clips[2].segmentIds, [sharedEdit.id]);
    assert.equal(savedReview.value?.segments.find(s => s.id === "shared")?.text, segments[0].text);
    assert.equal(savedReview.value?.segments.find(s => s.id === sharedEdit.id)?.text, "あかねです");
    assert.equal(drafts.value[segmentDraftKey(normal, "shared")], "直接の修正", "other clip's explicit draft survives");

    globalThis.requestAnimationFrame = callback => { callback(0); return 0; };
    Object.assign(context, { isEditable: true, subtitleListRef: { current: null }, segmentRowRefs: { current: {} },
      setIsSavingStructure: () => {}, setStyledSegmentId: () => {}, setSegmentCursor: () => {},
      setBulkCorrectionSelection: () => {}, setClipContentDrafts: clipDrafts.set });
    const split = [{ ...sharedEdit, id: "left", text: "あかね", end: 1.5 },
      { ...sharedEdit, id: "right", text: "です", start: 1.5 }];
    let source = [segments[0]];
    for (const [action, replacement] of [["split", split], ["merge", [sharedEdit]]] as const) {
      const ids = replacement.map(segment => segment.id);
      const inputs = source.map(segment => ({ segmentId: segment.id, before: segment.text, text: segment.text }));
      globalThis.fetch = async (_input, init) => {
        requests++;
        const request = JSON.parse(String(init?.body));
        assert.equal(request.action, action);
        assert.equal(request.clipId, short.id);
        assert.deepEqual(request.segments, inputs);
        return new Response(JSON.stringify({ ...review,
          clips: [normal, { ...short, segmentIds: ids }, { ...short2, segmentIds: ids }],
          segments: [...protectedSegments, ...replacement]
        }), { headers: { "Content-Type": "application/json" } });
      };
      Object.assign(context, { selectedSegments: source, dirtySegmentIds: new Set() });
      assert.equal(await createSubtitleEditing(context).saveSubtitleStructure({ action, segments: inputs,
        ...(action === "split" ? { splitOffset: 3, splitTime: 1.5 } : {}) }), true);
      assert.equal(confirmCalls, 0, `shared subtitle ${action} must save without a dialog`);
      assert.deepEqual(savedReview.value?.clips[0], normal);
      assert.deepEqual(savedReview.value?.clips[2].segmentIds, ids);
      assert.deepEqual(savedReview.value?.segments.slice(0, 2), protectedSegments);
      for (const id of [short.id, short2.id]) {
        assert.deepEqual(clipDrafts.value[id].subtitleStyles, replacement.map(({ start, end }) => ({ start, end, style })));
      }
      assert.deepEqual(clipDrafts.value[normal.id].subtitleStyles, [{ start: 1, end: 2, style }]);
      context.review = savedReview.value;
      source = [...replacement];
    }
    assert.equal(requests, 3);
    Object.assign(context, { review, setClipContentDrafts: () => {} });
    // Structure saves unconfirm the explicitly opened clip. Its other unsaved rows must survive that transition.
    drafts.value[segmentDraftKey(normal, "normal-only")] = "残しておく下書き";
    dirty.value.add(segmentDraftKey(normal, "normal-only"));
    const changedNormal = { ...normal, confirmed: false, segmentIds: ["normal-copy", "normal-only"], subtitleStyles: [] };
    globalThis.fetch = async () => new Response(JSON.stringify({ ...review,
      clips: [changedNormal, short, short2],
      segments: [...segments, { ...segments[0], id: "normal-copy", affectedClipIds: [normal.id] }]
    }), { headers: { "Content-Type": "application/json" } });
    globalThis.requestAnimationFrame = callback => { callback(0); return 0; };
    Object.assign(context, { selectedClip: normal, isEditable: true, subtitleListRef: { current: null },
      segmentRowRefs: { current: {} }, setIsSavingStructure: () => {}, setStyledSegmentId: () => {},
      setSegmentCursor: () => {}, setBulkCorrectionSelection: () => {} });
    assert.equal(await createSubtitleEditing(context).saveSubtitleStructure({ action: "line",
      segments: [{ segmentId: "shared", before: "アカネです", text: "直接の修正" }] }), true);
    assert.equal(drafts.value["normal-only"], "残しておく下書き");
    assert.ok(dirty.value.has("normal-only"));
    assert.ok(!dirty.value.has(segmentDraftKey(normal, "normal-only")));
  } finally {
    globalThis.fetch = previousFetch; globalThis.window = previousWindow; globalThis.requestAnimationFrame = previousAnimationFrame;
  }
  console.log("Confirmed subtitle protection: dialog-free apply, split and merge, shared styles and protected drafts passed");
}
void main().catch(error => { console.error(error); process.exitCode = 1; });
