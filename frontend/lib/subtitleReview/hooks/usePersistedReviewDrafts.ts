"use client";

import { canEditManualFraming } from "../manualFraming";
import { segmentDraftKey } from "../sharedSegments";
import { useEffect, useRef } from "react";
import { contentDraftForClip, isClipContentDirty } from "../drafts";
import { remapDraftEvidence } from "../draftEvidence";
import { readReviewDraft, reviewDraftFingerprint, writeReviewDraft, archiveReviewDraft } from "../draftStorage";
import { restoreContentDraft, synchronizeContentDraft } from "../contentDraftSync";
import type { SubtitleReviewState } from "./useSubtitleReviewState";

export function usePersistedReviewDrafts(state: SubtitleReviewState) {
  const { jobId, review, drafts, dirtySegmentIds, clipContentDrafts, shortFramingDrafts,
    setDrafts, setDirtySegmentIds, setClipContentDrafts, setShortFramingDrafts, locallyUpdatedReviewRef, setError } = state;
  const fingerprints = useRef<Record<string, string>>({});
  const activeJob = useRef("");
  const restoring = useRef(false);
  useEffect(() => {
    if (!review || review.jobId !== jobId) return;
    if (activeJob.current !== jobId) { activeJob.current = jobId; fingerprints.current = {}; }
    const ownedUpdate = locallyUpdatedReviewRef.current === review;
    locallyUpdatedReviewRef.current = null;
    const restoredSegments: Record<string, string> = {};
    const resetIds = new Set<string>();
    for (const clip of review.clips) {
      const saved = contentDraftForClip(clip);
      if (review.subtitleOnlyAuto && clip.confirmed) {
        const legacy = clipContentDrafts[clip.id];
        const canMigrate = !legacy || legacy._editedFields !== undefined || !isClipContentDirty(clip, { [clip.id]: legacy }) ||
          archiveReviewDraft(jobId, clip.id, { version: 1, fingerprint: reviewDraftFingerprint(review, clip), content: legacy,
            baseContent: saved, framing: shortFramingDrafts[clip.id] ?? null,
            segments: Object.fromEntries(clip.segmentIds.filter(id => dirtySegmentIds.has(segmentDraftKey(clip, id)))
              .map(id => [id, drafts[segmentDraftKey(clip, id)] ?? ""])) });
        if (!canMigrate) setError("以前の詳細下書きを保護できないため、同期を止めました。入力内容は保持しています。");
        setClipContentDrafts(current => {
          const draft = current[clip.id] ?? saved;
          if (draft._editedFields === undefined && (!canMigrate || legacy && JSON.stringify(legacy) !== JSON.stringify(draft))) return current;
          const mapped = remapDraftEvidence(draft, review, clip);
          const next = synchronizeContentDraft(mapped, saved);
          return JSON.stringify(draft) === JSON.stringify(next) ? current : { ...current, [clip.id]: next };
        });
      }
      const fingerprint = reviewDraftFingerprint(review, clip);
      const previous = fingerprints.current[clip.id];
      fingerprints.current[clip.id] = fingerprint;
      if (review.state !== "awaiting_review" && !(review.subtitleOnlyAuto && clip.confirmed)) { writeReviewDraft(jobId, clip.id, null); continue; }
      if (ownedUpdate || previous === fingerprint) continue;
      const stored = readReviewDraft(jobId, clip.id, fingerprint);
      const restored = restoreContentDraft(review, clip, stored, draft => archiveReviewDraft(jobId, clip.id, draft));
      if (restored.blocked) setError("以前の詳細下書きを保護できないため、同期を止めました。入力内容は保持しています。");
      restoring.current = true;
      setClipContentDrafts(current => ({ ...current, [clip.id]: restored.content }));
      setShortFramingDrafts(current => {
        const next = { ...current };
        if (stored?.framing && canEditManualFraming(review, clip)) next[clip.id] = stored.framing; else delete next[clip.id];
        return next;
      });
      for (const id of clip.segmentIds) {
        const key = segmentDraftKey(clip, id);
        resetIds.add(key);
        restoredSegments[key] = stored?.segments[id] ?? review.segments.find(segment => segment.id === id)?.text ?? "";
      }

    }
    if (resetIds.size > 0) {
      setDrafts(current => ({ ...current, ...restoredSegments }));
      setDirtySegmentIds(current => {
        const next = new Set(current);
        for (const id of resetIds) {
          const saved = review.segments.find(segment => id === segment.id || id.endsWith(`::${segment.id}`));
          if (saved && restoredSegments[id] !== saved.text) next.add(id); else next.delete(id);
        }
        return next;
      });
    }
    // Only incoming server documents trigger synchronization. A user keystroke
    // must not rerun restoration or replace its own draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, review, locallyUpdatedReviewRef, setClipContentDrafts, setShortFramingDrafts, setDrafts, setDirtySegmentIds, setError]);

  useEffect(() => {
    if (!review || review.jobId !== jobId || review.state !== "awaiting_review" && !review.subtitleOnlyAuto) return;
    if (restoring.current) { restoring.current = false; return; }
    for (const clip of review.clips) {
      const segments = Object.fromEntries(clip.segmentIds.filter(id => dirtySegmentIds.has(segmentDraftKey(clip, id)))
        .map(id => [id, drafts[segmentDraftKey(clip, id)] ?? ""]));
      const draft = clipContentDrafts[clip.id] ?? contentDraftForClip(clip);
      const content = review.subtitleOnlyAuto && clip.confirmed && draft._editedFields !== undefined
        ? synchronizeContentDraft(remapDraftEvidence(draft, review, clip), contentDraftForClip(clip)) : draft;
      const framing = shortFramingDrafts[clip.id] ?? null;
      const dirty = isClipContentDirty(clip, clipContentDrafts) || Boolean(framing) || Object.keys(segments).length > 0;
      writeReviewDraft(jobId, clip.id, dirty ? {
        version: 1, fingerprint: reviewDraftFingerprint(review, clip), content, baseContent: contentDraftForClip(clip), framing, segments
      } : null);
    }
  }, [jobId, review, drafts, dirtySegmentIds, clipContentDrafts, shortFramingDrafts]);
}
