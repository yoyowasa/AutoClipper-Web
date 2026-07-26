"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  confirmSubtitleReviewClip,
  finalizeSubtitleReview,
  getSubtitleReview,
  toApiUrl,
  updateSubtitleReviewClipContent,
  updateSubtitleReviewSegment
} from "../../../../lib/api";
import type {
  SubtitleReviewClip,
  SubtitleReviewDocument,
  SubtitleReviewSegment
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

type ClipContentDraft = {
  title: string;
  hookText: string;
  hookDurationSeconds: number;
};

function contentDraftForClip(clip: SubtitleReviewClip): ClipContentDraft {
  return {
    title: clip.title,
    hookText: clip.hookText,
    hookDurationSeconds: clip.hookDurationSeconds
  };
}

function isClipContentDirty(
  clip: SubtitleReviewClip,
  drafts: Record<string, ClipContentDraft>
): boolean {
  const draft = drafts[clip.id];
  return Boolean(
    draft &&
      (draft.title !== clip.title ||
        draft.hookText !== clip.hookText ||
        draft.hookDurationSeconds !== clip.hookDurationSeconds)
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
  const [review, setReview] = useState<SubtitleReviewDocument | null>(null);
  const [selectedClipId, setSelectedClipId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [clipContentDrafts, setClipContentDrafts] = useState<
    Record<string, ClipContentDraft>
  >({});
  const [dirtySegmentIds, setDirtySegmentIds] = useState<Set<string>>(new Set());
  const [savingSegmentId, setSavingSegmentId] = useState<string | null>(null);
  const [savingClipContentId, setSavingClipContentId] = useState<string | null>(null);
  const [confirmingClipId, setConfirmingClipId] = useState<string | null>(null);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [isPlayerReady, setIsPlayerReady] = useState(false);
  const [videoLoadSeconds, setVideoLoadSeconds] = useState(0);
  const [previewFallbackClipIds, setPreviewFallbackClipIds] = useState<Set<string>>(
    new Set()
  );
  const [clipTime, setClipTime] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;
    void getSubtitleReview(jobId)
      .then((document) => {
        if (!active) {
          return;
        }
        setReview(document);
        setSelectedClipId(document.clips[0]?.id ?? "");
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

  const selectedClip = useMemo(
    () => review?.clips.find((clip) => clip.id === selectedClipId) ?? null,
    [review, selectedClipId]
  );
  const isEditable = review?.state === "awaiting_review";
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
  const clipDuration = selectedClip
    ? Math.max(0, selectedClip.end - selectedClip.start)
    : 0;
  const usesClipPreview = Boolean(
    selectedClip?.previewVideoUrl && !previewFallbackClipIds.has(selectedClip.id)
  );
  const selectedVideoUrl = selectedClip
    ? usesClipPreview
      ? selectedClip.previewVideoUrl
      : review?.sourceVideoUrl
    : null;
  const selectedMediaStart = selectedClip
    ? usesClipPreview
      ? 0
      : selectedClip.start
    : null;
  const selectedMediaEnd = selectedClip
    ? usesClipPreview
      ? clipDuration
      : selectedClip.end
    : null;
  const selectedClipHasDirtySegments = selectedSegments.some((segment) =>
    dirtySegmentIds.has(segment.id)
  );
  const selectedClipContentDraft = selectedClip
    ? clipContentDrafts[selectedClip.id] ?? contentDraftForClip(selectedClip)
    : null;
  const selectedClipHasDirtyContent = Boolean(
    selectedClip && isClipContentDirty(selectedClip, clipContentDrafts)
  );
  const hasDirtyClipContent = Boolean(
    review?.clips.some((clip) => isClipContentDirty(clip, clipContentDrafts))
  );
  const selectedHookDurationIsValid =
    selectedClip?.type !== "short" ||
    (Number.isFinite(selectedClipContentDraft?.hookDurationSeconds ?? Number.NaN) &&
      (selectedClipContentDraft?.hookDurationSeconds ?? 0) >= 1 &&
      (selectedClipContentDraft?.hookDurationSeconds ?? 0) <= 8);
  const previewOverlayKind =
    selectedClip?.type === "short" &&
    selectedClipContentDraft?.hookText.trim() &&
    clipTime < selectedClipContentDraft.hookDurationSeconds
      ? "フック"
      : "タイトル";
  const previewOverlayText =
    selectedClip?.type === "short"
      ? previewOverlayKind === "フック"
        ? selectedClipContentDraft?.hookText.trim()
        : selectedClipContentDraft?.title.trim()
      : "";
  const absolutePlaybackTime = selectedClip
    ? selectedClip.start + clipTime
    : 0;
  const activeSegmentId = useMemo(() => {
    if (!selectedClip) {
      return null;
    }
    return (
      selectedSegments.find(
        (segment) =>
          absolutePlaybackTime >= Math.max(segment.start, selectedClip.start) &&
          absolutePlaybackTime < Math.min(segment.end, selectedClip.end)
      )?.id ?? null
    );
  }, [absolutePlaybackTime, selectedClip, selectedSegments]);

  useEffect(() => {
    const video = videoRef.current;
    subtitleListRef.current?.scrollTo({ top: 0 });
    if (!video || selectedMediaStart === null) {
      return;
    }
    video.pause();

    const moveToClipStart = () => {
      video.currentTime = selectedMediaStart;
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
  }, [selectedClipId, selectedMediaStart, selectedVideoUrl]);

  useEffect(() => {
    if (isPlayerReady || !selectedClip) {
      return;
    }
    const intervalId = window.setInterval(() => {
      setVideoLoadSeconds((current) => current + 1);
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [isPlayerReady, selectedClip]);

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

  function selectClip(clip: SubtitleReviewClip) {
    videoRef.current?.pause();
    setClipTime(0);
    setIsPlaying(false);
    setIsBuffering(true);
    setIsPlayerReady(false);
    setVideoLoadSeconds(0);
    setSelectedClipId(clip.id);
    setError(null);
  }

  function mediaTimeForClipTime(relativeTime: number): number {
    if (!selectedClip) {
      return 0;
    }
    return usesClipPreview ? relativeTime : selectedClip.start + relativeTime;
  }

  function seekToClipTime(nextTime: number) {
    if (!videoRef.current || !selectedClip) {
      return;
    }
    const relativeTime = clamp(nextTime, 0, clipDuration);
    videoRef.current.currentTime = mediaTimeForClipTime(relativeTime);
    setClipTime(relativeTime);
  }

  function playFrom(start: number) {
    if (!videoRef.current || !selectedClip) {
      return;
    }
    const absoluteTime = clamp(
      Math.max(selectedClip.start, start - 0.15),
      selectedClip.start,
      Math.max(selectedClip.start, selectedClip.end - 0.05)
    );
    const relativeTime = absoluteTime - selectedClip.start;
    videoRef.current.currentTime = mediaTimeForClipTime(relativeTime);
    setClipTime(relativeTime);
    void videoRef.current.play();
  }

  function togglePlayback() {
    const video = videoRef.current;
    if (!video || !selectedClip) {
      return;
    }
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
    if (
      !video ||
      !selectedClip ||
      selectedMediaStart === null ||
      selectedMediaEnd === null
    ) {
      return;
    }
    if (video.currentTime < selectedMediaStart - 0.05) {
      video.currentTime = selectedMediaStart;
      setClipTime(0);
      return;
    }
    if (video.currentTime >= selectedMediaEnd) {
      video.pause();
      video.currentTime = selectedMediaEnd;
      setClipTime(clipDuration);
      return;
    }
    setClipTime(
      clamp(
        usesClipPreview ? video.currentTime : video.currentTime - selectedClip.start,
        0,
        clipDuration
      )
    );
  }

  function handleVideoSeeking() {
    const video = videoRef.current;
    if (!video || selectedMediaStart === null || selectedMediaEnd === null) {
      return;
    }
    if (video.currentTime < selectedMediaStart) {
      video.currentTime = selectedMediaStart;
    } else if (video.currentTime > selectedMediaEnd) {
      video.currentTime = selectedMediaEnd;
    }
  }

  function retryVideoLoad() {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    setError(null);
    setVideoLoadSeconds(0);
    setIsPlayerReady(false);
    setIsBuffering(true);
    video.load();
  }

  function handleVideoError() {
    if (selectedClip?.previewVideoUrl && !previewFallbackClipIds.has(selectedClip.id)) {
      setPreviewFallbackClipIds((current) => new Set(current).add(selectedClip.id));
      setError("確認用動画を読み込めなかったため、元動画へ切り替えました。");
      setIsPlayerReady(false);
      setIsBuffering(true);
      setVideoLoadSeconds(0);
      return;
    }
    setError("動画を読み込めませんでした。再読み込みしてください。");
    setIsBuffering(false);
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
    setDrafts((current) => ({ ...current, [segmentId]: text }));
    setDirtySegmentIds((current) => new Set(current).add(segmentId));
  }

  function updateClipContentDraft(
    clipId: string,
    update: Partial<ClipContentDraft>
  ) {
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

  async function saveClipContent() {
    if (!selectedClip || !selectedClipContentDraft) {
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
    setSavingClipContentId(selectedClip.id);
    setError(null);
    try {
      const updated = await updateSubtitleReviewClipContent(jobId, selectedClip.id, {
        title,
        hookText:
          selectedClip.type === "short" ? selectedClipContentDraft.hookText.trim() : "",
        hookDurationSeconds: selectedClipContentDraft.hookDurationSeconds
      });
      setReview(updated);
      const updatedClip = updated.clips.find((clip) => clip.id === selectedClip.id);
      if (updatedClip) {
        setClipContentDrafts((current) => ({
          ...current,
          [updatedClip.id]: contentDraftForClip(updatedClip)
        }));
      }
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "タイトルとフックを保存できませんでした"
      );
    } finally {
      setSavingClipContentId(null);
    }
  }

  async function saveSegment(segment: SubtitleReviewSegment) {
    const text = drafts[segment.id] ?? "";
    setSavingSegmentId(segment.id);
    setError(null);
    try {
      const updated = await updateSubtitleReviewSegment(jobId, segment.id, text);
      setReview(updated);
      setDrafts((current) => ({ ...current, [segment.id]: text }));
      setDirtySegmentIds((current) => {
        const next = new Set(current);
        next.delete(segment.id);
        return next;
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "字幕を保存できませんでした");
    } finally {
      setSavingSegmentId(null);
    }
  }

  async function confirmSelectedClip() {
    if (!selectedClip || selectedClipHasDirtySegments || selectedClipHasDirtyContent) {
      setError("未保存のタイトル、フック、または字幕があります。先に保存してください。");
      return;
    }
    setConfirmingClipId(selectedClip.id);
    setError(null);
    try {
      const updated = await confirmSubtitleReviewClip(jobId, selectedClip.id);
      setReview(updated);
      const nextClip = updated.clips.find((clip) => !clip.confirmed);
      if (nextClip) {
        setSelectedClipId(nextClip.id);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "clipを確認済みにできませんでした");
    } finally {
      setConfirmingClipId(null);
    }
  }

  async function startRendering() {
    if (!review || dirtySegmentIds.size > 0 || hasDirtyClipContent) {
      setError("未保存のタイトル、フック、または字幕があります。先に保存してください。");
      return;
    }
    setIsFinalizing(true);
    setError(null);
    try {
      await finalizeSubtitleReview(jobId);
      router.push(`/jobs/${jobId}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "レンダリングを開始できませんでした");
      setIsFinalizing(false);
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
    <main className="min-h-screen bg-[#f7f7f4] px-3 py-4 text-neutral-950 sm:px-5">
      <section className="mx-auto flex w-full max-w-[1600px] flex-col gap-4">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-neutral-300 pb-4">
          <div>
            <p className="text-sm font-medium uppercase text-neutral-500">AutoClipper</p>
            <h1 className="mt-1 text-3xl font-semibold">clip別 字幕確認</h1>
            <p className="mt-1 text-sm text-neutral-600">
              左でclipを選び、動画を見ながら右側の字幕だけを確認します。確認済み{" "}
              {review.confirmedClipCount} / {review.totalClipCount} ・ 修正{" "}
              {review.editedSegmentCount}件
            </p>
          </div>
          <Link
            className="inline-flex min-h-10 items-center border border-neutral-300 bg-white px-4 text-sm font-medium"
            href={`/jobs/${jobId}`}
          >
            処理状況へ戻る
          </Link>
        </header>

        <div className="grid gap-2 sm:grid-cols-3">
          <div className="border-l-4 border-emerald-500 bg-emerald-50 px-4 py-3">
            <p className="text-xs font-semibold text-emerald-800">1. 自動処理</p>
            <p className="mt-1 text-sm font-semibold">完了</p>
          </div>
          <div
            className={`border-l-4 px-4 py-3 ${
              isEditable
                ? "border-sky-600 bg-sky-50"
                : "border-emerald-500 bg-emerald-50"
            }`}
          >
            <p
              className={`text-xs font-semibold ${
                isEditable ? "text-sky-800" : "text-emerald-800"
              }`}
            >
              2. clip別 字幕確認
            </p>
            <p className="mt-1 text-sm font-semibold">
              {isEditable ? "現在の工程" : "完了"}
            </p>
          </div>
          <div
            className={`border-l-4 px-4 py-3 ${
              review.state === "completed"
                ? "border-emerald-500 bg-emerald-50"
                : isEditable
                  ? "border-neutral-300 bg-white"
                  : "border-sky-600 bg-sky-50"
            }`}
          >
            <p
              className={`text-xs font-semibold ${
                review.state === "completed"
                  ? "text-emerald-800"
                  : isEditable
                    ? "text-neutral-500"
                    : "text-sky-800"
              }`}
            >
              3. 字幕焼き込み・書き出し
            </p>
            <p className="mt-1 text-sm font-semibold">
              {review.state === "completed"
                ? "完了"
                : isEditable
                  ? "全clip確認後に開始"
                  : "処理中"}
            </p>
          </div>
        </div>

        {!isEditable ? (
          <div className="border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-900">
            {review.state === "completed"
              ? "字幕確認と書き出しは完了しています。この画面は確認履歴として表示しています。"
              : "字幕は確定済みです。現在、動画を書き出しています。"}
          </div>
        ) : null}

        {isEditable && review.renderRevision > 1 ? (
          <div className="border border-violet-300 bg-violet-50 px-4 py-3 text-sm text-violet-950">
            完成済みjobの再編集です。元の動画、選定範囲、字幕修正を引き継いでいます。
            新しい書き出しが完了するまで、現在のMP4とZIPは保持されます。
          </div>
        ) : null}

        {error ? (
          <div className="border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        <div className="grid overflow-hidden border border-neutral-300 bg-white lg:h-[calc(100vh-14rem)] lg:min-h-[560px] lg:grid-cols-[230px_minmax(0,1fr)_390px] xl:grid-cols-[260px_minmax(0,1fr)_430px]">
          <aside className="flex min-h-0 flex-col border-b border-neutral-300 lg:border-b-0 lg:border-r">
            <div className="border-b border-neutral-200 px-4 py-4">
              <p className="text-sm font-semibold">生成予定clip</p>
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
              {review.clips.map((clip) => {
                const clipDraft = clipContentDrafts[clip.id];
                const contentDirty = isClipContentDirty(clip, clipContentDrafts);
                return (
                  <button
                    className={`block w-full border-b border-neutral-200 px-4 py-4 text-left ${
                      clip.id === selectedClipId ? "bg-neutral-950 text-white" : "bg-white"
                    }`}
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
                    <span
                      className={`mt-2 block text-xs ${
                        clip.id === selectedClipId ? "text-neutral-300" : "text-neutral-500"
                      }`}
                    >
                      clip長 {formatTime(clip.duration)} ・ {clip.segmentIds.length}字幕
                      {clip.editedSegmentCount > 0
                        ? ` ・ 修正${clip.editedSegmentCount}件`
                        : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="flex min-h-0 min-w-0 flex-col border-b border-neutral-300 lg:border-b-0 lg:border-r">
            {selectedClip ? (
              <>
                <div className="border-b border-neutral-300 px-4 py-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase text-sky-700">
                        {clipLabel(selectedClip, review.clips)} ・ 選択clipのみ再生
                      </p>
                      <h2 className="mt-1 line-clamp-2 text-lg font-semibold">
                        {selectedClipContentDraft?.title ?? selectedClip.title}
                      </h2>
                      <p className="mt-1 text-xs text-neutral-500">
                        clip長 {formatTime(clipDuration)} ・ 元動画{" "}
                        {formatTime(selectedClip.start)} - {formatTime(selectedClip.end)}
                      </p>
                    </div>
                    <button
                      className="min-h-10 border border-neutral-300 bg-white px-3 text-sm font-medium"
                      type="button"
                      onClick={() => playFrom(selectedClip.start)}
                    >
                      先頭から再生
                    </button>
                  </div>
                </div>

                <div className="flex min-h-0 flex-1 items-start justify-center overflow-y-auto bg-neutral-100 p-3 sm:p-4">
                  <div
                    className="w-full max-w-5xl overflow-hidden bg-neutral-950 text-white"
                    ref={playerShellRef}
                  >
                    <div className="relative">
                      <video
                        className="aspect-video w-full cursor-pointer bg-black object-contain lg:max-h-[calc(100vh-30rem)] lg:min-h-[220px]"
                        key={`${selectedClip.id}:${selectedVideoUrl ?? ""}`}
                        playsInline
                        preload="metadata"
                        ref={videoRef}
                        src={selectedVideoUrl ? toApiUrl(selectedVideoUrl) : undefined}
                        onCanPlay={() => {
                          setIsBuffering(false);
                          setIsPlayerReady(true);
                        }}
                        onClick={togglePlayback}
                        onError={handleVideoError}
                        onLoadedMetadata={() => setIsPlayerReady(true)}
                        onLoadStart={() => {
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
                      {previewOverlayText ? (
                        <div className="pointer-events-none absolute inset-x-4 top-4 z-10 flex justify-center">
                          <div className="max-w-[86%] bg-black/75 px-4 py-3 text-center text-base font-bold leading-snug text-white sm:text-xl">
                            <span className="mb-1 block text-[10px] font-semibold text-sky-200">
                              {previewOverlayKind}
                            </span>
                            {previewOverlayText}
                          </div>
                        </div>
                      ) : null}
                      {!isPlayerReady || isBuffering ? (
                        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/60 px-5 text-center text-sm font-semibold">
                          <p>
                            {isPlayerReady
                              ? "選択位置を読み込み中"
                              : usesClipPreview
                                ? `確認用clip動画を読み込み中 (${videoLoadSeconds}秒)`
                                : `元動画を読み込み中 (${videoLoadSeconds}秒)`}
                          </p>
                          {videoLoadSeconds >= 15 ? (
                            <>
                              <p className="text-xs font-normal text-neutral-200">
                                読み込みに時間がかかっています。停止状態ではありません。
                              </p>
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
                          aria-label="5秒戻る"
                          className="min-h-10 border border-neutral-600 px-3 text-sm font-medium"
                          type="button"
                          onClick={() => skipBy(-5)}
                        >
                          5秒戻る
                        </button>
                        <button
                          aria-label="5秒進む"
                          className="min-h-10 border border-neutral-600 px-3 text-sm font-medium"
                          type="button"
                          onClick={() => skipBy(5)}
                        >
                          5秒進む
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
                  </div>
                </div>
              </>
            ) : null}
          </section>

          <section className="flex min-h-0 flex-col">
            {selectedClip ? (
              <>
                <div className="border-b border-neutral-300 bg-neutral-50 px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-base font-semibold">タイトル・フック</h3>
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

                  <label className="mt-3 block text-xs font-semibold text-neutral-700">
                    表示タイトル
                    <input
                      className="mt-1 min-h-10 w-full border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-sky-600"
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
                  <p className="mt-1 text-right text-[11px] text-neutral-500">
                    {selectedClipContentDraft?.title.length ?? 0} / 80
                  </p>

                  {selectedClip.type === "short" ? (
                    <>
                      <label className="mt-2 block text-xs font-semibold text-neutral-700">
                        冒頭フック
                        <textarea
                          className="mt-1 min-h-16 w-full resize-y border border-neutral-300 bg-white px-3 py-2 text-sm leading-5 outline-none focus:border-sky-600"
                          disabled={!isEditable}
                          maxLength={120}
                          placeholder="空欄ならフックを表示しません"
                          value={selectedClipContentDraft?.hookText ?? ""}
                          onChange={(event) =>
                            updateClipContentDraft(selectedClip.id, {
                              hookText: event.target.value
                            })
                          }
                        />
                      </label>
                      <div className="mt-2 flex items-end justify-between gap-3">
                        <label className="block text-xs font-semibold text-neutral-700">
                          表示秒数
                          <input
                            className="mt-1 h-10 w-24 border border-neutral-300 bg-white px-3 text-sm tabular-nums outline-none focus:border-sky-600"
                            disabled={!isEditable}
                            max={8}
                            min={1}
                            step={0.5}
                            type="number"
                            aria-invalid={!selectedHookDurationIsValid}
                            value={selectedClipContentDraft?.hookDurationSeconds ?? 3}
                            onChange={(event) =>
                              updateClipContentDraft(selectedClip.id, {
                                hookDurationSeconds: Number(event.target.value)
                              })
                            }
                          />
                        </label>
                        <p className="text-[11px] text-neutral-500">
                          {selectedClipContentDraft?.hookText.length ?? 0} / 120
                        </p>
                      </div>
                      {!selectedHookDurationIsValid ? (
                        <p className="mt-1 text-xs font-semibold text-red-700">
                          1〜8秒で入力してください。
                        </p>
                      ) : null}
                    </>
                  ) : null}

                  <button
                    className="mt-3 min-h-10 w-full bg-neutral-950 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
                    disabled={
                      !isEditable ||
                      !selectedClipHasDirtyContent ||
                      !selectedClipContentDraft?.title.trim() ||
                      !selectedHookDurationIsValid ||
                      savingClipContentId === selectedClip.id
                    }
                    type="button"
                    onClick={() => void saveClipContent()}
                  >
                    {savingClipContentId === selectedClip.id
                      ? "保存中"
                      : "タイトル・フックを保存"}
                  </button>
                </div>

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
                  className="relative max-h-[640px] min-h-0 flex-1 overflow-y-auto lg:max-h-none"
                  ref={subtitleListRef}
                >
                  {selectedSegments.length > 0 ? (
                    selectedSegments.map((segment) => {
                      const isDirty = dirtySegmentIds.has(segment.id);
                      const isSaving = savingSegmentId === segment.id;
                      const isActive = activeSegmentId === segment.id;
                      const relativeStart = clamp(
                        segment.start - selectedClip.start,
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
                              onClick={() => playFrom(segment.start)}
                            >
                              {formatTime(relativeStart)} から再生
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
                            <button
                              className="min-h-9 bg-neutral-950 px-4 text-xs font-semibold text-white disabled:bg-neutral-300"
                              disabled={!isEditable || !isDirty || isSaving}
                              type="button"
                              onClick={() => void saveSegment(segment)}
                            >
                              {isSaving ? "保存中" : "この字幕を保存"}
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
                    {selectedClip.confirmed
                      ? "このclipは確認済みです。字幕を再編集すると未確認へ戻ります。"
                      : selectedClipHasDirtySegments || selectedClipHasDirtyContent
                        ? "未保存のタイトル、フック、または字幕があります。保存後に確認済みにできます。"
                        : "このclipの動画と字幕を確認したら完了にします。"}
                  </p>
                  <button
                    className="min-h-11 w-full bg-sky-700 px-4 text-sm font-semibold text-white disabled:bg-neutral-300"
                    disabled={
                      selectedClip.confirmed ||
                      !isEditable ||
                      selectedClipHasDirtySegments ||
                      selectedClipHasDirtyContent ||
                      confirmingClipId === selectedClip.id
                    }
                    type="button"
                    onClick={() => void confirmSelectedClip()}
                  >
                    {confirmingClipId === selectedClip.id
                      ? "確認中"
                      : selectedClip.confirmed
                        ? "このclipは確認済み"
                        : "このclipを確認済みにする"}
                  </button>
                </div>
              </>
            ) : null}
          </section>
        </div>

        <section className="border border-neutral-300 bg-white px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold">
                全clip確認済み {review.confirmedClipCount} / {review.totalClipCount}
              </p>
              <p className="mt-1 text-xs text-neutral-600">
                通常・ショートをすべて確認後、字幕焼き込みとZIP作成を開始します。
              </p>
            </div>
            <button
              className="min-h-12 bg-emerald-700 px-6 text-sm font-semibold text-white disabled:bg-neutral-300"
              disabled={
                !isEditable ||
                !allConfirmed ||
                dirtySegmentIds.size > 0 ||
                hasDirtyClipContent ||
                isFinalizing
              }
              type="button"
              onClick={() => void startRendering()}
            >
              {isFinalizing ? "レンダリングを開始しています" : "字幕を確定してレンダリング"}
            </button>
          </div>
        </section>
      </section>
    </main>
  );
}
