"use client";

import { useMemo, useRef, useState } from "react";

import type {
  ClipPlanClip,
  ClipPlanDocument,
  ExportType
} from "../lib/types";
import { toApiUrl } from "../lib/api";
import { ClipHookSceneEditor } from "./ClipHookSceneEditor";

type ManualClipPlanEditorProps = {
  plan: ClipPlanDocument;
  approvalProgressLabel?: string;
  selectedClipId: string;
  disabled: boolean;
  isApproving: boolean;
  isDeleting: boolean;
  isSaving: boolean;
  isUpdatingHookScene: boolean;
  onApprove: () => void;
  onCreate: (type: ExportType, start: number, end: number) => void;
  onDelete: (clipId: string) => void;
  onHookSceneUpdate: (start: number | null, end: number | null) => void;
  onSelect: (clipId: string) => void;
  onUpdate: (start: number, end: number) => void;
};

type TimeParts = {
  minutes: string;
  seconds: string;
};

function splitTime(value: number): TimeParts {
  const safe = Math.max(0, value);
  const minutes = Math.floor(safe / 60);
  const seconds = Math.round((safe - minutes * 60) * 1000) / 1000;
  return { minutes: String(minutes), seconds: String(seconds) };
}

function combineTime(parts: TimeParts): number | null {
  if (parts.minutes.trim() === "" || parts.seconds.trim() === "") {
    return null;
  }
  const minutes = Number(parts.minutes);
  const seconds = Number(parts.seconds);
  if (
    !Number.isFinite(minutes) ||
    !Number.isFinite(seconds) ||
    minutes < 0 ||
    seconds < 0 ||
    seconds >= 60
  ) {
    return null;
  }
  return Math.round((minutes * 60 + seconds) * 1000) / 1000;
}

function formatTime(value: number): string {
  const safe = Math.max(0, value);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  const secondText = seconds.toFixed(1).padStart(4, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${secondText}`
    : `${minutes}:${secondText}`;
}

function mediaErrorMessage(code?: number): string {
  if (code === 2) {
    return "動画の読み込みに失敗しました。通信状態または編集用動画の準備状態を確認してください。";
  }
  if (code === 3) {
    return "この動画をブラウザでデコードできません。編集用動画の再生成が必要です。";
  }
  if (code === 4) {
    return "この動画形式はブラウザで再生できません。編集用動画を利用できませんでした。";
  }
  return "動画を再生できません。時間を置いて再読み込みしてください。";
}

function clipLabel(clip: ClipPlanClip, clips: ClipPlanClip[]): string {
  const sameType = clips.filter((item) => item.type === clip.type);
  const index = sameType.findIndex((item) => item.id === clip.id) + 1;
  return `${clip.type === "normal" ? "通常" : "ショート"} ${index}`;
}

function TimeInput({
  label,
  parts,
  disabled,
  onAdjust,
  onChange
}: {
  label: string;
  parts: TimeParts;
  disabled: boolean;
  onAdjust: (delta: number) => void;
  onChange: (parts: TimeParts) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-neutral-700">{label}</span>
      <span className="mt-1 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] items-center gap-1.5">
        <input
          aria-label={`${label} 分`}
          className="min-h-10 min-w-0 border border-neutral-300 px-2 text-sm tabular-nums"
          disabled={disabled}
          min={0}
          step={1}
          type="number"
          value={parts.minutes}
          onChange={(event) => onChange({ ...parts, minutes: event.target.value })}
        />
        <span className="text-xs text-neutral-500">分</span>
        <input
          aria-label={`${label} 秒`}
          className="min-h-10 min-w-0 border border-neutral-300 px-2 text-sm tabular-nums"
          disabled={disabled}
          max={59.999}
          min={0}
          step={0.001}
          type="number"
          value={parts.seconds}
          onChange={(event) => onChange({ ...parts, seconds: event.target.value })}
        />
        <span className="text-xs text-neutral-500">秒</span>
      </span>
      <span className="mt-1.5 grid grid-cols-4 gap-1">
        {[-5, -1, 1, 5].map((delta) => (
          <button
            className="min-h-7 border border-neutral-300 bg-white px-1 text-[11px] font-semibold tabular-nums text-neutral-700 disabled:opacity-50"
            disabled={disabled}
            key={delta}
            type="button"
            onClick={() => onAdjust(delta)}
          >
            {delta > 0 ? "+" : ""}{delta}秒
          </button>
        ))}
      </span>
    </label>
  );
}

export function ManualClipPlanEditor({
  plan,
  approvalProgressLabel,
  selectedClipId,
  disabled,
  isApproving,
  isDeleting,
  isSaving,
  isUpdatingHookScene,
  onApprove,
  onCreate,
  onDelete,
  onHookSceneUpdate,
  onSelect,
  onUpdate
}: ManualClipPlanEditorProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const selectedClip =
    plan.clips.find((clip) => clip.id === selectedClipId) ?? null;
  const [draftType, setDraftType] = useState<ExportType>(
    selectedClip?.type ?? "normal"
  );
  const [startParts, setStartParts] = useState<TimeParts>(() =>
    splitTime(selectedClip?.start ?? 0)
  );
  const [endParts, setEndParts] = useState<TimeParts>(() =>
    splitTime(selectedClip?.end ?? Math.min(plan.sourceDuration ?? 60, 60))
  );
  const [playhead, setPlayhead] = useState(selectedClip?.start ?? 0);
  const [rangePlaybackEnd, setRangePlaybackEnd] = useState<number | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const start = combineTime(startParts);
  const end = combineTime(endParts);
  const duration = start !== null && end !== null ? end - start : null;
  const sourceDuration = plan.sourceDuration;
  const playbackUrl = toApiUrl(plan.editorVideoUrl ?? plan.sourceVideoUrl);
  const subtitleMode = plan.settings.manualSubtitleMode ?? "auto";
  const editing = selectedClip !== null;
  const validation = useMemo(() => {
    if (start === null || end === null) {
      return "分と秒を正しく入力してください";
    }
    if (end <= start) {
      return "終了は開始より後にしてください";
    }
    if (end - start < 1) {
      return "切り抜き範囲は1秒以上にしてください";
    }
    if (sourceDuration !== null && end > sourceDuration + 0.001) {
      return `元動画の長さ ${formatTime(sourceDuration)} を超えています`;
    }
    const outputType = selectedClip?.type ?? draftType;
    if (outputType === "short" && end - start > plan.settings.shortMaxDuration + 0.001) {
      return `ショートは ${formatTime(plan.settings.shortMaxDuration)} 以内にしてください`;
    }
    return null;
  }, [draftType, end, plan.settings.shortMaxDuration, selectedClip?.type, sourceDuration, start]);

  function beginCreate(type: ExportType) {
    const startAt = Math.min(playhead, Math.max(0, (sourceDuration ?? playhead) - 1));
    const suggestedLength = type === "short" ? 30 : 90;
    const endAt = Math.min(sourceDuration ?? startAt + suggestedLength, startAt + suggestedLength);
    onSelect("");
    setDraftType(type);
    setStartParts(splitTime(startAt));
    setEndParts(splitTime(Math.max(startAt + 1, endAt)));
    setRangePlaybackEnd(null);
  }

  function selectClip(clip: ClipPlanClip) {
    setStartParts(splitTime(clip.start));
    setEndParts(splitTime(clip.end));
    setDraftType(clip.type);
    setPlayhead(clip.start);
    setRangePlaybackEnd(null);
    if (videoRef.current) {
      videoRef.current.currentTime = clip.start;
    }
    onSelect(clip.id);
  }

  function setFromPlayhead(boundary: "start" | "end") {
    if (boundary === "start") {
      setStartParts(splitTime(playhead));
    } else {
      setEndParts(splitTime(playhead));
    }
  }

  function adjustBoundary(boundary: "start" | "end", delta: number) {
    const current = boundary === "start" ? start : end;
    if (current === null) {
      return;
    }
    const adjusted = Math.min(sourceDuration ?? Number.POSITIVE_INFINITY, Math.max(0, current + delta));
    if (boundary === "start") {
      setStartParts(splitTime(adjusted));
    } else {
      setEndParts(splitTime(adjusted));
    }
  }

  function playRange() {
    if (!videoRef.current || start === null || end === null || validation) {
      return;
    }
    videoRef.current.currentTime = start;
    setPlayhead(start);
    setRangePlaybackEnd(end);
    void videoRef.current.play().catch(() => {
      setVideoError("動画の再生を開始できません。ブラウザの再生許可と動画形式を確認してください。");
    });
  }

  function handleTimeUpdate() {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    setPlayhead(video.currentTime);
    if (rangePlaybackEnd !== null && video.currentTime >= rangePlaybackEnd - 0.02) {
      video.pause();
      video.currentTime = rangePlaybackEnd;
      setPlayhead(rangePlaybackEnd);
      setRangePlaybackEnd(null);
    }
  }

  function saveRange() {
    if (start === null || end === null || validation) {
      return;
    }
    if (selectedClip) {
      onUpdate(start, end);
    } else {
      onCreate(draftType, start, end);
    }
  }

  function requestDelete() {
    if (!selectedClip) {
      return;
    }
    if (window.confirm(`${clipLabel(selectedClip, plan.clips)} を削除しますか？`)) {
      onDelete(selectedClip.id);
    }
  }

  function retryVideoLoad() {
    setVideoError(null);
    videoRef.current?.load();
  }

  return (
    <div className="grid w-full lg:grid-cols-[280px_minmax(0,1fr)_390px]">
      <aside className="border-r border-neutral-300 bg-white lg:row-span-2 lg:min-h-[calc(100vh-145px)]">
        <div className="border-b border-neutral-300 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold">作成したclip</h2>
            <span className="text-xs tabular-nums text-neutral-500">{plan.clips.length}本</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button
              className="min-h-9 bg-neutral-950 px-2 text-xs font-semibold text-white disabled:opacity-50"
              disabled={disabled}
              type="button"
              onClick={() => beginCreate("normal")}
            >
              ＋通常clip
            </button>
            <button
              className="min-h-9 bg-sky-700 px-2 text-xs font-semibold text-white disabled:opacity-50"
              disabled={disabled}
              type="button"
              onClick={() => beginCreate("short")}
            >
              ＋ショート
            </button>
          </div>
        </div>
        <div className="max-h-[38vh] overflow-y-auto lg:max-h-[calc(100vh-245px)]">
          {plan.clips.length === 0 ? (
            <p className="px-4 py-5 text-sm leading-6 text-neutral-500">
              元動画を再生し、開始・終了を決めて最初のclipを追加してください。
            </p>
          ) : null}
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
                onClick={() => selectClip(clip)}
              >
                <span className={`text-xs font-semibold ${selected ? "text-blue-200" : "text-blue-700"}`}>
                  {clipLabel(clip, plan.clips)}
                </span>
                <span className="mt-1 line-clamp-2 block text-sm font-semibold">{clip.title}</span>
                <span className={`mt-2 block text-xs tabular-nums ${selected ? "text-neutral-300" : "text-neutral-500"}`}>
                  元動画 {formatTime(clip.start)} - {formatTime(clip.end)}・{formatTime(clip.duration)}
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="min-w-0 border-b border-r border-neutral-300 bg-white lg:col-start-2 lg:row-start-1">
        <div className="aspect-video w-full bg-black">
          <video
            aria-label="手動切り抜き用の元動画"
            className="h-full w-full object-contain"
            controls
            data-playback-source={plan.editorVideoUrl ? "editor-proxy" : "source-video"}
            preload="metadata"
            ref={videoRef}
            src={playbackUrl}
            onCanPlay={() => setVideoError(null)}
            onError={() => setVideoError(mediaErrorMessage(videoRef.current?.error?.code))}
            onLoadedMetadata={() => setVideoError(null)}
            onSeeked={handleTimeUpdate}
            onTimeUpdate={handleTimeUpdate}
          />
        </div>
        {videoError ? (
          <div
            className="flex flex-wrap items-center justify-between gap-3 border-b border-red-300 bg-red-50 px-5 py-3"
            role="alert"
          >
            <p className="text-xs font-semibold leading-5 text-red-800">{videoError}</p>
            <button
              className="min-h-9 border border-red-300 bg-white px-3 text-xs font-semibold text-red-800"
              type="button"
              onClick={retryVideoLoad}
            >
              動画を再読み込み
            </button>
          </div>
        ) : null}
        <div className="border-b border-neutral-300 bg-neutral-50 px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-semibold tabular-nums text-neutral-900">
              現在位置 {formatTime(playhead)}
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                className="min-h-9 border border-neutral-300 bg-white px-3 text-xs font-semibold disabled:opacity-50"
                disabled={disabled}
                type="button"
                onClick={() => setFromPlayhead("start")}
              >
                現在位置を開始に設定
              </button>
              <button
                className="min-h-9 border border-neutral-300 bg-white px-3 text-xs font-semibold disabled:opacity-50"
                disabled={disabled}
                type="button"
                onClick={() => setFromPlayhead("end")}
              >
                現在位置を終了に設定
              </button>
            </div>
          </div>
        </div>

        {selectedClip ? (
          <ClipHookSceneEditor
            clip={selectedClip}
            compact
            disabled={disabled}
            enforceMaximumDuration={selectedClip.type === "short"}
            key={`${selectedClip.id}-${selectedClip.hookSceneStart}-${selectedClip.hookSceneEnd}`}
            playheadSourceTime={playhead}
            saving={isUpdatingHookScene}
            shortMaxDuration={plan.settings.shortMaxDuration}
            onSave={onHookSceneUpdate}
          />
        ) : null}
      </section>

      <aside className="border-b border-neutral-300 bg-white px-5 py-5 lg:sticky lg:top-0 lg:col-start-3 lg:row-span-2 lg:row-start-1 lg:flex lg:h-[calc(100vh-145px)] lg:min-h-0 lg:flex-col lg:border-b-0">
        <div>
          <p className="text-xs font-semibold text-blue-700">
            {editing ? `${clipLabel(selectedClip, plan.clips)}を編集` : "新しいclipを追加"}
          </p>
          <h2 className="mt-1 text-lg font-semibold">
            {editing ? "開始・終了を調整" : draftType === "normal" ? "通常切り抜きを作成" : "ショートを作成"}
          </h2>
          <p className="mt-1 text-xs leading-5 text-neutral-600">
            動画を再生し、現在位置ボタンか分・秒入力で範囲を決めます。
          </p>
        </div>

        <div className="mt-4 grid gap-4">
          <TimeInput
            disabled={disabled}
            label="開始時刻"
            parts={startParts}
            onAdjust={(delta) => adjustBoundary("start", delta)}
            onChange={setStartParts}
          />
          <TimeInput
            disabled={disabled}
            label="終了時刻"
            parts={endParts}
            onAdjust={(delta) => adjustBoundary("end", delta)}
            onChange={setEndParts}
          />
        </div>

        <div className="mt-4 border-y border-neutral-200 py-3 text-xs leading-5 text-neutral-700">
          <p>範囲: {start === null ? "--" : formatTime(start)} - {end === null ? "--" : formatTime(end)}</p>
          <p className="font-semibold text-neutral-950">
            長さ: {duration !== null && duration > 0 ? formatTime(duration) : "--"}
          </p>
        </div>

        {validation ? <p className="mt-3 text-xs font-semibold text-red-700">{validation}</p> : null}

        <div className="mt-4 grid gap-2">
          <button
            className="min-h-10 border border-neutral-400 bg-white px-3 text-xs font-semibold disabled:opacity-50"
            disabled={disabled || validation !== null}
            type="button"
            onClick={playRange}
          >
            この範囲を再生
          </button>
          <button
            className="min-h-11 bg-blue-700 px-3 text-sm font-semibold text-white disabled:bg-neutral-300"
            disabled={disabled || validation !== null}
            type="button"
            onClick={saveRange}
          >
            {isSaving
              ? "保存中"
              : editing
                ? "この範囲に更新"
                : `${draftType === "normal" ? "通常clip" : "ショート"}として追加`}
          </button>
          {selectedClip ? (
            <button
              className="min-h-10 border border-red-300 bg-white px-3 text-xs font-semibold text-red-700 disabled:opacity-50"
              disabled={disabled}
              type="button"
              onClick={requestDelete}
            >
              {isDeleting ? "削除中" : "このclipを削除"}
            </button>
          ) : null}
        </div>

        <div className="mt-auto border-t border-neutral-300 pt-5">
          <p className="text-sm font-semibold text-neutral-900">clipを追加できたら次へ</p>
          <p className="mt-1 text-xs leading-5 text-neutral-600">
            {subtitleMode === "none"
              ? "次の画面でタイトル・フックと見た目を確認します。会話字幕は表示されません。"
              : subtitleMode === "manual"
                ? "次の画面で通常・ショート別に字幕を入力し、見た目を確認します。"
                : "次の画面で自動字幕と見た目を確認します。"}
          </p>
          <button
            className="mt-4 min-h-12 w-full bg-blue-700 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={disabled || plan.clips.length === 0}
            type="button"
            onClick={onApprove}
          >
            {isApproving
              ? approvalProgressLabel ||
                (subtitleMode === "none" ? "内容確認を準備中" : "字幕確認を準備中")
              : subtitleMode === "none"
                ? "字幕なしで内容確認へ"
                : subtitleMode === "manual"
                  ? "字幕を手入力へ"
                  : "自動字幕を確認へ"}
          </button>
        </div>
      </aside>
    </div>
  );
}
