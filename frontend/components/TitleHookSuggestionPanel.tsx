import type {
  TitleHookSuggestion,
  TitleHookSuggestionResponse
} from "../lib/types";

type TitleHookSuggestionPanelProps = {
  busy: boolean;
  canPreview: boolean;
  disabled: boolean;
  previewingSuggestionId: string | null;
  response: TitleHookSuggestionResponse | null;
  stale: boolean;
  onApply: (suggestion: TitleHookSuggestion) => void;
  onClearHook: () => void;
  onGenerate: (forceRegenerate: boolean) => void;
  onPreview: (suggestion: TitleHookSuggestion) => void;
};

function formatSeconds(value: number): string {
  const safe = Math.max(0, value);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${minutes}:${seconds.toFixed(1).padStart(4, "0")}`;
}

function hasHookScene(suggestion: TitleHookSuggestion): boolean {
  return (
    suggestion.hookSceneStart !== null &&
    suggestion.hookSceneEnd !== null &&
    suggestion.hookSceneEnd > suggestion.hookSceneStart
  );
}

export function TitleHookSuggestionPanel({
  busy,
  canPreview,
  disabled,
  previewingSuggestionId,
  response,
  stale,
  onApply,
  onClearHook,
  onGenerate,
  onPreview
}: TitleHookSuggestionPanelProps) {
  const pending = response?.state === "queued" || response?.state === "generating";
  const ready = response?.state === "ready";
  const generateLabel = stale
    ? "現在の字幕から再提案"
    : ready
      ? "別案を再生成"
      : "現在の字幕からAI案を生成";

  return (
    <section
      aria-labelledby="title-hook-suggestions-heading"
      className="mt-3 border border-violet-200 bg-violet-50/60"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-violet-200 px-3 py-2">
        <div>
          <h4
            className="text-xs font-semibold text-violet-950"
            id="title-hook-suggestions-heading"
          >
            AI タイトル・フック案
          </h4>
          <p className="mt-0.5 text-[11px] text-violet-800">
            ボタンを押した時だけ生成します。案を選ぶまで入力欄は変わりません。
          </p>
        </div>
        <button
          className="min-h-9 border border-violet-700 bg-white px-3 text-xs font-semibold text-violet-900 disabled:border-neutral-300 disabled:text-neutral-400"
          disabled={disabled || busy || pending}
          type="button"
          onClick={() => onGenerate(Boolean(response))}
        >
          {busy || pending ? "AI案を生成中" : generateLabel}
        </button>
      </div>

      <div aria-live="polite">
        {stale ? (
          <p className="border-b border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900">
            字幕が変更されています。この案は古いため適用できません。
          </p>
        ) : null}
        {response?.state === "failed" ? (
          <p className="border-b border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
            AI案を生成できませんでした。手入力はそのまま利用できます。
            {response.error ? ` ${response.error}` : ""}
          </p>
        ) : null}
        {pending ? (
          <p className="px-3 py-3 text-xs font-medium text-violet-900">
            字幕から候補を作成しています。この画面の入力は続けられます。
          </p>
        ) : null}
      </div>

      {ready && response.suggestions.length > 0 ? (
        <div className="grid gap-2 p-2">
          {response.suggestions.map((suggestion, index) => (
            <article className="border border-neutral-300 bg-white p-3" key={suggestion.id}>
              <div className="flex items-center justify-between gap-2">
                <h5 className="text-xs font-semibold text-neutral-900">案 {index + 1}</h5>
                {hasHookScene(suggestion) ? (
                  <button
                    className="min-h-8 border border-neutral-400 px-2 text-[11px] font-semibold disabled:text-neutral-400"
                    disabled={disabled || stale || !canPreview}
                    type="button"
                    onClick={() => onPreview(suggestion)}
                  >
                    {previewingSuggestionId === suggestion.id
                      ? "候補を再生中"
                      : "フック候補を再生"}
                  </button>
                ) : null}
              </div>
              <dl className="mt-2 grid gap-2 text-xs">
                <div>
                  <dt className="font-semibold text-neutral-500">公開用タイトル</dt>
                  <dd className="mt-0.5 break-words text-neutral-950">
                    {suggestion.publicationTitle}
                  </dd>
                </div>
                <div>
                  <dt className="font-semibold text-neutral-500">動画内タイトル</dt>
                  <dd className="mt-0.5 break-words text-neutral-950">
                    {suggestion.overlayTitle}
                  </dd>
                </div>
                <div>
                  <dt className="font-semibold text-neutral-500">冒頭フック</dt>
                  <dd className="mt-0.5 break-words text-neutral-950">
                    {suggestion.hookText || "表示なし"}
                  </dd>
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-neutral-600">
                  <span>表示 {suggestion.hookDurationSeconds.toFixed(1)}秒</span>
                  <span>
                    区間 {hasHookScene(suggestion) && suggestion.hookSceneStart !== null && suggestion.hookSceneEnd !== null
                      ? `${formatSeconds(suggestion.hookSceneStart)}〜${formatSeconds(suggestion.hookSceneEnd)}（clip内）`
                      : "なし"}
                  </span>
                </div>
                <div>
                  <dt className="font-semibold text-neutral-500">選定理由</dt>
                  <dd className="mt-0.5 text-[11px] leading-5 text-neutral-700">
                    {suggestion.reason}
                  </dd>
                </div>
              </dl>
              <button
                className="mt-3 min-h-9 w-full bg-violet-800 px-3 text-xs font-semibold text-white disabled:bg-neutral-300"
                disabled={disabled || stale}
                type="button"
                onClick={() => onApply(suggestion)}
              >
                この案を使う
              </button>
            </article>
          ))}
        </div>
      ) : null}

      <div className="border-t border-violet-200 p-2">
        <button
          className="min-h-9 w-full border border-neutral-400 bg-white px-3 text-xs font-semibold text-neutral-800 disabled:text-neutral-400"
          disabled={disabled}
          type="button"
          onClick={onClearHook}
        >
          フックなしにする
        </button>
      </div>
    </section>
  );
}
