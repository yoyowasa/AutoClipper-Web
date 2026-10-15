"use client";

import { ReviewCharacterPreset } from "../ReviewCharacterPreset";
import { TitleHookSuggestionPanel } from "../TitleHookSuggestionPanel";
import { descriptionWithHashtags, tagsFromText, youtubeTagsText } from "../../lib/youtubePosting";
import { limitToTwoTextLines } from "../../lib/subtitleReview/text";
import { hashtagsFromText, postCopyText } from "../../lib/subtitleReview/posting";
import type { SubtitleReviewViewContext } from "../../lib/subtitleReview/hooks/context";
import { ReviewHookSceneSettings } from "./ReviewHookSceneSettings";

export function ReviewContentEditor({ context }: { context: SubtitleReviewViewContext }) {
  const {
    selectedClip,
    selectedClipHasDirtyContent,
    isEditable,
    selectedClipContentDraft,
    updateClipContentDraft,
    hasReviewMutationInFlight,
    saveShortBannerSettings,
    review,
    isSavingShortBannerSettings,
    selectedHookDurationIsValid,
    copyPostField,
    copiedPostField,
    requestingSuggestionClipId,
    autoGeneratingSuggestionClipIds,
    selectedPlayerReady,
    previewingSuggestionId,
    selectedSuggestionRecord,
    selectedSuggestionsAreStale,
    applyTitleHookSuggestion,
    clearSelectedHook,
    generateTitleHookSuggestions,
    previewTitleHookSuggestion
  } = context;
  if (!selectedClip) return null;
  return (
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
                        フック映像の区間は、clipの確定でタイトル・字幕とまとめて保存します。
                      </p>
                    ) : null}

                    <p className="mt-3 border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-medium text-sky-900">
                      変更は簡易プレビューへ即時反映します。clipの確定で字幕修正もまとめて保存します。
                    </p>

                    <ReviewHookSceneSettings context={context} />
                    </div>
                  </div>
  );
}
