// Port of render/subtitle_timing.py; shared fixtures verify both render paths.
export type SubtitleWord = { start: number; end: number; word: string; probability?: number | null };
export const MIN_SUBTITLE_FRAGMENT_CHARACTERS = 6;
export const LONG_EDITED_SUBTITLE_SECONDS = 6;
const BREAKS = ["。、！？!?", "、，, ", "でにはをがともやへ"];
export const normalizeSubtitle = (text: string): string => text.trim().split(/\s+/u).filter(Boolean).join(" ");

export function usableSubtitleWords(text: string, words?: ReadonlyArray<SubtitleWord> | null): boolean {
  if (!words?.length || text.replace(/\s/gu, "") !== words.map(w => w.word).join("").replace(/\s/gu, "")) return false;
  let previous = Number.NEGATIVE_INFINITY;
  for (const word of words) {
    if (!Number.isFinite(word.start) || !Number.isFinite(word.end) || word.start < previous || word.end < word.start) return false;
    previous = word.end;
  }
  return words.some(w => w.end > w.start);
}

export function longEditedSubtitleWarning(segment: {
  start: number; end: number; text: string; originalText: string; words?: SubtitleWord[] | null;
}, text = segment.text): boolean {
  return text !== segment.originalText && segment.end - segment.start >= LONG_EDITED_SUBTITLE_SECONDS &&
    !usableSubtitleWords(text, segment.words);
}

export function subtitleChunkUnits(units: ReadonlyArray<string>, limit: number): [number, number][] {
  const chunks: [number, number][] = [];
  const length = (value: string) => Array.from(normalizeSubtitle(value)).length;
  let start = 0;
  while (start < units.length) {
    if (length(units.slice(start).join("")) <= limit) {
      chunks.push([start, units.length]);
      break;
    }
    const fitting: number[] = [];
    let overflow: number | undefined;
    for (let index = start + 1; index < units.length; index++) {
      const size = length(units.slice(start, index).join(""));
      if (size < MIN_SUBTITLE_FRAGMENT_CHARACTERS) continue;
      if (length(units.slice(index).join("")) < MIN_SUBTITLE_FRAGMENT_CHARACTERS) break;
      if (size > limit) { overflow = index; break; }
      fitting.push(index);
    }
    let end = fitting.at(-1) ?? overflow ?? units.length;
    if (fitting.length) {
      for (const breaks of BREAKS) {
        const preferred = fitting.filter(index => breaks.includes(Array.from(units.slice(start, index).join("")).at(-1) ?? ""));
        if (preferred.length) { end = preferred.at(-1)!; break; }
      }
    }
    chunks.push([start, end]);
    start = end;
  }
  return chunks;
}

export function speechSubtitleChunks(words: ReadonlyArray<SubtitleWord>, limit: number) {
  return subtitleChunkUnits(words.map(w => w.word), limit).map(([a, b]) => ({
    start: words[a].start, end: words[b - 1].end, text: normalizeSubtitle(words.slice(a, b).map(w => w.word).join(""))
  }));
}

export function subtitleTextChunks(text: string, limit: number): string[] {
  const characters = Array.from(normalizeSubtitle(text));
  return subtitleChunkUnits(characters, limit).map(([a, b]) => characters.slice(a, b).join("").trim());
}
