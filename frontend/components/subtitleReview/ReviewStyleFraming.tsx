"use client";

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
  return (
    <ClipTextStyleEditor
                    subtitleScopeLabel={selectedSegments.some((s) => s.id === styledSegmentId) ? "選択した字幕1件だけ" : "このclipの共通字幕"}
                    onCommonSubtitleStyle={() => setStyledSegmentId(null)}
                    clipType={selectedClip.type}
                    disabled={!isEditable}
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
                      subtitle: selectedClipContentDraft?.subtitleStyles.find((item) => {
                        const segment = selectedSegments.find((s) => s.id === styledSegmentId);
                        return segment && item.start === segment.start && item.end === segment.end;
                      })?.style ?? selectedClipTextStyles.subtitle
                    }}
                    resolvedStyles={selectedResolvedClipTextStyles}
                    defaultResolvedStyles={selectedDefaultResolvedClipTextStyles}
                    subtitleMaxCharsPerLine={selectedClip.subtitleMaxCharsPerLine}
                    subtitleMaxLines={selectedClip.subtitleMaxLines}
                    previewWidth={selectedClip.previewWidth}
                    previewHeight={selectedClip.previewHeight}
                    subtitleText={stylePreviewSubtitleText}
                    titleText={selectedClipContentDraft?.title ?? ""}
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
    saveSelectedShortFraming
  } = context;
  if (!selectedClip || !selectedShortFramingDraft || !canEditManualFraming(review, selectedClip)) return null;
  return (
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
  );
}
