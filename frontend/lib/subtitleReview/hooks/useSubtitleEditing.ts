"use client";

import { reconcileCaptionSave } from "../captionAutosave";
import { bulkEditableSegments, sharedSubtitleNotice, subtitleEditTargets, segmentDraftKey } from "../sharedSegments";
import { editSubtitleStructure, updateSubtitleReviewSegments } from "../../api";
import type { SubtitleStructureRequest } from "../../types";
import type { SubtitleBatchUpdate } from "../../subtitleBulkCorrection";
import { nextNonemptySubtitleStart } from "../../subtitlePauseInsert";
import { remapInsertedSubtitleDraft, subtitleStructureSources } from "../../subtitleStructureDrafts";
import type { SubtitleReviewContext } from "./context";

export function useSubtitleEditing(context: SubtitleReviewContext) {
  function openPausedSubtitleDraft() {
    const { videoRef, selectedClip, currentSourceTime, setError, selectedSegments, setPausedSubtitleDraft } = context;
    const video = videoRef.current;
    if (!video || !selectedClip) return;
    const start = currentSourceTime();
    if (start === null) {
      setError("冒頭フック以外の動画内で、終了位置より前に停止してください。");
      return;
    }
    const nextStart = nextNonemptySubtitleStart(selectedSegments, start, selectedClip.end);
    setPausedSubtitleDraft({
      clipId: selectedClip.id, start,
      end: Math.floor(Math.min(selectedClip.end, nextStart, start + 2) * 100 + 0.000001) / 100,
      text: "",
    });
    setError(null);
  }

  async function savePausedSubtitleDraft() {
    const {
      selectedClip,
      pausedSubtitleDraft,
      setError,
      hookSuppressionEnd,
      hookSceneDuration,
      saveSubtitleStructure,
      setPausedSubtitleDraft
    } = context;
    if (!selectedClip || !pausedSubtitleDraft || pausedSubtitleDraft.clipId !== selectedClip.id) return;
    if (!pausedSubtitleDraft.text.trim()) {
      setError("追加する字幕を入力してください。");
      return;
    }
    if (pausedSubtitleDraft.start < selectedClip.start + hookSuppressionEnd - hookSceneDuration ||
      pausedSubtitleDraft.end > selectedClip.end ||
      pausedSubtitleDraft.end - pausedSubtitleDraft.start < 0.1) {
      setError("冒頭の字幕非表示区間を避け、動画内の0.1秒以上の範囲にしてください。");
      return;
    }
    const saved = await saveSubtitleStructure({
      action: "insert_at_time", segments: [], clipId: selectedClip.id,
      start: pausedSubtitleDraft.start, end: pausedSubtitleDraft.end,
      text: pausedSubtitleDraft.text,
    });
    if (saved) setPausedSubtitleDraft(null);
  }

  async function saveBulkCorrection(updates: SubtitleBatchUpdate[]) {
    const { setDrafts, setDirtySegmentIds, setShowSavedPreview, review } = context;
    const eligible = new Set(review ? bulkEditableSegments(review).map(segment => segment.id) : []);
    updates = updates.filter(item => eligible.has(item.segmentId));
    setShowSavedPreview(false);
    setDrafts(current => ({ ...current, ...Object.fromEntries(updates.map(item => [item.segmentId, item.text])) }));
    setDirtySegmentIds(current => {
      const next = new Set(current);
      for (const update of updates) {
        const saved = review?.segments.find(item => item.id === update.segmentId);
        if (saved?.text === update.text) next.delete(update.segmentId); else next.add(update.segmentId);
      }
      return next;
    });
  }

  async function saveSubtitleStructure(request: SubtitleStructureRequest): Promise<boolean> {
    const {
      review,
      isEditable,
      subtitleListRef,
      beginReviewMutation,
      setIsSavingStructure,
      setShowSavedPreview,
      setError,
      jobId,
      isCurrentReviewMutation,
      setReview,
      setDrafts,
      setDirtySegmentIds,
      setClipContentDrafts,
      setStyledSegmentId,
      setSegmentCursor,
      setBulkCorrectionSelection,
      segmentRowRefs,
      locallyUpdatedReviewRef,
      endReviewMutation
    } = context;
    if (!review || !(context.isSubtitleEditable ?? isEditable) || !context.selectedClip) return false;
    const included = new Set(request.segments.map(item => item.segmentId));
    const edits = context.selectedSegments.filter(segment => context.dirtySegmentIds.has(segment.id) && !included.has(segment.id))
      .map(segment => ({ segmentId: segment.id, before: segment.text, text: context.drafts[segment.id] ?? segment.text }));
    request = { ...request, clipId: context.selectedClip.id, ...(edits.length ? { edits } : {}) };
    const oldDocument = review;
    const editableSegments = oldDocument.segments.filter(segment => subtitleEditTargets(oldDocument, [segment], request.clipId).length > 0);
    const sourceSegments = subtitleStructureSources(editableSegments, request);
    const targets = new Set(sourceSegments.map((segment) => segment.id));
    const affected = new Set(subtitleEditTargets(oldDocument, sourceSegments, request.clipId).map(clip => clip.id));
    if (request.action === "insert_at_time") for (const clip of oldDocument.clips) {
      if ((oldDocument.subtitleOnlyAuto && context.selectedClip.confirmed ? clip.id === request.clipId : !clip.confirmed || clip.id === request.clipId) && clip.start < request.end! && clip.end > request.start!) affected.add(clip.id);
    }
    const notice = sharedSubtitleNotice(oldDocument, [{ affectedClipIds: [...affected] }], request.clipId!);
    if (request.action !== "insert_at_time" && notice && !window.confirm(`${notice}\n確定済みの他のclipは変更しません。保存しますか？`)) return false;
    const first = sourceSegments[0];
    const oldIds = new Set(oldDocument.segments.map(segment => segment.id));
    const scrollTop = subtitleListRef.current?.scrollTop ?? 0;
    const generation = beginReviewMutation();
    setIsSavingStructure(true);
    setShowSavedPreview(false);
    setError(null);
    try {
      const updated = await editSubtitleStructure(jobId, request);
      if (!isCurrentReviewMutation(generation)) return false;
      locallyUpdatedReviewRef.current = updated;
      setReview(updated);
      const submitted = new Set([...targets, ...edits.map(item => item.segmentId)]);
      const savedKeys = new Set([...submitted].map(id => segmentDraftKey(context.selectedClip!, id)));
      const updatedClip = updated.clips.find(clip => clip.id === request.clipId);
      const retainedDraftIds = context.selectedClip.confirmed && updatedClip && !updatedClip.confirmed
        ? updatedClip.segmentIds.filter(id => !targets.has(id)) : [];
      setDrafts(current => {
        const next = { ...current };
        for (const key of savedKeys) delete next[key];
        for (const segment of updated.segments) if (!oldIds.has(segment.id) || targets.has(segment.id)) next[segment.id] = segment.text;
        for (const id of retainedDraftIds) {
          const key = segmentDraftKey(context.selectedClip!, id);
          if (current[key] !== undefined) next[id] = current[key];
          delete next[key];
        }
        return next;
      });
      setDirtySegmentIds(current => {
        const next = new Set([...current].filter(id => !savedKeys.has(id)));
        for (const id of retainedDraftIds) {
          const key = segmentDraftKey(context.selectedClip!, id);
          if (next.delete(key)) next.add(id);
        }
        return next;
      });
      setClipContentDrafts(current => {
        const next = { ...current };
        const replacementSegments = updated.segments.filter(segment => targets.has(segment.id) || !oldIds.has(segment.id));
        for (const clip of updated.clips) {
          if (!affected.has(clip.id) || !next[clip.id]) continue;
          const draft = next[clip.id];
          if (request.action === "insert_at_time" && request.start !== undefined && request.end !== undefined) {
            const previousClip = oldDocument.clips.find((item) => item.id === clip.id);
            if (previousClip) {
              next[clip.id] = remapInsertedSubtitleDraft(
                draft, previousClip, clip, sourceSegments, replacementSegments, request.start, request.end
              );
            }
            continue;
          }
          const firstStyle = first && draft.subtitleStyles.find(item => item.start === first.start && item.end === first.end)?.style;
          const keptStyles = draft.subtitleStyles.filter(item => !sourceSegments.some(segment => segment.start === item.start && segment.end === item.end));
          next[clip.id] = { ...draft, subtitleStyles: [...keptStyles, ...(firstStyle ? replacementSegments.filter(segment => segment.affectedClipIds.includes(clip.id)).map(segment =>
            ({ start: segment.start, end: segment.end, style: firstStyle })) : [])] };
        }
        return next;
      });
      setStyledSegmentId(null);
      setSegmentCursor(null);
      setBulkCorrectionSelection(null);
      const inserted = request.action === "insert_at_time"
        ? updated.segments.find(segment => !oldIds.has(segment.id) && segment.start === request.start && segment.end === request.end) : null;
      requestAnimationFrame(() => {
        const list = subtitleListRef.current;
        if (!list) return;
        const row = inserted ? segmentRowRefs.current[inserted.id] : null;
        list.scrollTo({ top: row ? row.offsetTop - list.offsetTop - list.clientHeight / 3 : scrollTop });
      });
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "字幕区間を変更できませんでした");
      return false;
    } finally {
      setIsSavingStructure(false);
      endReviewMutation();
    }
  }
  async function saveConfirmedSubtitles(clipId = context.selectedClip?.id) {
    const { review, rawDrafts, rawDirtySegmentIds, setDrafts, setDirtySegmentIds } = context;
    const clip = review?.clips.find(item => item.id === clipId);
    if (!review?.subtitleOnlyAuto || review.jobId !== context.jobId || !clip?.confirmed || context.hasReviewMutationInFlight ||
      (context.reviewMutationCountRef?.current ?? 0) > 0) return;
    const updates = review.segments.filter(segment => clip.segmentIds.includes(segment.id) && rawDirtySegmentIds.has(segmentDraftKey(clip, segment.id)))
      .map(segment => ({ segmentId: segment.id, before: segment.text, text: rawDrafts[segmentDraftKey(clip, segment.id)] ?? segment.text }));
    if (!updates.length) return;
    const generation = context.beginReviewMutation();
    const setSaving = context.setIsSavingConfirmedSubtitles ?? context.setIsSavingBulkCorrection;
    setSaving(true);
    context.setShowSavedPreview(false);
    context.setError(null);
    try {
      const updated = await updateSubtitleReviewSegments(context.jobId, updates, clip.id);
      if (!context.isCurrentReviewMutation(generation)) return;
      const reconciled = reconcileCaptionSave(review, updated, clip.id, updates,
        context.subtitleDraftsRef?.current ?? rawDrafts, context.subtitleDirtyRef?.current ?? rawDirtySegmentIds);
      context.locallyUpdatedReviewRef.current = updated;
      setDrafts(reconciled.drafts);
      setDirtySegmentIds(reconciled.dirty);
      context.setReview(updated);
    } catch (caught) {
      context.setError(caught instanceof Error ? caught.message : "字幕の変更を保存できませんでした。入力は保持しています。");
    } finally {
      setSaving(false);
      context.endReviewMutation();
    }
  }
  return { openPausedSubtitleDraft, savePausedSubtitleDraft, saveBulkCorrection, saveSubtitleStructure, saveConfirmedSubtitles };
}
