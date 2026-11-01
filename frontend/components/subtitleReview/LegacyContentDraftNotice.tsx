"use client";

import { useSyncExternalStore } from "react";
import { archivedDraftSnapshot, parseArchivedDrafts, subscribeArchivedDrafts } from "../../lib/subtitleReview/draftStorage";
import { contentDraftChangedFields, type ClipContentDraft } from "../../lib/subtitleReview/drafts";
import { remapDraftEvidence } from "../../lib/subtitleReview/draftEvidence";
import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";

export function LegacyContentDraftNotice({ context }: { context: SubtitleReviewViewContext }) {
  const { jobId, selectedClip, review, isEditable, hasReviewMutationInFlight, updateClipContentDraft } = context;
  const clipId = selectedClip?.id;
  const snapshot = useSyncExternalStore(subscribeArchivedDrafts, () => clipId ? archivedDraftSnapshot(jobId, clipId) : null, () => null);
  const copies = parseArchivedDrafts(snapshot);
  if (!selectedClip || !copies.length) return null;
  return <details className="mb-3 border border-amber-300 bg-amber-50 p-2 text-xs">
    <summary>以前の詳細下書きを保護しています（{copies.length}件）</summary>
    <p className="my-2">旧版では自動更新と手編集を区別できませんでした。字幕は引き継ぎ、タイトルなどは保存済みの値を使っています。必要な詳細下書きだけ復元できます。</p>
    {!isEditable && <p>詳細下書きの復元は、このclipを編集可能にしてから行えます。字幕の保存にこの操作は不要です。</p>}
    {copies.map((copy, index) => {
      const draft = remapDraftEvidence(copy.content, review, selectedClip);
      const fields = contentDraftChangedFields(selectedClip, draft);
      return <button key={index} type="button" disabled={!isEditable || hasReviewMutationInFlight || !fields.length}
        className="mt-2 block border border-neutral-400 bg-white px-2 py-1 disabled:opacity-40"
        onClick={() => updateClipContentDraft(selectedClip.id, Object.fromEntries(fields.map(key => [key, draft[key as keyof ClipContentDraft]])))}>
        下書き{index + 1}の詳細{fields.length}項目を復元
      </button>;
    })}
  </details>;
}
