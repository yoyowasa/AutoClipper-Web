import type { SelectionReviewWarning, SubtitleReviewClip } from "../../lib/types";
import { formatTime } from "../../lib/subtitleReview/display";

export function SelectionWarnings({ clip, seek }: { clip: SubtitleReviewClip; seek: (time: number) => void }) {
  if (!clip.selectionWarnings?.length) return null;
  const hookDuration = clip.hookSceneStart != null && clip.hookSceneEnd != null ? clip.hookSceneEnd - clip.hookSceneStart : 0;
  const relativeTime = (time: number) => formatTime(Math.max(0, time - clip.start) + hookDuration);
  return <aside aria-label="選定時の字幕確認の注意" className="border-b border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-950">
    <p className="font-semibold">このclipの字幕・内容の確認</p>
    <p className="mt-1">AIは注意が必要な字幕行を特定していません。以下の範囲の字幕全体が対象です。</p>
    {clip.selectionWarnings.map((warning: SelectionReviewWarning) => <div key={warning.code} className="mt-2">
      <button type="button" className="underline" onClick={() => seek(warning.start)}>
        {relativeTime(warning.start)}〜{relativeTime(warning.end)} を確認
      </button>
      <p>{warning.message}</p>
    </div>)}
  </aside>;
}
