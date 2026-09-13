import { API_BASE_URL, toBrowserApiUrl } from "./api";
import type { ClipSettings } from "./types";

export type ShortBannerPreset = {
  name: string;
  topAssetId: string;
  bottomAssetId: string;
  topEnabled: boolean;
  bottomEnabled: boolean;
};

export const RADEN_BANNERS: ShortBannerPreset = {
  name: "らでん用", topAssetId: "raden-top", bottomAssetId: "raden-bottom",
  topEnabled: true, bottomEnabled: true
};

export function bannerAssetUrl(assetId: string): string {
  return toBrowserApiUrl(`/api/preferences/short-banner-assets/${encodeURIComponent(assetId)}`);
}

export function applyBannerPreset(settings: ClipSettings, preset: ShortBannerPreset): ClipSettings {
  return { ...settings, shortBannerPresetName: preset.name,
    shortTopBannerAssetId: preset.topAssetId, shortBottomBannerAssetId: preset.bottomAssetId,
    shortTopBannerEnabled: preset.topEnabled, shortBottomBannerEnabled: preset.bottomEnabled };
}

export async function bannerRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/preferences/${path}`, { cache: "no-store", ...init });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "帯設定を保存できませんでした。");
  return body as T;
}
