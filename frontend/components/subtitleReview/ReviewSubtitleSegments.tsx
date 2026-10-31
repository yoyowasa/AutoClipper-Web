"use client";

import { captionRowKey } from "../../lib/subtitleReview/captionAutosave";
import { bulkEditableSegments, sharedSubtitleNotice } from "../../lib/subtitleReview/sharedSegments";

import { SelectionWarnings } from "./SelectionWarnings";
import { SubtitleSegmentActions } from "../SubtitleSegmentActions";
import { SubtitleBulkCorrection } from "../SubtitleBulkCorrection";
import { formatTime, clipLabel, clamp } from "../../lib/subtitleReview/display";
import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";
import { ReviewClipActions } from "./ReviewActions";
import { longEditedSubtitleWarning } from "../../lib/subtitleTiming";

export function ReviewSubtitleSegments({ context, showStyleControls = true }: { context: SubtitleReviewViewContext; showStyleControls?: boolean }) {
  const {
    selectedClip,
    review,
    selectedSegments,
    pausedSubtitleDraft,
    setPausedSubtitleDraft,
    hookSuppressionEnd,
    clipDuration,
    hookSceneDuration,
    currentSourceTime,
    isEditable, isSubtitleEditable,
    isSavingStructure,
    savePausedSubtitleDraft,
    bulkCorrectionSelection,
    setBulkCorrectionSelection,
    drafts,
    saveBulkCorrection,
    subtitleListRef,
    dirtySegmentIds,
    activeSegmentId,
    segmentRowRefs,
    seekToSubtitle,
    isPlaying,
    updateDraft,
    setSegmentCursor,
    segmentCursor,
    absolutePlaybackTime,
    saveSubtitleStructure,
    styledSegmentId,
    setWorkspaceTab,
    setStyledSegmentId,
    setSelectedTextStyleTarget,
    selectedClipContentDraft
  } = context;
  if (!selectedClip) return null;
  const structureSegments = selectedSegments.map(segment => ({ ...segment,
    affectedClipIds: segment.affectedClipIds.filter(id => review?.clips.some(clip =>
      clip.id === id && (review.subtitleOnlyAuto && selectedClip.confirmed ? clip.id === selectedClip.id : !clip.confirmed || clip.id === selectedClip.id)))
  }));
  const insertionNotice = pausedSubtitleDraft?.clipId === selectedClip.id ? sharedSubtitleNotice(review, [{
    affectedClipIds: review.clips.filter(clip => clip.start < pausedSubtitleDraft.end && clip.end > pausedSubtitleDraft.start).map(clip => clip.id)
  }], selectedClip.id) : "";
  return (
    <div className="subtitle-review-captions flex min-h-[640px] min-w-0 flex-col bg-white lg:col-span-1 lg:col-start-3 lg:row-start-1 2xl:col-span-1 2xl:col-start-3 2xl:row-start-1 2xl:min-h-0">
                <div className="border-b border-neutral-300 bg-white px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-base font-semibold">
                        {clipLabel(selectedClip, review.clips)} の字幕
                      </h3>
                      <p className="mt-1 text-xs text-neutral-500">
                        再生中の字幕へ自動で追従します
                      </p>
                    </div>
                    <p className="text-xs font-medium text-neutral-600">
                      {selectedSegments.length}件
                    </p>
                  </div>
                </div>

                <SelectionWarnings clip={selectedClip} seek={seekToSubtitle} />

                {pausedSubtitleDraft?.clipId === selectedClip.id ? (
                  <div className="border-b border-sky-300 bg-sky-50 px-3 py-3 text-sm">
                    <p className="font-semibold">プレビューの停止位置から字幕を追加</p>
                    <p className="mt-1 text-xs text-neutral-600">開始・終了は動画内の秒数です。重なる字幕は文字を残して区間を分け、編集中の文字も一緒に保存します。確定の操作は不要です。</p>
                    {insertionNotice && <p className="mt-1 text-xs text-violet-800">{insertionNotice}。確定済みの他のclipは変更しません。</p>}
                    <textarea
                      aria-label="追加する字幕"
                      className="mt-2 min-h-16 w-full border border-neutral-300 bg-white p-2"
                      maxLength={4000}
                      placeholder="抜けている字幕を入力"
                      value={pausedSubtitleDraft.text}
                      onChange={(event) => setPausedSubtitleDraft((current) => current ? { ...current, text: event.target.value } : current)}
                    />
                    {longEditedSubtitleWarning({ ...pausedSubtitleDraft, originalText: "" }) ? (
                      <p role="status" className="mt-2 text-xs font-medium text-amber-800">
                        区間が長すぎます。再生して分割してください
                      </p>
                    ) : null}
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {(["start", "end"] as const).map((field) => (
                        <div key={field}>
                          <label className="block text-xs font-medium" htmlFor={`paused-subtitle-${field}`}>
                            {field === "start" ? "開始" : "終了"}（秒）
                          </label>
                          <input
                            id={`paused-subtitle-${field}`}
                            className="mt-1 w-full border border-neutral-300 bg-white p-2 tabular-nums"
                            min={hookSuppressionEnd}
                            max={clipDuration}
                            step={0.05}
                            type="number"
                            value={Math.round((pausedSubtitleDraft[field] - selectedClip.start + hookSceneDuration) * 100) / 100}
                            onChange={(event) => setPausedSubtitleDraft((current) => current ? {
                              ...current, [field]: Math.round((selectedClip.start + Number(event.target.value) - hookSceneDuration) * 100) / 100,
                            } : current)}
                          />
                          <button
                            className="mt-1 text-xs font-medium text-sky-800 underline"
                            type="button"
                            onClick={() => {
                              const time = currentSourceTime();
                              if (time !== null) setPausedSubtitleDraft((current) => current ? { ...current, [field]: time } : current);
                            }}
                          >
                            今の再生位置を{field === "start" ? "開始" : "終了"}にする
                          </button>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 flex gap-2">
                      <button className="min-h-9 flex-1 bg-sky-700 px-2 font-semibold text-white disabled:opacity-50"
                        disabled={!isSubtitleEditable || isSavingStructure} type="button" onClick={() => void savePausedSubtitleDraft()}>
                        字幕を追加
                      </button>
                      <button className="min-h-9 border border-neutral-300 bg-white px-3" type="button"
                        onClick={() => setPausedSubtitleDraft(null)}>閉じる</button>
                    </div>
                  </div>
                ) : null}

                <SubtitleBulkCorrection draftOnly
                  selection={bulkCorrectionSelection} onSelection={setBulkCorrectionSelection}
                  segments={bulkEditableSegments(review)} clips={review.clips} drafts={context.rawDrafts} disabled={!isEditable}
                  onSave={saveBulkCorrection}
                />
                <div
                  aria-label="字幕一覧"
                  className="relative min-h-0 flex-1 overflow-y-auto overscroll-y-contain"
                  ref={subtitleListRef}
                >
                  {selectedSegments.length > 0 ? (
                    selectedSegments
                      .map((segment, segmentIndex) => ({ segment, segmentIndex }))
                      .sort((left, right) => left.segment.start - right.segment.start)
                      .map(({ segment, segmentIndex }) => {
                      const isDirty = dirtySegmentIds.has(segment.id);
                      const isActive = activeSegmentId === segment.id;
                      const relativeStart = clamp(
                        Math.max(
                          segment.start - selectedClip.start + hookSceneDuration,
                          hookSuppressionEnd
                        ),
                        0,
                        clipDuration
                      );
                      return (
                        <div
                          className={`border-b px-3 py-3 ${
                            isActive
                              ? "border-sky-300 bg-sky-50 shadow-[inset_4px_0_0_#0369a1]"
                              : "border-neutral-200 bg-white"
                          }`}
                          key={captionRowKey(selectedClip.id, segment)}
                          ref={(element) => {
                            segmentRowRefs.current[segment.id] = element;
                          }}
                        >
                          <div className="mb-2 flex items-center justify-between gap-3">
                            <button
                              className={`text-left text-sm font-semibold ${
                                isActive ? "text-sky-800" : "text-sky-700"
                              }`}
                              type="button"
                              onClick={() => seekToSubtitle(segment.start)}
                            >
                              {formatTime(relativeStart)} へ移動
                            </button>
                            <div className="flex flex-wrap justify-end gap-1 text-[11px]">
                              {isActive ? (
                                <span className="bg-sky-700 px-2 py-1 font-medium text-white">
                                  {isPlaying ? "再生中" : "現在位置"}
                                </span>
                              ) : null}
                              {segment.repaired ? (
                                <span className="rounded bg-cyan-950 px-2 py-0.5 text-xs text-cyan-200"
                                  title={segment.repairWindows?.map((window) =>
                                    `読み直した元動画の区間: ${formatTime(window.start)}〜${formatTime(window.end)}`).join("\n")}>
                                  補修
                                </span>
                              ) : null}
                              {segment.edited ? (
                                <span className="bg-sky-100 px-2 py-1 font-medium text-sky-800">
                                  修正済み
                                </span>
                              ) : null}
                              {sharedSubtitleNotice(review, [segment], selectedClip.id) ? (
                                <span className="bg-violet-100 px-2 py-1 font-medium text-violet-800">
                                  {sharedSubtitleNotice(review, [segment], selectedClip.id)}
                                </span>
                              ) : null}
                              {isDirty ? (
                                <span className="bg-amber-100 px-2 py-1 font-medium text-amber-800">
                                  未保存
                                </span>
                              ) : null}
                            </div>
                          </div>
                          <textarea
                            className={`min-h-20 w-full resize-y border px-3 py-2 text-sm leading-6 outline-none ${
                              isDirty
                                ? "border-amber-500 bg-amber-50"
                                : "border-neutral-300 bg-white focus:border-sky-600"
                            }`}
                            disabled={!(context.isSubtitleTextEditable ?? isSubtitleEditable)}
                            data-caption-edit-clip={selectedClip.id}
                            value={drafts[segment.id] ?? segment.text}
                            onInput={(event) => {
                              // Mirror pre-edit text too, so an older save reply cannot replace an active IME composition.
                              if ((event.nativeEvent as InputEvent).isComposing) updateDraft(segment.id, event.currentTarget.value);
                            }}
                            onChange={(event) => {
                              if (!(event.nativeEvent as InputEvent).isComposing) updateDraft(segment.id, event.target.value);
                            }}
                            aria-label={`字幕 ${formatTime(segment.start)}`}
                            onSelect={(event) => {
                              const field = event.currentTarget;
                              setSegmentCursor({ id: segment.id, offset: Array.from(field.value.slice(0, field.selectionStart)).length });
                              const source = field.value.slice(field.selectionStart, field.selectionEnd).trim();
                              if (source && source.length <= 200) {
                                setBulkCorrectionSelection((current) =>
                                  current?.segmentId === segment.id && current.source === source ? current
                                    : { segmentId: segment.id, source, replacement: "" });
                              }
                            }}
                          />
                          <div data-caption-edit-clip={selectedClip.id}><SubtitleSegmentActions segment={structureSegments[segmentIndex]} previous={structureSegments[segmentIndex - 1]}
                            next={structureSegments[segmentIndex + 1]}
                            text={drafts[segment.id] ?? segment.text}
                            nextText={selectedSegments[segmentIndex + 1] ? drafts[selectedSegments[segmentIndex + 1].id] ?? selectedSegments[segmentIndex + 1].text : ""}
                            cursor={segmentCursor?.id === segment.id ? segmentCursor.offset : null}
                            origin={selectedClip.start - hookSceneDuration} playhead={absolutePlaybackTime}
                            disabled={!isSubtitleEditable} onEdit={async (request) => { await saveSubtitleStructure(request); }} /></div>
                          {longEditedSubtitleWarning(segment, drafts[segment.id] ?? segment.text) ? (
                            <p role="status" className="mt-2 text-xs font-medium text-amber-800">
                              区間が長すぎます。再生して分割してください
                            </p>
                          ) : null}
                          <div className="mt-2 flex items-center justify-between gap-3">
                            <span className="text-[11px] text-neutral-400">
                              元動画 {formatTime(segment.start)}
                            </span>
                            {isDirty ? (
                              <span className="text-[11px] font-semibold text-amber-700">
                                {review.subtitleOnlyAuto && selectedClip.confirmed ? "編集欄を離れると保存します" : "字幕の追加・確定でまとめて反映"}
                              </span>
                            ) : null}
                            {showStyleControls && <button type="button" disabled={!isEditable}
                              className="border border-sky-600 px-2 py-1 text-xs text-sky-800"
                              aria-pressed={styledSegmentId === segment.id}
                              onClick={() => {
                                setWorkspaceTab("style");
                                setStyledSegmentId(segment.id);
                                setSelectedTextStyleTarget("subtitle");
                                seekToSubtitle(segment.start);
                              }}>
                              {selectedClipContentDraft?.subtitleStyles.some((s) => s.start === segment.start && s.end === segment.end)
                                ? "個別書式を編集" : "この字幕の書式"}
                            </button>}
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="px-4 py-8 text-sm text-neutral-600">
                      このclipに表示対象の字幕はありません。
                    </div>
                  )}
                </div>

                <ReviewClipActions context={context} />
                </div>
  );
}
