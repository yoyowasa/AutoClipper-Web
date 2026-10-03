import type {
  SubtitleReviewClip,
  SubtitleReviewSegment,
  SubtitleStructureRequest,
  SubtitleStyleOverride
} from "./types";

export function subtitleStructureSources(
  segments: SubtitleReviewSegment[], request: SubtitleStructureRequest
): SubtitleReviewSegment[] {
  const targets = new Set(request.segments.map((item) => item.segmentId));
  return segments.filter((segment) => targets.has(segment.id) || (
    request.action === "insert_at_time" && request.start !== undefined && request.end !== undefined &&
    !segment.text.trim() && segment.start < request.end && segment.end > request.start
  ));
}

export function remapInsertedSubtitleDraft<T extends { subtitleStyles: SubtitleStyleOverride[] }>(
  draft: T,
  previousClip: Pick<SubtitleReviewClip, "subtitleStyles">,
  updatedClip: Pick<SubtitleReviewClip, "id" | "subtitleStyles">,
  sources: SubtitleReviewSegment[],
  replacements: SubtitleReviewSegment[],
  start: number,
  end: number
): T {
  const clipSources = sources.filter((segment) => segment.affectedClipIds.includes(updatedClip.id))
    .sort((left, right) => left.start - right.start || left.end - right.end);
  const sameRange = (left: { start: number; end: number }, right: { start: number; end: number }) =>
    left.start === right.start && left.end === right.end;
  const kept = draft.subtitleStyles.filter((item) => !clipSources.some((segment) => sameRange(item, segment)));
  const moved: SubtitleStyleOverride[] = [];
  for (const replacement of replacements) {
    if (!replacement.affectedClipIds.includes(updatedClip.id)) continue;
    const source = replacement.start === start && replacement.end === end
      ? clipSources[0]
      : clipSources.find((segment) => segment.start <= replacement.start && segment.end >= replacement.end);
    if (!source) continue;
    const before = previousClip.subtitleStyles?.find((item) => sameRange(item, source));
    const current = draft.subtitleStyles.find((item) => sameRange(item, source));
    // A missing draft override may be an unsaved removal; do not resurrect it.
    if (!current) continue;
    const saved = updatedClip.subtitleStyles?.find((item) => sameRange(item, replacement));
    const style = before && JSON.stringify(before.style) === JSON.stringify(current.style)
      ? saved?.style ?? current.style : current.style;
    moved.push({ start: replacement.start, end: replacement.end, style });
  }
  return { ...draft, subtitleStyles: [...kept, ...moved] };
}
