"use client";

import { editSubtitleStructure } from "../../api";
import type { SubtitleStructureRequest } from "../../types";
import type { SubtitleBatchUpdate } from "../../subtitleBulkCorrection";
import { acknowledgeSubtitleReviewGap, updateSubtitleReviewSegments } from "../../api";
import { nextNonemptySubtitleStart, subtitleInsertionConflict } from "../../subtitlePauseInsert";
import { remapInsertedSubtitleDraft, subtitleStructureSources } from "../../subtitleStructureDrafts";
import { mergeSubtitleGapAcknowledgement } from "../../subtitleGaps";
import type { SubtitleReviewGap } from "../../types";
import type { SubtitleReviewContext } from "./context";

export function useSubtitleEditing(context: SubtitleReviewContext) {
  async function acknowledgeGap(gap: SubtitleReviewGap) {
    const {
      selectedClip,
      isEditable,
      beginReviewMutation,
      setAcknowledgingGapId,
      setError,
      jobId,
      isCurrentReviewMutation,
      setReview,
      endReviewMutation
    } = context;
    if (!selectedClip || !isEditable) return;
    const clipId = selectedClip.id;
    const generation = beginReviewMutation();
    setAcknowledgingGapId(gap.id);
    setError(null);
    try {
      const updated = await acknowledgeSubtitleReviewGap(jobId, clipId, gap.id);
      if (isCurrentReviewMutation(generation)) {
        setReview((current) => current ? mergeSubtitleGapAcknowledgement(current, updated, clipId) : current);
      }
    } catch (caught) {
      if (isCurrentReviewMutation(generation)) {
        setError(caught instanceof Error ? caught.message : "空白区間の確認を保存できませんでした");
      }
    } finally {
      endReviewMutation();
      setAcknowledgingGapId(null);
    }
  }

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
      review?.segments ?? [], pausedSubtitleDraft.start, pausedSubtitleDraft.end, dirtySegmentIds
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
    const {
      beginReviewMutation,
      setIsSavingBulkCorrection,
      setShowSavedPreview,
      jobId,
      isCurrentReviewMutation,
      setReview,
      setDrafts,
      setDirtySegmentIds,
      endReviewMutation
    } = context;
    const generation = beginReviewMutation();
    setIsSavingBulkCorrection(true);
    setShowSavedPreview(false);
    try {
      const updated = await updateSubtitleReviewSegments(jobId, updates);
      if (isCurrentReviewMutation(generation)) {
        const ids = new Set(updates.map((item) => item.segmentId));
        setReview(updated);
        setDrafts((current) => {
          const next = { ...current };
          for (const segment of updated.segments) if (ids.has(segment.id)) next[segment.id] = segment.text;
          return next;
        });
        setDirtySegmentIds((current) => new Set([...current].filter((id) => !ids.has(id))));
      }
    } finally {
      endReviewMutation();
      setIsSavingBulkCorrection(false);
    }
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
      endReviewMutation
    } = context;
    if (!review || !isEditable) return false;
    const oldDocument = review;
    const sourceSegments = subtitleStructureSources(oldDocument.segments, request);
    const targets = new Set(sourceSegments.map((segment) => segment.id));
    const affected = new Set([...sourceSegments.flatMap(segment => segment.affectedClipIds), ...(request.clipId ? [request.clipId] : [])]);
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
      setReview(updated);
      setDrafts(current => Object.fromEntries(updated.segments.map(segment => [segment.id,
        targets.has(segment.id) || !oldIds.has(segment.id) ? segment.text : current[segment.id] ?? segment.text])));
      setDirtySegmentIds(current => new Set([...current].filter(id => !targets.has(id))));
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
          next[clip.id] = { ...draft, subtitleStyles: [...keptStyles, ...(firstStyle ? replacementSegments.map(segment =>
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
  return { acknowledgeGap, openPausedSubtitleDraft, savePausedSubtitleDraft, saveBulkCorrection, saveSubtitleStructure };
}
