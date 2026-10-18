"use client";

import { livePlaybackSource } from "../../lib/subtitleReview/livePlaybackSource";
import { DraftReviewPlayer } from "./DraftReviewPlayer";
import { LiveShortFramingPreview } from "../LiveShortFramingPreview";
import { ClipTextOverlay } from "../ClipTextStyleEditor";
import { formatTime, clamp } from "../../lib/subtitleReview/display";
import { previewVideoSrc } from "../../lib/subtitleReview/preview";
import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";
import { ReviewShortFraming } from "./ReviewStyleFraming";

export function ReviewPreview({ context }: { context: SubtitleReviewViewContext }) {
  const {
    selectedClip: savedClip,
    selectedShortFramingDraft,
    retainedLivePreviews,
    review,
    jobId,
    isEditable,
    selectedShortPreviewRegenerating,
    selectedShortFramingDirty,
    playerShellRef,
    selectedPlayerReady,
    selectedPlayerVideoUrl,
    playerMediaKey,
    videoRef,
    selectedPlayerPreviewVersion,
    setPreviewLoadFailedClipIds,
    setIsBuffering,
    setIsPlayerReady,
    togglePlayback,
    handleVideoError,
    pendingPlayerResumeRef,
    setIsPlaying,
    setVideoLoadSeconds,
    handleVideoSeeking,
    handleVideoTimeUpdate,
    isShowingLivePreview,
    showLiveTitle,
    selectedDefaultResolvedClipTextStyles,
    selectedResolvedClipTextStyles,
    selectedClipTextStyles,
    selectedClipContentDraft,
    showLiveHook,
    liveHookText,
    showLiveSubtitle,
    activePreviewSubtitleEvent,
    retryingPreviewClipId,
    retrySelectedPreview,
    isPlayerReady,
    isBuffering,
    selectedPreviewLoadFailed,
    videoLoadSeconds,
    retryVideoLoad,
    openPausedSubtitleDraft,
    livePreviewReady,
    selectedPreviewReady,
    setShowSavedPreview,
    clipDuration,
    clipTime,
    seekToClipTime,
    isPlaying,
    playFromClipStart,
    skipBy,
    isMuted,
    toggleMuted,
    volume,
    changeVolume,
    playbackRate,
    changePlaybackRate,
    toggleFullscreen
  } = context;
  const selectedClip = savedClip ? { ...savedClip,
    hookSceneStart: selectedClipContentDraft?.hookSceneStart ?? null, hookSceneEnd: selectedClipContentDraft?.hookSceneEnd ?? null
  } : null;
  const media = savedClip ? livePlaybackSource(savedClip, review, retainedLivePreviews[savedClip.id]) : null;
  const draftFramingKey = selectedShortFramingDraft ? JSON.stringify([selectedShortFramingDraft.framingOffsetX,
    selectedShortFramingDraft.framingOffsetY, selectedShortFramingDraft.framingZoom,
    selectedShortFramingDraft.shortLayout ?? selectedClip?.shortLayout ?? review.shortLayout]) : null;
  const replacePicture = selectedShortFramingDirty || Boolean(selectedClip?.previewFraming)
    || (media?.framingKey !== null && media?.framingKey !== draftFramingKey);
  return (
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
                          画角は下書きに反映し、clipの確定時にまとめて保存します。
                        </p>
                      </div>

                    </div>
                    {selectedShortFramingDraft ? (
                      <div className="space-y-3 border-b border-neutral-300 bg-neutral-50 px-4 py-3">
                        <p className="text-sm font-semibold">このショートのみ微調整</p>
                        <p className="text-xs text-neutral-600">元映像の枠を動かして確認。位置・倍率は待たずに反映します。</p>
                        <ReviewShortFraming key={`${selectedClip.id}:${selectedClip.start}:${selectedClip.end}:${review.sourceVideoUrl}:${review.shortTopBannerEnabled}:${review.shortBottomBannerEnabled}`} context={context} />
                        <p className="text-xs text-neutral-600">
                          左右 {selectedShortFramingDraft.framingOffsetX} ・ 上下 {selectedShortFramingDraft.framingOffsetY} ・ 拡大 {Math.round(selectedShortFramingDraft.framingZoom * 100)}%
                        </p>
                        <p className="text-xs font-semibold text-sky-700" aria-live="polite">
                          {selectedShortPreviewRegenerating ? "プレビュー準備中" : selectedShortFramingDirty ? "未保存の変更あり" : "保存済み"}
                        </p>
                        {selectedClip.previewFraming ? <p className="text-xs text-sky-800">
                          変更した画角を編集プレビューで再生できます。動画の再生成は不要です。
                        </p> : null}
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
                      {isShowingLivePreview ? <DraftReviewPlayer context={context} /> : selectedPlayerReady && selectedPlayerVideoUrl ? (
                        <video
                        className="h-full w-full cursor-pointer bg-black object-contain"
                        key={playerMediaKey}
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
                        onLoadedMetadata={(event) => {
                          const resume = pendingPlayerResumeRef.current;
                          if (resume?.key === playerMediaKey) {
                            const video = event.currentTarget;
                            video.currentTime = clamp(resume.time, 0, Math.max(0, video.duration - 0.05));
                            pendingPlayerResumeRef.current = null;
                            if (resume.playing) void video.play().catch(() => {});
                          }
                          setIsPlayerReady(true);
                        }}
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
                      {isShowingLivePreview && selectedClip.type === "short" && replacePicture && selectedShortFramingDraft ? (
                        <LiveShortFramingPreview
                          key={`${selectedClip.id}:${selectedClip.shortLayout ?? review.shortLayout}`} jobId={jobId} clipId={selectedClip.id}
                          sourceUrl={review.sourceVideoUrl} clockRef={videoRef}
                          framing={selectedShortFramingDraft} layout={selectedShortFramingDraft.shortLayout ?? selectedClip.shortLayout ?? review.shortLayout}
                          start={selectedClip.start} end={selectedClip.end}
                          hookStart={selectedClip.hookSceneStart} hookEnd={selectedClip.hookSceneEnd}
                          topBannerUrl={review.shortTopBannerEnabled ? `/api/jobs/${jobId}/subtitle-review/banner-assets/top?v=${review.updatedAt}` : undefined}
                          bottomBannerUrl={review.shortBottomBannerEnabled ? `/api/jobs/${jobId}/subtitle-review/banner-assets/bottom?v=${review.updatedAt}` : undefined}
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
                            {review.state === "completed"
                              ? "完成済みです。結果画面で完成動画を確認してください。"
                              : selectedClip.previewState === "failed"
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
                          {review.state !== "completed" && (selectedClip.previewState === "queued" ||
                          selectedClip.previewState === "rendering") ? (
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
                        <div className="flex items-center gap-2">
                          <button
                            className="border border-sky-400 px-2 py-1 font-semibold text-sky-100 disabled:opacity-50"
                            disabled={!isEditable}
                            onClick={openPausedSubtitleDraft}
                            type="button"
                          >
                            停止位置に字幕を追加
                          </button>
                        {livePreviewReady && selectedPreviewReady ? (
                          <button className="border border-neutral-600 px-2 py-1" type="button"
                            onClick={() => setShowSavedPreview((current) => !current)}>
                            {isShowingLivePreview ? (selectedClip.previewFraming ? "変更前の画角を見る" : "保存済みを見る") : "編集プレビューへ戻る"}
                          </button>
                        ) : null}
                        </div>
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
  );
}
