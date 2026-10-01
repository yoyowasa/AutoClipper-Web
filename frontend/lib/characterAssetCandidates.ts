import { API_BASE_URL } from "./api";
import type { CharacterAsset, CharacterEmotion } from "./characterAssets";

export type CharacterAssetCandidate = {
  id: string; presetId: string; videoId: string; sourceSecond: number; imageUrl: string;
  faceBox: { x: number; y: number; w: number; h: number };
  suggestedEmotion: CharacterEmotion | "neutral" | null; usable: boolean | null;
  issues: string[]; score: number | null; sameCharacter: boolean | null;
  status: "pending" | "adopted" | "rejected"; warnings: string[]; createdAt: string;
};
export type HarvestState = {
  id: string; videoId: string; state: "queued" | "running" | "completed" | "failed";
  candidateCount: number; message: string; updatedAt: string;
};
export type CandidateList = { candidates: CharacterAssetCandidate[]; harvests: HarvestState[] };
export type HarvestVideo = { id: string; filename: string; duration: number | null };
export type AssetCounts = { assets: number; candidates: number };

export async function candidateRequest<T>(presetId: string, suffix: string, init?: RequestInit): Promise<T> {
  const result = await fetch(`${API_BASE_URL}/api/character-presets/${encodeURIComponent(presetId)}${suffix}`, {
    cache: "no-store", ...init
  });
  if (result.status === 204) return undefined as T;
  const payload = await result.json();
  if (!result.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "素材候補の操作に失敗しました。");
  return payload as T;
}
export function harvestCandidates(presetId: string, videoId: string): Promise<HarvestState> {
  return candidateRequest(presetId, "/asset-harvests", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ videoId })
  });
}
export function adoptCandidate(presetId: string, id: string, emotion: CharacterEmotion, replaceSlot?: number): Promise<CharacterAsset> {
  return candidateRequest(presetId, `/asset-candidates/${encodeURIComponent(id)}/adopt`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ emotion, replaceSlot })
  });
}
export function rejectCandidate(presetId: string, id: string): Promise<void> {
  return candidateRequest(presetId, `/asset-candidates/${encodeURIComponent(id)}/reject`, { method: "POST" });
}
export function deleteCharacterPreset(presetId: string, confirmedCounts: AssetCounts): Promise<void> {
  return candidateRequest(presetId, "", {
    method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify(confirmedCounts)
  });
}
export function candidateNeedsReview(candidate: CharacterAssetCandidate): boolean {
  return candidate.usable === false || candidate.sameCharacter === false || candidate.status === "rejected";
}
export function groupedCandidates(candidates: CharacterAssetCandidate[], needsReview: boolean) {
  const groups = ["joy", "anger", "sorrow", "fun", "neutral", "unclassified"] as const;
  return groups.map(emotion => ({ emotion, candidates: candidates.filter(candidate =>
    candidate.status !== "adopted" && candidateNeedsReview(candidate) === needsReview &&
    (candidate.suggestedEmotion ?? "unclassified") === emotion
  ).sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.sourceSecond - b.sourceSecond) }));
}
