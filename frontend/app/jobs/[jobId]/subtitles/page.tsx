"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";

import {
  confirmSubtitleReviewClip,
  finalizeSubtitleReview,
  getSubtitleReview,
  toApiUrl,
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

export default function SubtitleReviewPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [review, setReview] = useState<SubtitleReviewDocument | null>(null);
  const [selectedClipId, setSelectedClipId] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [dirtySegmentIds, setDirtySegmentIds] = useState<Set<string>>(new Set());
  const [savingSegmentId, setSavingSegmentId] = useState<string | null>(null);
  const [confirmingClipId, setConfirmingClipId] = useState<string | null>(null);
  const [isFinalizing, setIsFinalizing] = useState(false);
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
  const selectedClipStart = selectedClip?.start ?? null;
  const selectedClipHasDirtySegments = selectedSegments.some((segment) =>
    dirtySegmentIds.has(segment.id)
  );

  useEffect(() => {
    if (selectedClipStart === null || !videoRef.current) {
      return;
    }
    videoRef.current.currentTime = selectedClipStart;
  }, [selectedClipId, selectedClipStart]);

  function selectClip(clip: SubtitleReviewClip) {
    setSelectedClipId(clip.id);
    setError(null);
  }

  function playFrom(start: number) {
    if (!videoRef.current || !selectedClip) {
      return;
    }
    videoRef.current.currentTime = Math.max(selectedClip.start, start - 0.15);
    void videoRef.current.play();
  }

  function handleVideoTimeUpdate() {
    if (!videoRef.current || !selectedClip) {
      return;
    }
    if (videoRef.current.currentTime >= selectedClip.end) {
      videoRef.current.pause();
      videoRef.current.currentTime = selectedClip.end;
    }
  }

  function updateDraft(segmentId: string, text: string) {
    setDrafts((current) => ({ ...current, [segmentId]: text }));
    setDirtySegmentIds((current) => new Set(current).add(segmentId));
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
    if (!selectedClip || selectedClipHasDirtySegments) {
      setError("未保存の字幕があります。先に保存してください。");
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
    if (!review || dirtySegmentIds.size > 0) {
      setError("未保存の字幕があります。先に保存してください。");
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
    <main className="min-h-screen bg-[#f7f7f4] px-4 py-6 text-neutral-950 sm:px-6">
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-5">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-neutral-300 pb-5">
          <div>
            <p className="text-sm font-medium uppercase text-neutral-500">AutoClipper</p>
            <h1 className="mt-2 text-3xl font-semibold">字幕確認</h1>
            <p className="mt-2 text-sm text-neutral-600">
              確認済み {review.confirmedClipCount} / {review.totalClipCount} ・ 修正{" "}
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
              2. 字幕確認
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
              3. 書き出し
            </p>
            <p className="mt-1 text-sm font-semibold">
              {review.state === "completed"
                ? "完了"
                : isEditable
                  ? "確認後に開始"
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

        {error ? (
          <div className="border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        ) : null}

        <div className="grid min-h-[680px] border border-neutral-300 bg-white lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="border-b border-neutral-300 lg:border-b-0 lg:border-r">
            <div className="border-b border-neutral-200 px-4 py-4">
              <p className="text-sm font-semibold">生成予定clip</p>
              <div className="mt-2 h-2 overflow-hidden bg-neutral-100">
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
            <div className="max-h-72 overflow-y-auto lg:max-h-[760px]">
              {review.clips.map((clip) => (
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
                        clip.confirmed
                          ? clip.id === selectedClipId
                            ? "text-emerald-300"
                            : "text-emerald-700"
                          : clip.id === selectedClipId
                            ? "text-amber-200"
                            : "text-amber-700"
                      }`}
                    >
                      {clip.confirmed ? "確認済み" : "未確認"}
                    </span>
                  </span>
                  <span className="mt-2 block line-clamp-2 text-sm font-medium">{clip.title}</span>
                  <span
                    className={`mt-2 block text-xs ${
                      clip.id === selectedClipId ? "text-neutral-300" : "text-neutral-500"
                    }`}
                  >
                    {formatTime(clip.start)} - {formatTime(clip.end)}
                    {clip.editedSegmentCount > 0 ? ` ・ 修正${clip.editedSegmentCount}件` : ""}
                  </span>
                </button>
              ))}
            </div>
          </aside>

          <section className="min-w-0">
            {selectedClip ? (
              <>
                <div className="border-b border-neutral-300 p-4 sm:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase text-neutral-500">
                        {clipLabel(selectedClip, review.clips)}
                      </p>
                      <h2 className="mt-1 text-xl font-semibold">{selectedClip.title}</h2>
                      <p className="mt-1 text-sm text-neutral-600">
                        {formatTime(selectedClip.start)} - {formatTime(selectedClip.end)}
                      </p>
                    </div>
                    <button
                      className="min-h-10 border border-neutral-300 bg-white px-4 text-sm font-medium"
                      type="button"
                      onClick={() => playFrom(selectedClip.start)}
                    >
                      clip先頭から再生
                    </button>
                  </div>

                  <div className="mt-4 overflow-hidden bg-black">
                    <video
                      className="aspect-video w-full bg-black"
                      controls
                      playsInline
                      preload="metadata"
                      ref={videoRef}
                      src={toApiUrl(review.sourceVideoUrl)}
                      onTimeUpdate={handleVideoTimeUpdate}
                    />
                  </div>
                </div>

                <div className="px-4 py-5 sm:px-5">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-300 pb-3">
                    <div>
                      <h3 className="text-base font-semibold">字幕テキスト</h3>
                      <p className="mt-1 text-xs text-neutral-500">
                        時刻は固定です。再生して音声と違う文字だけ修正します。
                      </p>
                    </div>
                    <p className="text-xs font-medium text-neutral-600">
                      {selectedSegments.length} segments
                    </p>
                  </div>

                  {selectedSegments.length > 0 ? (
                    <div>
                      {selectedSegments.map((segment) => {
                        const isDirty = dirtySegmentIds.has(segment.id);
                        const isSaving = savingSegmentId === segment.id;
                        return (
                          <div
                            className="grid gap-3 border-b border-neutral-200 py-4 md:grid-cols-[120px_minmax(0,1fr)_92px]"
                            key={segment.id}
                          >
                            <button
                              className="h-fit text-left text-sm font-semibold text-sky-700"
                              type="button"
                              onClick={() => playFrom(segment.start)}
                            >
                              {formatTime(segment.start)}
                              <span className="mt-1 block text-xs font-normal text-neutral-500">
                                音声を再生
                              </span>
                            </button>
                            <div className="min-w-0">
                              <textarea
                                className={`min-h-24 w-full resize-y border px-3 py-2 text-base leading-7 outline-none ${
                                  isDirty
                                    ? "border-amber-500 bg-amber-50"
                                    : "border-neutral-300 bg-white focus:border-sky-600"
                                }`}
                                disabled={!isEditable}
                                value={drafts[segment.id] ?? segment.text}
                                onChange={(event) => updateDraft(segment.id, event.target.value)}
                              />
                              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                                {segment.edited ? (
                                  <span className="bg-sky-100 px-2 py-1 font-medium text-sky-800">
                                    修正済み
                                  </span>
                                ) : null}
                                {segment.affectedClipIds.length > 1 ? (
                                  <span className="bg-violet-100 px-2 py-1 font-medium text-violet-800">
                                    {segment.affectedClipIds.length}本のclipへ共通反映
                                  </span>
                                ) : null}
                                {isDirty ? (
                                  <span className="bg-amber-100 px-2 py-1 font-medium text-amber-800">
                                    未保存
                                  </span>
                                ) : null}
                              </div>
                            </div>
                            <button
                              className="min-h-10 h-fit bg-neutral-950 px-3 text-sm font-semibold text-white disabled:bg-neutral-300"
                              disabled={!isEditable || !isDirty || isSaving}
                              type="button"
                              onClick={() => void saveSegment(segment)}
                            >
                              {isSaving ? "保存中" : "保存"}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="border-b border-neutral-200 py-8 text-sm text-neutral-600">
                      このclipに表示対象の字幕はありません。
                    </div>
                  )}

                  <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-neutral-300 pt-5">
                    <p className="text-sm text-neutral-600">
                      {selectedClip.confirmed
                        ? "このclipは確認済みです。字幕を再編集すると未確認へ戻ります。"
                        : "音声と字幕を確認後、確認済みにしてください。"}
                    </p>
                    <button
                      className="min-h-11 bg-sky-700 px-5 text-sm font-semibold text-white disabled:bg-neutral-300"
                      disabled={
                        selectedClip.confirmed ||
                        !isEditable ||
                        selectedClipHasDirtySegments ||
                        confirmingClipId === selectedClip.id
                      }
                      type="button"
                      onClick={() => void confirmSelectedClip()}
                    >
                      {confirmingClipId === selectedClip.id
                        ? "確認中"
                        : selectedClip.confirmed
                          ? "確認済み"
                          : "このclipを確認済みにする"}
                    </button>
                  </div>
                </div>
              </>
            ) : null}
          </section>
        </div>

        <section className="sticky bottom-0 border border-neutral-300 bg-white px-5 py-4 shadow-[0_-6px_20px_rgba(0,0,0,0.08)]">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold">
                確認済み {review.confirmedClipCount} / {review.totalClipCount}
              </p>
              <p className="mt-1 text-xs text-neutral-600">
                全clip確認後に字幕焼き込みとZIP作成を開始します。
              </p>
            </div>
            <button
              className="min-h-12 bg-emerald-700 px-6 text-sm font-semibold text-white disabled:bg-neutral-300"
              disabled={
                !isEditable ||
                !allConfirmed ||
                dirtySegmentIds.size > 0 ||
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
