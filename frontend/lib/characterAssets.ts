import { API_BASE_URL, toBrowserApiUrl } from "./api";

export const CHARACTER_EMOTIONS = [
  { value: "joy", label: "喜" }, { value: "anger", label: "怒" },
  { value: "sorrow", label: "哀" }, { value: "fun", label: "楽" }
] as const;
export type CharacterEmotion = typeof CHARACTER_EMOTIONS[number]["value"];
export type CharacterAsset = {
  id: string; presetId: string; emotion: CharacterEmotion; slot: number; imageUrl: string;
  width: number; height: number; faceBox: { x: number; y: number; w: number; h: number } | null;
  hasAlpha: boolean; warnings: string[]; createdAt: string;
};
export type CharacterAssetList = {
  emotions: Record<CharacterEmotion, CharacterAsset[]>;
  minSidePixels: number; maxImageBytes: number; maxPerEmotion: number;
};

export function visibleCharacterAssetWarnings(warnings: string[] = []): string[] {
  // Saved face coordinates and notices remain in old data, but asset layout no longer uses them.
  return warnings.filter(warning => !warning.startsWith("顔を検出できません"));
}

function assetsPath(presetId: string): string {
  return `/api/character-presets/${encodeURIComponent(presetId)}/assets`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store", ...init });
  if (response.status === 204) return undefined as T;
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "素材を保存できませんでした。");
  return body as T;
}

export function getCharacterAssets(presetId: string): Promise<CharacterAssetList> {
  return request(assetsPath(presetId));
}

export function uploadCharacterAsset(presetId: string, emotion: CharacterEmotion, file: File): Promise<CharacterAsset> {
  const body = new FormData();
  body.set("emotion", emotion);
  body.set("file", file);
  return request(assetsPath(presetId), { method: "POST", body });
}

export function deleteCharacterAsset(presetId: string, assetId: string): Promise<void> {
  return request(`${assetsPath(presetId)}/${encodeURIComponent(assetId)}`, { method: "DELETE" });
}

export function characterAssetImageUrl(asset: CharacterAsset): string {
  return toBrowserApiUrl(asset.imageUrl);
}

export function characterAssetSlots(assets: CharacterAsset[], count: number): (CharacterAsset | undefined)[] {
  return Array.from({ length: count }, (_, index) => assets.find(asset => asset.slot === index + 1));
}
