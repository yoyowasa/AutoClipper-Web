"use client";

import { ClipHookSceneEditor } from "../ClipHookSceneEditor";
import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";

export function ReviewHookSceneSettings({ context }: { context: SubtitleReviewViewContext }) {
  const { selectedClip, selectedClipContentDraft, isEditable, absolutePlaybackTime, isUpdatingHookScene, review, saveHookScene } = context;
  if (!selectedClip) return null;
  return (
    <details className="mt-2 border border-neutral-300 bg-white">
                          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">
                            フック映像設定
                          </summary>
                          <div className="border-t border-neutral-300">
                            <ClipHookSceneEditor draftOnly
                              clip={{ ...selectedClip, hookSceneStart: selectedClipContentDraft?.hookSceneStart ?? null, hookSceneEnd: selectedClipContentDraft?.hookSceneEnd ?? null }}
                              disabled={!isEditable}
                              enforceMaximumDuration={selectedClip.type === "short"}
                              key={`${selectedClip.id}-${selectedClipContentDraft?.hookSceneStart}-${selectedClipContentDraft?.hookSceneEnd}`}
                              playheadSourceTime={absolutePlaybackTime}
                              saving={isUpdatingHookScene}
                              shortMaxDuration={review.shortMaxDuration}
                              onSave={(start, end) =>
                                void saveHookScene(start, end)
                              }
                            />
                          </div>
                        </details>
  );
}
