import { API_BASE_URL } from "./api";
import type { FramingGuide } from "./shortFraming";

export async function prepareShortFramingGuide(jobId: string, clipId: string, signal: AbortSignal, force = false, layout?: string): Promise<FramingGuide> {
  const query = new URLSearchParams({ force: String(force) });
  if (layout) query.set("layout", layout);
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/framing-guide?${query}`, {
    method: "POST", signal, cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "画角を読み込めませんでした。");
  }
  return response.json();
}
