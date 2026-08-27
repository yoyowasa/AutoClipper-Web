"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { ClipHookSceneEditor } from "../../../../components/ClipHookSceneEditor";
import {
  ClipTextOverlay,
  ClipTextStyleEditor
} from "../../../../components/ClipTextStyleEditor";
import { ShortConversionEditor } from "../../../../components/ShortConversionEditor";
import { TitleHookSuggestionPanel } from "../../../../components/TitleHookSuggestionPanel";
import {
  applySubtitleReviewClip,
  convertSubtitleReviewClipToShort,
  finalizeSubtitleReview,
  getJobStatus,
  getSubtitleReview,
  getTitleHookSuggestions,
  requestTitleHookSuggestions,
  retrySubtitleReviewPreview,
  toApiUrl,
  updateSubtitleReviewClipFraming,
  updateSubtitleReviewHookScene,
  updateSubtitleReviewShortBannerSettings
} from "../../../../lib/api";
import { type ClipTextTarget } from "../../../../lib/clipTextStyle";
import { subtitlePreviewEvents } from "../../../../lib/subtitlePreview";
import type {
  ClipTextStyle,
  ExportType,
  SubtitleReviewClip,
  SubtitleReviewClipFramingUpdateRequest,
  SubtitleReviewConvertToShortRequest,
  SubtitleReviewDocument,
  SubtitleReviewSegment,
  TitleHookSuggestion,
  TitleHookSuggestionResponse
} from "../../../../lib/types";

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
  return value.trim().split(/\s+/u).filter(Boolean).join(" ");
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
  publicationTitle: string;
  title: string;
  hookText: string;
  hookDurationSeconds: number;
  hookSceneStart: number | null;
  hookSceneEnd: number | null;
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

type ShortFramingRangeProps = {
  ariaLabel: string;
  disabled: boolean;
  endLabel: string;
  label: string;
  max: number;
  min: number;
  startLabel: string;
  step: number;
  value: number;
  valueLabel: string;
  onChange: (value: number) => void;
  onCommit: (value: number) => void;
};

function ShortFramingRange({
  ariaLabel,
  disabled,
  endLabel,
  label,
  max,
  min,
  startLabel,
  step,
  value,
  valueLabel,
  onChange,
  onCommit
}: ShortFramingRangeProps) {
  return (
    <label className="min-w-0 border border-neutral-300 bg-white px-3 py-2">
      <span className="flex items-center justify-between gap-2 text-xs font-semibold text-neutral-700">
        <span>{label}</span>
        <span>{valueLabel}</span>
      </span>
      <input
        aria-label={ariaLabel}
        className="mt-2 block h-2 w-full cursor-pointer accent-sky-600 disabled:cursor-default"
        disabled={disabled}
        max={max}
        min={min}
        step={step}
        type="range"
        value={value}
        onBlur={(event) => onCommit(Number(event.currentTarget.value))}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
        onKeyUp={(event) => onCommit(Number(event.currentTarget.value))}
        onPointerCancel={(event) => onCommit(Number(event.currentTarget.value))}
        onPointerUp={(event) => onCommit(Number(event.currentTarget.value))}
      />
      <span className="mt-1 flex justify-between text-[10px] text-neutral-500">
        <span>{startLabel}</span>
        <span>{endLabel}</span>
      </span>
    </label>
  );
}

function contentDraftForClip(clip: SubtitleReviewClip): ClipContentDraft {
  return {
    publicationTitle: clip.publicationTitle ?? clip.title,
    title: clip.title,
    hookText: clip.hookText,
    hookDurationSeconds: clip.hookDurationSeconds,
    hookSceneStart: clip.hookSceneStart,
    hookSceneEnd: clip.hookSceneEnd,
    titleStyle: clip.titleStyle,
    hookStyle: clip.hookStyle,
    subtitleStyle: clip.subtitleStyle
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
        draft.hookText !== clip.hookText ||
        draft.hookDurationSeconds !== clip.hookDurationSeconds ||
        draft.hookSceneStart !== clip.hookSceneStart ||
        draft.hookSceneEnd !== clip.hookSceneEnd ||
        !stylesEqual(draft.titleStyle, clip.titleStyle) ||
        !stylesEqual(draft.hookStyle, clip.hookStyle) ||
        !stylesEqual(draft.subtitleStyle, clip.subtitleStyle))
  );
}

export default function SubtitleReviewPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playerShellRef = useRef<HTMLDivElement | null>(null);
  const subtitleListRef = useRef<HTMLDivElement | null>(null);
  const segmentRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const suggestionPlaybackEndRef = useRef<number | null>(null);
  const suggestionRequestGenerationRef = useRef<Record<string, number>>({});
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
  const [isConvertingToShort, setIsConvertingToShort] = useState(false);
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
  const [previewingSuggestionId, setPreviewingSuggestionId] = useState<
    string | null
  >(null);
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
    retryingPreviewClipId !== null ||
    isUpdatingHookScene ||
    confirmingClipId !== null ||
    isSavingShortBannerSettings ||
    savingShortFramingClipId !== null ||
    isConvertingToShort ||
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
        text: drafts[segment.id] ?? segment.text
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
    selectedSegments
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
    subtitleListRef.current?.scrollTo({ top: 0 });
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

  function selectClip(clip: SubtitleReviewClip) {
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
    updateClipContentDraft(selectedClip.id, { subtitleStyle: style });
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
      return;
    }
    const nextFraming = {
      framingOffsetX: clamp(framing.framingOffsetX, -100, 100),
      framingOffsetY: clamp(framing.framingOffsetY, -100, 100),
      framingZoom: clamp(framing.framingZoom, 1, 1.6)
    };
    const savedFraming = {
      framingOffsetX: clip.framingOffsetX,
      framingOffsetY: clip.framingOffsetY,
      framingZoom: clip.framingZoom
    };
    const signature = shortFramingSignature(nextFraming);
    if (shortFramingEquals(nextFraming, savedFraming)) {
      setShortFramingDrafts((drafts) => {
        const next = { ...drafts };
        delete next[clipId];
        return next;
      });
      return;
    }
    if (lastSavedShortFramingSignatureRef.current[clipId] === signature) {
      setShortFramingDrafts((drafts) => {
        const next = { ...drafts };
        delete next[clipId];
        return next;
      });
      return;
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
        nextFraming
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
    } catch (caught) {
      delete lastSavedShortFramingSignatureRef.current[clipId];
      setError(
        caught instanceof Error
          ? caught.message
          : "ショート画角を保存できませんでした"
      );
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
    shortBottomBannerEnabled: boolean
  ) {
    if (!review || !isEditable || hasReviewMutationInFlight) {
      return;
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
      }
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
            suggestions: [],
            error:
              caught instanceof Error
                ? caught.message
                : "AI案を生成できませんでした",
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
      publicationTitle: suggestion.publicationTitle.slice(0, 100),
      title: suggestion.overlayTitle.slice(0, 80),
      hookText: suggestion.hookText.slice(0, 120),
      hookDurationSeconds: clamp(suggestion.hookDurationSeconds, 1, 8),
      hookSceneStart: hasValidHookScene
        ? selectedClip.start + suggestedHookStart
        : null,
      hookSceneEnd: hasValidHookScene
        ? selectedClip.start + suggestedHookEnd
        : null
    });
    setSelectedTextStyleTarget("title");
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
        "未保存のタイトル、フック文字、文字スタイル、または字幕を先に保存してください。"
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
    if (!title) {
      setError("タイトルを入力してください。");
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
    const mutationGeneration = beginReviewMutation();
    setConfirmingClipId(selectedClip.id);
    setError(null);
    try {
      const updated = await applySubtitleReviewClip(jobId, selectedClip.id, {
        title,
        publicationTitle: selectedClipContentDraft.publicationTitle.trim() || title,
        hookText: selectedClipContentDraft.hookText.trim(),
        hookDurationSeconds: selectedClipContentDraft.hookDurationSeconds,
        hookSceneStart: selectedClipContentDraft.hookSceneStart,
        hookSceneEnd: selectedClipContentDraft.hookSceneEnd,
        titleStyle: selectedClipContentDraft.titleStyle,
        hookStyle: selectedClipContentDraft.hookStyle,
        subtitleStyle: selectedClipContentDraft.subtitleStyle,
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
      const nextClip =
        updated.clips.find(
          (clip) => clip.type === selectedClip.type && !clip.confirmed
        ) ?? updated.clips.find((clip) => !clip.confirmed);
      if (nextClip) {
        selectClip(nextClip);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "clipの内容を保存できませんでした");
    } finally {
      endReviewMutation();
      setConfirmingClipId(null);
    }
  }

  async function convertSelectedNormalClipToShort(
    request: SubtitleReviewConvertToShortRequest
  ) {
    if (
      !selectedClip ||
      selectedClip.type !== "normal" ||
      !selectedClipContentDraft
    ) {
      return;
    }
    if (isSavingShortBannerSettings) {
      setError("ショート画面設定の保存完了後に変換してください。");
      return;
    }
    const title = selectedClipContentDraft.title.trim();
    if (!title) {
      setError("タイトルを入力してください。");
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
    const savedSegmentIds = new Set(
      segmentUpdates.map((segment) => segment.segmentId)
    );
    const mutationGeneration = beginReviewMutation();
    setIsConvertingToShort(true);
    setError(null);
    try {
      if (selectedClipHasDirtySegments || selectedClipHasDirtyContent) {
        const saved = await applySubtitleReviewClip(jobId, selectedClip.id, {
          title,
          publicationTitle:
            selectedClipContentDraft.publicationTitle.trim() || title,
          hookText: selectedClipContentDraft.hookText.trim(),
          hookDurationSeconds: selectedClipContentDraft.hookDurationSeconds,
          hookSceneStart: selectedClipContentDraft.hookSceneStart,
          hookSceneEnd: selectedClipContentDraft.hookSceneEnd,
          titleStyle: selectedClipContentDraft.titleStyle,
          hookStyle: selectedClipContentDraft.hookStyle,
          subtitleStyle: selectedClipContentDraft.subtitleStyle,
          segments: segmentUpdates
        });
        if (isCurrentReviewMutation(mutationGeneration)) {
          setReview(saved);
          setDrafts(
            Object.fromEntries(
              saved.segments.map((segment) => [segment.id, segment.text])
            )
          );
          setDirtySegmentIds((current) => {
            const next = new Set(current);
            for (const segmentId of savedSegmentIds) {
              next.delete(segmentId);
            }
            return next;
          });
          const savedClip = saved.clips.find(
            (clip) => clip.id === selectedClip.id
          );
          if (savedClip) {
            setClipContentDrafts((current) => ({
              ...current,
              [savedClip.id]: contentDraftForClip(savedClip)
            }));
          }
        }
      }
      const updated = await convertSubtitleReviewClipToShort(
        jobId,
        selectedClip.id,
        request
      );
      const converted = updated.clips.find((clip) => clip.id === selectedClip.id);
      if (isCurrentReviewMutation(mutationGeneration)) {
        setReview(updated);
        setActiveClipType("short");
        setSelectedClipId(converted?.id ?? selectedClip.id);
        setLastSelectedClipIds({
          normal: "",
          short: converted?.id ?? selectedClip.id
        });
        setClipContentDrafts(
          Object.fromEntries(
            updated.clips.map((clip) => [clip.id, contentDraftForClip(clip)])
          )
        );
        setDrafts(
          Object.fromEntries(
            updated.segments.map((segment) => [segment.id, segment.text])
          )
        );
        setDirtySegmentIds(new Set());
        setTitleHookSuggestionRecords({});
      }
      setSelectedTextStyleTarget("title");
      setShowSavedPreview(false);
      setPreviewLoadFailedClipIds(new Set());
      setClipTime(0);
      setIsPlaying(false);
      setIsPlayerReady(false);
      setIsBuffering(true);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "通常動画をショートへ変更できませんでした"
      );
    } finally {
      setIsConvertingToShort(false);
      endReviewMutation();
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
      setError("未保存のタイトル、フック、または字幕があります。先に保存してください。");
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
  const shortConversionHookStartSeconds =
    selectedClip && selectedClipContentDraft?.hookSceneStart != null
      ? clamp(
          (selectedClipContentDraft?.hookSceneStart ?? selectedClip.start) -
            selectedClip.start,
          0,
          bodyDuration
        )
      : null;
  const shortConversionHookEndSeconds =
    selectedClip && selectedClipContentDraft?.hookSceneEnd != null
      ? clamp(
          (selectedClipContentDraft?.hookSceneEnd ?? selectedClip.start) -
            selectedClip.start,
          0,
          bodyDuration
        )
      : null;
  const shortConversionHookDuration =
    shortConversionHookStartSeconds !== null &&
    shortConversionHookEndSeconds !== null
      ? Math.max(
          0,
          shortConversionHookEndSeconds - shortConversionHookStartSeconds
        )
      : 0;
  const shortConversionCurrentPosition = selectedClip
    ? clamp(absolutePlaybackTime - selectedClip.start, 0, bodyDuration)
    : 0;

  return (
    <main className="min-h-screen bg-[#f7f7f4] px-3 py-2 text-neutral-950 sm:px-5">
      <section className="mx-auto flex w-full flex-col gap-2">
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
                : isEditable
                  ? "bg-sky-100 text-sky-800"
                  : "bg-amber-100 text-amber-800"
            }`}
          >
            {review.state === "completed"
              ? "完了"
              : isEditable
                ? "字幕確認中"
                : "書き出し中"}
          </span>
          <Link
            className="ml-auto inline-flex min-h-9 items-center border border-neutral-300 bg-white px-3 text-xs font-medium sm:text-sm"
            href={`/jobs/${jobId}`}
          >
            処理状況へ戻る
          </Link>
        </header>

        {!isEditable ? (
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

        <div
          aria-label="編集する動画形式"
          className="grid grid-cols-2 border border-neutral-300 bg-neutral-100 p-1"
          role="tablist"
        >
          <button
            aria-selected={activeClipType === "normal"}
            className={`min-h-11 px-4 text-sm font-semibold ${
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
            className={`min-h-11 px-4 text-sm font-semibold ${
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

        {review.reeditSourceJobId && selectedClip?.type === "normal" ? (
          <ShortConversionEditor
            busy={isConvertingToShort}
            clipDurationSeconds={bodyDuration}
            currentPositionSeconds={shortConversionCurrentPosition}
            disabled={!isEditable}
            hasUnsavedChanges={
              selectedClipHasDirtySegments || selectedClipHasDirtyContent
            }
            hookDurationSeconds={shortConversionHookDuration}
            hookRangeEndSeconds={shortConversionHookEndSeconds}
            hookRangeStartSeconds={shortConversionHookStartSeconds}
            key={selectedClip.id}
            shortMaxDurationSeconds={review.shortMaxDuration}
            onConvert={(request) =>
              void convertSelectedNormalClipToShort(request)
            }
          />
        ) : null}

        <div className="grid overflow-hidden border border-neutral-300 bg-white lg:grid-cols-[230px_minmax(0,1fr)_390px] xl:grid-cols-[260px_minmax(0,1fr)_clamp(360px,26vw,480px)] 2xl:h-[calc(100vh-4.5rem)] 2xl:min-h-[760px] 2xl:grid-cols-[clamp(210px,13vw,260px)_minmax(560px,1fr)_clamp(320px,22vw,440px)] 2xl:grid-rows-[minmax(500px,62vh)_minmax(260px,1fr)]">
          <aside className="relative min-h-[420px] border-b border-neutral-300 lg:min-h-0 lg:border-r">
            <div className="flex min-h-[420px] flex-col lg:absolute lg:inset-0 lg:min-h-0">
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

          <section className="flex min-w-0 flex-col border-b border-neutral-300 lg:border-r">
            {selectedClip ? (
              <>
                {selectedClip.type === "short" ? (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-300 bg-white px-4 py-2">
                      <div>
                        <p className="text-sm font-semibold text-neutral-900">ショート画角</p>
                        <p className="text-xs text-neutral-500">
                          選択後、完成動画と同じ画角でプレビューを再生成します
                        </p>
                      </div>
                      <label className="flex items-center gap-2 text-sm font-semibold text-neutral-700">
                        <span>{isSavingShortBannerSettings ? "変更中" : "基本配置"}</span>
                        <select
                          aria-label="ショート画角"
                          className="min-h-10 min-w-52 border border-neutral-300 bg-white px-3 text-sm text-neutral-900"
                          disabled={!isEditable || isSavingShortBannerSettings}
                          value={review.shortLayout}
                          onChange={(event) =>
                            void saveShortBannerSettings(
                              event.target.value as SubtitleReviewDocument["shortLayout"],
                              review.shortTopBannerEnabled,
                              review.shortBottomBannerEnabled
                            )
                          }
                        >
                          <option value="auto">自動（人物を優先）</option>
                          <option value="face_tracking_crop">人物アップ（顔を追従）</option>
                          <option value="center_crop">中央を拡大</option>
                          <option value="blur_background">全体表示（ぼかし背景）</option>
                        </select>
                      </label>
                    </div>
                    {selectedShortFramingDraft ? (
                      <div className="border-b border-neutral-300 bg-neutral-50 px-4 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-neutral-900">
                              このショートのみ微調整
                            </p>
                            <p className="text-xs text-neutral-500">
                              スライダーを離すと保存し、このclipだけプレビューを再生成します
                            </p>
                          </div>
                          <div className="flex flex-wrap items-center justify-end gap-2">
                            <span
                              aria-live="polite"
                              className={`text-xs font-semibold ${
                                selectedShortPreviewRegenerating
                                  ? "text-sky-700"
                                  : selectedShortFramingDirty
                                    ? "text-amber-700"
                                    : "text-emerald-700"
                              }`}
                            >
                              {savingShortFramingClipId === selectedClip.id
                                ? "画角を保存中"
                                : selectedShortPreviewRegenerating
                                  ? "このclipのプレビューを再生成中"
                                  : selectedShortFramingDirty
                                    ? "未反映"
                                    : "反映済み"}
                            </span>
                            <button
                              className="min-h-9 border border-neutral-300 bg-white px-3 text-xs font-semibold text-neutral-700 disabled:bg-neutral-200 disabled:text-neutral-400"
                              disabled={
                                !isEditable ||
                                savingShortFramingClipId !== null ||
                                (selectedShortFramingDraft.framingOffsetX === 0 &&
                                  selectedShortFramingDraft.framingOffsetY === 0 &&
                                  selectedShortFramingDraft.framingZoom === 1)
                              }
                              type="button"
                              onClick={() => {
                                const next = changeSelectedShortFraming({
                                  framingOffsetX: 0,
                                  framingOffsetY: 0,
                                  framingZoom: 1
                                });
                                if (next) {
                                  void saveSelectedShortFraming(selectedClip.id, next);
                                }
                              }}
                            >
                              自動値へ戻す
                            </button>
                          </div>
                        </div>
                        <div className="mt-3 grid gap-3 md:grid-cols-3">
                          <ShortFramingRange
                            ariaLabel="このショートの左右画角"
                            disabled={!isEditable || savingShortFramingClipId !== null}
                            endLabel="右側を表示"
                            label="左右"
                            max={100}
                            min={-100}
                            startLabel="左側を表示"
                            step={5}
                            value={selectedShortFramingDraft.framingOffsetX}
                            valueLabel={`${Math.round(selectedShortFramingDraft.framingOffsetX)}`}
                            onChange={(value) =>
                              changeSelectedShortFraming({ framingOffsetX: value })
                            }
                            onCommit={(value) => {
                              const next = changeSelectedShortFraming({
                                framingOffsetX: value
                              });
                              if (next) {
                                void saveSelectedShortFraming(selectedClip.id, next);
                              }
                            }}
                          />
                          <ShortFramingRange
                            ariaLabel="このショートの上下画角"
                            disabled={!isEditable || savingShortFramingClipId !== null}
                            endLabel="下側を表示"
                            label="上下"
                            max={100}
                            min={-100}
                            startLabel="上側を表示"
                            step={5}
                            value={selectedShortFramingDraft.framingOffsetY}
                            valueLabel={`${Math.round(selectedShortFramingDraft.framingOffsetY)}`}
                            onChange={(value) =>
                              changeSelectedShortFraming({ framingOffsetY: value })
                            }
                            onCommit={(value) => {
                              const next = changeSelectedShortFraming({
                                framingOffsetY: value
                              });
                              if (next) {
                                void saveSelectedShortFraming(selectedClip.id, next);
                              }
                            }}
                          />
                          <ShortFramingRange
                            ariaLabel="このショートの拡大率"
                            disabled={!isEditable || savingShortFramingClipId !== null}
                            endLabel="160%"
                            label="拡大"
                            max={1.6}
                            min={1}
                            startLabel="標準"
                            step={0.05}
                            value={selectedShortFramingDraft.framingZoom}
                            valueLabel={`${Math.round(
                              selectedShortFramingDraft.framingZoom * 100
                            )}%`}
                            onChange={(value) =>
                              changeSelectedShortFraming({ framingZoom: value })
                            }
                            onCommit={(value) => {
                              const next = changeSelectedShortFraming({
                                framingZoom: value
                              });
                              if (next) {
                                void saveSelectedShortFraming(selectedClip.id, next);
                              }
                            }}
                          />
                        </div>
                      </div>
                    ) : null}
                  </>
                ) : null}
                <div className="flex items-start justify-center bg-neutral-100 p-3 sm:p-4">
                  <div
                    className="w-full max-w-5xl overflow-hidden bg-neutral-950 text-white"
                    ref={playerShellRef}
                  >
                    <div
                      className={`relative overflow-hidden bg-black ${
                        selectedClip.type === "short"
                          ? "mx-auto aspect-[9/16] w-full max-w-[360px] 2xl:w-[clamp(210px,calc(34.875vh-4.078125rem),360px)]"
                          : "mx-auto aspect-video w-full max-w-5xl 2xl:w-[clamp(640px,calc(110.222vh-12.8889rem),1024px)] 2xl:max-w-full"
                      }`}
                      style={{ containerType: "inline-size" }}
                    >
                      <div className="absolute inset-x-2 top-2 z-40 flex items-center justify-between gap-2">
                        <span className="pointer-events-none bg-black/70 px-2 py-1 text-[10px] font-semibold text-white">
                          {isShowingLivePreview
                            ? "編集中・即時反映"
                            : "保存済み・完成表示"}
                        </span>
                        {livePreviewReady && selectedPreviewReady ? (
                          <button
                            className="bg-black/75 px-2 py-1 text-[10px] font-semibold text-white"
                            type="button"
                            onClick={() => setShowSavedPreview((current) => !current)}
                          >
                            {isShowingLivePreview ? "保存済み表示" : "編集表示へ戻る"}
                          </button>
                        ) : null}
                      </div>
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
                              style={selectedClipTextStyles.subtitle}
                              subtitleMaxCharsPerLine={
                                selectedClip.subtitleMaxCharsPerLine
                              }
                              subtitleMaxLines={selectedClip.subtitleMaxLines}
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

                    {selectedPlayerReady ? (
                    <div className="border-t border-neutral-700 bg-neutral-900 px-3 py-3">
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
              </>
            ) : null}
          </section>

          <section className="contents">
            {selectedClip ? (
              <div className="contents">
                <div className="grid min-w-0 bg-white lg:col-span-3 lg:row-start-2 2xl:col-span-3 2xl:col-start-1 2xl:row-start-2 2xl:h-full 2xl:min-h-0 2xl:grid-cols-4 2xl:overflow-hidden">
                  <div className="min-w-0 border-b border-neutral-300 bg-neutral-50 p-3 2xl:h-full 2xl:min-h-0 2xl:overflow-y-auto 2xl:border-b-0 2xl:border-r">
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
                            publicationTitle: event.target.value
                          })
                        }
                      />
                    </label>
                    <p className="mt-1 text-right text-[10px] text-neutral-500">
                      {selectedClipContentDraft?.publicationTitle.length ?? 0} / 100
                    </p>

                    <label className="mt-2 block text-xs font-semibold text-neutral-700">
                      動画内タイトル
                      <input
                        className="mt-1 min-h-9 w-full border border-neutral-300 bg-white px-2 text-sm outline-none focus:border-sky-600"
                        disabled={!isEditable}
                        maxLength={80}
                        type="text"
                        value={selectedClipContentDraft?.title ?? ""}
                        onChange={(event) =>
                          updateClipContentDraft(selectedClip.id, {
                            title: event.target.value
                          })
                        }
                      />
                    </label>
                    <p className="mt-1 text-right text-[10px] text-neutral-500">
                      {selectedClipContentDraft?.title.length ?? 0} / 80
                    </p>
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
                          const hookText = event.target.value;
                          updateClipContentDraft(selectedClip.id, {
                            hookText,
                            ...(hookText.trim()
                              ? {}
                              : { hookSceneStart: null, hookSceneEnd: null })
                          });
                        }}
                      />
                    </label>
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

                    <TitleHookSuggestionPanel
                      busy={requestingSuggestionClipId === selectedClip.id}
                      canPreview={selectedPlayerReady}
                      disabled={!isEditable}
                      previewingSuggestionId={previewingSuggestionId}
                      response={selectedSuggestionRecord?.response ?? null}
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
                        AI案のフック映像区間は、右下のOKでタイトル・字幕とまとめて保存します。
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

                  <ClipTextStyleEditor
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
                      `/api/jobs/${jobId}/subtitle-review/banner-assets/top`
                    )}
                    shortBottomBannerEnabled={review.shortBottomBannerEnabled}
                    shortBottomBannerUrl={toApiUrl(
                      `/api/jobs/${jobId}/subtitle-review/banner-assets/bottom`
                    )}
                    styles={selectedClipTextStyles}
                    resolvedStyles={selectedResolvedClipTextStyles}
                    defaultResolvedStyles={selectedDefaultResolvedClipTextStyles}
                    subtitleMaxCharsPerLine={selectedClip.subtitleMaxCharsPerLine}
                    subtitleMaxLines={selectedClip.subtitleMaxLines}
                    previewWidth={selectedClip.previewWidth}
                    previewHeight={selectedClip.previewHeight}
                    subtitleText={stylePreviewSubtitleText}
                    titleText={selectedClipContentDraft?.title ?? ""}
                    onChange={updateClipTextStyle}
                    onSelectedTargetChange={setSelectedTextStyleTarget}
                  />
                </div>
                <div className="flex min-h-[640px] min-w-0 flex-col bg-white lg:col-span-1 lg:col-start-3 lg:row-start-1 2xl:col-span-1 2xl:col-start-3 2xl:row-start-1 2xl:min-h-0">
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

                <div
                  className="relative min-h-0 flex-1 overflow-y-auto"
                  ref={subtitleListRef}
                >
                  {selectedSegments.length > 0 ? (
                    selectedSegments.map((segment) => {
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
                          />
                          <div className="mt-2 flex items-center justify-between gap-3">
                            <span className="text-[11px] text-neutral-400">
                              元動画 {formatTime(segment.start)}
                            </span>
                            {isDirty ? (
                              <span className="text-[11px] font-semibold text-amber-700">
                                下のOKでまとめて保存
                              </span>
                            ) : null}
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
                      !selectedClipContentDraft?.title.trim() ||
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
                        : "この内容でOK（保存して次へ）"}
                  </button>
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
