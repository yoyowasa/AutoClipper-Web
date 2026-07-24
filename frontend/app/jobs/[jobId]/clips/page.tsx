"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ClipSelectionEditor } from "../../../../components/ClipSelectionEditor";
import {
  approveClipPlan,
  getClipPlan,
  getJobStatus,
  reselectClipPlan,
  toApiUrl
} from "../../../../lib/api";
import type {
  ClipPlanClip,
  ClipPlanDocument,
  ClipPlanReselectionRequest,
  ClipSettings,
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

function reselectionPayload(settings: ClipSettings): ClipPlanReselectionRequest {
  return {
    normalClipSelectionPreset: settings.normalClipSelectionPreset,
    shortClipSelectionPreset: settings.shortClipSelectionPreset,
    normalClipGuidance: settings.normalClipGuidance,
    shortClipGuidance: settings.shortClipGuidance,
    excludeIntroOutro: settings.excludeIntroOutro,
    excludePromotionalContent: settings.excludePromotionalContent,
    selectionPolicy: settings.selectionPolicy,
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
  const [isApproving, setIsApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPlan = useCallback(async () => {
    const document = await getClipPlan(jobId);
    setPlan(document);
    setDraftSettings(document.settings);
    setSelectedClipId((current) =>
      document.clips.some((clip) => clip.id === current)
        ? current
        : (document.clips[0]?.id ?? "")
    );
    return document;
  }, [jobId]);

  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;
    void Promise.all([getClipPlan(jobId), getJobStatus(jobId)])
      .then(([document, status]) => {
        if (!active) {
          return;
        }
        setPlan(document);
        setDraftSettings(document.settings);
        setSelectedClipId(document.clips[0]?.id ?? "");
        setJob(status);
      })
      .catch((caught) => {
        if (active) {
          setError(
            caught instanceof Error
              ? caught.message
              : "切り抜き予定を読み込めませんでした"
          );
        }
      });
    return () => {
      active = false;
    };
  }, [jobId]);

  useEffect(() => {
    if (!isReselecting || !jobId) {
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
          if (status.status === "awaiting_clip_review") {
            window.clearInterval(intervalId);
            await loadPlan();
            setIsReselecting(false);
            if (status.error) {
              setError(status.error.message);
            }
          } else if (status.status === "failed") {
            window.clearInterval(intervalId);
            setIsReselecting(false);
            setError(status.error?.message ?? "再選定に失敗しました");
          }
        })
        .catch((caught) => {
          if (active) {
            window.clearInterval(intervalId);
            setIsReselecting(false);
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
  }, [isReselecting, jobId, loadPlan]);

  const selectedClip =
    plan?.clips.find((clip) => clip.id === selectedClipId) ?? null;
  const controlsDisabled =
    isReselecting || isApproving || plan?.state !== "awaiting_review";

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
      await approveClipPlan(jobId);
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
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold text-blue-700">工程 2 / 4</p>
            <h1 className="mt-1 text-2xl font-semibold">切り抜き予定の確認</h1>
            <p className="mt-1 text-sm text-neutral-600">
              字幕作成・焼き込み前です。選ばれた範囲だけを軽量動画で確認できます。
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
        <div className="mx-auto grid max-w-[1600px] grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div className="border-l-4 border-emerald-500 px-3 py-2 text-emerald-900">
            1. 解析・選定済み
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
        <div className="mx-auto mt-4 max-w-[1600px] px-5">
          <div className="border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        </div>
      ) : null}

      <div className="mx-auto grid max-w-[1600px] lg:grid-cols-[280px_minmax(0,1fr)_390px]">
        <aside className="border-r border-neutral-300 bg-white lg:min-h-[calc(100vh-145px)]">
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
                  onClick={() => setSelectedClipId(clip.id)}
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
                    {formatTime(clip.start)} - {formatTime(clip.end)}・
                    {formatTime(clip.duration)}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="min-w-0 border-b border-neutral-300 bg-white lg:border-r">
          {selectedClip ? (
            <>
              <div className="border-b border-neutral-300 px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold text-blue-700">
                      {clipLabel(selectedClip, plan.clips)}
                    </p>
                    <h2 className="mt-1 text-lg font-semibold">{selectedClip.title}</h2>
                    <p className="mt-1 text-sm tabular-nums text-neutral-600">
                      元動画 {formatTime(selectedClip.start)} -{" "}
                      {formatTime(selectedClip.end)}（{formatTime(selectedClip.duration)}）
                    </p>
                  </div>
                  <span className="border border-neutral-300 bg-neutral-50 px-3 py-2 text-xs text-neutral-700">
                    {selectedClip.boundaryRefined ? "境界補正あり" : "選定範囲"}
                  </span>
                </div>
              </div>

              <div className="bg-neutral-950 p-4">
                <div className="mx-auto aspect-video w-full max-w-[1100px] bg-black">
                  {selectedClip.previewVideoUrl ? (
                    <video
                      className="h-full w-full object-contain"
                      controls
                      key={selectedClip.id}
                      preload="metadata"
                      src={toApiUrl(selectedClip.previewVideoUrl)}
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-sm text-neutral-300">
                      プレビュー動画を準備できませんでした
                    </div>
                  )}
                </div>
              </div>

              <div className="border-b border-neutral-300 px-5 py-4">
                <p className="text-xs font-semibold text-neutral-500">選定時の文字起こし抜粋</p>
                <p className="mt-2 text-sm leading-6 text-neutral-800">
                  {selectedClip.transcriptExcerpt || "文字起こし抜粋なし"}
                </p>
                <p className="mt-2 text-xs text-neutral-500">
                  これは選定用の内部データです。字幕の修正は次の工程で行います。
                </p>
              </div>
            </>
          ) : (
            <div className="p-5 text-sm text-neutral-600">clipがありません</div>
          )}
        </section>

        <aside className="bg-[#f7f7f4] px-5 py-5">
          <div>
            <p className="text-xs font-semibold text-neutral-500">再選定</p>
            <h2 className="mt-1 text-lg font-semibold">狙う場面を調整</h2>
            <p className="mt-2 text-sm leading-6 text-neutral-600">
              保存済みの文字起こし・候補を使うため、動画の再アップロードや再文字起こしは行いません。
            </p>
          </div>

          <div className="mt-4">
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
        </aside>
      </div>
    </main>
  );
}
