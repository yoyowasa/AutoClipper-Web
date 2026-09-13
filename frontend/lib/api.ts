import type {
  ClipTextStyle,
  ClipPlanActionResponse,
  ClipPlanBoundaryUpdateRequest,
  ClipPlanClipCreateRequest,
  ClipPlanDocument,
  ClipPlanHookSceneUpdateRequest,
  ClipPlanReselectionRequest,
  ClipPlanTypeUpdateRequest,
  ClipPlanTranscriptSegment,
  ClipSettings,
  CompletedVideoReeditResponse,
  JobCreateResponse,
  JobResultsResponse,
  JobStatusResponse,
  PostTitleCandidate,
  StorageCleanupResponse,
  StorageStatusResponse,
  SubtitleReviewDocument,
  SubtitleReviewClipFramingUpdateRequest,
  SubtitleReviewConvertToShortRequest,
  SubtitleReviewFinalizeResponse,
  SubtitleReviewShortBannerSettings,
  ThumbnailRegenerationResponse,
  TitleHookSuggestionResponse,
  VideoUploadResponse,
  YouTubePostingProfile,
  YouTubePostingProfileDocument
} from "./types";
import type {
  SubtitleStylePresetDocument,
  SubtitleStylePresetSlots
} from "./subtitleStylePresets";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function thumbnailCopyRequest(exportId: string, generate = false): Promise<import("./types").ThumbnailCopyState> {
  return parseJsonResponse(await fetch(`${API_BASE_URL}/api/exports/${exportId}/thumbnail/copy${generate ? "?force=true" : ""}`,
    { method: generate ? "POST" : "GET", cache: "no-store" }));
}

export async function prepareThumbnailPreview(exportId: string, signal: AbortSignal, force = false): Promise<{
  state: "queued" | "ready" | "failed"; frameKey: string; error?: string;
}> {
  return parseJsonResponse(await fetch(`${API_BASE_URL}/api/exports/${exportId}/thumbnail/preview/prepare?force=${force}`, {
    method: "POST", signal, cache: "no-store",
  }));
}

export async function renderThumbnailPreview(exportId: string, draft: {
  frameKey: string; text: import("./types").ThumbnailCopyText; textStyles: import("./types").ThumbnailTextStyles;
}, signal: AbortSignal): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/exports/${exportId}/thumbnail/preview`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft), signal, cache: "no-store",
  });
  if (!response.ok) await parseJsonResponse(response);
  return response.blob();
}

export async function editSubtitleStructure(
  jobId: string, request: import("./types").SubtitleStructureRequest,
): Promise<SubtitleReviewDocument> {
  return parseJsonResponse<SubtitleReviewDocument>(await fetch(`${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/segment-structure`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
  }));
}

export async function updateSubtitleReviewSegments(
  jobId: string, segments: Array<{ segmentId: string; before: string; text: string }>,
): Promise<SubtitleReviewDocument> {
  return parseJsonResponse<SubtitleReviewDocument>(await fetch(`${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/segments`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ segments }),
  }));
}

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

export function toBrowserApiUrl(pathOrUrl: string): string {
  let apiPath = pathOrUrl;
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    const url = new URL(pathOrUrl);
    apiPath = `${url.pathname}${url.search}`;
  }
  if (!apiPath.startsWith("/api/")) {
    return toApiUrl(pathOrUrl);
  }

  const queryIndex = apiPath.indexOf("?");
  const pathname = queryIndex >= 0 ? apiPath.slice(0, queryIndex) : apiPath;
  const search = queryIndex >= 0 ? apiPath.slice(queryIndex) : "";
  const exportDownload = pathname.match(/^\/api\/exports\/([^/]+)\/download$/);
  if (exportDownload) {
    return `/backend-api/exports/${exportDownload[1]}/video.mp4${search}`;
  }
  const zipDownload = pathname.match(/^\/api\/jobs\/([^/]+)\/download\.zip$/);
  if (zipDownload) {
    return `/backend-api/jobs/${zipDownload[1]}/archive.zip${search}`;
  }
  return `/backend-api/${apiPath.slice("/api/".length)}`;
}

export async function getStorageStatus(): Promise<StorageStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/storage/status`, {
    cache: "no-store"
  });
  return parseJsonResponse<StorageStatusResponse>(response);
}

export async function cleanupExpiredStorage(): Promise<StorageCleanupResponse> {
  const response = await fetch(`${API_BASE_URL}/api/storage/cleanup`, {
    method: "POST",
    headers: {
      "X-AutoClipper-Action": "storage-cleanup"
    }
  });
  return parseJsonResponse<StorageCleanupResponse>(response);
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
  onProgress?: (percentage: number) => void,
  heatmap?: File | null
): Promise<VideoUploadResponse> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);
    if (heatmap) {
      body.append("heatmap", heatmap);
    }

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

export function reopenCompletedVideo(
  file: File,
  onProgress?: (percentage: number) => void
): Promise<CompletedVideoReeditResponse> {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);

    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE_URL}/api/jobs/reedit-upload`);
    request.responseType = "json";
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress?.(100);
        resolve(request.response as CompletedVideoReeditResponse);
        return;
      }
      reject(
        new Error(
          apiErrorMessage(
            request.response,
            `${request.status} ${request.statusText || "Re-edit upload failed"}`
          )
        )
      );
    });
    request.addEventListener("error", () => {
      reject(new Error("再編集用MP4を照合できませんでした。Backendへ接続できません。"));
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

export async function updateClipPlanType(
  jobId: string,
  clipId: string,
  request: ClipPlanTypeUpdateRequest
): Promise<ClipPlanDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/clip-plan/clips/${clipId}/type`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(request)
    }
  );
  return parseJsonResponse<ClipPlanDocument>(response);
}

export async function updateClipPlanHookScene(
  jobId: string,
  clipId: string,
  hookScene: ClipPlanHookSceneUpdateRequest
): Promise<ClipPlanActionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/clip-plan/clips/${clipId}/hook-scene`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(hookScene)
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
    titleStyle: ClipTextStyle | null;
    hookStyle: ClipTextStyle | null;
    subtitleStyle: ClipTextStyle | null;
    subtitleStyles?: import("./types").SubtitleStyleOverride[];
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

export async function getYouTubePostingProfile(): Promise<YouTubePostingProfileDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/preferences/youtube-posting-profile`,
    { cache: "no-store" }
  );
  return parseJsonResponse<YouTubePostingProfileDocument>(response);
}

export async function saveYouTubePostingProfile(
  profile: YouTubePostingProfile
): Promise<YouTubePostingProfileDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/preferences/youtube-posting-profile`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version: 1, profile })
    }
  );
  return parseJsonResponse<YouTubePostingProfileDocument>(response);
}

export async function updateSubtitleReviewClipFraming(
  jobId: string,
  clipId: string,
  framing: SubtitleReviewClipFramingUpdateRequest
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/framing`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(framing)
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function createClipReedit(
  jobId: string,
  clipId: string
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/clips/${clipId}/reedit`,
    { method: "POST" }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function convertSubtitleReviewClipToShort(
  jobId: string,
  clipId: string,
  request: SubtitleReviewConvertToShortRequest
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/convert-to-short`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(request)
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function getTitleHookSuggestions(
  jobId: string,
  clipId: string
): Promise<TitleHookSuggestionResponse | null> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/title-hook-suggestions`,
    { cache: "no-store" }
  );
  if (response.status === 404) {
    return null;
  }
  return parseJsonResponse<TitleHookSuggestionResponse>(response);
}

export async function requestTitleHookSuggestions(
  jobId: string,
  clipId: string,
  request: {
    segments: Array<{ segmentId: string; text: string }>;
    forceRegenerate: boolean;
  }
): Promise<TitleHookSuggestionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/title-hook-suggestions`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(request)
    }
  );
  return parseJsonResponse<TitleHookSuggestionResponse>(response);
}

export async function createClipPlanClip(
  jobId: string,
  clip: ClipPlanClipCreateRequest
): Promise<ClipPlanDocument> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/clip-plan/clips`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(clip)
  });
  return parseJsonResponse<ClipPlanDocument>(response);
}

export async function updateManualClipPlanClip(
  jobId: string,
  clipId: string,
  boundary: ClipPlanBoundaryUpdateRequest
): Promise<ClipPlanDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/clip-plan/clips/${clipId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(boundary)
    }
  );
  return parseJsonResponse<ClipPlanDocument>(response);
}

export async function deleteClipPlanClip(
  jobId: string,
  clipId: string
): Promise<ClipPlanDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/clip-plan/clips/${clipId}`,
    {
      method: "DELETE"
    }
  );
  return parseJsonResponse<ClipPlanDocument>(response);
}

export async function retrySubtitleReviewPreview(
  jobId: string,
  clipId: string
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/preview/retry`,
    {
      method: "POST"
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function retryJob(jobId: string): Promise<JobCreateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/retry`, {
    method: "POST"
  });
  return parseJsonResponse<JobCreateResponse>(response);
}

export async function regenerateExportThumbnail(
  exportId: string,
  request: {
    frameSeconds: number;
    subjectAnchorX: number;
    advanceFrame?: boolean;
    cropMode?: "standard" | "close";
    textStyles?: import("./types").ThumbnailTextStyles;
    text?: import("./types").ThumbnailCopyText;
  }
): Promise<ThumbnailRegenerationResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/exports/${exportId}/thumbnail/regenerate`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(request)
    }
  );
  return parseJsonResponse<ThumbnailRegenerationResponse>(response);
}

export async function updateSubtitleReviewShortBannerSettings(
  jobId: string,
  settings: SubtitleReviewShortBannerSettings
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/settings`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(settings)
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function applySubtitleReviewClip(
  jobId: string,
  clipId: string,
  content: {
    title: string;
    publicationTitle: string;
    titleCandidates: PostTitleCandidate[];
    recommendedTitleId: string | null;
    selectedTitleId: string | null;
    youtubeDescription: string;
    youtubeHashtags: string[];
    youtubeTags: string[];
    descriptionEvidenceSegmentIds: string[];
    postMetadataSource: string | null;
    postMetadataRevisionHash: string | null;
    hookText: string;
    hookDurationSeconds: number;
    hookSceneStart: number | null;
    hookSceneEnd: number | null;
    thumbnailKicker: string;
    thumbnailLine1: string;
    thumbnailLine2: string;
    thumbnailFrameSeconds: number | null;
    titleStyle: ClipTextStyle | null;
    hookStyle: ClipTextStyle | null;
    subtitleStyle: ClipTextStyle | null;
    segments: Array<{ segmentId: string; text: string }>;
    subtitleStyles?: import("./types").SubtitleStyleOverride[];
  }
): Promise<SubtitleReviewDocument> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/apply`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(content)
    }
  );
  return parseJsonResponse<SubtitleReviewDocument>(response);
}

export async function updateSubtitleReviewHookScene(
  jobId: string,
  clipId: string,
  hookScene: ClipPlanHookSceneUpdateRequest
): Promise<ClipPlanActionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/jobs/${jobId}/subtitle-review/clips/${clipId}/hook-scene`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(hookScene)
    }
  );
  return parseJsonResponse<ClipPlanActionResponse>(response);
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
