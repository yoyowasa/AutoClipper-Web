export type JobStatus =
  | "uploaded"
  | "queued"
  | "probing"
  | "extracting_audio"
  | "transcribing"
  | "detecting_scenes"
  | "generating_candidates"
  | "scoring_candidates"
  | "selecting_clips"
  | "rendering_normal_clips"
  | "rendering_shorts"
  | "packaging_zip"
  | "completed"
  | "failed";

export type ExportType = "normal" | "short";

export type ClipSettings = {
  mode: "fast" | "high_quality";
  profile: "auto" | "talk" | "gameplay" | "lecture";
  normalClipCount: number;
  shortCount: number;
  normalMinDuration: number;
  normalMaxDuration: number;
  shortMinDuration: number;
  shortMaxDuration: number;
  selectionPolicy: "fill_requested" | "strict_quality";
  crossTypeOverlapDedupe: boolean;
  burnSubtitles: boolean;
  shortLayout: "auto" | "center_crop" | "blur_background";
};

export type VideoUploadResponse = {
  videoId: string;
  filename: string;
};

export type JobCreateResponse = {
  jobId: string;
  status: JobStatus;
};

export type JobError = {
  code: string;
  message: string;
};

export type JobStatusResponse = {
  id: string;
  status: JobStatus;
  progress: number;
  currentStep: string;
  details: Record<string, unknown>;
  error: JobError | null;
};

export type ResultExportItem = {
  id: string;
  type: ExportType;
  title: string;
  duration: number;
  score: number;
  videoUrl: string;
  downloadUrl: string;
};

export type JobResultsResponse = {
  jobId: string;
  zipDownloadUrl: string;
  normalClips: ResultExportItem[];
  shorts: ResultExportItem[];
};
