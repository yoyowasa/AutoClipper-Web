"use client";

import { useParams, useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import type { CorrectionSelection } from "../../subtitleBulkCorrection";
import { type ClipTextTarget } from "../../clipTextStyle";
import type { ExportType, SubtitleReviewDocument, TitleHookSuggestionResponse } from "../../types";
import { readJobId } from "../display";
import { type ClipContentDraft } from "../drafts";
import type { LivePreviewReference } from "../livePlaybackSource";
import { type ShortFramingDrafts } from "../framing";

export function useSubtitleReviewState() {
  const locallyUpdatedReviewRef = useRef<SubtitleReviewDocument | null>(null);
  const [styledSegmentId, setStyledSegmentId] = useState<string | null>(null);
  const params = useParams();
  const router = useRouter();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const currentPlayerMediaRef = useRef<{ clipId: string; key: string } | null>(null);
  const pendingPlayerResumeRef = useRef<{ key: string; time: number; playing: boolean } | null>(null);
  const playerShellRef = useRef<HTMLDivElement | null>(null);
  const subtitleListRef = useRef<HTMLDivElement | null>(null);
  const segmentRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const suggestionPlaybackEndRef = useRef<number | null>(null);
  const suggestionRequestGenerationRef = useRef<Record<string, number>>({});
  const autoSuggestionAttemptedClipIdsRef = useRef<Set<string>>(new Set());
  const reviewRequestGenerationRef = useRef(0);
  const reviewMutationCountRef = useRef(0);
  const shortFramingSaveInFlightRef = useRef<Set<string>>(new Set());
  const lastSavedShortFramingSignatureRef = useRef<Record<string, string>>({});
  const [review, setReview] = useState<SubtitleReviewDocument | null>(null);
  const [selectedClipId, setSelectedClipId] = useState("");
  const [activeClipType, setActiveClipType] = useState<ExportType>("normal");
  const [lastSelectedClipIds, setLastSelectedClipIds] = useState<
    Record<ExportType, string>
  >({ normal: "", short: "" });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [clipContentDrafts, setClipContentDrafts] = useState<
    Record<string, ClipContentDraft>
  >({});
  const [dirtySegmentIds, setDirtySegmentIds] = useState<Set<string>>(new Set());
  const [retryingPreviewClipId, setRetryingPreviewClipId] = useState<
    string | null
  >(null);
  const [isSavingShortBannerSettings, setIsSavingShortBannerSettings] =
    useState(false);
  const [savingShortFramingClipId, setSavingShortFramingClipId] = useState<
    string | null
  >(null);
  const [shortFramingDrafts, setShortFramingDrafts] =
    useState<ShortFramingDrafts>({});
  const [isUpdatingHookScene, setIsUpdatingHookScene] = useState(false);
  const [confirmingClipId, setConfirmingClipId] = useState<string | null>(null);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [isReopeningBoundaries, setIsReopeningBoundaries] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [isPlayerReady, setIsPlayerReady] = useState(false);
  const [videoLoadSeconds, setVideoLoadSeconds] = useState(0);
  const [previewLoadFailedClipIds, setPreviewLoadFailedClipIds] = useState<Set<string>>(
    new Set()
  );
  const [clipTime, setClipTime] = useState(0);
  const [pausedSubtitleDraft, setPausedSubtitleDraft] = useState<{
    clipId: string; start: number; end: number; text: string;
  } | null>(null);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [openedFromReupload, setOpenedFromReupload] = useState(false);
  const [selectedTextStyleTarget, setSelectedTextStyleTarget] =
    useState<ClipTextTarget>("title");
  const [showSavedPreview, setShowSavedPreview] = useState(false);
  const [titleHookSuggestionRecords, setTitleHookSuggestionRecords] = useState<
    Record<
      string,
      {
        response: TitleHookSuggestionResponse;
        draftHashVerified: boolean;
        inputSnapshot: string;
        requestGeneration: number;
      }
    >
  >({});
  const [requestingSuggestionClipId, setRequestingSuggestionClipId] = useState<
    string | null
  >(null);
  const [autoGeneratingSuggestionClipIds, setAutoGeneratingSuggestionClipIds] =
    useState<Set<string>>(new Set());
  const [previewingSuggestionId, setPreviewingSuggestionId] = useState<
    string | null
  >(null);
  const [copiedPostField, setCopiedPostField] = useState<string | null>(null);
  const [bulkCorrectionSelection, setBulkCorrectionSelection] = useState<CorrectionSelection | null>(null);
  const [isSavingBulkCorrection, setIsSavingBulkCorrection] = useState(false);
  const [isSavingStructure, setIsSavingStructure] = useState(false);
  const [retainedLivePreviews, setRetainedLivePreviews] = useState<
    Record<string, LivePreviewReference>
  >({});
  const [segmentCursor, setSegmentCursor] = useState<{ id: string; offset: number } | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<"content" | "style">("content");
  const [suggestionHydrationRetryVersion, setSuggestionHydrationRetryVersion] =
    useState(0);
  return { locallyUpdatedReviewRef, styledSegmentId, setStyledSegmentId, params, router, jobId, videoRef, currentPlayerMediaRef, pendingPlayerResumeRef, playerShellRef, subtitleListRef, segmentRowRefs, suggestionPlaybackEndRef, suggestionRequestGenerationRef, autoSuggestionAttemptedClipIdsRef, reviewRequestGenerationRef, reviewMutationCountRef, shortFramingSaveInFlightRef, lastSavedShortFramingSignatureRef, review, setReview, selectedClipId, setSelectedClipId, activeClipType, setActiveClipType, lastSelectedClipIds, setLastSelectedClipIds, drafts, setDrafts, clipContentDrafts, setClipContentDrafts, dirtySegmentIds, setDirtySegmentIds, retryingPreviewClipId, setRetryingPreviewClipId, isSavingShortBannerSettings, setIsSavingShortBannerSettings, savingShortFramingClipId, setSavingShortFramingClipId, shortFramingDrafts, setShortFramingDrafts, isUpdatingHookScene, setIsUpdatingHookScene, confirmingClipId, setConfirmingClipId, isFinalizing, setIsFinalizing, isReopeningBoundaries, setIsReopeningBoundaries, isPlaying, setIsPlaying, isBuffering, setIsBuffering, isPlayerReady, setIsPlayerReady, videoLoadSeconds, setVideoLoadSeconds, previewLoadFailedClipIds, setPreviewLoadFailedClipIds, clipTime, setClipTime, pausedSubtitleDraft, setPausedSubtitleDraft, volume, setVolume, isMuted, setIsMuted, playbackRate, setPlaybackRate, error, setError, openedFromReupload, setOpenedFromReupload, selectedTextStyleTarget, setSelectedTextStyleTarget, showSavedPreview, setShowSavedPreview, titleHookSuggestionRecords, setTitleHookSuggestionRecords, requestingSuggestionClipId, setRequestingSuggestionClipId, autoGeneratingSuggestionClipIds, setAutoGeneratingSuggestionClipIds, previewingSuggestionId, setPreviewingSuggestionId, copiedPostField, setCopiedPostField, bulkCorrectionSelection, setBulkCorrectionSelection, isSavingBulkCorrection, setIsSavingBulkCorrection, isSavingStructure, setIsSavingStructure, retainedLivePreviews, setRetainedLivePreviews, segmentCursor, setSegmentCursor, workspaceTab, setWorkspaceTab, suggestionHydrationRetryVersion, setSuggestionHydrationRetryVersion };
}

export type SubtitleReviewState = ReturnType<typeof useSubtitleReviewState>;
