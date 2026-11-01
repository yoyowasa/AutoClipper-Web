import type { SubtitleReviewClip, SubtitleReviewDocument } from "../types";
import type { ClipContentDraft } from "./drafts";

// COW keeps the original row for another clip. Repair only references to its
// unique copy in this clip; keep user-written metadata and ambiguous IDs intact.
export function remapDraftEvidence(draft: ClipContentDraft, document: SubtitleReviewDocument, clip: SubtitleReviewClip): ClipContentDraft {
  const selected = new Set(clip.segmentIds);
  const rows = document.segments.filter(row => selected.has(row.id));
  const remap = (id: string) => {
    if (selected.has(id)) return id;
    const source = document.segments.find(row => row.id === id);
    if (!source?.clipScoped) return id;
    const copies = rows.filter(row => row.clipScoped && row.index === source.index && row.start === source.start && row.end === source.end &&
      JSON.stringify(row.sourceIndices) === JSON.stringify(source.sourceIndices));
    return copies.length === 1 ? copies[0].id : id;
  };
  return { ...draft,
    descriptionEvidenceSegmentIds: (draft.descriptionEvidenceSegmentIds ?? []).map(remap),
    titleCandidates: draft.titleCandidates.map(candidate => ({ ...candidate, evidenceSegmentIds: (candidate.evidenceSegmentIds ?? []).map(remap) }))
  };
}
