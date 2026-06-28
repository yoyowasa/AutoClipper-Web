import type {
  ClipSettings,
  JobCreateResponse,
  JobResultsResponse,
  JobStatusResponse,
  VideoUploadResponse
} from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as {
        detail?: string | { code?: string; message?: string };
      };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail?.message) {
        message = payload.detail.message;
      }
    } catch {
      // Keep the HTTP status message when the backend returns a non-JSON error.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export function toApiUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  return `${API_BASE_URL}${pathOrUrl}`;
}

export async function uploadVideo(file: File): Promise<VideoUploadResponse> {
  const body = new FormData();
  body.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/videos/upload`, {
    method: "POST",
    body
  });

  return parseJsonResponse<VideoUploadResponse>(response);
}

export async function createJob(
  videoId: string,
  settings: ClipSettings
): Promise<JobCreateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      videoId,
      settings
    })
  });

  return parseJsonResponse<JobCreateResponse>(response);
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`, {
    cache: "no-store"
  });

  return parseJsonResponse<JobStatusResponse>(response);
}

export async function getJobResults(jobId: string): Promise<JobResultsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/results`, {
    cache: "no-store"
  });

  return parseJsonResponse<JobResultsResponse>(response);
}
