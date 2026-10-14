import { subtitleGapLabel } from "../lib/subtitleGaps";
import type { SubtitleReviewGap } from "../lib/types";

export function SubtitleGapMarkers({
  gaps, duration, onSelect
}: {
  gaps?: SubtitleReviewGap[];
  duration: number;
  onSelect: (gap: SubtitleReviewGap) => void;
}) {
  const visibleGaps = gaps ?? [];
  if (duration <= 0 || visibleGaps.length === 0) return null;
  return (
    <div className="mb-1" aria-label="字幕なし（音あり）の再生バー">
      <p className="mb-1 text-[11px] text-amber-200">橙色: 字幕なし（音あり）</p>
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
