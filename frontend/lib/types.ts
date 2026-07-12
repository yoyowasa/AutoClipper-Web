export type JobStatus =
  | "uploaded"
  | "queued"
  | "probing"
  | "extracting_audio"
  | "transcribing"
  | "correcting_subtitles"
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
  ensureSelectedOpenAIScored?: boolean;
  openaiFinalistScoringLimit?: number;
  enableBoundaryRefinement: boolean;
  boundaryLeadingPaddingSeconds: number;
  boundaryTrailingPaddingSeconds: number;
  maxBoundaryExpansionSeconds: number;
  allowBoundaryExpansionBeyondMaxDuration: boolean;
  burnSubtitles: boolean;
  maxCharsPerLineShort: number;
  maxCharsPerLineNormal: number;
  maxLines: number;
  minSubtitleDuration: number;
  maxSubtitleDuration: number;
  minGapBetweenSubtitles: number;
  subtitleFontName?: string;
  subtitleFontSize?: number;
  subtitleOutline?: number;
  subtitleLowerMargin?: number;
  subtitleAlignment?: number;
  shortLayout: "auto" | "center_crop" | "blur_background";
  shortOverlayTitleMode: "auto" | "always" | "high_quality_only" | "never";
  enableTranscriptPostProcessing?: boolean;
  transcriptNormalizeUnicode?: boolean;
  transcriptNormalizeWhitespace?: boolean;
  transcriptNormalizePunctuation?: boolean;
  useDefaultTranscriptDictionary?: boolean;
  transcriptReplacements?: Record<string, string>;
  whisperModelSize: "base" | "small" | "medium" | "large-v3";
  transcriptionLanguage: "auto" | "ja";
  subtitleCorrectionMode: "off" | "openai";
  subtitleCorrectionScope: "all" | "suspicious";
  subtitleCorrectionSuspicionThreshold: number;
  subtitleCorrectionModel: string;
  subtitleCorrectionMinConfidence: number;
  subtitleCorrectionBatchSize: number;
  subtitleCorrectionContextSegments: number;
  subtitleCorrectionFallbackEnabled: boolean;
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
  candidateId: string | null;
  title: string;
  titleSource: string | null;
  duration: number;
  score: number;
  finalScore: number | null;
  ruleScore: number | null;
  aiScore: number | null;
  selectionReason: string | null;
  belowQualityThreshold: boolean | null;
  qualityWarning: string | null;
  openaiScoreSource: string | null;
  boundaryRefined: boolean | null;
  overlayTitleExpected: boolean | null;
  overlayTitleRendered: boolean | null;
  start: number | null;
  end: number | null;
  originalStart: number | null;
  originalEnd: number | null;
  refinedStart: number | null;
  refinedEnd: number | null;
  resolution: {
    width?: number | null;
    height?: number | null;
    source?: string | null;
  } | null;
  auditWarnings: string[];
  subtitlePath: string | null;
  subtitleUrl: string | null;
  metadataPath: string | null;
  metadataUrl: string | null;
  videoUrl: string;
  downloadUrl: string;
};

export type JobAuditSummary = {
  available: boolean;
  generatedNormalCount: number | null;
  generatedShortCount: number | null;
  clipsRequiringHumanVisualInspectionCount: number | null;
  warningsByType: Record<string, Record<string, number>>;
  warningCounts: Record<string, number>;
};

export type JobResultsResponse = {
  jobId: string;
  zipDownloadUrl: string;
  auditSummary: JobAuditSummary | null;
  normalClips: ResultExportItem[];
  shorts: ResultExportItem[];
};
