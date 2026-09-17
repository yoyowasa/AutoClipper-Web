"use client";

import Link from "next/link";
import { ReviewCharacterPreset } from "../../../../components/ReviewCharacterPreset";
import { ShortFramingWorkspace } from "../../../../components/ShortFramingWorkspace";
import { SubtitleSegmentActions } from "../../../../components/SubtitleSegmentActions";
import { editSubtitleStructure } from "../../../../lib/api";
import type { SubtitleStructureRequest } from "../../../../lib/types";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { ClipHookSceneEditor } from "../../../../components/ClipHookSceneEditor";
import {
  ClipTextOverlay,
  ClipTextStyleEditor
} from "../../../../components/ClipTextStyleEditor";
import { TitleHookSuggestionPanel } from "../../../../components/TitleHookSuggestionPanel";
import { SubtitleBulkCorrection } from "../../../../components/SubtitleBulkCorrection";
import type { CorrectionSelection, SubtitleBatchUpdate } from "../../../../lib/subtitleBulkCorrection";
import {
  applySubtitleReviewClip,
  finalizeSubtitleReview,
  getJobStatus,
  getSubtitleReview,
  getTitleHookSuggestions,
  requestTitleHookSuggestions,
  retrySubtitleReviewPreview,
  toApiUrl,
  updateSubtitleReviewClipFraming,
  updateSubtitleReviewHookScene,
  updateSubtitleReviewShortBannerSettings,
  updateSubtitleReviewSegments
} from "../../../../lib/api";
import { type ClipTextTarget } from "../../../../lib/clipTextStyle";
import { subtitlePreviewEvents } from "../../../../lib/subtitlePreview";
import type {
  ClipTextStyle,
  ExportType,
  PostTitleCandidate,
  SubtitleReviewClip,
  SubtitleReviewClipFramingUpdateRequest,
  SubtitleReviewDocument,
  SubtitleReviewSegment,
  TitleHookSuggestion,
  TitleHookSuggestionResponse
} from "../../../../lib/types";
import {
  descriptionWithHashtags,
  postMetadataApplyPayload,
  tagsFromText,
  youtubeTagsText
} from "../../../../lib/youtubePosting";

function readJobId(param: string | string[] | undefined): string {
  if (Array.isArray(param)) {
    return param[0] ?? "";
  }
  return param ?? "";
}

function formatTime(value: number): string {
  const safeValue = Math.max(0, value);
  const hours = Math.floor(safeValue / 3600);
  const minutes = Math.floor((safeValue % 3600) / 60);
  const seconds = safeValue % 60;
  const secondText = seconds.toFixed(1).padStart(4, "0");
  return hours > 0
    ? `${hours}:${minutes.toString().padStart(2, "0")}:${secondText}`
    : `${minutes}:${secondText}`;
}

function clipLabel(clip: SubtitleReviewClip, clips: SubtitleReviewClip[]): string {
  const sameType = clips.filter((item) => item.type === clip.type);
  const index = sameType.findIndex((item) => item.id === clip.id) + 1;
  return `${clip.type === "normal" ? "通常" : "ショート"} ${index}`;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), maximum);
}

function previewVideoSrc(url: string, specHash: string): string {
  const resolved = toApiUrl(url);
  if (!specHash) {
    return resolved;
  }
  const separator = resolved.includes("?") ? "&" : "?";
  return `${resolved}${separator}v=${encodeURIComponent(specHash)}`;
}

function isPreviewReady(
  clip: SubtitleReviewClip | null,
  reviewState: SubtitleReviewDocument["state"] | null | undefined
): boolean {
  return Boolean(
    clip?.previewState === "ready" &&
      clip.previewVideoUrl &&
      (reviewState !== "awaiting_review" || clip.previewSpecHash)
  );
}

function normalizeReviewTitle(value: string): string {
  return limitToTwoTextLines(value)
    .split("\n")
    .map((line) => line.trim().split(/\s+/u).filter(Boolean).join(" "))
    .filter(Boolean)
    .join("\n");
}

function limitToTwoTextLines(value: string): string {
  const [firstLine = "", ...remainingLines] = value
    .replace(/\r\n|\r|\u2028|\u2029|\\N/gu, "\n")
    .split("\n");
  if (remainingLines.length === 0) {
    return firstLine;
  }
  return `${firstLine}\n${remainingLines.join(" ")}`;
}

function canonicalSuggestionDraft(
  segments: Array<{ segmentId: string; text: string }>
): string {
  return JSON.stringify(
    segments.map((segment) => ({
      segmentId: segment.segmentId,
      text: segment.text
    }))
  );
}

function normalizeYoutubeHashtags(values: string[]): string[] {
  return Array.from(
    new Set(
      values
        .flatMap((value) => value.split(/[\s,、]+/u))
        .map((value) => value.trim())
        .filter(Boolean)
        .map((value) => (value.startsWith("#") ? value : `#${value}`))
    )
  ).slice(0, 12);
}

function hashtagsFromText(value: string): string[] {
  return normalizeYoutubeHashtags([value]);
}

function postCopyText(title: string, description: string, hashtags: string[]): string {
  return [title.trim(), description.trim(), normalizeYoutubeHashtags(hashtags).join(" ")]
    .filter(Boolean)
    .join("\n\n");
}

function postMetadataSourceForProvider(provider: string | null | undefined): string | null {
  if (provider === "codex") {
    return "codex";
  }
  if (provider) {
    return "manual";
  }
  return null;
}

async function sha256Hex(value: string): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value)
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}

function shortTitleOutputExpected({
  renderMode,
  storedMode,
  topBannerEnabled,
  titleManuallyReviewed
}: {
  renderMode: string;
  storedMode: SubtitleReviewDocument["shortOverlayTitleMode"];
  topBannerEnabled: boolean;
  titleManuallyReviewed: boolean;
}): boolean {
  if (topBannerEnabled || storedMode === "always") {
    return true;
  }
  if (storedMode === "never") {
    return false;
  }
  if (renderMode === "high_quality") {
    return true;
  }
  return storedMode === "auto" && titleManuallyReviewed;
}

type ClipContentDraft = {
  subtitleStyles: NonNullable<SubtitleReviewClip["subtitleStyles"]>;
  publicationTitle: string;
  titleCandidates: PostTitleCandidate[];
  recommendedTitleId: string | null;
  selectedTitleId: string | null;
  youtubeDescription: string;
  youtubeHashtagsText: string;
  youtubeTagsText: string;
  descriptionEvidenceSegmentIds: string[];
  postMetadataSource: string | null;
  postMetadataRevisionHash: string | null;
  title: string;
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
};

type ShortFramingDrafts = Record<
  string,
  SubtitleReviewClipFramingUpdateRequest
>;

function shortFramingSignature(
  framing: SubtitleReviewClipFramingUpdateRequest
): string {
  return `${framing.framingOffsetX}:${framing.framingOffsetY}:${framing.framingZoom}`;
}

function shortFramingEquals(
  left: SubtitleReviewClipFramingUpdateRequest,
  right: SubtitleReviewClipFramingUpdateRequest
): boolean {
  return shortFramingSignature(left) === shortFramingSignature(right);
}

function contentDraftForClip(clip: SubtitleReviewClip): ClipContentDraft {
  return {
    publicationTitle: clip.publicationTitle ?? clip.title,
    titleCandidates: clip.titleCandidates ?? [],
    recommendedTitleId: clip.recommendedTitleId ?? null,
    selectedTitleId: clip.selectedTitleId ?? null,
    youtubeDescription: clip.youtubeDescription ?? "",
    youtubeHashtagsText: (clip.youtubeHashtags ?? []).join(" "),
    youtubeTagsText: youtubeTagsText(clip.youtubeTags ?? []),
    descriptionEvidenceSegmentIds: clip.descriptionEvidenceSegmentIds ?? [],
    postMetadataSource: clip.postMetadataSource ?? null,
    postMetadataRevisionHash: clip.postMetadataRevisionHash ?? null,
    title: clip.title,
    hookText: clip.hookText,
    hookDurationSeconds: clip.hookDurationSeconds,
    hookSceneStart: clip.hookSceneStart,
    hookSceneEnd: clip.hookSceneEnd,
    thumbnailKicker: clip.thumbnailKicker ?? "",
    thumbnailLine1: clip.thumbnailLine1 ?? "",
    thumbnailLine2: clip.thumbnailLine2 ?? "",
    thumbnailFrameSeconds: clip.thumbnailFrameSeconds ?? null,
    titleStyle: clip.titleStyle,
    hookStyle: clip.hookStyle,
    subtitleStyle: clip.subtitleStyle,
    subtitleStyles: clip.subtitleStyles ?? []
  };
}

function stylesEqual(
  left: ClipTextStyle | null,
  right: ClipTextStyle | null
): boolean {
  if (left === right) {
    return true;
  }
  if (!left || !right) {
    return false;
  }
  return (
    left.fontPreset === right.fontPreset &&
    left.fontName === right.fontName &&
    left.bold === right.bold &&
    left.fontSize === right.fontSize &&
    left.primaryColor === right.primaryColor &&
    left.outlineColor === right.outlineColor &&
    left.outlineWidth === right.outlineWidth &&
    (left.outerOutlineWidth ?? 0) === (right.outerOutlineWidth ?? 0) &&
    (left.outerOutlineColor ?? "#FFFFFF") === (right.outerOutlineColor ?? "#FFFFFF") &&
    left.xPercent === right.xPercent &&
    left.yPercent === right.yPercent &&
    left.positionMode === right.positionMode
  );
}

function isClipContentDirty(
  clip: SubtitleReviewClip,
  drafts: Record<string, ClipContentDraft>
): boolean {
  const draft = drafts[clip.id];
  return Boolean(
    draft &&
      (draft.title !== clip.title ||
        draft.publicationTitle !== (clip.publicationTitle ?? clip.title) ||
        JSON.stringify(draft.titleCandidates) !== JSON.stringify(clip.titleCandidates ?? []) ||
        draft.recommendedTitleId !== (clip.recommendedTitleId ?? null) ||
        draft.selectedTitleId !== (clip.selectedTitleId ?? null) ||
        draft.youtubeDescription !== (clip.youtubeDescription ?? "") ||
        JSON.stringify(hashtagsFromText(draft.youtubeHashtagsText)) !==
          JSON.stringify(normalizeYoutubeHashtags(clip.youtubeHashtags ?? [])) ||
        JSON.stringify(draft.descriptionEvidenceSegmentIds) !==
          JSON.stringify(clip.descriptionEvidenceSegmentIds ?? []) ||
        draft.postMetadataSource !== (clip.postMetadataSource ?? null) ||
        draft.postMetadataRevisionHash !== (clip.postMetadataRevisionHash ?? null) ||
        draft.hookText !== clip.hookText ||
        draft.hookDurationSeconds !== clip.hookDurationSeconds ||
        draft.hookSceneStart !== clip.hookSceneStart ||
        draft.hookSceneEnd !== clip.hookSceneEnd ||
        draft.thumbnailKicker !== (clip.thumbnailKicker ?? "") ||
        draft.thumbnailLine1 !== (clip.thumbnailLine1 ?? "") ||
        draft.thumbnailLine2 !== (clip.thumbnailLine2 ?? "") ||
        draft.thumbnailFrameSeconds !== (clip.thumbnailFrameSeconds ?? null) ||
        !stylesEqual(draft.titleStyle, clip.titleStyle) ||
        !stylesEqual(draft.hookStyle, clip.hookStyle) ||
        !stylesEqual(draft.subtitleStyle, clip.subtitleStyle) ||
        JSON.stringify(draft.subtitleStyles) !== JSON.stringify(clip.subtitleStyles ?? []))
  );
}

export default function SubtitleReviewPage() {
  const [styledSegmentId, setStyledSegmentId] = useState<string | null>(null);
  const params = useParams();
  const router = useRouter();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const videoRef = useRef<HTMLVideoElement | null>(null);
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
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [isPlayerReady, setIsPlayerReady] = useState(false);
  const [videoLoadSeconds, setVideoLoadSeconds] = useState(0);
  const [previewLoadFailedClipIds, setPreviewLoadFailedClipIds] = useState<Set<string>>(
    new Set()
  );
  const [clipTime, setClipTime] = useState(0);
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
  const [segmentCursor, setSegmentCursor] = useState<{ id: string; offset: number } | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<"content" | "style">("content");
  const [suggestionHydrationRetryVersion, setSuggestionHydrationRetryVersion] =
    useState(0);

  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;
    const requestGeneration = reviewRequestGenerationRef.current;
    const search = new URLSearchParams(window.location.search);
    void getSubtitleReview(jobId)
      .then((document) => {
        if (
          !active ||
          requestGeneration !== reviewRequestGenerationRef.current ||
          reviewMutationCountRef.current > 0
        ) {
          return;
        }
        setReview(document);
        setOpenedFromReupload(search.get("source") === "reupload");
        const requestedClipId = search.get("clipId");
        const requestedClip = document.clips.find(
          (clip) => clip.id === requestedClipId
        );
        const firstNormalClip = document.clips.find((clip) => clip.type === "normal");
        const firstShortClip = document.clips.find((clip) => clip.type === "short");
        const initialClip = requestedClip ?? firstNormalClip ?? firstShortClip;
        setSelectedClipId(initialClip?.id ?? "");
        setActiveClipType(initialClip?.type ?? "normal");
        setLastSelectedClipIds({
          normal:
            initialClip?.type === "normal"
              ? initialClip.id
              : (firstNormalClip?.id ?? ""),
          short:
            initialClip?.type === "short"
              ? initialClip.id
              : (firstShortClip?.id ?? "")
        });
        setSelectedTextStyleTarget("title");
        setDrafts(
          Object.fromEntries(document.segments.map((segment) => [segment.id, segment.text]))
        );
        setClipContentDrafts(
          Object.fromEntries(
            document.clips.map((clip) => [clip.id, contentDraftForClip(clip)])
          )
        );
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof Error ? caught.message : "字幕確認データを取得できませんでした");
        }
      });
    return () => {
      active = false;
    };
  }, [jobId]);

  useEffect(() => {
    autoSuggestionAttemptedClipIdsRef.current = new Set();
    setAutoGeneratingSuggestionClipIds(new Set());
  }, [jobId]);

  useEffect(() => {
    if (!isUpdatingHookScene || !jobId) {
      return;
    }
    let active = true;
    const intervalId = window.setInterval(() => {
      void getJobStatus(jobId)
        .then(async (status) => {
          if (!active) {
            return;
          }
          if (status.status === "awaiting_subtitle_review") {
            if (reviewMutationCountRef.current > 0) {
              return;
            }
            window.clearInterval(intervalId);
            reviewRequestGenerationRef.current += 1;
            const requestGeneration = reviewRequestGenerationRef.current;
            const document = await getSubtitleReview(jobId);
            if (
              !active ||
              requestGeneration !== reviewRequestGenerationRef.current ||
              reviewMutationCountRef.current > 0
            ) {
              return;
            }
            setReview(document);
            setDrafts(
              Object.fromEntries(
                document.segments.map((segment) => [segment.id, segment.text])
              )
            );
            setClipContentDrafts(
              Object.fromEntries(
                document.clips.map((clip) => [
                  clip.id,
                  contentDraftForClip(clip)
                ])
              )
            );
            setPreviewLoadFailedClipIds((current) => {
              const next = new Set(current);
              next.delete(selectedClipId);
              return next;
            });
            setClipTime(0);
            setIsPlayerReady(false);
            setIsBuffering(true);
            setIsUpdatingHookScene(false);
            if (status.error) {
              setError(status.error.message);
            }
          } else if (status.status === "failed") {
            window.clearInterval(intervalId);
            setIsUpdatingHookScene(false);
            setError(
              status.error?.message ?? "冒頭フック映像の更新に失敗しました"
            );
          }
        })
        .catch((caught) => {
          if (!active) {
            return;
          }
          window.clearInterval(intervalId);
          setIsUpdatingHookScene(false);
          setError(
            caught instanceof Error
              ? caught.message
              : "冒頭フック映像の状態を取得できませんでした"
          );
        });
    }, 1500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [isUpdatingHookScene, jobId, selectedClipId]);

  const selectedClip = useMemo(
    () => review?.clips.find((clip) => clip.id === selectedClipId) ?? null,
    [review, selectedClipId]
  );
  const normalClips = useMemo(
    () => review?.clips.filter((clip) => clip.type === "normal") ?? [],
    [review]
  );
  const shortClips = useMemo(
    () => review?.clips.filter((clip) => clip.type === "short") ?? [],
    [review]
  );
  const visibleClips = activeClipType === "normal" ? normalClips : shortClips;
  const hasPendingPreviews = Boolean(
    review?.clips.some(
      (clip) =>
        clip.previewState === "queued" ||
        clip.previewState === "rendering" ||
        (review.state === "awaiting_review" && !clip.livePreviewVideoUrl)
    )
  );

  useEffect(() => {
    if (!jobId || !hasPendingPreviews || isUpdatingHookScene) {
      return;
    }
    let active = true;
    const refreshReview = () => {
      if (reviewMutationCountRef.current > 0) {
        return;
      }
      const requestGeneration = reviewRequestGenerationRef.current;
      void getSubtitleReview(jobId)
        .then((document) => {
          if (
            active &&
            requestGeneration === reviewRequestGenerationRef.current &&
            reviewMutationCountRef.current === 0
          ) {
            setReview(document);
          }
        })
        .catch(() => {
          // The existing review remains usable while a transient poll fails.
        });
    };
    const intervalId = window.setInterval(refreshReview, 1500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [hasPendingPreviews, isUpdatingHookScene, jobId]);

  const hasReviewMutationInFlight =
    isSavingBulkCorrection ||
    isSavingStructure ||
    retryingPreviewClipId !== null ||
    isUpdatingHookScene ||
    confirmingClipId !== null ||
    isSavingShortBannerSettings ||
    savingShortFramingClipId !== null ||
    isFinalizing;
  const isEditable =
    review?.state === "awaiting_review" &&
    !hasReviewMutationInFlight;
  const segmentsById = useMemo(
    () => new Map(review?.segments.map((segment) => [segment.id, segment]) ?? []),
    [review]
  );
  const selectedSegments = useMemo(
    () =>
      selectedClip?.segmentIds
        .map((segmentId) => segmentsById.get(segmentId))
        .filter((segment): segment is SubtitleReviewSegment => Boolean(segment)) ?? [],
    [segmentsById, selectedClip]
  );
  const selectedSuggestionSegments = useMemo(
    () =>
      [...selectedSegments]
        .sort((left, right) => left.index - right.index)
        .map((segment) => ({
          segmentId: segment.id,
          text: drafts[segment.id] ?? segment.text
        })),
    [drafts, selectedSegments]
  );
  const selectedSuggestionInputSnapshot = useMemo(
    () => JSON.stringify(selectedSuggestionSegments),
    [selectedSuggestionSegments]
  );
  const selectedSuggestionRecord = selectedClip
    ? titleHookSuggestionRecords[selectedClip.id] ?? null
    : null;
  const selectedSuggestionClipId = selectedClip?.id ?? "";
  const selectedSuggestionState = selectedSuggestionRecord?.response.state ?? null;
  const selectedSuggestionInputHash =
    selectedSuggestionRecord?.response.inputHash ?? null;
  const selectedSuggestionRequestGeneration =
    selectedSuggestionRecord?.requestGeneration ?? 0;
  const selectedSuggestionsAreStale = Boolean(
    selectedSuggestionRecord &&
      selectedSuggestionRecord.response.suggestions.length > 0 &&
      (!selectedSuggestionRecord.draftHashVerified ||
        selectedSuggestionRecord.inputSnapshot !== selectedSuggestionInputSnapshot)
  );

  useEffect(() => {
    if (
      !jobId ||
      !review ||
      review.jobId !== jobId ||
      review.state !== "awaiting_review" ||
      review.clips.length === 0 ||
      review.segments.some((segment) => !(segment.id in drafts))
    ) {
      return;
    }
    const pendingClips = review.clips.filter(
      (clip) => !autoSuggestionAttemptedClipIdsRef.current.has(clip.id)
    );
    if (pendingClips.length === 0) {
      return;
    }
    for (const clip of pendingClips) {
      autoSuggestionAttemptedClipIdsRef.current.add(clip.id);
    }
    const queue = [...pendingClips];
    const runNext = async () => {
      while (true) {
        const clip = queue.shift();
        if (!clip) {
          return;
        }
        const segments = clip.segmentIds
          .map((segmentId) => review.segments.find((segment) => segment.id === segmentId))
          .filter((segment): segment is SubtitleReviewSegment => Boolean(segment))
          .sort((left, right) => left.index - right.index)
          .map((segment) => ({
            segmentId: segment.id,
            text: drafts[segment.id] ?? segment.text
          }));
        const inputSnapshot = JSON.stringify(segments);
        setAutoGeneratingSuggestionClipIds((current) =>
          new Set(current).add(clip.id)
        );
        try {
          const existing = await getTitleHookSuggestions(jobId, clip.id);
          const response =
            existing ??
            (await requestTitleHookSuggestions(jobId, clip.id, {
              segments,
              forceRegenerate: false
            }));
          const currentDraftHash = await sha256Hex(canonicalSuggestionDraft(segments));
          const requestGeneration =
            (suggestionRequestGenerationRef.current[clip.id] ?? 0) + 1;
          suggestionRequestGenerationRef.current[clip.id] = requestGeneration;
          setTitleHookSuggestionRecords((current) => ({
            ...current,
            [clip.id]: {
              response,
              draftHashVerified:
                Boolean(response.draftHash) && response.draftHash === currentDraftHash,
              inputSnapshot,
              requestGeneration
            }
          }));
        } catch (caught) {
          const requestGeneration =
            (suggestionRequestGenerationRef.current[clip.id] ?? 0) + 1;
          suggestionRequestGenerationRef.current[clip.id] = requestGeneration;
          setTitleHookSuggestionRecords((current) => ({
            ...current,
            [clip.id]: {
              draftHashVerified: false,
              inputSnapshot,
              requestGeneration,
              response: {
                clipId: clip.id,
                state: "failed",
                inputHash: null,
                draftHash: null,
                revisionHash: null,
                model: null,
                provider: null,
                recommendedSuggestionId: null,
                youtubeDescription: "",
                hashtags: [],
                descriptionEvidenceSegmentIds: [],
                suggestions: [],
                error:
                  caught instanceof Error
                    ? caught.message
                    : "投稿案を生成できませんでした",
                generatedAt: null
              }
            }
          }));
        } finally {
          setAutoGeneratingSuggestionClipIds((current) => {
            const next = new Set(current);
            next.delete(clip.id);
            return next;
          });
        }
      }
    };
    const workers = Array.from(
      { length: Math.min(2, pendingClips.length) },
      () => runNext()
    );
    void Promise.all(workers);
  }, [drafts, jobId, review]);

  useEffect(() => {
    if (
      !jobId ||
      !selectedSuggestionClipId ||
      selectedSuggestionRecord
    ) {
      return;
    }
    let active = true;
    let retryTimeoutId: number | null = null;
    const clipId = selectedSuggestionClipId;
    const inputSnapshot = selectedSuggestionInputSnapshot;
    const requestGeneration =
      (suggestionRequestGenerationRef.current[clipId] ?? 0) + 1;
    suggestionRequestGenerationRef.current[clipId] = requestGeneration;
    void Promise.all([
      getTitleHookSuggestions(jobId, clipId),
      sha256Hex(canonicalSuggestionDraft(selectedSuggestionSegments))
    ])
      .then(([response, currentDraftHash]) => {
        if (
          !active ||
          suggestionRequestGenerationRef.current[clipId] !== requestGeneration
        ) {
          return;
        }
        if (!response) {
          retryTimeoutId = window.setTimeout(
            () => setSuggestionHydrationRetryVersion((current) => current + 1),
            15000
          );
          return;
        }
        setTitleHookSuggestionRecords((current) => ({
          ...current,
          [clipId]: {
            response,
            draftHashVerified:
              Boolean(response.draftHash) && response.draftHash === currentDraftHash,
            inputSnapshot,
            requestGeneration
          }
        }));
      })
      .catch(() => {
        if (active) {
          retryTimeoutId = window.setTimeout(
            () => setSuggestionHydrationRetryVersion((current) => current + 1),
            3000
          );
        }
      });
    return () => {
      active = false;
      if (retryTimeoutId !== null) {
        window.clearTimeout(retryTimeoutId);
      }
    };
  }, [
    jobId,
    selectedSuggestionClipId,
    selectedSuggestionInputSnapshot,
    selectedSuggestionRecord,
    selectedSuggestionSegments,
    suggestionHydrationRetryVersion
  ]);

  useEffect(() => {
    if (
      !jobId ||
      !selectedSuggestionClipId ||
      !selectedSuggestionInputHash ||
      (selectedSuggestionState !== "queued" &&
        selectedSuggestionState !== "generating")
    ) {
      return;
    }
    let active = true;
    let pollInFlight = false;
    const clipId = selectedSuggestionClipId;
    const expectedInputHash = selectedSuggestionInputHash;
    const requestGeneration = selectedSuggestionRequestGeneration;
    const pollSuggestions = () => {
      if (pollInFlight) {
        return;
      }
      pollInFlight = true;
      void getTitleHookSuggestions(jobId, clipId)
        .then((response) => {
          if (!active || !response) {
            return;
          }
          setTitleHookSuggestionRecords((current) => {
            const currentRecord = current[clipId];
            if (!currentRecord || currentRecord.requestGeneration !== requestGeneration) {
              return current;
            }
            if (response.inputHash !== expectedInputHash) {
              return {
                ...current,
                [clipId]: {
                  ...currentRecord,
                  response: {
                    ...currentRecord.response,
                    state: "failed",
                    suggestions: [],
                    error:
                      "別の字幕内容から再生成されました。現在の字幕からもう一度生成してください。"
                  }
                }
              };
            }
            return {
              ...current,
              [clipId]: {
                ...currentRecord,
                response
              }
            };
          });
        })
        .catch(() => {
          // Keep polling after a transient network error. The worker state remains authoritative.
        })
        .finally(() => {
          pollInFlight = false;
        });
    };
    pollSuggestions();
    const intervalId = window.setInterval(pollSuggestions, 1500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [
    jobId,
    selectedSuggestionClipId,
    selectedSuggestionInputHash,
    selectedSuggestionRequestGeneration,
    selectedSuggestionState
  ]);
  const bodyDuration = selectedClip
    ? Math.max(0, selectedClip.end - selectedClip.start)
    : 0;
  const hookSceneDuration =
    selectedClip?.hookSceneStart !== null &&
    selectedClip?.hookSceneStart !== undefined &&
    selectedClip.hookSceneEnd !== null &&
    selectedClip.hookSceneEnd !== undefined
      ? Math.max(0, selectedClip.hookSceneEnd - selectedClip.hookSceneStart)
      : 0;
  const clipDuration = bodyDuration + hookSceneDuration;
  const selectedPreviewReady = isPreviewReady(selectedClip, review?.state);
  const allPreviewsReady = Boolean(
    review &&
      review.clips.length > 0 &&
      review.clips.every((clip) => isPreviewReady(clip, review.state))
  );
  const selectedVideoUrl = selectedPreviewReady
    ? selectedClip?.previewVideoUrl ?? null
    : null;
  const selectedPreviewVersion = selectedPreviewReady
    ? selectedClip?.previewSpecHash ?? ""
    : "";
  const selectedLiveVideoUrl = selectedClip?.livePreviewVideoUrl ?? null;
  const selectedLivePreviewVersion = selectedClip?.livePreviewSpecHash ?? "";
  const livePreviewReady = Boolean(
    selectedLiveVideoUrl && selectedLivePreviewVersion
  );
  const isShowingLivePreview = livePreviewReady && !showSavedPreview;
  const selectedPlayerVideoUrl = isShowingLivePreview
    ? selectedLiveVideoUrl
    : selectedVideoUrl;
  const selectedPlayerPreviewVersion = isShowingLivePreview
    ? selectedLivePreviewVersion
    : selectedPreviewVersion;
  const selectedPlayerReady = Boolean(selectedPlayerVideoUrl);
  const selectedPreviewLoadFailed = Boolean(
    selectedClip && previewLoadFailedClipIds.has(selectedClip.id)
  );
  const selectedClipHasDirtySegments = selectedSegments.some((segment) =>
    dirtySegmentIds.has(segment.id)
  );
  const selectedClipContentDraft = selectedClip
    ? clipContentDrafts[selectedClip.id] ?? contentDraftForClip(selectedClip)
    : null;
  const selectedSavedShortFraming =
    selectedClip?.type === "short"
      ? {
          framingOffsetX: selectedClip.framingOffsetX,
          framingOffsetY: selectedClip.framingOffsetY,
          framingZoom: selectedClip.framingZoom
        }
      : null;
  const selectedShortFramingDraft =
    selectedClip?.type === "short"
      ? shortFramingDrafts[selectedClip.id] ?? selectedSavedShortFraming
      : null;
  const selectedShortFramingDirty = Boolean(
    selectedClip?.type === "short" &&
      selectedShortFramingDraft &&
      selectedSavedShortFraming &&
      !shortFramingEquals(selectedShortFramingDraft, selectedSavedShortFraming)
  );
  const hasDirtyShortFraming = Boolean(
    review?.clips.some((clip) => {
      if (clip.type !== "short") {
        return false;
      }
      const draft = shortFramingDrafts[clip.id];
      return Boolean(
        draft &&
          !shortFramingEquals(draft, {
            framingOffsetX: clip.framingOffsetX,
            framingOffsetY: clip.framingOffsetY,
            framingZoom: clip.framingZoom
          })
      );
    })
  );
  const selectedShortPreviewRegenerating = Boolean(
    selectedClip?.type === "short" &&
      (savingShortFramingClipId === selectedClip.id ||
        selectedClip.previewState === "queued" ||
        selectedClip.previewState === "rendering")
  );
  const selectedClipHasDirtyContent = Boolean(
    selectedClip && isClipContentDirty(selectedClip, clipContentDrafts)
  );
  const hasDirtyClipContent = Boolean(
    review?.clips.some((clip) => isClipContentDirty(clip, clipContentDrafts))
  );
  const selectedHookDurationIsValid =
    Number.isFinite(selectedClipContentDraft?.hookDurationSeconds ?? Number.NaN) &&
    (selectedClipContentDraft?.hookDurationSeconds ?? 0) >= 1 &&
    (selectedClipContentDraft?.hookDurationSeconds ?? 0) <= 8;
  const hookSuppressionEnd = selectedClip
    ? Math.min(
        clipDuration,
        Math.max(
          hookSceneDuration,
          selectedClipContentDraft?.hookText.trim()
            ? selectedClipContentDraft.hookDurationSeconds
            : 0
        )
      )
    : 0;
  const isInHookSuppression = clipTime < hookSuppressionEnd;
  const absolutePlaybackTime = selectedClip
    ? hookSceneDuration > 0 &&
      selectedClip.hookSceneStart !== null &&
      selectedClip.hookSceneEnd !== null &&
      clipTime < hookSceneDuration
      ? Math.min(
          selectedClip.hookSceneEnd,
          selectedClip.hookSceneStart + clipTime
        )
      : selectedClip.start + Math.max(0, clipTime - hookSceneDuration)
    : 0;
  const activeSegment = useMemo(() => {
    if (!selectedClip || isInHookSuppression) {
      return null;
    }
    return selectedSegments.find(
      (segment) =>
        absolutePlaybackTime >= Math.max(segment.start, selectedClip.start) &&
        absolutePlaybackTime < Math.min(segment.end, selectedClip.end)
    );
  }, [absolutePlaybackTime, isInHookSuppression, selectedClip, selectedSegments]);
  const activeSegmentId = activeSegment?.id ?? null;
  const selectedClipTextStyles = {
    title: selectedClipContentDraft?.titleStyle ?? null,
    hook: selectedClipContentDraft?.hookStyle ?? null,
    subtitle: selectedClipContentDraft?.subtitleStyle ?? null
  };
  const selectedResolvedClipTextStyles = {
    title: selectedClip?.resolvedTitleStyle ?? null,
    hook: selectedClip?.resolvedHookStyle ?? null,
    subtitle: selectedClip?.resolvedSubtitleStyle ?? null
  };
  const selectedDefaultResolvedClipTextStyles = {
    title: selectedClip?.resolvedDefaultTitleStyle ?? null,
    hook: selectedClip?.resolvedDefaultHookStyle ?? null,
    subtitle: selectedClip?.resolvedDefaultSubtitleStyle ?? null
  };
  const selectedDraftTitleEdited = Boolean(
    selectedClip &&
      selectedClipContentDraft &&
      normalizeReviewTitle(selectedClipContentDraft.title) !==
        normalizeReviewTitle(selectedClip.originalTitle ?? selectedClip.title)
  );
  const selectedShortTitleOutputEnabled = Boolean(
    selectedClip?.type === "short" &&
      review &&
      shortTitleOutputExpected({
        renderMode: review.renderMode,
        storedMode: review.shortOverlayTitleMode,
        topBannerEnabled: review.shortTopBannerEnabled,
        titleManuallyReviewed: selectedDraftTitleEdited
      })
  );
  const subtitlePreviewEventList = useMemo(() => {
    if (!selectedClip) {
      return [];
    }
    return subtitlePreviewEvents({
      segments: selectedSegments.map((segment) => ({
        start: segment.start,
        end: segment.end,
        text: drafts[segment.id] ?? segment.text,
        preserveSegmentation: segment.preserveSegmentation,
        singleLine: segment.singleLine,
        style: selectedClipContentDraft?.subtitleStyles.find(
          (item) => item.start === segment.start && item.end === segment.end
        )?.style
      })),
      candidateStart: selectedClip.start,
      candidateEnd: selectedClip.end,
      hookSceneDuration,
      suppressionEnd: hookSuppressionEnd,
      maxCharsPerLine:
        selectedClip.subtitleMaxCharsPerLine ??
        (selectedClip.type === "short" ? 16 : 28),
      maxLines: selectedClip.subtitleMaxLines ?? 2,
      minSubtitleDuration: selectedClip.subtitleMinDurationSeconds ?? 1.1,
      maxSubtitleDuration: selectedClip.subtitleMaxDurationSeconds ?? 4.2,
      minGapBetweenSubtitles: selectedClip.subtitleMinGapSeconds ?? 0.08
    });
  }, [
    drafts,
    hookSceneDuration,
    hookSuppressionEnd,
    selectedClip,
    selectedSegments,
    selectedClipContentDraft?.subtitleStyles
  ]);
  const activePreviewSubtitleEvent = useMemo(
    () =>
      subtitlePreviewEventList.find(
        (event) => clipTime >= event.start && clipTime < event.end
      ) ?? null,
    [clipTime, subtitlePreviewEventList]
  );
  const stylePreviewSubtitleText =
    activePreviewSubtitleEvent?.text ?? subtitlePreviewEventList[0]?.text ?? "";
  const liveHookText = selectedClipContentDraft?.hookText.trim() ?? "";
  const liveHookEnd = Math.min(
    clipDuration,
    selectedClipContentDraft?.hookDurationSeconds ?? 3
  );
  const liveTitleStart = selectedClip
    ? selectedClip.type === "normal"
      ? Math.max(hookSceneDuration, liveHookText ? liveHookEnd : 0)
      : liveHookText
        ? liveHookEnd
        : 0
    : 0;
  const showLiveHook = Boolean(
    isShowingLivePreview &&
      liveHookText &&
      clipTime < liveHookEnd
  );
  const showLiveTitle = Boolean(
    isShowingLivePreview &&
      selectedClip &&
      (selectedClip.type === "normal" || selectedShortTitleOutputEnabled) &&
      selectedClipContentDraft?.title.trim() &&
      clipTime >= liveTitleStart
  );
  const showLiveSubtitle = Boolean(
    isShowingLivePreview && activePreviewSubtitleEvent?.text
  );

  useEffect(() => {
    const video = videoRef.current;

    if (!video || !selectedPlayerReady) {
      return;
    }
    video.pause();

    const moveToClipStart = () => {
      video.currentTime = 0;
    };

    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
      moveToClipStart();
      return;
    }

    video.addEventListener("loadedmetadata", moveToClipStart, { once: true });
    video.load();
    return () => {
      video.removeEventListener("loadedmetadata", moveToClipStart);
    };
  }, [
    selectedClipId,
    selectedPlayerPreviewVersion,
    selectedPlayerReady,
    selectedPlayerVideoUrl
  ]);

  useEffect(() => {
    if (isPlayerReady || !selectedClip || !selectedPlayerReady) {
      return;
    }
    const intervalId = window.setInterval(() => {
      setVideoLoadSeconds((current) => current + 1);
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [isPlayerReady, selectedClip, selectedPlayerReady]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.playbackRate = playbackRate;
    }
  }, [playbackRate]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.volume = volume;
      videoRef.current.muted = isMuted;
    }
  }, [isMuted, volume]);

  useEffect(() => {
    if (!activeSegmentId || !isPlaying) {
      return;
    }
    const container = subtitleListRef.current;
    const row = segmentRowRefs.current[activeSegmentId];
    if (!container || !row) {
      return;
    }
    const containerRect = container.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const visibleTop = containerRect.top + 12;
    const visibleBottom = containerRect.bottom - 12;
    if (rowRect.top >= visibleTop && rowRect.bottom <= visibleBottom) {
      return;
    }
    container.scrollBy({
      top: rowRect.top - containerRect.top - container.clientHeight * 0.28,
      behavior: "smooth"
    });
  }, [activeSegmentId, isPlaying]);

  function beginReviewMutation(): number {
    reviewMutationCountRef.current += 1;
    reviewRequestGenerationRef.current += 1;
    return reviewRequestGenerationRef.current;
  }

  function endReviewMutation() {
    reviewMutationCountRef.current = Math.max(
      0,
      reviewMutationCountRef.current - 1
    );
  }

  function isCurrentReviewMutation(generation: number): boolean {
    return generation === reviewRequestGenerationRef.current;
  }

  useEffect(() => { subtitleListRef.current?.scrollTo({ top: 0 }); }, [selectedClipId]);

  function selectClip(clip: SubtitleReviewClip) {
    setStyledSegmentId(null);
    videoRef.current?.pause();
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
    setClipTime(0);
    setIsPlaying(false);
    setIsBuffering(
      Boolean(clip.livePreviewVideoUrl) || isPreviewReady(clip, review?.state)
    );
    setIsPlayerReady(false);
    setVideoLoadSeconds(0);
    setSelectedClipId(clip.id);
    setActiveClipType(clip.type);
    setLastSelectedClipIds((current) => ({ ...current, [clip.type]: clip.id }));
    setSelectedTextStyleTarget("title");
    setShowSavedPreview(false);
    setCopiedPostField(null);
    setError(null);
  }

  function selectClipType(clipType: ExportType) {
    const candidates = clipType === "normal" ? normalClips : shortClips;
    if (candidates.length === 0) {
      return;
    }
    const remembered = candidates.find(
      (clip) => clip.id === lastSelectedClipIds[clipType]
    );
    selectClip(remembered ?? candidates[0]);
  }

  function seekToClipTime(nextTime: number) {
    if (!videoRef.current || !selectedClip) {
      return;
    }
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
    const relativeTime = clamp(nextTime, 0, clipDuration);
    videoRef.current.currentTime = relativeTime;
    setClipTime(relativeTime);
  }

  function playFromClipStart() {
    if (!videoRef.current || !selectedClip) {
      return;
    }
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
    videoRef.current.currentTime = 0;
    setClipTime(0);
    void videoRef.current.play();
  }

  function seekToSubtitle(start: number) {
    const video = videoRef.current;
    if (!video || !selectedClip) {
      return;
    }
    const absoluteTime = clamp(
      start,
      selectedClip.start,
      Math.max(selectedClip.start, selectedClip.end - 0.05)
    );
    const relativeTime = clamp(
      Math.max(
        absoluteTime - selectedClip.start + hookSceneDuration,
        hookSuppressionEnd
      ),
      0,
      clipDuration
    );
    video.pause();
    video.currentTime = relativeTime;
    setClipTime(relativeTime);
    setIsPlaying(false);
  }

  function togglePlayback() {
    const video = videoRef.current;
    if (!video || !selectedClip) {
      return;
    }
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
    if (video.paused) {
      if (clipTime >= clipDuration - 0.05) {
        seekToClipTime(0);
      }
      void video.play();
      return;
    }
    video.pause();
  }

  function skipBy(seconds: number) {
    seekToClipTime(clipTime + seconds);
  }

  function handleVideoTimeUpdate() {
    const video = videoRef.current;
    if (!video || !selectedClip || !selectedPlayerReady) {
      return;
    }
    const suggestionPlaybackEnd = suggestionPlaybackEndRef.current;
    if (
      suggestionPlaybackEnd !== null &&
      video.currentTime >= suggestionPlaybackEnd - 0.03
    ) {
      suggestionPlaybackEndRef.current = null;
      setPreviewingSuggestionId(null);
      video.pause();
      video.currentTime = suggestionPlaybackEnd;
      setClipTime(suggestionPlaybackEnd);
      return;
    }
    if (video.currentTime < -0.05) {
      video.currentTime = 0;
      setClipTime(0);
      return;
    }
    if (video.currentTime >= clipDuration) {
      video.pause();
      video.currentTime = clipDuration;
      setClipTime(clipDuration);
      return;
    }
    setClipTime(clamp(video.currentTime, 0, clipDuration));
  }

  function handleVideoSeeking() {
    const video = videoRef.current;
    if (!video || !selectedPlayerReady) {
      return;
    }
    if (video.currentTime < 0) {
      video.currentTime = 0;
    } else if (video.currentTime > clipDuration) {
      video.currentTime = clipDuration;
    }
  }

  function retryVideoLoad() {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    if (selectedClip) {
      setPreviewLoadFailedClipIds((current) => {
        const next = new Set(current);
        next.delete(selectedClip.id);
        return next;
      });
    }
    setVideoLoadSeconds(0);
    setIsPlayerReady(false);
    setIsBuffering(true);
    video.load();
  }

  function handleVideoError() {
    if (selectedClip) {
      setPreviewLoadFailedClipIds((current) => new Set(current).add(selectedClip.id));
    }
    setIsPlayerReady(false);
    setIsBuffering(false);
    suggestionPlaybackEndRef.current = null;
    setPreviewingSuggestionId(null);
  }

  function toggleMuted() {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    const nextMuted = !video.muted;
    video.muted = nextMuted;
    setIsMuted(nextMuted);
  }

  function changeVolume(nextVolume: number) {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.volume = nextVolume;
    video.muted = nextVolume === 0;
    setVolume(nextVolume);
    setIsMuted(nextVolume === 0);
  }

  function changePlaybackRate(nextRate: number) {
    if (videoRef.current) {
      videoRef.current.playbackRate = nextRate;
    }
    setPlaybackRate(nextRate);
  }

  async function toggleFullscreen() {
    if (!playerShellRef.current) {
      return;
    }
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    await playerShellRef.current.requestFullscreen();
  }

  function updateDraft(segmentId: string, text: string) {
    setShowSavedPreview(false);
    setDrafts((current) => ({ ...current, [segmentId]: text }));
    setDirtySegmentIds((current) => new Set(current).add(segmentId));
  }

  async function saveBulkCorrection(updates: SubtitleBatchUpdate[]) {
    const generation = beginReviewMutation();
    setIsSavingBulkCorrection(true);
    setShowSavedPreview(false);
    try {
      const updated = await updateSubtitleReviewSegments(jobId, updates);
      if (isCurrentReviewMutation(generation)) {
        const ids = new Set(updates.map((item) => item.segmentId));
        setReview(updated);
        setDrafts((current) => {
          const next = { ...current };
          for (const segment of updated.segments) if (ids.has(segment.id)) next[segment.id] = segment.text;
          return next;
        });
        setDirtySegmentIds((current) => new Set([...current].filter((id) => !ids.has(id))));
      }
    } finally {
      endReviewMutation();
      setIsSavingBulkCorrection(false);
    }
  }

  function updateClipContentDraft(
    clipId: string,
    update: Partial<ClipContentDraft>
  ) {
    setShowSavedPreview(false);
    setClipContentDrafts((current) => {
      const clip = review?.clips.find((item) => item.id === clipId);
      if (!clip) {
        return current;
      }
      return {
        ...current,
        [clipId]: {
          ...(current[clipId] ?? contentDraftForClip(clip)),
          ...update
        }
      };
    });
  }

  function updateClipTextStyle(
    target: ClipTextTarget,
    style: ClipTextStyle | null
  ) {
    if (!selectedClip) {
      return;
    }
    if (target === "title") {
      updateClipContentDraft(selectedClip.id, { titleStyle: style });
      return;
    }
    if (target === "hook") {
      updateClipContentDraft(selectedClip.id, { hookStyle: style });
      return;
    }
    const segment = selectedSegments.find((item) => item.id === styledSegmentId);
    if (segment && selectedClipContentDraft) {
      const remaining = selectedClipContentDraft.subtitleStyles.filter(
        (item) => item.start !== segment.start || item.end !== segment.end
      );
      updateClipContentDraft(selectedClip.id, {
        subtitleStyles: style ? [...remaining, { start: segment.start, end: segment.end, style }] : remaining
      });
    } else {
      updateClipContentDraft(selectedClip.id, { subtitleStyle: style });
    }
  }

  function changeSelectedShortFraming(
    update: Partial<SubtitleReviewClipFramingUpdateRequest>
  ): SubtitleReviewClipFramingUpdateRequest | null {
    if (!selectedClip || selectedClip.type !== "short") {
      return null;
    }
    const current =
      selectedShortFramingDraft ?? {
        framingOffsetX: selectedClip.framingOffsetX,
        framingOffsetY: selectedClip.framingOffsetY,
        framingZoom: selectedClip.framingZoom
      };
    const next = {
      ...current,
      ...update
    };
    setShortFramingDrafts((drafts) => ({
      ...drafts,
      [selectedClip.id]: next
    }));
    return next;
  }

  async function saveSelectedShortFraming(
    clipId: string,
    framing: SubtitleReviewClipFramingUpdateRequest
  ) {
    const clip = review?.clips.find((item) => item.id === clipId);
    if (
      !clip ||
      clip.type !== "short" ||
      !isEditable ||
      shortFramingSaveInFlightRef.current.has(clipId)
    ) {
      return false;
    }
    const nextFraming = {
      framingOffsetX: clamp(framing.framingOffsetX, -100, 100),
      framingOffsetY: clamp(framing.framingOffsetY, -100, 100),
      framingZoom: clamp(framing.framingZoom, 1, 3)
    };
    const savedFraming = {
      framingOffsetX: clip.framingOffsetX,
      framingOffsetY: clip.framingOffsetY,
      framingZoom: clip.framingZoom
    };
    const signature = shortFramingSignature(nextFraming);
    const layoutChanged = framing.shortLayout !== undefined && framing.shortLayout !== (clip.shortLayout ?? review?.shortLayout);
    if (!layoutChanged && shortFramingEquals(nextFraming, savedFraming)) {
      setShortFramingDrafts((drafts) => {
        const next = { ...drafts };
        delete next[clipId];
        return next;
      });
      return true;
    }
    if (!layoutChanged && lastSavedShortFramingSignatureRef.current[clipId] === signature) {
      setShortFramingDrafts((drafts) => {
        const next = { ...drafts };
        delete next[clipId];
        return next;
      });
      return true;
    }

    shortFramingSaveInFlightRef.current.add(clipId);
    const mutationGeneration = beginReviewMutation();
    setSavingShortFramingClipId(clipId);
    setShowSavedPreview(false);
    setError(null);
    try {
      const updated = await updateSubtitleReviewClipFraming(
        jobId,
        clipId,
        { ...nextFraming, shortLayout: framing.shortLayout }
      );
      lastSavedShortFramingSignatureRef.current[clipId] = signature;
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(updated);
      }
      setShortFramingDrafts((drafts) => {
        if (
          !drafts[clipId] ||
          shortFramingSignature(drafts[clipId]) !== signature
        ) {
          return drafts;
        }
        const next = { ...drafts };
        delete next[clipId];
        return next;
      });
      return true;
    } catch (caught) {
      delete lastSavedShortFramingSignatureRef.current[clipId];
      setError(
        caught instanceof Error
          ? caught.message
          : "ショート画角を保存できませんでした"
      );
      return false;
    } finally {
      endReviewMutation();
      shortFramingSaveInFlightRef.current.delete(clipId);
      setSavingShortFramingClipId((current) =>
        current === clipId ? null : current
      );
    }
  }

  async function saveShortBannerSettings(
    shortLayout: SubtitleReviewDocument["shortLayout"],
    shortTopBannerEnabled: boolean,
    shortBottomBannerEnabled: boolean,
    assets: { shortTopBannerAssetId?: string; shortBottomBannerAssetId?: string; characterPresetName?: string } = {}
  ) {
    if (!review || !isEditable || hasReviewMutationInFlight) {
      return false;
    }
    const previousSettings = {
      shortOverlayTitleMode: review.shortOverlayTitleMode,
      shortLayout: review.shortLayout,
      shortTopBannerEnabled: review.shortTopBannerEnabled,
      shortBottomBannerEnabled: review.shortBottomBannerEnabled,
      clips: review.clips
    };
    const topBannerChanged =
      shortTopBannerEnabled !== review.shortTopBannerEnabled;
    const nextShortOverlayTitleMode: SubtitleReviewDocument["shortOverlayTitleMode"] =
      topBannerChanged && !shortTopBannerEnabled
        ? "always"
        : review.shortOverlayTitleMode;
    const optimisticSettings = {
      shortOverlayTitleMode: nextShortOverlayTitleMode,
      shortLayout,
      shortTopBannerEnabled,
      shortBottomBannerEnabled,
      clips:
        topBannerChanged
          ? review.clips.map((clip) =>
              clip.type === "short"
                ? { ...clip, overlayTitleExpected: true }
                : clip
            )
          : review.clips
    };
    const requestBody = {
      ...assets,
      shortLayout,
      shortTopBannerEnabled,
      shortBottomBannerEnabled
    };
    const mutationGeneration = beginReviewMutation();
    setReview((current) =>
      current
        ? {
            ...current,
            ...optimisticSettings
          }
        : current
    );
    setIsSavingShortBannerSettings(true);
    setError(null);
    try {
      const updated = await updateSubtitleReviewShortBannerSettings(
        jobId,
        requestBody
      );
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(updated);
        if (assets.characterPresetName) {
          setClipContentDrafts(current => {
            const next = { ...current };
            for (const clip of updated.clips) {
              const fresh = contentDraftForClip(clip);
              const before = review.clips.find(item => item.id === clip.id);
              const old = before ? contentDraftForClip(before) : fresh;
              const draft = { ...(current[clip.id] ?? fresh) };
              for (const key of Object.keys(fresh) as (keyof ClipContentDraft)[]) {
                if (["titleStyle", "hookStyle", "subtitleStyle", "subtitleStyles"].includes(key)
                    || JSON.stringify(draft[key]) === JSON.stringify(old[key])) {
                  Object.assign(draft, { [key]: fresh[key] });
                }
              }
              next[clip.id] = draft;
            }
            return next;
          });
        }
      }
      return true;
    } catch (caught) {
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview((current) =>
          current
            ? {
                ...current,
                ...previousSettings
              }
            : current
        );
      }
      setError(
        caught instanceof Error
          ? caught.message
          : "ショート画面設定を保存できませんでした"
      );
      return false;
    } finally {
      endReviewMutation();
      setIsSavingShortBannerSettings(false);
    }
  }

  async function generateTitleHookSuggestions(forceRegenerate: boolean) {
    if (!selectedClip) {
      return;
    }
    const clipId = selectedClip.id;
    const inputSnapshot = selectedSuggestionInputSnapshot;
    const requestGeneration =
      (suggestionRequestGenerationRef.current[clipId] ?? 0) + 1;
    suggestionRequestGenerationRef.current[clipId] = requestGeneration;
    setRequestingSuggestionClipId(clipId);
    setTitleHookSuggestionRecords((current) => ({
      ...current,
      [clipId]: {
        draftHashVerified: false,
        inputSnapshot,
        requestGeneration,
        response: {
          clipId,
          state: "queued",
          inputHash: null,
          draftHash: null,
          model: null,
          provider: null,
          revisionHash: null,
          recommendedSuggestionId: null,
          youtubeDescription: "",
          hashtags: [],
          descriptionEvidenceSegmentIds: [],
          suggestions: [],
          error: null,
          generatedAt: null
        }
      }
    }));
    try {
      const currentDraftHash = await sha256Hex(
        canonicalSuggestionDraft(selectedSuggestionSegments)
      );
      if (suggestionRequestGenerationRef.current[clipId] !== requestGeneration) {
        return;
      }
      const response = await requestTitleHookSuggestions(jobId, clipId, {
        segments: selectedSuggestionSegments,
        forceRegenerate
      });
      if (suggestionRequestGenerationRef.current[clipId] !== requestGeneration) {
        return;
      }
      setTitleHookSuggestionRecords((current) => ({
        ...current,
        [clipId]: {
          response,
          draftHashVerified:
            Boolean(response.draftHash) && response.draftHash === currentDraftHash,
          inputSnapshot,
          requestGeneration
        }
      }));
    } catch (caught) {
      if (suggestionRequestGenerationRef.current[clipId] !== requestGeneration) {
        return;
      }
      setTitleHookSuggestionRecords((current) => ({
        ...current,
        [clipId]: {
          draftHashVerified: false,
          inputSnapshot,
          requestGeneration,
          response: {
            clipId,
            state: "failed",
            inputHash: null,
            draftHash: null,
            model: null,
            provider: null,
            revisionHash: null,
            recommendedSuggestionId: null,
            youtubeDescription: "",
            hashtags: [],
            descriptionEvidenceSegmentIds: [],
            suggestions: [],
            error:
              caught instanceof Error
                ? caught.message
                : "投稿案を生成できませんでした",
            generatedAt: null
          }
        }
      }));
    } finally {
      if (suggestionRequestGenerationRef.current[clipId] === requestGeneration) {
        setRequestingSuggestionClipId((current) =>
          current === clipId ? null : current
        );
      }
    }
  }

  function applyTitleHookSuggestion(suggestion: TitleHookSuggestion) {
    if (!selectedClip || selectedSuggestionsAreStale) {
      return;
    }
    const suggestionResponse = selectedSuggestionRecord?.response;
    const titleCandidates =
      suggestionResponse?.suggestions.map((item) => ({
        id: item.id,
        title: item.publicationTitle,
        intent: item.intent,
        reason: item.reason,
        evidenceSegmentIds: item.evidenceSegmentIds
      })) ?? [];
    const suggestedHookStart = clamp(
      suggestion.hookSceneStart ?? 0,
      0,
      bodyDuration
    );
    const suggestedHookEnd = clamp(
      suggestion.hookSceneEnd ?? 0,
      suggestedHookStart,
      bodyDuration
    );
    const hasValidHookScene =
      Boolean(suggestion.hookText.trim()) &&
      suggestion.hookSceneStart !== null &&
      suggestion.hookSceneEnd !== null &&
      suggestedHookEnd > suggestedHookStart;
    updateClipContentDraft(selectedClip.id, {
      publicationTitle: suggestion.publicationTitle
        .trim()
        .split(/\s+/u)
        .filter(Boolean)
        .join(" ")
        .slice(0, 100),
      titleCandidates,
      recommendedTitleId: suggestionResponse?.recommendedSuggestionId ?? null,
      selectedTitleId: suggestion.id,
      youtubeDescription: suggestionResponse?.youtubeDescription ?? "",
      youtubeHashtagsText: (suggestionResponse?.hashtags ?? []).join(" "),
      youtubeTagsText: selectedClipContentDraft?.youtubeTagsText ?? "",
      descriptionEvidenceSegmentIds:
        suggestionResponse?.descriptionEvidenceSegmentIds ?? [],
      postMetadataSource: postMetadataSourceForProvider(suggestionResponse?.provider),
      postMetadataRevisionHash: suggestionResponse?.revisionHash ?? null,
      title: limitToTwoTextLines(suggestion.overlayTitle).slice(0, 80),
      hookText: limitToTwoTextLines(suggestion.hookText).slice(0, 120),
      hookDurationSeconds: clamp(suggestion.hookDurationSeconds, 1, 8),
      hookSceneStart: hasValidHookScene
        ? selectedClip.start + suggestedHookStart
        : null,
      hookSceneEnd: hasValidHookScene
        ? selectedClip.start + suggestedHookEnd
        : null,
      thumbnailKicker:
        selectedClip.type === "normal"
          ? (suggestion.thumbnailKicker ?? "").trim().slice(0, 40)
          : "",
      thumbnailLine1:
        selectedClip.type === "normal"
          ? (suggestion.thumbnailLine1 ?? "").trim().slice(0, 60)
          : "",
      thumbnailLine2:
        selectedClip.type === "normal"
          ? (suggestion.thumbnailLine2 ?? "").trim().slice(0, 60)
          : "",
      thumbnailFrameSeconds:
        selectedClip.type === "normal" &&
        suggestion.thumbnailFrameSeconds !== null
          ? clamp(suggestion.thumbnailFrameSeconds, 0, bodyDuration)
          : null
    });
    setSelectedTextStyleTarget("title");
  }

  async function copyPostField(field: string, value: string) {
    if (!value.trim()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopiedPostField(field);
      setError(null);
    } catch {
      setError("クリップボードへコピーできませんでした。");
    }
  }

  function clearSelectedHook() {
    if (!selectedClip) {
      return;
    }
    updateClipContentDraft(selectedClip.id, {
      hookText: "",
      hookSceneStart: null,
      hookSceneEnd: null
    });
  }

  function previewTitleHookSuggestion(suggestion: TitleHookSuggestion) {
    const video = videoRef.current;
    if (
      !video ||
      !selectedClip ||
      !selectedPlayerReady ||
      suggestion.hookSceneStart === null ||
      suggestion.hookSceneEnd === null ||
      suggestion.hookSceneEnd <= suggestion.hookSceneStart
    ) {
      return;
    }
    const relativePreviewStart = clamp(suggestion.hookSceneStart, 0, bodyDuration);
    const relativePreviewEnd = clamp(
      suggestion.hookSceneEnd,
      relativePreviewStart,
      bodyDuration
    );
    const previewStart = hookSceneDuration + relativePreviewStart;
    const previewEnd = hookSceneDuration + relativePreviewEnd;
    if (previewEnd <= previewStart) {
      return;
    }
    video.pause();
    video.currentTime = previewStart;
    suggestionPlaybackEndRef.current = previewEnd;
    setClipTime(previewStart);
    setPreviewingSuggestionId(suggestion.id);
    void video.play().catch(() => {
      suggestionPlaybackEndRef.current = null;
      setPreviewingSuggestionId(null);
    });
  }

  async function retrySelectedPreview() {
    if (
      !selectedClip ||
      selectedClip.previewState !== "failed" ||
      retryingPreviewClipId !== null
    ) {
      return;
    }
    const mutationGeneration = beginReviewMutation();
    setRetryingPreviewClipId(selectedClip.id);
    setError(null);
    try {
      const queued = await retrySubtitleReviewPreview(jobId, selectedClip.id);
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(queued);
      }
      const refreshed = await getSubtitleReview(jobId);
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(refreshed);
      }
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "完成表示プレビューを再生成できませんでした"
      );
    } finally {
      endReviewMutation();
      setRetryingPreviewClipId(null);
    }
  }

  async function saveHookScene(
    start: number | null,
    end: number | null
  ) {
    if (!selectedClip) {
      return;
    }
    if (dirtySegmentIds.size > 0 || hasDirtyClipContent) {
      setError(
        "未保存のタイトル、投稿情報、フック文字、文字スタイル、または字幕を先に保存してください。"
      );
      return;
    }
    beginReviewMutation();
    videoRef.current?.pause();
    setError(null);
    setIsUpdatingHookScene(true);
    try {
      await updateSubtitleReviewHookScene(jobId, selectedClip.id, {
        start,
        end
      });
    } catch (caught) {
      setIsUpdatingHookScene(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "冒頭フック映像を更新できませんでした"
      );
    } finally {
      endReviewMutation();
    }
  }

  async function saveSubtitleStructure(request: SubtitleStructureRequest) {
    if (!review || !isEditable) return;
    const oldDocument = review;
    const targets = new Set(request.segments.map(item => item.segmentId));
    const sourceSegments = oldDocument.segments.filter(segment => targets.has(segment.id));
    const affected = new Set(sourceSegments.flatMap(segment => segment.affectedClipIds));
    const first = sourceSegments[0];
    const oldIds = new Set(oldDocument.segments.map(segment => segment.id));
    const scrollTop = subtitleListRef.current?.scrollTop ?? 0;
    const generation = beginReviewMutation();
    setIsSavingStructure(true);
    videoRef.current?.pause();
    setError(null);
    try {
      const updated = await editSubtitleStructure(jobId, request);
      if (!isCurrentReviewMutation(generation)) return;
      setReview(updated);
      setDrafts(current => Object.fromEntries(updated.segments.map(segment => [segment.id,
        targets.has(segment.id) || !oldIds.has(segment.id) ? segment.text : current[segment.id] ?? segment.text])));
      setDirtySegmentIds(current => new Set([...current].filter(id => !targets.has(id))));
      setClipContentDrafts(current => {
        const next = { ...current };
        const replacementSegments = updated.segments.filter(segment => targets.has(segment.id) || !oldIds.has(segment.id));
        for (const clip of updated.clips) {
          if (!affected.has(clip.id) || !next[clip.id]) continue;
          const draft = next[clip.id];
          const firstStyle = draft.subtitleStyles.find(item => item.start === first.start && item.end === first.end)?.style;
          const keptStyles = draft.subtitleStyles.filter(item => !sourceSegments.some(segment => segment.start === item.start && segment.end === item.end));
          next[clip.id] = { ...draft, subtitleStyles: [...keptStyles, ...(firstStyle ? replacementSegments.map(segment =>
            ({ start: segment.start, end: segment.end, style: firstStyle })) : [])] };
        }
        return next;
      });
      setStyledSegmentId(null);
      setSegmentCursor(null);
      setBulkCorrectionSelection(null);
      requestAnimationFrame(() => subtitleListRef.current?.scrollTo({ top: scrollTop }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "字幕区間を変更できませんでした");
    } finally {
      setIsSavingStructure(false);
      endReviewMutation();
    }
  }

  async function confirmSelectedClip() {
    if (isSavingShortBannerSettings) {
      setError("ショート帯設定の保存完了後に確認してください。");
      return;
    }
    if (!selectedClip || !selectedClipContentDraft) {
      return;
    }
    if (selectedShortFramingDirty) {
      setError("このclipの画角調整を保存してからOKにしてください。");
      return;
    }
    const title = selectedClipContentDraft.title.trim();
    const publicationTitle = selectedClipContentDraft.publicationTitle.trim();
    if (!publicationTitle) {
      setError("公開用タイトルを入力してください。");
      return;
    }
    if (!selectedHookDurationIsValid) {
      setError("冒頭フックの表示秒数は1〜8秒で入力してください。");
      return;
    }
    const segmentUpdates = selectedSegments
      .filter((segment) => dirtySegmentIds.has(segment.id))
      .map((segment) => ({
        segmentId: segment.id,
        text: drafts[segment.id] ?? segment.text
      }));
    const savedSegmentIds = new Set(segmentUpdates.map((segment) => segment.segmentId));
    const postMetadata = postMetadataApplyPayload(selectedClipContentDraft);
    const mutationGeneration = beginReviewMutation();
    setConfirmingClipId(selectedClip.id);
    setError(null);
    try {
      const updated = await applySubtitleReviewClip(jobId, selectedClip.id, {
        title,
        publicationTitle,
        ...postMetadata,
        hookText: selectedClipContentDraft.hookText.trim(),
        hookDurationSeconds: selectedClipContentDraft.hookDurationSeconds,
        hookSceneStart: selectedClipContentDraft.hookSceneStart,
        hookSceneEnd: selectedClipContentDraft.hookSceneEnd,
        thumbnailKicker: selectedClipContentDraft.thumbnailKicker.trim(),
        thumbnailLine1: selectedClipContentDraft.thumbnailLine1.trim(),
        thumbnailLine2: selectedClipContentDraft.thumbnailLine2.trim(),
        thumbnailFrameSeconds: selectedClipContentDraft.thumbnailFrameSeconds,
        titleStyle: selectedClipContentDraft.titleStyle,
        hookStyle: selectedClipContentDraft.hookStyle,
        subtitleStyle: selectedClipContentDraft.subtitleStyle,
        subtitleStyles: selectedClipContentDraft.subtitleStyles,
        segments: segmentUpdates
      });
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(updated);
        const updatedClip = updated.clips.find((clip) => clip.id === selectedClip.id);
        if (updatedClip) {
          setClipContentDrafts((current) => ({
            ...current,
            [updatedClip.id]: contentDraftForClip(updatedClip)
          }));
        }
        setDrafts((current) => {
          const next = { ...current };
          for (const segment of updated.segments) {
            if (savedSegmentIds.has(segment.id)) {
              next[segment.id] = segment.text;
            }
          }
          return next;
        });
        setDirtySegmentIds((current) => {
          const next = new Set(current);
          for (const segmentId of savedSegmentIds) {
            next.delete(segmentId);
          }
          return next;
        });
      }

    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "clipの内容を保存できませんでした");
    } finally {
      endReviewMutation();
      setConfirmingClipId(null);
    }
  }

  async function startRendering() {
    if (isSavingShortBannerSettings) {
      setError("ショート帯設定の保存完了後にレンダリングしてください。");
      return;
    }
    if (hasDirtyShortFraming) {
      setError("未保存のショート画角があります。各clipの画角を保存してください。");
      return;
    }
    if (!review || dirtySegmentIds.size > 0 || hasDirtyClipContent) {
      setError("未保存のタイトル、投稿情報、フック、または字幕があります。先に保存してください。");
      return;
    }
    if (!allPreviewsReady) {
      setError("全clipの完成表示プレビューが揃ってからレンダリングしてください。");
      return;
    }
    beginReviewMutation();
    setIsFinalizing(true);
    setError(null);
    try {
      await finalizeSubtitleReview(jobId);
      router.push(`/jobs/${jobId}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "レンダリングを開始できませんでした");
      setIsFinalizing(false);
    } finally {
      endReviewMutation();
    }
  }

  if (!review) {
    return (
      <main className="min-h-screen bg-[#f7f7f4] px-6 py-8 text-neutral-950">
        <div className="mx-auto w-full max-w-6xl border border-neutral-300 bg-white p-6 text-sm">
          {error ?? "字幕確認データを読み込んでいます"}
        </div>
      </main>
    );
  }

  const allConfirmed =
    review.totalClipCount > 0 && review.confirmedClipCount === review.totalClipCount;

  return (
    <main className="subtitle-review-screen min-h-screen bg-[#f7f7f4] px-3 py-2 text-neutral-950 sm:px-5">
      <section className="subtitle-review-shell mx-auto flex w-full flex-col gap-2">
        <header className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-2 border-b border-neutral-300 py-1">
          <h1 className="text-lg font-semibold sm:text-xl">clip別 字幕確認</h1>
          <p className="text-xs text-neutral-600">
            確認 {review.confirmedClipCount} / {review.totalClipCount} ・ 修正{" "}
            {review.editedSegmentCount}件
          </p>
          <span
            className={`px-2 py-1 text-[11px] font-semibold ${
              review.state === "completed"
                ? "bg-emerald-100 text-emerald-800"
                : review.state === "awaiting_review"
                  ? "bg-sky-100 text-sky-800"
                  : "bg-amber-100 text-amber-800"
            }`}
          >
            {review.state === "completed"
              ? "完了"
              : review.state === "awaiting_review"
                ? hasReviewMutationInFlight ? "保存中" : "字幕確認中"
                : "書き出し中"}
          </span>
          <Link
            className="ml-auto inline-flex min-h-9 items-center border border-neutral-300 bg-white px-3 text-xs font-medium sm:text-sm"
            href={`/jobs/${jobId}`}
          >
            処理状況へ戻る
          </Link>
        </header>

        {review.state !== "awaiting_review" ? (
          <div className="border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-900">
            {review.state === "completed"
              ? "字幕確認と書き出しは完了しています。この画面は確認履歴として表示しています。"
              : "字幕は確定済みです。現在、動画を書き出しています。"}
          </div>
        ) : null}

        {error ? (
          <div className="border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        <div data-clip-type={selectedClip?.type} className="subtitle-review-grid grid overflow-hidden border border-neutral-300 bg-white lg:grid-cols-[230px_minmax(0,1fr)_390px] xl:grid-cols-[260px_minmax(0,1fr)_clamp(360px,26vw,480px)] 2xl:h-[calc(100vh-4.5rem)] 2xl:min-h-[760px] 2xl:grid-cols-[clamp(210px,13vw,260px)_minmax(560px,1fr)_clamp(320px,22vw,440px)] 2xl:grid-rows-[minmax(500px,62vh)_minmax(260px,1fr)]">
          <aside className="subtitle-review-clips flex min-h-0 flex-col border border-neutral-300">
<div
          aria-label="編集する動画形式"
          className="grid grid-cols-1 border border-neutral-300 bg-neutral-100 p-1"
          role="tablist"
        >
          <button
            aria-selected={activeClipType === "normal"}
            className={`min-h-11 px-2 text-sm font-semibold ${
              activeClipType === "normal"
                ? "bg-neutral-950 text-white"
                : "bg-white text-neutral-700"
            } disabled:cursor-not-allowed disabled:text-neutral-400`}
            disabled={normalClips.length === 0}
            role="tab"
            type="button"
            onClick={() => selectClipType("normal")}
          >
            通常編集（{normalClips.length}本）
          </button>
          <button
            aria-selected={activeClipType === "short"}
            className={`min-h-11 px-2 text-sm font-semibold ${
              activeClipType === "short"
                ? "bg-neutral-950 text-white"
                : "bg-white text-neutral-700"
            } disabled:cursor-not-allowed disabled:text-neutral-400`}
            disabled={shortClips.length === 0}
            role="tab"
            type="button"
            onClick={() => selectClipType("short")}
          >
            ショート編集（{shortClips.length}本）
          </button>
        </div>
            <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="border-b border-neutral-200 px-4 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold">
                  {activeClipType === "normal" ? "通常clip" : "ショートclip"}
                </p>
                <div className="flex flex-wrap justify-end gap-1">
                  {isEditable &&
                  (review.renderRevision > 1 || review.reeditSourceJobId) ? (
                    <span className="bg-violet-100 px-2 py-1 text-[10px] font-semibold text-violet-800">
                      1本のみ再編集
                    </span>
                  ) : null}
                  {openedFromReupload ? (
                    <span className="bg-emerald-100 px-2 py-1 text-[10px] font-semibold text-emerald-800">
                      MP4照合済み
                    </span>
                  ) : null}
                </div>
              </div>
              <p className="mt-1 text-xs text-neutral-500">選ぶと動画と字幕が切り替わります</p>
              <div className="mt-3 h-2 overflow-hidden bg-neutral-100">
                <div
                  className="h-full bg-sky-600"
                  style={{
                    width: `${review.totalClipCount > 0
                      ? (review.confirmedClipCount / review.totalClipCount) * 100
                      : 0}%`
                  }}
                />
              </div>
            </div>
            <div className="max-h-64 min-h-0 overflow-y-auto lg:max-h-none lg:flex-1">
              {visibleClips.map((clip) => {
                const clipDraft = clipContentDrafts[clip.id];
                const contentDirty = isClipContentDirty(clip, clipContentDrafts);
                return (
                  <button
                    className={`block w-full border-b border-neutral-200 px-4 py-4 text-left disabled:cursor-wait disabled:opacity-60 ${
                      clip.id === selectedClipId ? "bg-neutral-950 text-white" : "bg-white"
                    }`}
                    disabled={isUpdatingHookScene}
                    key={clip.id}
                    type="button"
                    onClick={() => selectClip(clip)}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <span className="text-xs font-semibold uppercase">
                        {clipLabel(clip, review.clips)}
                      </span>
                      <span
                        className={`text-xs font-medium ${
                          contentDirty
                            ? clip.id === selectedClipId
                              ? "text-amber-200"
                              : "text-amber-700"
                            : clip.confirmed
                              ? clip.id === selectedClipId
                                ? "text-emerald-300"
                                : "text-emerald-700"
                              : clip.id === selectedClipId
                                ? "text-amber-200"
                                : "text-amber-700"
                        }`}
                      >
                        {contentDirty ? "未保存" : clip.confirmed ? "確認済み" : "未確認"}
                      </span>
                    </span>
                    <span className="mt-2 block line-clamp-2 text-sm font-medium">
                      {clipDraft ? clipDraft.title : clip.title}
                    </span>
                    {!isPreviewReady(clip, review.state) ? (
                      <span
                        className={`mt-2 block text-[11px] font-semibold ${
                          clip.previewState === "failed"
                            ? clip.id === selectedClipId
                              ? "text-red-200"
                              : "text-red-700"
                            : clip.id === selectedClipId
                              ? "text-sky-200"
                              : "text-sky-700"
                        }`}
                      >
                        {clip.previewState === "failed"
                          ? "プレビュー生成失敗"
                          : "完成表示プレビューを更新中"}
                      </span>
                    ) : null}
                    <span
                      className={`mt-2 block text-xs ${
                        clip.id === selectedClipId ? "text-neutral-300" : "text-neutral-500"
                      }`}
                    >
                      clip長 {formatTime(clip.duration)} ・ {clip.segmentIds.length}字幕
                      {clip.hookSceneStart !== null &&
                      clip.hookSceneEnd !== null
                        ? ` ・ 冒頭複製${formatTime(
                            clip.hookSceneEnd - clip.hookSceneStart
                          )}`
                        : ""}
                      {clip.editedSegmentCount > 0
                        ? ` ・ 修正${clip.editedSegmentCount}件`
                        : ""}
                      {clip.id === selectedClipId
                        ? ` ・ 本編${formatTime(bodyDuration)} ・ 元動画${formatTime(
                            clip.start
                          )}-${formatTime(clip.end)}`
                        : ""}
                    </span>
                  </button>
                );
              })}
            </div>
              <div className="border-t border-neutral-300 bg-neutral-50 p-3">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="font-semibold">
                  確認 {review.confirmedClipCount} / {review.totalClipCount}
                </span>
                <span className="text-neutral-500">修正 {review.editedSegmentCount}件</span>
              </div>
              <button
                className="mt-2 min-h-10 w-full bg-emerald-700 px-3 py-2 text-xs font-semibold text-white disabled:bg-neutral-300"
                disabled={
                  !isEditable ||
                  !allConfirmed ||
                  !allPreviewsReady ||
                  dirtySegmentIds.size > 0 ||
                  hasDirtyClipContent ||
                  hasDirtyShortFraming ||
                  isSavingShortBannerSettings ||
                  isFinalizing
                }
                type="button"
                onClick={() => void startRendering()}
              >
                {isFinalizing
                  ? "レンダリング開始中"
                  : hasDirtyShortFraming
                    ? "未保存のショート画角があります"
                  : !allPreviewsReady
                    ? "プレビュー更新完了を待っています"
                    : "字幕を確定してレンダリング"}
              </button>
              </div>
            </div>
          </aside>



          <section className="subtitle-review-player flex min-w-0 flex-col border-b border-neutral-300 lg:border-r 2xl:min-h-0 2xl:overflow-hidden">
            {selectedClip ? (
              <>
                <div
                  className={`flex min-h-0 flex-1 flex-col ${
                    selectedClip.type === "short"
                      ? "2xl:grid 2xl:grid-cols-[340px_minmax(0,1fr)]"
                      : ""
                  }`}
                >
                {selectedClip.type === "short" ? (
                  <div className="min-w-0 2xl:min-h-0 2xl:overflow-y-auto 2xl:border-r 2xl:border-neutral-300">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-300 bg-white px-4 py-2">
                      <div>
                        <p className="text-sm font-semibold text-neutral-900">ショート画角</p>
                        <p className="text-xs text-neutral-500">
                          配置を試してから保存。試し表示では動画を再生成しません
                        </p>
                      </div>

                    </div>
                    {selectedShortFramingDraft ? (
                      <div className="space-y-3 border-b border-neutral-300 bg-neutral-50 px-4 py-3">
                        <p className="text-sm font-semibold">このショートのみ微調整</p>
                        <p className="text-xs text-neutral-600">元映像の枠を動かして確認。位置・倍率は待たずに反映します。</p>
                        <ShortFramingWorkspace
                          key={`${selectedClip.id}:${selectedClip.start}:${selectedClip.end}:${review.sourceVideoUrl}:${review.shortTopBannerEnabled}:${review.shortBottomBannerEnabled}`}
                          jobId={jobId} clipId={selectedClip.id} sourceUrl={review.sourceVideoUrl}
                          start={selectedClip.start} end={selectedClip.end}
                          value={selectedShortFramingDraft} layout={selectedClip.shortLayout ?? review.shortLayout} editable={isEditable && !hasReviewMutationInFlight}
                          onSave={async (next) => {
                            changeSelectedShortFraming(next);
                            return saveSelectedShortFraming(selectedClip.id, next);
                          }}
                        />
                        <p className="text-xs text-neutral-600">
                          左右 {selectedShortFramingDraft.framingOffsetX} ・ 上下 {selectedShortFramingDraft.framingOffsetY} ・ 拡大 {Math.round(selectedShortFramingDraft.framingZoom * 100)}%
                        </p>
                        <p className="text-xs font-semibold text-sky-700" aria-live="polite">
                          {selectedShortPreviewRegenerating ? "保存した画角で動画を再生成中" : selectedShortFramingDirty ? "未保存の変更あり" : "保存済み"}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="subtitle-video-area flex items-start justify-center bg-neutral-100 p-3 sm:p-4 2xl:h-full 2xl:min-h-0 2xl:flex-1 2xl:items-stretch 2xl:overflow-hidden">
                  <div
                    className="subtitle-video-chrome w-full max-w-5xl overflow-hidden bg-neutral-950 text-white 2xl:flex 2xl:min-h-0 2xl:flex-col"
                    ref={playerShellRef}
                  >
                    <div className="subtitle-video-fit flex items-center justify-center bg-black 2xl:min-h-0 2xl:flex-1 2xl:overflow-hidden">
                      <div
                        className={`relative overflow-hidden bg-black ${
                          selectedClip.type === "short"
                            ? "aspect-[9/16] w-full max-w-[360px] 2xl:h-full 2xl:w-auto 2xl:max-w-full"
                            : "aspect-video w-full max-w-5xl 2xl:h-full 2xl:w-auto 2xl:max-w-full"
                        }`}
                        style={{ containerType: "inline-size" }}
                      >
                      {selectedPlayerReady && selectedPlayerVideoUrl ? (
                        <video
                        className="h-full w-full cursor-pointer bg-black object-contain"
                        key={`${selectedClip.id}:${selectedPlayerVideoUrl}:${selectedPlayerPreviewVersion}`}
                        playsInline
                        preload="metadata"
                        ref={videoRef}
                        src={previewVideoSrc(
                          selectedPlayerVideoUrl,
                          selectedPlayerPreviewVersion
                        )}
                        onCanPlay={() => {
                          setPreviewLoadFailedClipIds((current) => {
                            const next = new Set(current);
                            next.delete(selectedClip.id);
                            return next;
                          });
                          setIsBuffering(false);
                          setIsPlayerReady(true);
                        }}
                        onClick={togglePlayback}
                        onError={handleVideoError}
                        onLoadedMetadata={() => setIsPlayerReady(true)}
                        onLoadStart={() => {
                          setIsPlaying(false);
                          setIsPlayerReady(false);
                          setIsBuffering(true);
                          setVideoLoadSeconds(0);
                        }}
                        onPause={() => setIsPlaying(false)}
                        onPlay={() => setIsPlaying(true)}
                        onPlaying={() => setIsBuffering(false)}
                        onSeeking={handleVideoSeeking}
                        onTimeUpdate={handleVideoTimeUpdate}
                        onWaiting={() => setIsBuffering(true)}
                        />
                      ) : null}
                      {isShowingLivePreview && selectedClip ? (
                        <>
                          {showLiveTitle ? (
                            <ClipTextOverlay
                              clipType={selectedClip.type}
                              defaultResolvedStyle={
                                selectedDefaultResolvedClipTextStyles.title
                              }
                              previewWidth={selectedClip.previewWidth}
                              resolvedStyle={selectedResolvedClipTextStyles.title}
                              style={selectedClipTextStyles.title}
                              target="title"
                              text={selectedClipContentDraft?.title ?? ""}
                            />
                          ) : null}
                          {showLiveHook ? (
                            <ClipTextOverlay
                              clipType={selectedClip.type}
                              defaultResolvedStyle={
                                selectedDefaultResolvedClipTextStyles.hook
                              }
                              previewWidth={selectedClip.previewWidth}
                              resolvedStyle={selectedResolvedClipTextStyles.hook}
                              style={selectedClipTextStyles.hook}
                              target="hook"
                              text={liveHookText}
                            />
                          ) : null}
                          {showLiveSubtitle ? (
                            <ClipTextOverlay
                              clipType={selectedClip.type}
                              defaultResolvedStyle={
                                selectedDefaultResolvedClipTextStyles.subtitle
                              }
                              previewWidth={selectedClip.previewWidth}
                              resolvedStyle={selectedResolvedClipTextStyles.subtitle}
                              style={activePreviewSubtitleEvent?.style ?? selectedClipTextStyles.subtitle}
                              subtitleMaxCharsPerLine={
                                selectedClip.subtitleMaxCharsPerLine
                              }
                              subtitleMaxLines={activePreviewSubtitleEvent?.singleLine ? 1 : selectedClip.subtitleMaxLines}
                              target="subtitle"
                              text={activePreviewSubtitleEvent?.text ?? ""}
                            />
                          ) : null}
                        </>
                      ) : null}
                      {!selectedPlayerReady ? (
                        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-neutral-950 px-5 text-center text-sm font-semibold">
                          <p>
                            {selectedClip.previewState === "failed"
                              ? "完成表示と同じプレビューの生成に失敗しました"
                              : "完成表示と同じプレビューを更新中"}
                          </p>
                          {selectedClip.previewState === "failed" &&
                          selectedClip.previewError ? (
                            <p className="max-w-md text-xs font-normal text-red-200">
                              {selectedClip.previewError}
                            </p>
                          ) : null}
                          {selectedClip.previewState === "failed" ? (
                            <button
                              className="min-h-10 border border-white bg-white px-4 text-sm font-semibold text-neutral-950 disabled:border-neutral-500 disabled:bg-neutral-700 disabled:text-neutral-300"
                              disabled={!isEditable || retryingPreviewClipId !== null}
                              type="button"
                              onClick={() => void retrySelectedPreview()}
                            >
                              {retryingPreviewClipId === selectedClip.id
                                ? "再生成を開始中"
                                : "プレビューを再生成"}
                            </button>
                          ) : null}
                          {selectedClip.previewState === "queued" ||
                          selectedClip.previewState === "rendering" ? (
                            <p className="text-xs font-normal text-neutral-300">
                              完成動画と同じ縦横比・画角・字幕・タイトル・帯を準備しています。
                            </p>
                          ) : null}
                        </div>
                      ) : !isPlayerReady || isBuffering ? (
                        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/60 px-5 text-center text-sm font-semibold">
                          <p>
                            {selectedPreviewLoadFailed
                              ? "完成表示と同じプレビューを読み込めませんでした"
                              : isPlayerReady
                              ? "選択位置を読み込み中"
                              : `完成表示と同じプレビューを読み込み中 (${videoLoadSeconds}秒)`}
                          </p>
                          {selectedPreviewLoadFailed || videoLoadSeconds >= 15 ? (
                            <>
                              {!selectedPreviewLoadFailed ? (
                                <p className="text-xs font-normal text-neutral-200">
                                  読み込みに時間がかかっています。停止状態ではありません。
                                </p>
                              ) : null}
                              <button
                                className="min-h-10 border border-white bg-white px-4 text-sm font-semibold text-neutral-950"
                                type="button"
                                onClick={retryVideoLoad}
                              >
                                動画を再読み込み
                              </button>
                            </>
                          ) : null}
                        </div>
                      ) : null}
                      </div>
                    </div>

                    {selectedPlayerReady ? (
                    <div className="shrink-0 border-t border-neutral-700 bg-neutral-900 px-3 py-2">
                      <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                        <span>{isShowingLivePreview ? "編集プレビュー" : "保存済みプレビュー"}</span>
                        {livePreviewReady && selectedPreviewReady ? (
                          <button className="border border-neutral-600 px-2 py-1" type="button"
                            onClick={() => setShowSavedPreview((current) => !current)}>
                            {isShowingLivePreview ? "保存済みを見る" : "編集プレビューへ戻る"}
                          </button>
                        ) : null}
                      </div>
                      <input
                        aria-label="clip再生位置"
                        className="block h-2 w-full cursor-pointer accent-sky-500"
                        max={Math.max(clipDuration, 0.1)}
                        min={0}
                        step={0.05}
                        type="range"
                        value={clamp(clipTime, 0, clipDuration)}
                        onChange={(event) => seekToClipTime(Number(event.target.value))}
                      />
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <button
                          aria-label={isPlaying ? "一時停止" : "再生"}
                          className="min-h-10 min-w-20 bg-white px-3 text-sm font-semibold text-neutral-950"
                          type="button"
                          onClick={togglePlayback}
                        >
                          {isPlaying ? "一時停止" : "再生"}
                        </button>
                        <button
                          aria-label="clip先頭から再生"
                          className="min-h-10 border border-neutral-600 px-3 text-sm font-medium"
                          type="button"
                          onClick={playFromClipStart}
                        >
                          先頭
                        </button>
                        <button
                          aria-label="5秒戻る"
                          className="min-h-10 border border-neutral-600 px-2 text-sm font-medium"
                          type="button"
                          onClick={() => skipBy(-5)}
                        >
                          -5秒
                        </button>
                        <button
                          aria-label="1秒戻る"
                          className="min-h-10 border border-neutral-600 px-2 text-sm font-medium"
                          type="button"
                          onClick={() => skipBy(-1)}
                        >
                          -1秒
                        </button>
                        <button
                          aria-label="1秒進む"
                          className="min-h-10 border border-neutral-600 px-2 text-sm font-medium"
                          type="button"
                          onClick={() => skipBy(1)}
                        >
                          +1秒
                        </button>
                        <button
                          aria-label="5秒進む"
                          className="min-h-10 border border-neutral-600 px-2 text-sm font-medium"
                          type="button"
                          onClick={() => skipBy(5)}
                        >
                          +5秒
                        </button>
                        <span className="min-w-32 text-sm font-medium tabular-nums">
                          {formatTime(clipTime)} / {formatTime(clipDuration)}
                        </span>
                        <div className="ml-auto flex flex-wrap items-center gap-2">
                          <button
                            aria-label={isMuted ? "音声をオン" : "ミュート"}
                            className="min-h-10 border border-neutral-600 px-3 text-sm font-medium"
                            type="button"
                            onClick={toggleMuted}
                          >
                            {isMuted ? "音声オフ" : "音声オン"}
                          </button>
                          <input
                            aria-label="音量"
                            className="w-20 accent-sky-500"
                            max={1}
                            min={0}
                            step={0.05}
                            type="range"
                            value={isMuted ? 0 : volume}
                            onChange={(event) => changeVolume(Number(event.target.value))}
                          />
                          <select
                            aria-label="再生速度"
                            className="min-h-10 border border-neutral-600 bg-neutral-900 px-2 text-sm"
                            value={playbackRate}
                            onChange={(event) => changePlaybackRate(Number(event.target.value))}
                          >
                            <option value={0.75}>0.75x</option>
                            <option value={1}>1.0x</option>
                            <option value={1.25}>1.25x</option>
                            <option value={1.5}>1.5x</option>
                            <option value={2}>2.0x</option>
                          </select>
                          <button
                            aria-label="全画面"
                            className="min-h-10 border border-neutral-600 px-3 text-sm font-medium"
                            type="button"
                            onClick={() => void toggleFullscreen()}
                          >
                            全画面
                          </button>
                        </div>
                      </div>
                      </div>
                    ) : null}
                  </div>
                </div>
                </div>
              </>
            ) : null}
          </section>

          <section className="contents">
            {selectedClip ? (
              <div className="contents">
                <div data-tab={workspaceTab} className="subtitle-review-editors grid min-w-0 bg-white lg:col-span-3 lg:row-start-2 2xl:col-span-3 2xl:col-start-1 2xl:row-start-2 2xl:h-full 2xl:min-h-0 2xl:grid-cols-4 2xl:overflow-hidden">
                  <div role="tablist" aria-label="編集項目" className="subtitle-editor-tabs flex border-b bg-neutral-50">
                    <button type="button" role="tab" aria-selected={workspaceTab === "content"} onClick={() => setWorkspaceTab("content")} className="px-4 py-2 text-sm font-semibold aria-selected:bg-neutral-950 aria-selected:text-white">タイトル・フック</button>
                    <button type="button" role="tab" aria-selected={workspaceTab === "style"} onClick={() => setWorkspaceTab("style")} className="px-4 py-2 text-sm font-semibold aria-selected:bg-neutral-950 aria-selected:text-white">書式・位置・色</button>
                  </div>
                  <div key={`content-${selectedClip.id}`} className="subtitle-content-editor min-w-0 border-b border-neutral-300 bg-neutral-50 p-3 2xl:h-full 2xl:min-h-0 2xl:overflow-y-auto 2xl:border-b-0 2xl:border-r">
                    <div className="subtitle-content-fields">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-semibold">タイトル・フック</h3>
                      {selectedClipHasDirtyContent ? (
                        <span className="bg-amber-100 px-2 py-1 text-[11px] font-semibold text-amber-800">
                          未保存
                        </span>
                      ) : selectedClip.titleEdited || selectedClip.hookText ? (
                        <span className="bg-emerald-100 px-2 py-1 text-[11px] font-semibold text-emerald-800">
                          保存済み
                        </span>
                      ) : null}
                    </div>

                    <label className="mt-2 block text-xs font-semibold text-neutral-700">
                      公開用タイトル
                      <input
                        className="mt-1 min-h-9 w-full border border-neutral-300 bg-white px-2 text-sm outline-none focus:border-sky-600"
                        disabled={!isEditable}
                        maxLength={100}
                        type="text"
                        value={selectedClipContentDraft?.publicationTitle ?? ""}
                        onChange={(event) =>
                          updateClipContentDraft(selectedClip.id, {
                            publicationTitle: event.target.value,
                            selectedTitleId: null,
                            postMetadataSource: "manual"
                          })
                        }
                      />
                    </label>
                    <p className="mt-1 text-right text-[10px] text-neutral-500">
                      {selectedClipContentDraft?.publicationTitle.length ?? 0} / 100
                    </p>

                    <label className="mt-2 block text-xs font-semibold text-neutral-700">
                      動画内タイトル
                      <textarea
                        className="mt-1 min-h-14 w-full resize-y border border-neutral-300 bg-white px-2 py-2 text-sm leading-5 outline-none focus:border-sky-600"
                        disabled={!isEditable}
                        maxLength={80}
                        placeholder="空欄なら非表示。2行にする位置でEnter"
                        rows={2}
                        value={selectedClipContentDraft?.title ?? ""}
                        onChange={(event) =>
                          updateClipContentDraft(selectedClip.id, {
                            title: limitToTwoTextLines(event.target.value)
                          })
                        }
                      />
                    </label>
                    <div className="mt-1 flex items-center justify-between gap-3 text-[10px] text-neutral-500">
                      <span>空欄なら非表示。Enterを入れた位置で2行表示します（最大2行）</span>
                      <span>{selectedClipContentDraft?.title.length ?? 0} / 80</span>
                    </div>
                    <ReviewCharacterPreset disabled={!isEditable || hasReviewMutationInFlight}
                      onApply={characterPresetName => saveShortBannerSettings(
                        review.shortLayout, review.shortTopBannerEnabled, review.shortBottomBannerEnabled, { characterPresetName }
                      )} />
                    {selectedClip.type === "short" ? (
                      <fieldset className="mt-3 border-t border-neutral-300 pt-3">
                          <legend className="sr-only">ショート帯（書出し時）</legend>
                          <div className="grid min-h-10 grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)] border border-neutral-300 bg-white">
                            <span
                              aria-live="polite"
                              className="flex items-center border-r border-neutral-300 bg-neutral-50 px-3 text-sm font-semibold text-neutral-700"
                            >
                              {isSavingShortBannerSettings ? "保存中" : "上下帯（基本ON）"}
                            </span>
                            <label className="flex cursor-pointer items-center gap-2 border-r border-neutral-300 px-3">
                              <input
                                checked={review.shortTopBannerEnabled}
                                className="h-4 w-4"
                                disabled={!isEditable || isSavingShortBannerSettings}
                                type="checkbox"
                                onChange={(event) =>
                                  void saveShortBannerSettings(
                                    review.shortLayout,
                                    event.target.checked,
                                    review.shortBottomBannerEnabled
                                  )
                                }
                              />
                              <span className="text-sm font-semibold text-neutral-700">
                                上: 柄帯
                              </span>
                            </label>
                            <label className="flex cursor-pointer items-center gap-2 px-3">
                              <input
                                checked={review.shortBottomBannerEnabled}
                                className="h-4 w-4"
                                disabled={!isEditable || isSavingShortBannerSettings}
                                type="checkbox"
                                onChange={(event) =>
                                  void saveShortBannerSettings(
                                    review.shortLayout,
                                    review.shortTopBannerEnabled,
                                    event.target.checked
                                  )
                                }
                              />
                              <span className="text-sm font-semibold text-neutral-700">
                                下: ロゴ
                              </span>
                            </label>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-neutral-500">
                            帯をONにすると、映像は帯の間へ収まり、顔や頭が帯の下へ隠れにくくなります。
                          </p>
                      </fieldset>
                    ) : null}

                    <label className="mt-2 block text-xs font-semibold text-neutral-700">
                      冒頭フック
                      <textarea
                        className="mt-1 min-h-14 w-full resize-y border border-neutral-300 bg-white px-2 py-2 text-sm leading-5 outline-none focus:border-sky-600"
                        disabled={!isEditable}
                        maxLength={120}
                        placeholder="空欄なら表示しません"
                        value={selectedClipContentDraft?.hookText ?? ""}
                        onChange={(event) => {
                          const hookText = limitToTwoTextLines(event.target.value);
                          updateClipContentDraft(selectedClip.id, {
                            hookText,
                            ...(hookText.trim()
                              ? {}
                              : { hookSceneStart: null, hookSceneEnd: null })
                          });
                        }}
                      />
                    </label>
                    <p className="mt-1 text-[10px] text-neutral-500">
                      Enterを入れた位置で2行表示します（最大2行）
                    </p>
                    <div className="mt-2 flex items-end justify-between gap-3">
                      <label className="block text-xs font-semibold text-neutral-700">
                        表示秒数
                        <input
                          aria-invalid={!selectedHookDurationIsValid}
                          className="mt-1 h-9 w-20 border border-neutral-300 bg-white px-2 text-sm tabular-nums outline-none focus:border-sky-600"
                          disabled={!isEditable}
                          max={8}
                          min={1}
                          step={0.5}
                          type="number"
                          value={selectedClipContentDraft?.hookDurationSeconds ?? 3}
                          onChange={(event) =>
                            updateClipContentDraft(selectedClip.id, {
                              hookDurationSeconds: Number(event.target.value)
                            })
                          }
                        />
                      </label>
                      <p className="text-[10px] text-neutral-500">
                        {selectedClipContentDraft?.hookText.length ?? 0} / 120
                      </p>
                    </div>
                    {!selectedHookDurationIsValid ? (
                      <p className="mt-1 text-xs font-semibold text-red-700">
                        1〜8秒で入力してください。
                      </p>
                    ) : null}

                    {selectedClip.type === "normal" && <p className="mt-3 border-t border-neutral-300 pt-3 text-xs text-neutral-600">
                      サムネの文言・書式・場面は、書き出し後の結果画面でまとめて調整できます。
                    </p>}

                    <section className="mt-3 border-t border-neutral-300 pt-3">
                      <div className="flex items-center justify-between gap-2">
                        <h4 className="text-xs font-semibold text-neutral-800">
                          YouTube投稿用
                        </h4>
                        {selectedClipContentDraft?.postMetadataSource ? (
                          <span className="text-[10px] text-neutral-500">
                            {selectedClipContentDraft.postMetadataSource}
                          </span>
                        ) : null}
                      </div>
                      <label className="mt-2 block text-xs font-semibold text-neutral-700">
                        説明欄
                        <textarea
                          className="mt-1 min-h-28 w-full resize-y border border-neutral-300 bg-white px-2 py-2 text-sm leading-5 outline-none focus:border-sky-600"
                          disabled={!isEditable}
                          maxLength={2000}
                          placeholder="動画の要約・見どころ"
                          value={selectedClipContentDraft?.youtubeDescription ?? ""}
                          onChange={(event) =>
                            updateClipContentDraft(selectedClip.id, {
                              youtubeDescription: event.target.value,
                              descriptionEvidenceSegmentIds: [],
                              postMetadataSource: "manual"
                            })
                          }
                        />
                      </label>
                      <p className="mt-1 text-right text-[10px] text-neutral-500">
                        {selectedClipContentDraft?.youtubeDescription.length ?? 0} / 2000
                      </p>
                      <label className="mt-2 block text-xs font-semibold text-neutral-700">
                        ハッシュタグ
                        <input
                          className="mt-1 min-h-9 w-full border border-neutral-300 bg-white px-2 text-sm outline-none focus:border-sky-600"
                          disabled={!isEditable}
                          maxLength={500}
                          placeholder="#切り抜き #ショート"
                          type="text"
                          value={selectedClipContentDraft?.youtubeHashtagsText ?? ""}
                          onChange={(event) =>
                            updateClipContentDraft(selectedClip.id, {
                              youtubeHashtagsText: event.target.value,
                              postMetadataSource: "manual"
                            })
                          }
                        />
                      </label>
                      <p className="mt-1 text-[10px] text-neutral-500">
                        空白またはカンマ区切り・最大12個
                      </p>
                      <label className="mt-2 block text-xs font-semibold text-neutral-700">
                        タグ
                        <textarea
                          className="mt-1 min-h-20 w-full resize-y border border-neutral-300 bg-white px-2 py-2 text-sm leading-5 outline-none focus:border-sky-600"
                          disabled={!isEditable}
                          maxLength={500}
                          placeholder="儒烏風亭らでん,ReGLOSS,ホロライブ切り抜き"
                          value={selectedClipContentDraft?.youtubeTagsText ?? ""}
                          onChange={(event) =>
                            updateClipContentDraft(selectedClip.id, {
                              youtubeTagsText: event.target.value,
                              postMetadataSource: "manual"
                            })
                          }
                        />
                      </label>
                      <p className="mt-1 text-[10px] text-neutral-500">
                        カンマ区切り・最大500文字
                      </p>
                      <div className="mt-2 grid grid-cols-2 gap-1 sm:grid-cols-4">
                        <button
                          className="min-h-9 border border-neutral-400 bg-white px-2 text-[11px] font-semibold disabled:text-neutral-400"
                          disabled={!selectedClipContentDraft?.publicationTitle.trim()}
                          type="button"
                          onClick={() =>
                            void copyPostField(
                              "title",
                              selectedClipContentDraft?.publicationTitle ?? ""
                            )
                          }
                        >
                          {copiedPostField === "title" ? "コピー済み" : "タイトルをコピー"}
                        </button>
                        <button
                          className="min-h-9 border border-neutral-400 bg-white px-2 text-[11px] font-semibold disabled:text-neutral-400"
                          disabled={!selectedClipContentDraft?.youtubeDescription.trim()}
                          type="button"
                          onClick={() =>
                            void copyPostField(
                              "description",
                              descriptionWithHashtags(
                                selectedClipContentDraft?.youtubeDescription ?? "",
                                hashtagsFromText(
                                  selectedClipContentDraft?.youtubeHashtagsText ?? ""
                                )
                              )
                            )
                          }
                        >
                          {copiedPostField === "description"
                            ? "コピー済み"
                            : "説明欄をコピー"}
                        </button>
                        <button
                          className="min-h-9 border border-neutral-400 bg-white px-2 text-[11px] font-semibold disabled:text-neutral-400"
                          disabled={!selectedClipContentDraft?.youtubeTagsText.trim()}
                          type="button"
                          onClick={() =>
                            void copyPostField(
                              "tags",
                              youtubeTagsText(
                                tagsFromText(selectedClipContentDraft?.youtubeTagsText ?? "")
                              )
                            )
                          }
                        >
                          {copiedPostField === "tags" ? "コピー済み" : "タグをコピー"}
                        </button>
                        <button
                          className="min-h-9 border border-neutral-400 bg-white px-2 text-[11px] font-semibold disabled:text-neutral-400"
                          disabled={
                            !postCopyText(
                              selectedClipContentDraft?.publicationTitle ?? "",
                              selectedClipContentDraft?.youtubeDescription ?? "",
                              hashtagsFromText(
                                selectedClipContentDraft?.youtubeHashtagsText ?? ""
                              )
                            )
                          }
                          type="button"
                          onClick={() =>
                            void copyPostField(
                              "all",
                              postCopyText(
                                selectedClipContentDraft?.publicationTitle ?? "",
                                selectedClipContentDraft?.youtubeDescription ?? "",
                                hashtagsFromText(
                                  selectedClipContentDraft?.youtubeHashtagsText ?? ""
                                )
                              )
                            )
                          }
                        >
                          {copiedPostField === "all" ? "コピー済み" : "全部コピー"}
                        </button>
                      </div>
                    </section>

                    </div>
                    <div className="subtitle-content-suggestions">
                    <TitleHookSuggestionPanel
                      busy={
                        requestingSuggestionClipId === selectedClip.id ||
                        autoGeneratingSuggestionClipIds.has(selectedClip.id)
                      }
                      canPreview={selectedPlayerReady}
                      disabled={!isEditable}
                      previewingSuggestionId={previewingSuggestionId}
                      response={selectedSuggestionRecord?.response ?? null}
                      selectedSuggestionId={selectedClipContentDraft?.selectedTitleId ?? null}
                      stale={selectedSuggestionsAreStale}
                      onApply={applyTitleHookSuggestion}
                      onClearHook={clearSelectedHook}
                      onGenerate={(forceRegenerate) =>
                        void generateTitleHookSuggestions(forceRegenerate)
                      }
                      onPreview={previewTitleHookSuggestion}
                    />
                    {selectedClipContentDraft &&
                    (selectedClipContentDraft.hookSceneStart !== selectedClip.hookSceneStart ||
                      selectedClipContentDraft.hookSceneEnd !== selectedClip.hookSceneEnd) ? (
                      <p className="mt-2 border border-violet-200 bg-violet-50 px-3 py-2 text-xs font-medium text-violet-900">
                        投稿案のフック映像区間は、右下のOKでタイトル・字幕とまとめて保存します。
                      </p>
                    ) : null}

                    <p className="mt-3 border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-medium text-sky-900">
                      変更はメインへ即時反映します。右下のOKで字幕修正もまとめて保存します。
                    </p>

                    <>
                        {dirtySegmentIds.size > 0 || hasDirtyClipContent ? (
                          <p className="mt-2 border border-amber-300 bg-amber-50 px-2 py-2 text-[11px] font-medium text-amber-900">
                            フック映像の変更前に、文字設定と字幕を保存してください。
                          </p>
                        ) : null}
                        <details className="mt-2 border border-neutral-300 bg-white">
                          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">
                            フック映像設定
                          </summary>
                          <div className="border-t border-neutral-300">
                            <ClipHookSceneEditor
                              clip={selectedClip}
                              disabled={
                                !isEditable ||
                                dirtySegmentIds.size > 0 ||
                                hasDirtyClipContent
                              }
                              enforceMaximumDuration={selectedClip.type === "short"}
                              key={`${selectedClip.id}-${selectedClip.hookSceneStart}-${selectedClip.hookSceneEnd}`}
                              playheadSourceTime={absolutePlaybackTime}
                              saving={isUpdatingHookScene}
                              shortMaxDuration={review.shortMaxDuration}
                              onSave={(start, end) =>
                                void saveHookScene(start, end)
                              }
                            />
                          </div>
                        </details>
                    </>
                    </div>
                  </div>

                  <ClipTextStyleEditor
                    subtitleScopeLabel={selectedSegments.some((s) => s.id === styledSegmentId) ? "選択した字幕1件だけ" : "このclipの共通字幕"}
                    onCommonSubtitleStyle={() => setStyledSegmentId(null)}
                    clipType={selectedClip.type}
                    disabled={!isEditable}
                    hookText={selectedClipContentDraft?.hookText ?? ""}
                    key={selectedClip.id}
                    layout="workspace"
                    selectedTarget={selectedTextStyleTarget}
                    showPreview={false}
                    shortTitleOutputEnabled={selectedShortTitleOutputEnabled}
                    shortTopBannerEnabled={review.shortTopBannerEnabled}
                    shortTopBannerUrl={toApiUrl(
                      `/api/jobs/${jobId}/subtitle-review/banner-assets/top?v=${encodeURIComponent(review.updatedAt)}`
                    )}
                    shortBottomBannerEnabled={review.shortBottomBannerEnabled}
                    shortBottomBannerUrl={toApiUrl(
                      `/api/jobs/${jobId}/subtitle-review/banner-assets/bottom?v=${encodeURIComponent(review.updatedAt)}`
                    )}
                    styles={{
                      ...selectedClipTextStyles,
                      subtitle: selectedClipContentDraft?.subtitleStyles.find((item) => {
                        const segment = selectedSegments.find((s) => s.id === styledSegmentId);
                        return segment && item.start === segment.start && item.end === segment.end;
                      })?.style ?? selectedClipTextStyles.subtitle
                    }}
                    resolvedStyles={selectedResolvedClipTextStyles}
                    defaultResolvedStyles={selectedDefaultResolvedClipTextStyles}
                    subtitleMaxCharsPerLine={selectedClip.subtitleMaxCharsPerLine}
                    subtitleMaxLines={selectedClip.subtitleMaxLines}
                    previewWidth={selectedClip.previewWidth}
                    previewHeight={selectedClip.previewHeight}
                    subtitleText={stylePreviewSubtitleText}
                    titleText={selectedClipContentDraft?.title ?? ""}
                    onChange={updateClipTextStyle}
                    onSelectedTargetChange={(target) => {
                      setSelectedTextStyleTarget(target);
                      setStyledSegmentId(null);
                    }}
                  />
                </div>
                <div className="subtitle-review-captions flex min-h-[640px] min-w-0 flex-col bg-white lg:col-span-1 lg:col-start-3 lg:row-start-1 2xl:col-span-1 2xl:col-start-3 2xl:row-start-1 2xl:min-h-0">
                <div className="border-b border-neutral-300 bg-white px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-base font-semibold">
                        {clipLabel(selectedClip, review.clips)} の字幕
                      </h3>
                      <p className="mt-1 text-xs text-neutral-500">
                        再生中の字幕へ自動で追従します
                      </p>
                    </div>
                    <p className="text-xs font-medium text-neutral-600">
                      {selectedSegments.length}件
                    </p>
                  </div>
                </div>

                <SubtitleBulkCorrection
                  selection={bulkCorrectionSelection} onSelection={setBulkCorrectionSelection}
                  segments={review.segments} drafts={drafts} disabled={!isEditable}
                  onSave={saveBulkCorrection}
                />
                <div
                  aria-label="字幕一覧"
                  className="relative min-h-0 flex-1 overflow-y-auto overscroll-y-contain"
                  ref={subtitleListRef}
                >
                  {selectedSegments.length > 0 ? (
                    selectedSegments.map((segment, segmentIndex) => {
                      const isDirty = dirtySegmentIds.has(segment.id);
                      const isActive = activeSegmentId === segment.id;
                      const relativeStart = clamp(
                        Math.max(
                          segment.start - selectedClip.start + hookSceneDuration,
                          hookSuppressionEnd
                        ),
                        0,
                        clipDuration
                      );
                      return (
                        <div
                          className={`border-b px-3 py-3 ${
                            isActive
                              ? "border-sky-300 bg-sky-50 shadow-[inset_4px_0_0_#0369a1]"
                              : "border-neutral-200 bg-white"
                          }`}
                          key={segment.id}
                          ref={(element) => {
                            segmentRowRefs.current[segment.id] = element;
                          }}
                        >
                          <div className="mb-2 flex items-center justify-between gap-3">
                            <button
                              className={`text-left text-sm font-semibold ${
                                isActive ? "text-sky-800" : "text-sky-700"
                              }`}
                              type="button"
                              onClick={() => seekToSubtitle(segment.start)}
                            >
                              {formatTime(relativeStart)} へ移動
                            </button>
                            <div className="flex flex-wrap justify-end gap-1 text-[11px]">
                              {isActive ? (
                                <span className="bg-sky-700 px-2 py-1 font-medium text-white">
                                  {isPlaying ? "再生中" : "現在位置"}
                                </span>
                              ) : null}
                              {segment.edited ? (
                                <span className="bg-sky-100 px-2 py-1 font-medium text-sky-800">
                                  修正済み
                                </span>
                              ) : null}
                              {segment.affectedClipIds.length > 1 ? (
                                <span className="bg-violet-100 px-2 py-1 font-medium text-violet-800">
                                  {segment.affectedClipIds.length}本へ反映
                                </span>
                              ) : null}
                              {isDirty ? (
                                <span className="bg-amber-100 px-2 py-1 font-medium text-amber-800">
                                  未保存
                                </span>
                              ) : null}
                            </div>
                          </div>
                          <textarea
                            className={`min-h-20 w-full resize-y border px-3 py-2 text-sm leading-6 outline-none ${
                              isDirty
                                ? "border-amber-500 bg-amber-50"
                                : "border-neutral-300 bg-white focus:border-sky-600"
                            }`}
                            disabled={!isEditable}
                            value={drafts[segment.id] ?? segment.text}
                            onChange={(event) => updateDraft(segment.id, event.target.value)}
                            aria-label={`字幕 ${formatTime(segment.start)}`}
                            onSelect={(event) => {
                              const field = event.currentTarget;
                              setSegmentCursor({ id: segment.id, offset: Array.from(field.value.slice(0, field.selectionStart)).length });
                              const source = field.value.slice(field.selectionStart, field.selectionEnd).trim();
                              if (source && source.length <= 200) {
                                setBulkCorrectionSelection((current) =>
                                  current?.segmentId === segment.id && current.source === source ? current
                                    : { segmentId: segment.id, source, replacement: "" });
                              }
                            }}
                          />
                          <SubtitleSegmentActions segment={segment} next={selectedSegments[segmentIndex + 1]}
                            text={drafts[segment.id] ?? segment.text}
                            nextText={selectedSegments[segmentIndex + 1] ? drafts[selectedSegments[segmentIndex + 1].id] ?? selectedSegments[segmentIndex + 1].text : ""}
                            cursor={segmentCursor?.id === segment.id ? segmentCursor.offset : null}
                            origin={selectedClip.start - hookSceneDuration} playhead={absolutePlaybackTime}
                            disabled={!isEditable} onEdit={saveSubtitleStructure} />
                          <div className="mt-2 flex items-center justify-between gap-3">
                            <span className="text-[11px] text-neutral-400">
                              元動画 {formatTime(segment.start)}
                            </span>
                            {isDirty ? (
                              <span className="text-[11px] font-semibold text-amber-700">
                                下の保存でまとめて反映
                              </span>
                            ) : null}
                            <button type="button" disabled={!isEditable}
                              className="border border-sky-600 px-2 py-1 text-xs text-sky-800"
                              aria-pressed={styledSegmentId === segment.id}
                              onClick={() => {
                                setWorkspaceTab("style");
                                setStyledSegmentId(segment.id);
                                setSelectedTextStyleTarget("subtitle");
                                seekToSubtitle(segment.start);
                              }}>
                              {selectedClipContentDraft?.subtitleStyles.some((s) => s.start === segment.start && s.end === segment.end)
                                ? "個別書式を編集" : "この字幕の書式"}
                            </button>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="px-4 py-8 text-sm text-neutral-600">
                      このclipに表示対象の字幕はありません。
                    </div>
                  )}
                </div>

                <div className="border-t border-neutral-300 bg-neutral-50 p-4">
                  <p className="mb-3 text-xs text-neutral-600">
                    {selectedShortFramingDirty
                      ? "画角調整を保存してから、このclipをOKにしてください。"
                      : selectedClipHasDirtySegments || selectedClipHasDirtyContent
                      ? "メインの即時表示を確認し、OKでタイトル・文字設定・字幕をまとめて保存します。"
                      : selectedClip.confirmed && !selectedPreviewReady
                        ? "OK済みです。完成表示はバックグラウンドで更新しています。"
                        : selectedClip.confirmed
                          ? "このclipはOK済みです。"
                          : "メインの動画と字幕を確認し、OKで保存します。"}
                  </p>
                  <button
                    className="min-h-11 w-full bg-sky-700 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
                    disabled={
                      !isEditable ||
                      selectedShortFramingDirty ||
                      (selectedClip.confirmed &&
                        !selectedClipHasDirtySegments &&
                        !selectedClipHasDirtyContent) ||
                      !selectedClipContentDraft?.publicationTitle.trim() ||
                      !selectedHookDurationIsValid ||
                      isSavingShortBannerSettings ||
                      confirmingClipId === selectedClip.id
                    }
                    type="button"
                    onClick={() => void confirmSelectedClip()}
                  >
                    {confirmingClipId === selectedClip.id
                      ? "OKを反映中"
                      : selectedShortFramingDirty
                        ? "画角調整の保存が必要です"
                      : selectedClip.confirmed &&
                          !selectedClipHasDirtySegments &&
                          !selectedClipHasDirtyContent
                        ? "このclipはOK済み"
                        : "この内容を保存してOK"}
                  </button>
                  <button type="button" className="mt-2 min-h-9 w-full border border-neutral-400 bg-white text-sm disabled:opacity-40"
                    disabled={hasReviewMutationInFlight || review.clips.length < 2}
                    onClick={() => {
                      const index = review.clips.findIndex(clip => clip.id === selectedClip.id);
                      selectClip(review.clips[(index + 1) % review.clips.length]);
                    }}>次のclipへ</button>
                </div>
                </div>
              </div>
            ) : null}
          </section>
        </div>

      </section>
    </main>
  );
}
