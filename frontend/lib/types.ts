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
  | "reselecting_clips"
  | "preparing_clip_review"
  | "awaiting_manual_edit"
  | "awaiting_clip_review"
  | "preparing_subtitle_review"
  | "awaiting_subtitle_review"
  | "rendering_normal_clips"
  | "rendering_shorts"
  | "packaging_zip"
  | "completed"
  | "failed";

export type ExportType = "normal" | "short";
export type WorkflowMode = "automatic" | "manual";
export type AutomationMode = "manual" | "shadow" | "guarded" | "auto";
export type AutomationGateState =
  | "passed"
  | "needs_attention"
  | "fallback_manual"
  | "evaluating";
export type AutomationGateStage = "selection" | "content" | "post_render";
export type AutomationGateOutcome = "pass" | "fail" | "unknown";
export type PostTitleIntent = "factual" | "engagement" | "concise";

export type PostTitleCandidate = {
  id: string;
  title: string;
  intent: PostTitleIntent;
  reason: string;
  evidenceSegmentIds: string[];
};

export type YouTubePostingProfile = {
  performerName: string;
  affiliation: string;
  baseHashtags: string[];
  shortHashtags: string[];
  baseTags: string[];
};

export type YouTubePostingProfileDocument = {
  version: 1;
  profile: YouTubePostingProfile;
};
export type ManualSubtitleMode = "auto" | "none" | "manual";

export type ClipSelectionPreset =
  | "auto"
  | "highlights"
  | "funny"
  | "important"
  | "emotional"
  | "informative";

export type ClipTimeRange = {
  startSeconds: number | null;
  endSeconds: number | null;
};

export type ClipSettings = {
  workflowMode: WorkflowMode;
  automationMode: AutomationMode;
  manualSubtitleMode: ManualSubtitleMode;
  mode: "fast" | "high_quality";
  profile: "auto" | "talk" | "gameplay" | "lecture";
  normalClipCount: number;
  shortCount: number;
  normalMinDuration: number;
  normalMaxDuration: number;
  shortMinDuration: number;
  shortMaxDuration: number;
  normalClipSelectionPreset: ClipSelectionPreset;
  shortClipSelectionPreset: ClipSelectionPreset;
  normalClipGuidance: string;
  shortClipGuidance: string;
  normalClipTimeRanges: ClipTimeRange[];
  shortClipTimeRanges: ClipTimeRange[];
  excludeIntroOutro: boolean;
  excludePromotionalContent: boolean;
  selectionPolicy: "fill_requested" | "strict_quality";
  crossTypeOverlapDedupe: boolean;
  heatmapIntervalMode: boolean;
  initialSelectionProvider: "legacy" | "codex";
  useOpenAIScoring: boolean;
  openaiCandidateLimit: number;
  openaiModel: string;
  openaiFallbackToRuleScore: boolean;
  ensureSelectedOpenAIScored?: boolean;
  openaiFinalistScoringLimit?: number;
  enableBoundaryRefinement: boolean;
  boundaryLeadingPaddingSeconds: number;
  boundaryTrailingPaddingSeconds: number;
  maxBoundaryExpansionSeconds: number;
  allowBoundaryExpansionBeyondMaxDuration: boolean;
  burnSubtitles: boolean;
  requireClipPlanReview: boolean;
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
  shortSubtitleXPercent?: number;
  shortSubtitleYPercent?: number;
  shortSubtitlePrimaryColor?: string;
  shortSubtitleOutlineColor?: string;
  normalSubtitleFontName?: string;
  normalSubtitleFontSize?: number;
  normalSubtitleOutline?: number;
  normalSubtitleLowerMargin?: number;
  normalSubtitleAlignment?: number;
  normalSubtitleXPercent?: number;
  normalSubtitleYPercent?: number;
  normalSubtitlePrimaryColor?: string;
  normalSubtitleOutlineColor?: string;
  shortLayout: "auto" | "face_tracking_crop" | "center_crop" | "blur_background";
  shortOverlayTitleMode: "auto" | "always" | "high_quality_only" | "never";
  shortTopBannerEnabled: boolean;
  shortBottomBannerEnabled: boolean;
  enableTranscriptPostProcessing?: boolean;
  transcriptNormalizeUnicode?: boolean;
  transcriptNormalizeWhitespace?: boolean;
  transcriptNormalizePunctuation?: boolean;
  useDefaultTranscriptDictionary?: boolean;
  transcriptReplacements?: Record<string, string>;
  whisperModelSize: "base" | "small" | "medium" | "large-v3" | "turbo";
  transcriptionLanguage: "ja";
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
  youtubeSourceTitle: string;
  youtubeSourceUrl: string;
  youtubePostingProfile: YouTubePostingProfile;
};

export type VideoUploadResponse = {
  videoId: string;
  filename: string;
};

export type StorageStatusResponse = {
  storageBytes: number;
  storageLimitBytes: number;
  diskFreeBytes: number;
  diskTotalBytes: number;
  diskFreePercent: number;
  warning: boolean;
  reasons: string[];
  cleanupEligibleJobs: number;
  cleanupEligibleVideos: number;
};

export type StorageCleanupResponse = {
  removedJobs: number;
  removedVideos: number;
  removedFiles: number;
  reclaimedBytes: number;
  errors: string[];
};

export type CompletedVideoReeditResponse = {
  jobId: string;
  exportId: string;
  matchedClipId: string | null;
  clipType: "normal" | "short";
  title: string;
  reviewState: string;
};

export type JobCreateResponse = {
  jobId: string;
  status: JobStatus;
};

export type JobError = {
  code: string;
  message: string;
};

export type JobStatusDetails = Record<string, unknown> & {
  automationMode?: AutomationMode;
  automationEffectiveMode?: AutomationMode;
  automationGateState?: AutomationGateState;
  automationGateStage?: AutomationGateStage;
  automationGateOutcome?: AutomationGateOutcome;
  automationGateReasonCodes?: string[];
  automationGateAttentionClipIds?: string[];
  automationGateAutoPassedClips?: number;
  automationGateAttentionClips?: number;
};

export type JobStatusResponse = {
  id: string;
  status: JobStatus;
  progress: number;
  currentStep: string;
  details: JobStatusDetails;
  error: JobError | null;
};

export type ResultExportItem = {
  id: string;
  type: ExportType;
  candidateId: string | null;
  title: string;
  titleSource: string | null;
  titleCandidates: PostTitleCandidate[];
  recommendedTitleId: string | null;
  selectedTitleId: string | null;
  youtubeDescription: string;
  youtubeHashtags: string[];
  youtubeTags: string[];
  descriptionEvidenceSegmentIds: string[];
  postMetadataSource: string | null;
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
  thumbnailUrl: string | null;
  thumbnailDownloadUrl: string | null;
  thumbnailStatus: "not_generated" | "ready" | "failed" | null;
  thumbnailFilename: string | null;
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
  canReopenForEditing: boolean;
  reeditSourceJobId: string | null;
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

export type ClipTextFontPreset =
  | "sans"
  | "sans_bold"
  | "noto_black"
  | "heavy"
  | "mplus_extrabold"
  | "mplus_rounded_extrabold"
  | "chikara"
  | "dela_gothic"
  | "corporate_logo"
  | "serif"
  | "mono";

export type ClipTextStyle = {
  fontPreset: ClipTextFontPreset | null;
  fontName: string | null;
  bold: boolean | null;
  fontSize: number;
  primaryColor: string;
  outlineColor: string;
  outlineWidth: number;
  xPercent: number;
  yPercent: number;
  positionMode: "explicit" | "layout";
};

export type ResolvedClipTextStyle = {
  fontPreset: ClipTextFontPreset | null;
  fontName: string;
  fontSize: number;
  primaryColor: string;
  outlineColor: string;
  outlineWidth: number;
  shadow: number;
  bold: boolean;
  alignment: number;
  marginX: number;
  marginV: number;
  xPercent: number;
  yPercent: number;
  positionMode: "explicit" | "layout";
  positionOverride: boolean;
};

export type SubtitleReviewClip = {
  id: string;
  type: ExportType;
  title: string;
  publicationTitle?: string | null;
  titleCandidates: PostTitleCandidate[];
  recommendedTitleId: string | null;
  selectedTitleId: string | null;
  youtubeDescription: string;
  youtubeHashtags: string[];
  youtubeTags: string[];
  descriptionEvidenceSegmentIds: string[];
  postMetadataSource: string | null;
  postMetadataRevisionHash: string | null;
  originalTitle: string | null;
  titleEdited: boolean;
  overlayTitleExpected: boolean;
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
  framingOffsetX: number;
  framingOffsetY: number;
  framingZoom: number;
  resolvedTitleStyle: ResolvedClipTextStyle | null;
  resolvedHookStyle: ResolvedClipTextStyle | null;
  resolvedSubtitleStyle: ResolvedClipTextStyle | null;
  resolvedDefaultTitleStyle: ResolvedClipTextStyle | null;
  resolvedDefaultHookStyle: ResolvedClipTextStyle | null;
  resolvedDefaultSubtitleStyle: ResolvedClipTextStyle | null;
  subtitleMaxCharsPerLine: number | null;
  subtitleMaxLines: number | null;
  subtitleMinDurationSeconds: number | null;
  subtitleMaxDurationSeconds: number | null;
  subtitleMinGapSeconds: number | null;
  previewWidth: number | null;
  previewHeight: number | null;
  start: number;
  end: number;
  duration: number;
  previewState: "queued" | "rendering" | "ready" | "failed";
  previewSpecHash: string | null;
  previewError: string | null;
  previewVideoUrl: string | null;
  livePreviewSpecHash: string | null;
  livePreviewVideoUrl: string | null;
  segmentIds: string[];
  confirmed: boolean;
  editedSegmentCount: number;
};

export type SubtitleReviewDocument = {
  version: number;
  jobId: string;
  state: "awaiting_review" | "render_queued" | "rendering" | "completed";
  renderRevision: number;
  reopenedAt: string | null;
  reeditSourceJobId: string | null;
  reeditSourceClipId: string | null;
  sourceVideoUrl: string;
  renderMode: string;
  shortMaxDuration: number;
  shortOverlayTitleMode: "auto" | "always" | "high_quality_only" | "never";
  shortLayout: ClipSettings["shortLayout"];
  shortTopBannerEnabled: boolean;
  shortBottomBannerEnabled: boolean;
  clips: SubtitleReviewClip[];
  segments: SubtitleReviewSegment[];
  confirmedClipCount: number;
  totalClipCount: number;
  editedSegmentCount: number;
  createdAt: string;
  updatedAt: string;
};

export type SubtitleReviewShortBannerSettings = Pick<
  SubtitleReviewDocument,
  "shortLayout" | "shortTopBannerEnabled" | "shortBottomBannerEnabled"
>;

export type SubtitleReviewClipFramingUpdateRequest = Pick<
  SubtitleReviewClip,
  "framingOffsetX" | "framingOffsetY" | "framingZoom"
>;

export type SubtitleReviewFinalizeResponse = {
  jobId: string;
  status: JobStatus;
};

export type SubtitleReviewConvertToShortRequest = {
  startSeconds?: number;
  endSeconds?: number;
};

export type TitleHookSuggestion = {
  id: string;
  intent: PostTitleIntent;
  publicationTitle: string;
  overlayTitle: string;
  hookText: string;
  hookDurationSeconds: number;
  hookSceneStart: number | null;
  hookSceneEnd: number | null;
  thumbnailKicker: string;
  thumbnailLine1: string;
  thumbnailLine2: string;
  thumbnailFrameSeconds: number | null;
  reason: string;
  evidenceSegmentIds: string[];
};

export type TitleHookSuggestionResponse = {
  clipId: string;
  state: "queued" | "generating" | "ready" | "failed";
  inputHash: string | null;
  draftHash?: string | null;
  revisionHash?: string | null;
  model: string | null;
  provider: string | null;
  threadId?: string | null;
  recommendedSuggestionId: string | null;
  youtubeDescription: string;
  hashtags: string[];
  descriptionEvidenceSegmentIds: string[];
  suggestions: TitleHookSuggestion[];
  error: string | null;
  generatedAt: string | null;
};

export type ClipPlanClip = {
  id: string;
  type: ExportType;
  title: string;
  start: number;
  end: number;
  duration: number;
  previewVideoUrl: string | null;
  transcriptExcerpt: string;
  finalScore: number | null;
  ruleScore: number | null;
  aiScore: number | null;
  selectionReason: string | null;
  boundaryRefined: boolean;
  recommendedStart: number | null;
  recommendedEnd: number | null;
  manuallyAdjusted: boolean;
  hookSceneStart: number | null;
  hookSceneEnd: number | null;
};

export type ClipPlanDocument = {
  version: number;
  jobId: string;
  state: "preparing" | "manual_editing" | "awaiting_review" | "reselecting" | "approved";
  revision: number;
  sourceVideoUrl: string;
  editorVideoUrl?: string | null;
  sourceDuration: number | null;
  workflowMode?: WorkflowMode;
  clips: ClipPlanClip[];
  settings: ClipSettings;
  createdAt: string;
  updatedAt: string;
};

export type ClipPlanReselectionRequest = Pick<
  ClipSettings,
  | "normalClipSelectionPreset"
  | "shortClipSelectionPreset"
  | "normalClipGuidance"
  | "shortClipGuidance"
  | "excludeIntroOutro"
  | "excludePromotionalContent"
  | "selectionPolicy"
  | "heatmapIntervalMode"
  | "useOpenAIScoring"
>;

export type ClipPlanActionResponse = {
  jobId: string;
  status: JobStatus;
};

export type ClipPlanBoundaryUpdateRequest = {
  start: number;
  end: number;
};

export type ClipPlanTypeUpdateRequest = {
  type: "normal";
};

export type ClipPlanClipCreateRequest = ClipPlanBoundaryUpdateRequest & {
  type: ExportType;
};

export type ClipPlanHookSceneUpdateRequest = {
  start: number | null;
  end: number | null;
};

export type ClipPlanTranscriptSegment = {
  start: number;
  end: number;
  text: string;
  confidence: number | null;
};
