"use client";

import { bulkEditableSegments, sharedSubtitleNotice, subtitleEditTargets, segmentDraftKey } from "../sharedSegments";
import { editSubtitleStructure } from "../../api";
import type { SubtitleStructureRequest } from "../../types";
import type { SubtitleBatchUpdate } from "../../subtitleBulkCorrection";
import { nextNonemptySubtitleStart, subtitleInsertionConflict } from "../../subtitlePauseInsert";
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
      review,
      dirtySegmentIds,
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
    const insertionConflict = subtitleInsertionConflict(
      (review?.segments ?? []).filter(segment => segment.affectedClipIds.some(id =>
        review?.clips.some(clip => clip.id === id && (!clip.confirmed || clip.id === selectedClip.id)))), pausedSubtitleDraft.start, pausedSubtitleDraft.end, dirtySegmentIds
    );
    if (insertionConflict === "unsaved") {
      setError("追加区間に未保存の字幕があります。先に保存してから字幕を追加してください。");
      return;
    }
    if (insertionConflict === "overlap") {
      setError("既存字幕と時間が重なっています。空白区間に合わせてください。");
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
    if (!review || !isEditable || !context.selectedClip) return false;
    request = { ...request, clipId: context.selectedClip.id };
    const oldDocument = review;
    const editableSegments = oldDocument.segments.filter(segment => segment.affectedClipIds.some(id =>
      oldDocument.clips.some(clip => clip.id === id && (!clip.confirmed || clip.id === request.clipId))));
    const sourceSegments = subtitleStructureSources(editableSegments, request);
    const targets = new Set(sourceSegments.map((segment) => segment.id));
    const affected = new Set(subtitleEditTargets(oldDocument, sourceSegments, request.clipId).map(clip => clip.id));
    if (request.action === "insert_at_time") for (const clip of oldDocument.clips) {
      if ((!clip.confirmed || clip.id === request.clipId) && clip.start < request.end! && clip.end > request.start!) affected.add(clip.id);
    }
    const notice = sharedSubtitleNotice(oldDocument, [{ affectedClipIds: [...affected] }], request.clipId!);
    if (notice && !window.confirm(`${notice}\n確定済みの他のclipは変更しません。保存しますか？`)) return false;
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
      const savedKeys = new Set([...targets].flatMap(id => [id, segmentDraftKey(context.selectedClip!, id)]));
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
  return { openPausedSubtitleDraft, savePausedSubtitleDraft, saveBulkCorrection, saveSubtitleStructure };
}
