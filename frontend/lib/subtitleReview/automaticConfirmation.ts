import type { applySubtitleReviewClip } from "../api";
import type { SubtitleReviewClip } from "../types";
import { postMetadataApplyPayload } from "../youtubePosting";
import { contentDraftForClip } from "./drafts";

type ApplyPayload = Parameters<typeof applySubtitleReviewClip>[2];

/** Send only explicit detail edits; unchanged initial suggestions are not manual choices. */
export function automaticApplyPayload(clip: SubtitleReviewClip, payload: ApplyPayload): ApplyPayload {
  const posting = postMetadataApplyPayload(contentDraftForClip(clip));
  const baseline: Record<string, unknown> = { ...contentDraftForClip(clip), ...posting };
  const changed: Record<string, unknown> = Object.fromEntries(Object.entries(payload).filter(([key, value]) =>
    key === "segments" || key === "framing" || JSON.stringify(value) !== JSON.stringify(baseline[key])
  ));
  if ("hookSceneStart" in changed || "hookSceneEnd" in changed) {
    changed.hookSceneStart = payload.hookSceneStart;
    changed.hookSceneEnd = payload.hookSceneEnd;
  }
  if (Object.keys(posting).some(key => key in changed)) {
    for (const key of Object.keys(posting)) changed[key] = payload[key as keyof ApplyPayload];
  }
  return changed as ApplyPayload;
}
