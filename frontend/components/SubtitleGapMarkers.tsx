import { subtitleGapLabel, unacknowledgedSubtitleGaps } from "../lib/subtitleGaps";
import type { SubtitleReviewGap } from "../lib/types";

export function SubtitleGapMarkers({
  gaps, duration, onSelect
}: {
  gaps?: SubtitleReviewGap[];
  duration: number;
  onSelect: (gap: SubtitleReviewGap) => void;
}) {
  const visibleGaps = unacknowledgedSubtitleGaps(gaps);
  if (duration <= 0 || visibleGaps.length === 0) return null;
  return (
    <div className="mb-1" aria-label="字幕なし（音あり）の再生バー">
      <p className="mb-1 text-[11px] text-amber-200">橙色: 字幕なし（音あり）{visibleGaps.length}か所</p>
      <div className="relative h-2 w-full bg-neutral-700">
        {visibleGaps.map((gap) => (
          <button
            aria-label={`${subtitleGapLabel(gap)}へ移動して停止`}
            className="absolute top-0 h-full min-w-px bg-amber-400 hover:bg-amber-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
            key={gap.id}
            style={{ left: `${gap.start / duration * 100}%`, width: `${(gap.end - gap.start) / duration * 100}%` }}
            title={subtitleGapLabel(gap)}
            type="button"
            onClick={() => onSelect(gap)}
          />
        ))}
      </div>
    </div>
  );
}

export function SubtitleGapRow({
  gap, editable, saving, canSeek, onSelect, onAcknowledge
}: {
  gap: SubtitleReviewGap;
  editable: boolean;
  saving: boolean;
  canSeek: boolean;
  onSelect: (gap: SubtitleReviewGap) => void;
  onAcknowledge: (gap: SubtitleReviewGap) => void;
}) {
  if (gap.acknowledged) return null;
  return (
    <div className="border-b border-amber-300 bg-amber-50 px-3 py-3">
      <button
        className="text-left text-sm font-semibold text-amber-900 underline disabled:no-underline disabled:opacity-60"
        disabled={!canSeek}
        type="button"
        onClick={() => onSelect(gap)}
      >
        {subtitleGapLabel(gap)}
      </button>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-amber-900">移動して音声を確認し、停止位置から字幕を追加できます。</p>
        <button
          className="min-h-8 border border-amber-600 bg-white px-2 text-xs font-medium text-amber-900 disabled:opacity-50"
          disabled={!editable || saving}
          type="button"
          onClick={() => onAcknowledge(gap)}
        >
          {saving ? "確認を保存中" : "確認済みにする"}
        </button>
      </div>
    </div>
  );
}
