import { API_BASE_URL } from "./api";

export type YouTubeSyncRun = {
  id: string; status: "queued" | "running" | "success" | "partial" | "failed";
  queuedAt: string; finishedAt: string | null; errorCode: string | null; errorMessage: string | null;
  requestedStart: string | null; requestedEnd: string | null; lastReportDate: string | null;
  fetchedCount: number; truncated: boolean; missingReportCount: number;
};
export type ConnectedYouTubeChannel = {
  id: number; externalId: string; name: string | null;
  connectionStatus: "connected" | "reconnect_required"; errorMessage: string | null;
  lastSyncAt: string | null; latestRun: YouTubeSyncRun | null;
};
export type YouTubeConnections = {
  clientConfigured: boolean; channels: ConnectedYouTubeChannel[];
  derivedAllowed: boolean; extendedStorage: boolean; reviewedAt: string; policyReference: string;
  automation?: { enabled: boolean; syncHourUtc: number; analysisWeekday: number; timezone: string } | null;
};

export function automationLabel(automation: YouTubeConnections["automation"]): string {
  if (!automation) return "定時実行の設定は未取得です。";
  if (!automation.enabled) return "定時実行は無効です。手動で同期・分析できます。";
  const hour = (automation.syncHourUtc + 9) % 24;
  const day = (automation.analysisWeekday + Math.floor((automation.syncHourUtc + 9) / 24)) % 7;
  return `毎日${hour}:00に同期、${["月", "火", "水", "木", "金", "土", "日"][day]}曜は同期後に自己分析（日本時間）。` +
    "処理中・停止中は再開後に実行し、失敗は次回の予定で再試行します。";
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/intelligence${path}`, {
    ...init, cache: "no-store", credentials: "include"
  });
  if (response.status === 204) return undefined as T;
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "YouTube連携の処理に失敗しました。");
  return data as T;
}
export const getYouTubeConnections = () => request<YouTubeConnections>("/channels");
export const startYouTubeConnection = (channelExternalId: string) => request<{ authorizationUrl: string }>("/oauth/start", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channelExternalId })
});
export const syncYouTubeChannel = (id: number) => request<YouTubeSyncRun>(`/channels/${id}/sync`, { method: "POST" });

export function youtubeSyncLabel(run: YouTubeSyncRun | null): string {
  if (!run) return "未同期";
  if (["success", "partial"].includes(run.status) && !run.lastReportDate) return "同期完了（Analyticsは未返却）";
  return { queued: "同期の順番待ち", running: "同期中", success: "同期成功", partial: "同期完了（取得範囲に上限あり）",
    failed: "同期失敗" }[run.status];
}
export function youtubeSyncTime(value: string | null): string {
  if (!value) return "未同期";
  const utc = /Z$|[+-]\d\d:\d\d$/.test(value) ? value : value + "Z";
  return new Date(utc).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}
