import assert from "node:assert/strict";
import { contentDraftForClip, contentDraftChangedFields, isClipContentDirty } from "../lib/subtitleReview/drafts";
import { editContentDraft, restoreContentDraft, synchronizeContentDraft } from "../lib/subtitleReview/contentDraftSync";
import { archiveReviewDraft, archivedReviewDrafts, readReviewDraft, reviewDraftFingerprint, writeReviewDraft, legacyReviewDraftKey, clearJobReviewDrafts } from "../lib/subtitleReview/draftStorage";
import type { StoredReviewDraft } from "../lib/subtitleReview/draftStorage";
import type { SubtitleReviewClip, SubtitleReviewDocument } from "../lib/types";

const a = { id: "normal", type: "normal", start: 100, end: 200, confirmed: true, title: "以前の自動タイトル",
  publicationTitle: "以前の公開タイトル", hookText: "フック", hookDurationSeconds: 3, hookSceneStart: null, hookSceneEnd: null,
  titleStyle: null, hookStyle: null, subtitleStyle: null, segmentIds: ["row"] } as SubtitleReviewClip;
const b = { ...a, title: "新しい自動タイトル", publicationTitle: "新しい公開タイトル", thumbnailLine1: "新しいサムネ" };
const document = { jobId: "qa-record", subtitleOnlyAuto: true, state: "awaiting_review", clips: [b],
  segments: [{ id: "row", index: 1, start: 100, end: 105, text: "保存済みの字幕" }] } as SubtitleReviewDocument;
const old = contentDraftForClip(a), saved = contentDraftForClip(b);
const values = new Map<string, string>();
const storage = { getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => { values.set(k, v); },
  removeItem: (k: string) => { values.delete(k); }, key: (i: number) => [...values.keys()][i] ?? null, get length() { return values.size; } };
const legacy: StoredReviewDraft = { version: 1, fingerprint: reviewDraftFingerprint(document, b), content: old,
  baseContent: saved, framing: null, segments: { row: "まだ保存していない字幕" } };
writeReviewDraft(document.jobId, b.id, legacy, storage);
const stored = readReviewDraft(document.jobId, b.id, legacy.fingerprint, storage)!;
assert.equal(isClipContentDirty(b, { normal: stored.content }), true, "a successful old save can leave its former automatic snapshot dirty forever");
const result = restoreContentDraft(document, b, stored, record => archiveReviewDraft(document.jobId, b.id, record, storage));
assert.equal(result.blocked, false);
assert.deepEqual(contentDraftChangedFields(b, result.content), []);
assert.deepEqual(result.content._editedFields, []);
assert.deepEqual(stored.segments, { row: "まだ保存していない字幕" }, "caption drafts are still restored independently");
assert.deepEqual(archivedReviewDrafts(document.jobId, b.id, storage), [legacy], "uncertain legacy values are preserved in full, not guessed to be manual or thrown away");
assert.ok(archiveReviewDraft(document.jobId, b.id, legacy, storage));
assert.equal(archivedReviewDrafts(document.jobId, b.id, storage).length, 1);
const userLegacy = { ...legacy, content: { ...old, title: "人が書きかけた未保存のタイトル" } };
restoreContentDraft(document, b, userLegacy, record => archiveReviewDraft(document.jobId, b.id, record, storage));
assert.equal(archivedReviewDrafts(document.jobId, b.id, storage)[1].content.title, userLegacy.content.title);
const failed = restoreContentDraft(document, b, userLegacy, () => false);
assert.ok(failed.blocked);
assert.equal(failed.content.title, userLegacy.content.title, "failed backup cannot discard the active draft");

let draft = editContentDraft(result.content, saved, { title: "いま手で書いたタイトル" });
const newer = { ...saved, title: "さらに更新された自動案", hookText: "新しいフック", thumbnailLine1: "別のサムネ" };
draft = synchronizeContentDraft(draft, newer);
assert.equal(draft.title, "いま手で書いたタイトル");
assert.equal(draft.hookText, newer.hookText);
assert.equal(draft.thumbnailLine1, newer.thumbnailLine1);
assert.deepEqual(draft._editedFields, ["title"]);
writeReviewDraft(document.jobId, b.id, { ...legacy, content: draft, baseContent: newer }, storage);
const reopened = restoreContentDraft(document, { ...b, hookText: newer.hookText },
  readReviewDraft(document.jobId, b.id, legacy.fingerprint, storage), () => { throw Error("new explicit edits must not be archived"); });
assert.equal(reopened.content.title, draft.title);
const accepted = synchronizeContentDraft(draft, { ...newer, title: draft.title });
assert.deepEqual(accepted._editedFields, [], "a saved edit clears its intent as well as its dirty value");
assert.deepEqual(synchronizeContentDraft(accepted, newer), { ...newer, _editedFields: [] }, "later automatic choices do not resurrect saved edits");
assert.deepEqual(editContentDraft(draft, newer, { title: newer.title })._editedFields, [], "undo to the saved value is clean");
const manual = restoreContentDraft({ ...document, subtitleOnlyAuto: false }, b, legacy, () => { throw Error("legacy workflow must not migrate"); });
assert.equal(manual.content.title, old.title);
const unconfirmed = restoreContentDraft(document, { ...b, confirmed: false }, legacy, () => { throw Error("unconfirmed workflow must not migrate"); });
assert.equal(unconfirmed.content.title, old.title);
values.set(legacyReviewDraftKey("other-job", b.id), "protected");
clearJobReviewDrafts(document.jobId, storage as unknown as Storage);
assert.deepEqual([...values.keys()], [legacyReviewDraftKey("other-job", b.id)]);
console.log("Automatic draft persistence: old snapshot recurrence, full backup/restore, backup failure, explicit edits, acknowledgment, undo and legacy isolation passed");
