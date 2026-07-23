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
  | "awaiting_subtitle_review"
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
  requireSubtitleReview: boolean;
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
  subtitlePrimaryColor?: string;
  subtitleOutlineColor?: string;
  shortSubtitleFontName?: string;
  shortSubtitleFontSize?: number;
  shortSubtitleOutline?: number;
  shortSubtitleLowerMargin?: number;
  shortSubtitleAlignment?: number;
  shortSubtitlePrimaryColor?: string;
  shortSubtitleOutlineColor?: string;
  normalSubtitleFontName?: string;
  normalSubtitleFontSize?: number;
  normalSubtitleOutline?: number;
  normalSubtitleLowerMargin?: number;
  normalSubtitleAlignment?: number;
  normalSubtitlePrimaryColor?: string;
  normalSubtitleOutlineColor?: string;
  shortLayout: "auto" | "center_crop" | "blur_background";
  shortOverlayTitleMode: "auto" | "always" | "high_quality_only" | "never";
  enableTranscriptPostProcessing?: boolean;
  transcriptNormalizeUnicode?: boolean;
  transcriptNormalizeWhitespace?: boolean;
  transcriptNormalizePunctuation?: boolean;
  useDefaultTranscriptDictionary?: boolean;
  transcriptReplacements?: Record<string, string>;
  whisperModelSize: "base" | "small" | "medium" | "large-v3" | "turbo";
  transcriptionLanguage: "auto" | "ja";
  transcriptionDevice: "auto" | "cpu" | "cuda";
  transcriptionComputeType: "auto" | "int8" | "float16" | "int8_float16";
  subtitleCorrectionMode: "off" | "openai";
  subtitleCorrectionScope: "all" | "suspicious";
  transcriptCorrectionGlossary?: string[];
  subtitleCorrectionSuspicionThreshold: number;
  subtitleCorrectionModel: string;
  subtitleCorrectionReasoningEffort:
    | "default"
    | "none"
    | "minimal"
    | "low"
    | "medium"
    | "high"
    | "xhigh"
    | "max";
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

export type SubtitleReviewSegment = {
  id: string;
  index: number;
  start: number;
  end: number;
  originalText: string;
  text: string;
  confidence: number | null;
  edited: boolean;
  affectedClipIds: string[];
};

export type SubtitleReviewClip = {
  id: string;
  type: ExportType;
  title: string;
  start: number;
  end: number;
  duration: number;
  segmentIds: string[];
  confirmed: boolean;
  editedSegmentCount: number;
};

export type SubtitleReviewDocument = {
  version: number;
  jobId: string;
  state: "awaiting_review" | "render_queued" | "rendering" | "completed";
  sourceVideoUrl: string;
  clips: SubtitleReviewClip[];
  segments: SubtitleReviewSegment[];
  confirmedClipCount: number;
  totalClipCount: number;
  editedSegmentCount: number;
  createdAt: string;
  updatedAt: string;
};

export type SubtitleReviewFinalizeResponse = {
  jobId: string;
  status: JobStatus;
};
