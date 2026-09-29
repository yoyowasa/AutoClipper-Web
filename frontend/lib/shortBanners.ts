import { API_BASE_URL, toBrowserApiUrl } from "./api";

export function bannerAssetUrl(assetId: string): string {
  return toBrowserApiUrl(`/api/preferences/short-banner-assets/${encodeURIComponent(assetId)}`);
}

export async function bannerRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/preferences/${path}`, { cache: "no-store", ...init });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "帯設定を保存できませんでした。");
  return body as T;
}
