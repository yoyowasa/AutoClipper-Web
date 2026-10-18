"use client";

import type { SubtitleStructureRequest } from "../../types";
import type { SubtitleBatchUpdate } from "../../subtitleBulkCorrection";
import { type ClipTextTarget } from "../../clipTextStyle";
import type {
  ClipTextStyle,
  ExportType,
  SubtitleReviewClip,
  SubtitleReviewClipFramingUpdateRequest,
  SubtitleReviewDocument,
  SubtitleReviewGap,
  SubtitleReviewSegment,
  TitleHookSuggestion,
  TitleHookSuggestionResponse
} from "../../types";
import { type ClipContentDraft } from "../drafts";
import type { SubtitleReviewState } from "./useSubtitleReviewState";
import type { ResolvedClipTextStyle } from "../../types";
import type { SubtitlePreviewEvent } from "../../subtitlePreview";

export type SubtitleReviewContext = SubtitleReviewState & {
  selectedClip: SubtitleReviewClip | null;
  normalClips: SubtitleReviewClip[];
  shortClips: SubtitleReviewClip[];
  visibleClips: SubtitleReviewClip[];
  hasPendingPreviews: boolean;
  hasReviewMutationInFlight: boolean;
  isEditable: boolean;
  segmentsById: Map<string, SubtitleReviewSegment>;
  selectedSegments: SubtitleReviewSegment[];
  selectedSuggestionSegments: { segmentId: string; text: string; }[];
  selectedSuggestionInputSnapshot: string;
  selectedSuggestionRecord: { response: TitleHookSuggestionResponse; draftHashVerified: boolean; inputSnapshot: string; requestGeneration: number; } | null;
  selectedSuggestionClipId: string;
  selectedSuggestionState: "queued" | "ready" | "failed" | "generating" | null;
  selectedSuggestionInputHash: string | null;
  selectedSuggestionRequestGeneration: number;
  selectedSuggestionsAreStale: boolean;
  bodyDuration: number;
  hookSceneDuration: number;
  clipDuration: number;
  selectedPreviewReady: boolean;
  allPreviewsReady: boolean;
  selectedVideoUrl: string | null;
  selectedPreviewVersion: string;
  retainedLivePreview: { url: string; version: string; } | undefined;
  selectedLiveVideoUrl: string | null;
  selectedLivePreviewVersion: string;
  livePreviewReady: boolean;
  isShowingLivePreview: boolean;
  selectedPlayerVideoUrl: string | null;
  selectedPlayerPreviewVersion: string;
  selectedPlayerReady: boolean;
  playerMediaKey: string;
  selectedPreviewLoadFailed: boolean;
  selectedClipHasDirtySegments: boolean;
  selectedClipContentDraft: ClipContentDraft | null;
  selectedSavedShortFraming: { framingOffsetX: number; framingOffsetY: number; framingZoom: number; } | null;
  selectedShortFramingDraft: SubtitleReviewClipFramingUpdateRequest | null;
  selectedShortFramingDirty: boolean;
  hasDirtyShortFraming: boolean;
  selectedShortPreviewRegenerating: boolean;
  selectedClipHasDirtyContent: boolean;
  hasDirtyClipContent: boolean;
  selectedHookDurationIsValid: boolean;
  hookSuppressionEnd: number;
  isInHookSuppression: boolean;
  absolutePlaybackTime: number;
  activeSegment: SubtitleReviewSegment | null | undefined;
  activeSegmentId: string | null;
  selectedClipTextStyles: { title: ClipTextStyle | null; hook: ClipTextStyle | null; subtitle: ClipTextStyle | null; };
  selectedResolvedClipTextStyles: { title: ResolvedClipTextStyle | null; hook: ResolvedClipTextStyle | null; subtitle: ResolvedClipTextStyle | null; };
  selectedDefaultResolvedClipTextStyles: { title: ResolvedClipTextStyle | null; hook: ResolvedClipTextStyle | null; subtitle: ResolvedClipTextStyle | null; };
  selectedDraftTitleEdited: boolean;
  selectedShortTitleOutputEnabled: boolean;
  subtitlePreviewEventList: SubtitlePreviewEvent[];
  activePreviewSubtitleEvent: SubtitlePreviewEvent | null;
  stylePreviewSubtitleText: string;
  liveHookText: string;
  liveHookEnd: number;
  liveTitleStart: number;
  showLiveHook: boolean;
  showLiveTitle: boolean;
  showLiveSubtitle: boolean;
  beginReviewMutation: () => number;
  endReviewMutation: () => void;
  isCurrentReviewMutation: (generation: number) => boolean;
  selectClip: (clip: SubtitleReviewClip) => void;
  selectClipType: (clipType: ExportType) => void;
  seekToClipTime: (nextTime: number) => void;
  playFromClipStart: () => void;
  seekToSubtitle: (start: number) => void;
  seekToSubtitleGap: (gap: SubtitleReviewGap) => void;
  togglePlayback: () => void;
  skipBy: (seconds: number) => void;
  currentSourceTime: () => number | null;
  openPausedSubtitleDraft: () => void;
  savePausedSubtitleDraft: () => Promise<void>;
  handleVideoTimeUpdate: () => void;
  handleVideoSeeking: () => void;
  retryVideoLoad: () => void;
  handleVideoError: () => void;
  toggleMuted: () => void;
  changeVolume: (nextVolume: number) => void;
  changePlaybackRate: (nextRate: number) => void;
  toggleFullscreen: () => Promise<void>;
  updateDraft: (segmentId: string, text: string) => void;
  saveBulkCorrection: (updates: SubtitleBatchUpdate[]) => Promise<void>;
  updateClipContentDraft: (clipId: string, update: Partial<ClipContentDraft>) => void;
  updateClipTextStyle: (target: ClipTextTarget, style: ClipTextStyle | null) => void;
  changeSelectedShortFraming: (update: Partial<SubtitleReviewClipFramingUpdateRequest>) => SubtitleReviewClipFramingUpdateRequest | null;
  saveSelectedShortFraming: (clipId: string, framing: SubtitleReviewClipFramingUpdateRequest) => Promise<boolean>;
  saveShortBannerSettings: (shortLayout: SubtitleReviewDocument["shortLayout"], shortTopBannerEnabled: boolean, shortBottomBannerEnabled: boolean, assets?: { shortTopBannerAssetId?: string; shortBottomBannerAssetId?: string; characterPresetName?: string; }) => Promise<boolean>;
  generateTitleHookSuggestions: (forceRegenerate: boolean) => Promise<void>;
  applyTitleHookSuggestion: (suggestion: TitleHookSuggestion) => void;
  copyPostField: (field: string, value: string) => Promise<void>;
  clearSelectedHook: () => void;
  previewTitleHookSuggestion: (suggestion: TitleHookSuggestion) => void;
  retrySelectedPreview: () => Promise<void>;
  saveHookScene: (start: number | null, end: number | null) => Promise<void>;
  saveSubtitleStructure: (request: SubtitleStructureRequest) => Promise<boolean>;
  confirmSelectedClip: () => Promise<void>;
  startRendering: () => Promise<void>;
  returnToBoundaryEditor: () => Promise<void>;
  returnToClipPlan: () => Promise<void>;
};

export type SubtitleReviewViewContext = SubtitleReviewContext & { review: SubtitleReviewDocument; allConfirmed: boolean };
