import type {
  ClipPlanActionResponse,
  ClipPlanBoundaryUpdateRequest,
  ClipPlanDocument,
  ClipPlanReselectionRequest,
  ClipPlanTranscriptSegment,
  ClipSettings,
  JobCreateResponse,
  JobResultsResponse,
  JobStatusResponse,
  SubtitleReviewDocument,
  SubtitleReviewFinalizeResponse,
  VideoUploadResponse
} from "./types";
import type {
  SubtitleStylePresetDocument,
  SubtitleStylePresetSlots
} from "./subtitleStylePresets";

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

function apiErrorMessage(payload: unknown, fallback: string): string {
  const parsed = payload as {
    detail?: string | { code?: string; message?: string };
  } | null;
  if (typeof parsed?.detail === "string") {
    return parsed.detail;
  }
  return parsed?.detail?.message ?? fallback;
}

export function toApiUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  return `${API_BASE_URL}${pathOrUrl}`;
}

export async function getSubtitleStylePresets(): Promise<SubtitleStylePresetDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/preferences/subtitle-style-presets`,
    {
      cache: "no-store"
    }
  );
  return parseJsonResponse<SubtitleStylePresetDocument>(response);
}

export async function saveSubtitleStylePresets(
  slots: SubtitleStylePresetSlots
): Promise<SubtitleStylePresetDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/preferences/subtitle-style-presets`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        version: 1,
        slots
      })
    }
  );
  return parseJsonResponse<SubtitleStylePresetDocument>(response);
}

export function uploadVideo(
  file: File,
  onProgress?: (percentage: number) => void
): Promise<VideoUploadResponse> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);

    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE_URL}/api/videos/upload`);
    request.responseType = "json";
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(100);
        resolve(request.response as VideoUploadResponse);
        return;
      }
      reject(
        new Error(
          apiErrorMessage(
            request.response,
            `${request.status} ${request.statusText || "Upload failed"}`
          )
        )
      );
    });
    request.addEventListener("error", () => {
      reject(new Error("Upload failed because the server could not be reached"));
    });
    request.send(body);
  });
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

export async function getClipPlan(jobId: string): Promise<ClipPlanDocument> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/clip-plan`, {
    cache: "no-store"
  });
  return parseJsonResponse<ClipPlanDocument>(response);
}

export async function reselectClipPlan(
  jobId: string,
  settings: ClipPlanReselectionRequest
): Promise<ClipPlanActionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/clip-plan/reselect`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(settings)
  });
  return parseJsonResponse<ClipPlanActionResponse>(response);
}

export async function updateClipPlanBoundary(
  jobId: string,
  clipId: string,
  boundary: ClipPlanBoundaryUpdateRequest
): Promise<ClipPlanActionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/clip-plan/clips/${clipId}/boundary`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(boundary)
    }
  );
  return parseJsonResponse<ClipPlanActionResponse>(response);
}

export async function getClipPlanTranscriptSegments(
  jobId: string,
  clipId: string,
  boundary: ClipPlanBoundaryUpdateRequest,
  signal?: AbortSignal
): Promise<ClipPlanTranscriptSegment[]> {
  const query = new URLSearchParams({
    start: String(boundary.start),
    end: String(boundary.end)
  });
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/clip-plan/clips/${clipId}/transcript-segments?${query}`,
    {
      cache: "no-store",
      signal
    }
  );
  return parseJsonResponse<ClipPlanTranscriptSegment[]>(response);
}

export async function approveClipPlan(jobId: string): Promise<ClipPlanActionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/clip-plan/approve`, {
    method: "POST"
  });
  return parseJsonResponse<ClipPlanActionResponse>(response);
}

export async function getSubtitleReview(jobId: string): Promise<SubtitleReviewDocument> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/subtitle-review`, {
    cache: "no-store"
  });
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function reopenSubtitleReview(
  jobId: string
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/reopen`,
    {
      method: "POST"
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function updateSubtitleReviewSegment(
  jobId: string,
  segmentId: string,
  text: string
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/segments/${segmentId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ text })
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function updateSubtitleReviewClipContent(
  jobId: string,
  clipId: string,
  content: {
    title: string;
    hookText: string;
    hookDurationSeconds: number;
  }
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/content`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(content)
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function confirmSubtitleReviewClip(
  jobId: string,
  clipId: string
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/confirm`,
    {
      method: "POST"
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function finalizeSubtitleReview(
  jobId: string
): Promise<SubtitleReviewFinalizeResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/finalize`,
    {
      method: "POST"
    }
  );
  return parseJsonResponse<SubtitleReviewFinalizeResponse>(response);
}
