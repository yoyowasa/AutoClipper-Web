"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ClipBoundaryEditor,
  type ClipBoundaryDraft
} from "../../../../components/ClipBoundaryEditor";
import { ClipHookSceneEditor } from "../../../../components/ClipHookSceneEditor";
import { ClipSelectionEditor } from "../../../../components/ClipSelectionEditor";
import { ManualClipPlanEditor } from "../../../../components/ManualClipPlanEditor";
import {
  approveClipPlan,
  createClipPlanClip,
  deleteClipPlanClip,
  getClipPlan,
  getClipPlanTranscriptSegments,
  getJobStatus,
  reselectClipPlan,
  toApiUrl,
  updateClipPlanBoundary,
  updateClipPlanHookScene,
  updateManualClipPlanClip
} from "../../../../lib/api";
import type {
  ClipPlanClip,
  ClipPlanDocument,
  ClipPlanReselectionRequest,
  ClipPlanTranscriptSegment,
  ClipSettings,
  ExportType,
  JobStatusResponse
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

function clipLabel(clip: ClipPlanClip, clips: ClipPlanClip[]): string {
  const sameType = clips.filter((item) => item.type === clip.type);
  const index = sameType.findIndex((item) => item.id === clip.id) + 1;
  return `${clip.type === "normal" ? "通常" : "ショート"} ${index}`;
}

type TranscriptPreview = ClipBoundaryDraft & {
  segments: ClipPlanTranscriptSegment[];
};

function reselectionPayload(settings: ClipSettings): ClipPlanReselectionRequest {
  return {
    normalClipSelectionPreset: settings.normalClipSelectionPreset,
    shortClipSelectionPreset: settings.shortClipSelectionPreset,
    normalClipGuidance: settings.normalClipGuidance,
    shortClipGuidance: settings.shortClipGuidance,
    excludeIntroOutro: settings.excludeIntroOutro,
    excludePromotionalContent: settings.excludePromotionalContent,
    selectionPolicy: settings.selectionPolicy,
    heatmapIntervalMode: settings.heatmapIntervalMode,
    useOpenAIScoring: settings.useOpenAIScoring
  };
}

export default function ClipPlanReviewPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = useMemo(() => readJobId(params.jobId), [params.jobId]);
  const [plan, setPlan] = useState<ClipPlanDocument | null>(null);
  const [draftSettings, setDraftSettings] = useState<ClipSettings | null>(null);
  const [selectedClipId, setSelectedClipId] = useState("");
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [isReselecting, setIsReselecting] = useState(false);
  const [isAdjusting, setIsAdjusting] = useState(false);
  const [isCreatingManualClip, setIsCreatingManualClip] = useState(false);
  const [isDeletingManualClip, setIsDeletingManualClip] = useState(false);
  const [isUpdatingHookScene, setIsUpdatingHookScene] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [previewPlayheadSourceTime, setPreviewPlayheadSourceTime] = useState(0);
  const [boundaryDraft, setBoundaryDraft] = useState<ClipBoundaryDraft | null>(
    null
  );
  const [transcriptPreview, setTranscriptPreview] =
    useState<TranscriptPreview | null>(null);
  const [isTranscriptPreviewLoading, setIsTranscriptPreviewLoading] =
    useState(false);
  const [transcriptPreviewError, setTranscriptPreviewError] = useState<
    string | null
  >(null);
  const [error, setError] = useState<string | null>(null);

  const loadPlan = useCallback(async () => {
    const document = await getClipPlan(jobId);
    setPlan(document);
    setDraftSettings(document.settings);
    const nextSelectedClipId = document.clips.some(
      (clip) => clip.id === selectedClipId
    )
      ? selectedClipId
      : (document.clips[0]?.id ?? "");
    setSelectedClipId(nextSelectedClipId);
    const nextSelectedClip = document.clips.find(
      (clip) => clip.id === nextSelectedClipId
    );
    setPreviewPlayheadSourceTime(
      nextSelectedClip?.hookSceneStart ?? nextSelectedClip?.start ?? 0
    );
    return document;
  }, [jobId, selectedClipId]);

  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;
    let timeoutId = 0;
    async function refresh() {
      try {
        const status = await getJobStatus(jobId);
        if (!active) {
          return;
        }
        setJob(status);
        if (status.status === "failed") {
          setError(status.error?.message ?? "手動切り抜きの準備に失敗しました");
          return;
        }
        let document: ClipPlanDocument;
        try {
          document = await getClipPlan(jobId);
        } catch (caught) {
          if (
            status.status === "awaiting_clip_review" ||
            status.status === "awaiting_manual_edit"
          ) {
            throw caught;
          }
          timeoutId = window.setTimeout(refresh, 1500);
          return;
        }
        if (!active) {
          return;
        }
        setPlan(document);
        setDraftSettings(document.settings);
        setSelectedClipId(document.clips[0]?.id ?? "");
        setPreviewPlayheadSourceTime(
          document.clips[0]?.hookSceneStart ?? document.clips[0]?.start ?? 0
        );
        setError(null);
        const documentWorkflowMode =
          document.workflowMode ?? document.settings.workflowMode ?? "automatic";
        if (
          documentWorkflowMode === "manual" &&
          status.status === "awaiting_subtitle_review"
        ) {
          router.push(`/jobs/${jobId}/subtitles`);
          return;
        }
        if (
          documentWorkflowMode === "manual" &&
          document.state === "approved" &&
          status.status !== "awaiting_manual_edit"
        ) {
          router.push(`/jobs/${jobId}`);
          return;
        }
        if (document.state === "preparing" || document.state === "reselecting") {
          timeoutId = window.setTimeout(refresh, 1500);
        }
      } catch (caught) {
        if (active) {
          setError(
            caught instanceof Error
              ? caught.message
              : "切り抜き予定を読み込めませんでした"
          );
        }
      }
    }
    void refresh();
    return () => {
      active = false;
      window.clearTimeout(timeoutId);
    };
  }, [jobId, router]);

  useEffect(() => {
    if (
      (!isReselecting &&
        !isAdjusting &&
        !isCreatingManualClip &&
        !isDeletingManualClip &&
        !isUpdatingHookScene) ||
      !jobId
    ) {
      return;
    }
    let active = true;
    const intervalId = window.setInterval(() => {
      void getJobStatus(jobId)
        .then(async (status) => {
          if (!active) {
            return;
          }
          setJob(status);
          if (
            status.status === "awaiting_clip_review" ||
            status.status === "awaiting_manual_edit"
          ) {
            window.clearInterval(intervalId);
            await loadPlan();
            setIsReselecting(false);
            setIsAdjusting(false);
            setIsCreatingManualClip(false);
            setIsDeletingManualClip(false);
            setIsUpdatingHookScene(false);
            if (status.error) {
              setError(status.error.message);
            }
          } else if (status.status === "failed") {
            window.clearInterval(intervalId);
            setIsReselecting(false);
            setIsAdjusting(false);
            setIsCreatingManualClip(false);
            setIsDeletingManualClip(false);
            setIsUpdatingHookScene(false);
            setError(
              status.error?.message ??
                (isUpdatingHookScene
                  ? "冒頭フック映像の更新に失敗しました"
                  : isAdjusting
                  ? "切り抜き範囲の更新に失敗しました"
                  : "再選定に失敗しました")
            );
          }
        })
        .catch((caught) => {
          if (active) {
            window.clearInterval(intervalId);
            setIsReselecting(false);
            setIsAdjusting(false);
            setIsCreatingManualClip(false);
            setIsDeletingManualClip(false);
            setIsUpdatingHookScene(false);
            setError(
              caught instanceof Error ? caught.message : "再選定の状態を取得できませんでした"
            );
          }
        });
    }, 1500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [
    isAdjusting,
    isCreatingManualClip,
    isDeletingManualClip,
    isReselecting,
    isUpdatingHookScene,
    jobId,
    loadPlan
  ]);

  const handleBoundaryDraftChange = useCallback(
    (draft: ClipBoundaryDraft | null) => {
      setBoundaryDraft(draft);
      setTranscriptPreview(null);
      setTranscriptPreviewError(null);
      if (!draft) {
        setIsTranscriptPreviewLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!boundaryDraft || !jobId) {
      return;
    }
    let active = true;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      setIsTranscriptPreviewLoading(true);
      void getClipPlanTranscriptSegments(
        jobId,
        boundaryDraft.clipId,
        boundaryDraft,
        controller.signal
      )
        .then((segments) => {
          if (!active) {
            return;
          }
          setTranscriptPreview({
            ...boundaryDraft,
            segments
          });
          setTranscriptPreviewError(null);
        })
        .catch((caught) => {
          if (
            !active ||
            (caught instanceof DOMException && caught.name === "AbortError")
          ) {
            return;
          }
          setTranscriptPreviewError(
            caught instanceof Error
              ? caught.message
              : "変更範囲の文字起こしを取得できませんでした"
          );
        })
        .finally(() => {
          if (active) {
            setIsTranscriptPreviewLoading(false);
          }
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [boundaryDraft, jobId]);

  const selectedClip =
    plan?.clips.find((clip) => clip.id === selectedClipId) ?? null;
  const selectedBoundaryDraft =
    boundaryDraft?.clipId === selectedClipId ? boundaryDraft : null;
  const selectedTranscriptPreview =
    transcriptPreview?.clipId === selectedClipId ? transcriptPreview : null;
  const workflowMode =
    plan?.workflowMode ?? plan?.settings.workflowMode ?? "automatic";
  const isManualWorkflow = workflowMode === "manual";
  const planIsEditable =
    plan?.state === "awaiting_review" ||
    (isManualWorkflow && plan?.state === "manual_editing");
  const controlsDisabled =
    isReselecting ||
    isAdjusting ||
    isCreatingManualClip ||
    isDeletingManualClip ||
    isUpdatingHookScene ||
    isApproving ||
    !planIsEditable;

  useEffect(() => {
    if (!isManualWorkflow || !isApproving || !jobId) {
      return;
    }
    let active = true;
    const intervalId = window.setInterval(() => {
      void getJobStatus(jobId)
        .then((status) => {
          if (!active) {
            return;
          }
          setJob(status);
          if (status.status === "awaiting_subtitle_review") {
            window.clearInterval(intervalId);
            router.push(`/jobs/${jobId}/subtitles`);
          } else if (status.status === "failed") {
            window.clearInterval(intervalId);
            setIsApproving(false);
            setError(
              status.error?.message ?? "手動切り抜きの字幕準備に失敗しました"
            );
          }
        })
        .catch((caught) => {
          if (!active) {
            return;
          }
          window.clearInterval(intervalId);
          setIsApproving(false);
          setError(
            caught instanceof Error
              ? caught.message
              : "字幕準備の状態を取得できませんでした"
          );
        });
    }, 1500);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [isApproving, isManualWorkflow, jobId, router]);

  async function handleBoundaryUpdate(start: number, end: number) {
    if (!selectedClip) {
      return;
    }
    setError(null);
    setIsAdjusting(true);
    try {
      await updateClipPlanBoundary(jobId, selectedClip.id, { start, end });
      setJob((current) =>
        current
          ? {
              ...current,
              status: "preparing_clip_review",
              currentStep: "調整した範囲の確認動画を準備中"
            }
          : current
      );
    } catch (caught) {
      setIsAdjusting(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "切り抜き範囲を更新できませんでした"
      );
    }
  }

  async function handleManualClipCreate(type: ExportType, start: number, end: number) {
    setError(null);
    setIsCreatingManualClip(true);
    try {
      const document = await createClipPlanClip(jobId, { type, start, end });
      setPlan(document);
      setDraftSettings(document.settings);
      setSelectedClipId(document.clips.at(-1)?.id ?? "");
      setIsCreatingManualClip(false);
    } catch (caught) {
      setIsCreatingManualClip(false);
      setError(caught instanceof Error ? caught.message : "clipを追加できませんでした");
    }
  }

  async function handleManualBoundaryUpdate(start: number, end: number) {
    if (!selectedClip) {
      return;
    }
    setError(null);
    setIsAdjusting(true);
    try {
      const document = await updateManualClipPlanClip(jobId, selectedClip.id, {
        start,
        end
      });
      setPlan(document);
      setDraftSettings(document.settings);
      setIsAdjusting(false);
    } catch (caught) {
      setIsAdjusting(false);
      setError(
        caught instanceof Error ? caught.message : "切り抜き範囲を更新できませんでした"
      );
    }
  }

  async function handleManualClipDelete(clipId: string) {
    setError(null);
    setIsDeletingManualClip(true);
    try {
      const document = await deleteClipPlanClip(jobId, clipId);
      setPlan(document);
      setDraftSettings(document.settings);
      setSelectedClipId(document.clips[0]?.id ?? "");
      setIsDeletingManualClip(false);
    } catch (caught) {
      setIsDeletingManualClip(false);
      setError(caught instanceof Error ? caught.message : "clipを削除できませんでした");
    }
  }

  async function handleHookSceneUpdate(
    start: number | null,
    end: number | null
  ) {
    if (!selectedClip) {
      return;
    }
    setError(null);
    setIsUpdatingHookScene(true);
    try {
      const action = await updateClipPlanHookScene(jobId, selectedClip.id, { start, end });
      if (isManualWorkflow && action.status === "awaiting_manual_edit") {
        await loadPlan();
        setJob((current) =>
          current ? { ...current, status: action.status } : current
        );
        setIsUpdatingHookScene(false);
        return;
      }
      setJob((current) =>
        current
          ? {
              ...current,
              status: "preparing_clip_review",
              currentStep: "冒頭フック映像の確認動画を準備中"
            }
          : current
      );
    } catch (caught) {
      setIsUpdatingHookScene(false);
      setError(
        caught instanceof Error
          ? caught.message
          : "冒頭フック映像を更新できませんでした"
      );
    }
  }

  function handlePreviewTimeUpdate(
    event: React.SyntheticEvent<HTMLVideoElement>
  ) {
    if (!selectedClip) {
      return;
    }
    const previewTime = event.currentTarget.currentTime;
    const hookStart = selectedClip.hookSceneStart;
    const hookEnd = selectedClip.hookSceneEnd;
    if (hookStart !== null && hookEnd !== null) {
      const hookDuration = hookEnd - hookStart;
      if (previewTime < hookDuration) {
        setPreviewPlayheadSourceTime(
          Math.min(hookEnd, hookStart + previewTime)
        );
        return;
      }
      setPreviewPlayheadSourceTime(
        Math.min(
          selectedClip.end,
          selectedClip.start + previewTime - hookDuration
        )
      );
      return;
    }
    setPreviewPlayheadSourceTime(
      Math.min(selectedClip.end, selectedClip.start + previewTime)
    );
  }

  async function handleReselect() {
    if (!draftSettings) {
      return;
    }
    setError(null);
    setIsReselecting(true);
    try {
      await reselectClipPlan(jobId, reselectionPayload(draftSettings));
      setJob((current) =>
        current
          ? {
              ...current,
              status: "reselecting_clips",
              currentStep: "保存済み解析結果から切り抜きを再選定中"
            }
          : current
      );
    } catch (caught) {
      setIsReselecting(false);
      setError(caught instanceof Error ? caught.message : "再選定を開始できませんでした");
    }
  }

  async function handleApprove() {
    setError(null);
    setIsApproving(true);
    try {
      const action = await approveClipPlan(jobId);
      if (isManualWorkflow) {
        setJob((current) =>
          current
            ? {
                ...current,
                status: action.status,
                currentStep: "文字起こしと字幕確認を準備中"
              }
            : current
        );
        return;
      }
      router.push(`/jobs/${jobId}/subtitles`);
    } catch (caught) {
      setIsApproving(false);
      setError(
        caught instanceof Error ? caught.message : "字幕確認へ進めませんでした"
      );
    }
  }

  if (!plan || !draftSettings) {
    return (
      <main className="min-h-screen bg-[#f7f7f4] px-6 py-8 text-neutral-950">
        <div className="mx-auto max-w-5xl border border-neutral-300 bg-white p-5 text-sm">
          {error ?? "切り抜き予定を読み込んでいます"}
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f7f7f4] text-neutral-950">
      <header className="border-b border-neutral-300 bg-white px-5 py-4">
        <div className="flex w-full flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold text-blue-700">工程 2 / 4</p>
            <h1 className="mt-1 text-2xl font-semibold">
              {isManualWorkflow ? "元動画から手動で切り抜く" : "切り抜き予定の確認"}
            </h1>
            <p className="mt-1 text-sm text-neutral-600">
              {isManualWorkflow
                ? "元動画を再生し、通常切り抜きとショートの開始・終了を指定します。"
                : "字幕作成・焼き込み前です。選ばれた範囲だけを軽量動画で確認できます。"}
            </p>
          </div>
          <Link
            className="inline-flex min-h-10 items-center border border-neutral-300 px-4 text-sm font-medium"
            href={`/jobs/${jobId}`}
          >
            Job画面へ戻る
          </Link>
        </div>
      </header>

      <div className="border-b border-neutral-300 bg-neutral-100 px-5 py-3">
        <div className="grid w-full grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div className="border-l-4 border-emerald-500 px-3 py-2 text-emerald-900">
            {isManualWorkflow ? "1. 動画準備済み" : "1. 解析・選定済み"}
          </div>
          <div className="border-l-4 border-blue-600 bg-blue-50 px-3 py-2 font-semibold text-blue-900">
            2. 予定確認
          </div>
          <div className="border-l-4 border-neutral-300 px-3 py-2 text-neutral-500">
            3. 字幕確認
          </div>
          <div className="border-l-4 border-neutral-300 px-3 py-2 text-neutral-500">
            4. 書き出し
          </div>
        </div>
      </div>

      {error ? (
        <div className="mt-4 w-full px-5">
          <div className="border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        </div>
      ) : null}

      {isManualWorkflow ? (
        <ManualClipPlanEditor
          approvalProgressLabel={job?.currentStep}
          disabled={controlsDisabled}
          isApproving={isApproving}
          isDeleting={isDeletingManualClip}
          isSaving={isAdjusting || isCreatingManualClip}
          isUpdatingHookScene={isUpdatingHookScene}
          key={plan.updatedAt}
          plan={plan}
          selectedClipId={selectedClipId}
          onApprove={() => void handleApprove()}
          onCreate={(type, start, end) => void handleManualClipCreate(type, start, end)}
          onDelete={(clipId) => void handleManualClipDelete(clipId)}
          onHookSceneUpdate={(start, end) => void handleHookSceneUpdate(start, end)}
          onSelect={setSelectedClipId}
          onUpdate={(start, end) => void handleManualBoundaryUpdate(start, end)}
        />
      ) : (

      <div className="grid w-full lg:grid-cols-[280px_minmax(0,1fr)_390px]">
        <aside className="border-r border-neutral-300 bg-white lg:row-span-2 lg:min-h-[calc(100vh-145px)]">
          <div className="border-b border-neutral-300 px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">生成予定clip</h2>
              <span className="text-xs tabular-nums text-neutral-500">
                {plan.clips.length}本・第{plan.revision}案
              </span>
            </div>
          </div>
          <div className="max-h-[38vh] overflow-y-auto lg:max-h-[calc(100vh-190px)]">
            {plan.clips.map((clip) => {
              const selected = clip.id === selectedClipId;
              return (
                <button
                  className={`block w-full border-b border-neutral-200 px-4 py-4 text-left ${
                    selected
                      ? "bg-neutral-950 text-white"
                      : "bg-white text-neutral-900 hover:bg-neutral-50"
                  }`}
                  key={clip.id}
                  type="button"
                  onClick={() => {
                    setSelectedClipId(clip.id);
                    setPreviewPlayheadSourceTime(
                      clip.hookSceneStart ?? clip.start
                    );
                  }}
                >
                  <span
                    className={`text-xs font-semibold ${
                      selected ? "text-blue-200" : "text-blue-700"
                    }`}
                  >
                    {clipLabel(clip, plan.clips)}
                  </span>
                  <span className="mt-1 line-clamp-2 block text-sm font-semibold">
                    {clip.title}
                  </span>
                  <span
                    className={`mt-2 block text-xs tabular-nums ${
                      selected ? "text-neutral-300" : "text-neutral-500"
                    }`}
                  >
                    元動画 {formatTime(clip.start)} - {formatTime(clip.end)}・
                    {formatTime(clip.duration)}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="min-w-0 border-b border-neutral-300 bg-white lg:col-start-2 lg:row-start-1 lg:border-r">
          {selectedClip ? (
            <>
              <div className="min-[1900px]:grid min-[1900px]:grid-cols-[minmax(0,1fr)_480px] min-[1900px]:items-start">
                <div className="aspect-video w-full bg-black">
                  {selectedClip.previewVideoUrl ? (
                    <video
                      aria-label={`${selectedClip.title} のプレビュー`}
                      className="h-full w-full object-contain"
                      controls
                      key={`${selectedClip.id}-${selectedClip.start}-${selectedClip.end}-${selectedClip.hookSceneStart}-${selectedClip.hookSceneEnd}-${plan.updatedAt}`}
                      preload="metadata"
                      src={`${toApiUrl(selectedClip.previewVideoUrl)}?v=${encodeURIComponent(plan.updatedAt)}`}
                      onTimeUpdate={handlePreviewTimeUpdate}
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-sm text-neutral-300">
                      プレビュー動画を準備できませんでした
                    </div>
                  )}
                </div>

                <div className="min-w-0 min-[1900px]:border-l min-[1900px]:border-neutral-300">
                  <ClipBoundaryEditor
                    clip={selectedClip}
                    disabled={controlsDisabled}
                    key={`${selectedClip.id}-${selectedClip.start}-${selectedClip.end}`}
                    saving={isAdjusting}
                    sourceDuration={plan.sourceDuration}
                    onDraftChange={handleBoundaryDraftChange}
                    onSave={(start, end) =>
                      void handleBoundaryUpdate(start, end)
                    }
                  />

                  <>
                    <ClipHookSceneEditor
                      clip={selectedClip}
                      compact
                      disabled={controlsDisabled}
                      enforceMaximumDuration={selectedClip.type === "short"}
                      key={`${selectedClip.id}-${selectedClip.hookSceneStart}-${selectedClip.hookSceneEnd}`}
                      playheadSourceTime={
                        previewPlayheadSourceTime >= selectedClip.start &&
                        previewPlayheadSourceTime <= selectedClip.end
                          ? previewPlayheadSourceTime
                          : (selectedClip.hookSceneStart ?? selectedClip.start)
                      }
                      saving={isUpdatingHookScene}
                      shortMaxDuration={plan.settings.shortMaxDuration}
                      onSave={(start, end) =>
                        void handleHookSceneUpdate(start, end)
                      }
                    />
                    <p className="border-b border-neutral-300 bg-sky-50 px-5 py-2 text-xs font-medium text-sky-900">
                      タイトルと冒頭フック文字は、次の「字幕確認」で編集できます。
                    </p>
                  </>
                </div>
              </div>
            </>
          ) : (
            <div className="p-5 text-sm text-neutral-600">clipがありません</div>
          )}
        </section>

        <aside className="border-b border-neutral-300 bg-white px-5 py-5 lg:sticky lg:top-0 lg:col-start-3 lg:row-span-2 lg:row-start-1 lg:flex lg:h-[calc(100vh-145px)] lg:min-h-0 lg:flex-col lg:border-b-0">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold text-blue-700">選択clip</p>
              <h2 className="mt-1 text-lg font-semibold text-neutral-950">
                入力中の範囲に含まれる文字起こし
              </h2>
              <p className="mt-1 text-xs tabular-nums text-neutral-500">
                {selectedBoundaryDraft
                  ? `${formatTime(selectedBoundaryDraft.start)} - ${formatTime(selectedBoundaryDraft.end)}`
                  : "開始・終了を正しく入力してください"}
              </p>
            </div>
            <span className="border border-neutral-300 bg-neutral-50 px-2 py-1 text-xs text-neutral-700">
              {isTranscriptPreviewLoading
                ? "更新中"
                : `${selectedTranscriptPreview?.segments.length ?? 0}区間`}
            </span>
          </div>

          {transcriptPreviewError ? (
            <p className="mt-3 border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {transcriptPreviewError}
            </p>
          ) : null}

          {selectedTranscriptPreview &&
          selectedTranscriptPreview.segments.length > 0 ? (
            <div className="mt-3 max-h-80 overflow-y-auto border border-neutral-200 bg-neutral-50 lg:min-h-0 lg:max-h-none lg:flex-1">
              {selectedTranscriptPreview.segments.map((segment, index) => (
                <div
                  className="border-b border-neutral-200 px-3 py-2 last:border-b-0"
                  key={`${segment.start}-${segment.end}-${index}`}
                >
                  <span className="text-xs tabular-nums text-neutral-500">
                    {formatTime(segment.start)} - {formatTime(segment.end)}
                  </span>
                  <p className="mt-1 break-words text-sm leading-6 text-neutral-900">
                    {segment.text}
                  </p>
                </div>
              ))}
            </div>
          ) : isTranscriptPreviewLoading ? (
            <p className="mt-3 text-sm text-neutral-600">
              変更した時間範囲から文字起こしを読み込んでいます
            </p>
          ) : (
            <p className="mt-3 text-sm text-neutral-600">
              この範囲に発話の文字起こしはありません
            </p>
          )}

          <p className="mt-2 text-xs leading-5 text-neutral-500">
            分秒入力と前後追加に合わせて自動更新します。字幕の修正は次の工程で行います。
          </p>
        </aside>

        <section className="border-b border-neutral-300 bg-[#f7f7f4] px-5 py-5 lg:col-start-2 lg:row-start-2 lg:border-r">
          <div>
            <p className="text-xs font-semibold text-neutral-500">再選定</p>
            <h2 className="mt-1 text-lg font-semibold">狙う場面を調整</h2>
            <p className="mt-2 text-sm leading-6 text-neutral-600">
              保存済みの文字起こし・音声・映像解析を使うため、動画の再アップロードや再文字起こしは行いません。
            </p>
          </div>

          <div className="mt-4 flex flex-col gap-3 border border-neutral-300 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-neutral-900">候補基準</p>
              <p className="mt-1 text-xs leading-5 text-neutral-600">
                {draftSettings.heatmapIntervalMode
                  ? "人気区間JSONを起点に候補を作り、既存の品質条件で絞ります。"
                  : "字幕・音声・映像で候補を作り、有効なJSON値は最大+10点の補助評価として使います。"}
              </p>
            </div>
            <div
              aria-label="再選定の候補基準"
              className="grid shrink-0 grid-cols-2 border border-neutral-300"
              role="group"
            >
              <button
                aria-pressed={!draftSettings.heatmapIntervalMode}
                className={`min-h-9 px-3 text-xs font-semibold ${
                  !draftSettings.heatmapIntervalMode
                    ? "bg-neutral-950 text-white"
                    : "bg-white text-neutral-600 hover:bg-neutral-50"
                } disabled:cursor-not-allowed disabled:opacity-50`}
                disabled={controlsDisabled}
                type="button"
                onClick={() =>
                  setDraftSettings((current) =>
                    current ? { ...current, heatmapIntervalMode: false } : current
                  )
                }
              >
                従来評価
              </button>
              <button
                aria-pressed={draftSettings.heatmapIntervalMode}
                className={`min-h-9 px-3 text-xs font-semibold ${
                  draftSettings.heatmapIntervalMode
                    ? "bg-emerald-700 text-white"
                    : "bg-white text-neutral-600 hover:bg-neutral-50"
                } disabled:cursor-not-allowed disabled:opacity-50`}
                disabled={controlsDisabled}
                type="button"
                onClick={() =>
                  setDraftSettings((current) =>
                    current ? { ...current, heatmapIntervalMode: true } : current
                  )
                }
              >
                JSON区間
              </button>
            </div>
          </div>

          <div className="mt-3">
            <ClipSelectionEditor
              disabled={controlsDisabled}
              settings={draftSettings}
              onChange={setDraftSettings}
            />
          </div>

          {draftSettings.useOpenAIScoring ? (
            <p className="mt-3 border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              AI文脈判定を有効にすると、再選定でもOpenAI APIを使用します。
            </p>
          ) : (
            <p className="mt-3 text-xs text-neutral-600">
              現在はローカル判定です。再選定によるAPI料金は発生しません。
            </p>
          )}

          <button
            className="mt-4 min-h-11 w-full border border-neutral-950 bg-white px-4 text-sm font-semibold text-neutral-950 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={controlsDisabled}
            type="button"
            onClick={() => void handleReselect()}
          >
            {isReselecting
              ? job?.currentStep || "再選定中"
              : "この条件でもう一度選ぶ"}
          </button>

          <div className="my-5 border-t border-neutral-300" />

          <p className="text-sm font-semibold text-neutral-900">
            この予定で問題なければ次へ
          </p>
          <p className="mt-1 text-xs leading-5 text-neutral-600">
            次の画面でclipごとの字幕を再生しながら修正します。まだ最終レンダリングは始まりません。
          </p>
          <button
            className="mt-4 min-h-12 w-full bg-blue-700 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={controlsDisabled || plan.clips.length === 0}
            type="button"
            onClick={() => void handleApprove()}
          >
            {isApproving ? "字幕確認を準備中" : "この切り抜き予定で字幕確認へ"}
          </button>
        </section>
      </div>
      )}
    </main>
  );
}
