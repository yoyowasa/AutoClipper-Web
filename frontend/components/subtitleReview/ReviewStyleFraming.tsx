"use client";

import { resolvedClipTextStyle } from "../../lib/clipTextStyle";
import { canEditManualFraming } from "../../lib/subtitleReview/manualFraming";
import { ShortFramingWorkspace } from "../ShortFramingWorkspace";
import { ClipTextStyleEditor } from "../ClipTextStyleEditor";
import { toApiUrl } from "../../lib/api";
import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";

export function ReviewTextStyles({ context }: { context: SubtitleReviewViewContext }) {
  const {
    selectedSegments,
    styledSegmentId,
    setStyledSegmentId,
    selectedClip,
    isEditable,
    selectedClipContentDraft,
    selectedTextStyleTarget,
    selectedShortTitleOutputEnabled,
    review,
    jobId,
    selectedClipTextStyles,
    selectedResolvedClipTextStyles,
    selectedDefaultResolvedClipTextStyles,
    stylePreviewSubtitleText,
    updateClipTextStyle,
    setSelectedTextStyleTarget
  } = context;
  if (!selectedClip) return null;
  const cue = selectedSegments.find(s => s.id === styledSegmentId);
  const override = selectedClipContentDraft?.subtitleStyles.find(s => cue && s.start === cue.start && s.end === cue.end);
  const resolvedCue = resolvedClipTextStyle(override ? { ...override.style, ...override.layoutAdjustment } : undefined,
    resolvedClipTextStyle(selectedClipTextStyles.subtitle, selectedResolvedClipTextStyles.subtitle, "subtitle", selectedClip.type), "subtitle", selectedClip.type);
  return (
    <ClipTextStyleEditor
                    subtitleScopeLabel={selectedSegments.some((s) => s.id === styledSegmentId) ? "選択した字幕1件だけ" : "このclipの共通字幕"}
                    onCommonSubtitleStyle={() => setStyledSegmentId(null)}
                    clipType={selectedClip.type}
                    disabled={!(selectedTextStyleTarget === "subtitle" && selectedSegments.some(s => s.id === styledSegmentId)
                      ? context.isSubtitleEditable : isEditable)}
                    hookText={selectedClipContentDraft?.hookText ?? ""}
                    key={selectedClip.id}
                    layout="workspace"
                    selectedTarget={selectedTextStyleTarget}
                    showPreview={false}
                    shortTitleOutputEnabled={selectedShortTitleOutputEnabled}
                    shortTopBannerEnabled={review.shortTopBannerEnabled}
                    shortTopBannerUrl={toApiUrl(
                      `/api/jobs/${jobId}/subtitle-review/banner-assets/top?v=${encodeURIComponent(review.updatedAt)}`
                    )}
                    shortBottomBannerEnabled={review.shortBottomBannerEnabled}
                    shortBottomBannerUrl={toApiUrl(
                      `/api/jobs/${jobId}/subtitle-review/banner-assets/bottom?v=${encodeURIComponent(review.updatedAt)}`
                    )}
                    styles={{
                      ...selectedClipTextStyles,
                      subtitle: cue ? resolvedCue : selectedClipTextStyles.subtitle
                    }}
                    resolvedStyles={selectedResolvedClipTextStyles}
                    defaultResolvedStyles={selectedDefaultResolvedClipTextStyles}
                    subtitleMaxCharsPerLine={selectedClip.subtitleMaxCharsPerLine}
                    subtitleMaxLines={selectedClip.subtitleMaxLines}
                    previewWidth={selectedClip.previewWidth}
                    previewHeight={selectedClip.previewHeight}
                    subtitleText={stylePreviewSubtitleText}
                    titleText={selectedClipContentDraft?.title ?? ""}
                    cueStyle={cue ? override?.style : undefined}
                    onCueStyleChange={cue && selectedClipContentDraft ? (style) => context.updateClipContentDraft(selectedClip.id, {
                      subtitleStyles: [...selectedClipContentDraft.subtitleStyles.filter(s => s.start !== cue.start || s.end !== cue.end),
                        { start: cue.start, end: cue.end, style, styleVersion: 2 }]
                    }) : undefined}
                    onChange={updateClipTextStyle}
                    onSelectedTargetChange={(target) => {
                      setSelectedTextStyleTarget(target);
                      setStyledSegmentId(null);
                    }}
                  />
  );
}

export function ReviewShortFraming({ context }: { context: SubtitleReviewViewContext }) {
  const {
    selectedClip,
    review,
    jobId,
    selectedShortFramingDraft,
    isEditable,
    hasReviewMutationInFlight,
    changeSelectedShortFraming,
    saveSelectedShortFraming,
    resetSelectedShortFraming
  } = context;
  if (!selectedClip || !selectedShortFramingDraft || !canEditManualFraming(review, selectedClip)) return null;
  return (
    <>
    {review.subtitleOnlyAuto && selectedClip.manualDecisionFields?.includes("framing") && <div className="space-y-1">
      <button type="button" className="min-h-10 border border-sky-700 px-3 text-sm text-sky-900"
        disabled={hasReviewMutationInFlight} onClick={() => void resetSelectedShortFraming(selectedClip.id)}>
        自動に戻す
      </button>
      <p className="text-xs text-neutral-500">手動の指定を解除し、このclipの内容から画角を選び直して作り直します。</p>
    </div>}
    <ShortFramingWorkspace
                          key={`${selectedClip.id}:${selectedClip.start}:${selectedClip.end}:${review.sourceVideoUrl}:${review.shortTopBannerEnabled}:${review.shortBottomBannerEnabled}`}
                          jobId={jobId} clipId={selectedClip.id} sourceUrl={review.sourceVideoUrl}
                          start={selectedClip.start} end={selectedClip.end}
                          draftOnly={!review.subtitleOnlyAuto} value={selectedShortFramingDraft} layout={selectedShortFramingDraft.shortLayout ?? selectedClip.shortLayout ?? review.shortLayout} editable={(review.subtitleOnlyAuto || isEditable) && !hasReviewMutationInFlight}
                          onSave={async (next) => {
                            changeSelectedShortFraming(next);
                            return saveSelectedShortFraming(selectedClip.id, next);
                          }}
                        />
    </>
  );
}
