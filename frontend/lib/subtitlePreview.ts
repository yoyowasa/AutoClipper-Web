import type { ClipTextStyle } from "./types";

type SubtitlePreviewSegment = {
  style?: ClipTextStyle;
  start: number;
  end: number;
  text: string;
};

export type SubtitlePreviewEvent = {
  style?: ClipTextStyle;
  start: number;
  end: number;
  text: string;
};

type SubtitlePreviewEventOptions = {
  segments: ReadonlyArray<SubtitlePreviewSegment>;
  candidateStart: number;
  candidateEnd: number;
  hookSceneDuration: number;
  suppressionEnd: number;
  maxCharsPerLine: number;
  maxLines: number;
  minSubtitleDuration: number;
  maxSubtitleDuration: number;
  minGapBetweenSubtitles: number;
};

const PUNCTUATION_BREAKS = new Set(Array.from("。、！？!?"));
const PHRASE_BREAKS = new Set(Array.from("、，, "));
const SOFT_JA_BOUNDARIES = new Set(Array.from("でにはをがともやへ"));
const OVERLAY_MAX_LINES = 2;
const OVERLAY_HORIZONTAL_SAFE_RATIO = 0.05;
const OVERLAY_MIN_FONT_SIZE_RATIO = 0.55;
const OVERLAY_MIN_FONT_SIZE_PX = 36;

export type OverlayTextFit = {
  lines: string[];
  effectiveFontSize: number;
  maxWidthPx: number;
  fits: boolean;
  overflowReason: "min_font_size" | null;
};

export type OverlayTextFitOptions = {
  outputWidth: number;
  fontSize: number;
  fontSizeScale: number;
  marginX: number;
  outlineWidth: number;
  shadow: number;
  alignment: number;
  xPercent: number;
  maxLines?: number;
  minFontSize?: number;
};

function normalizeText(text: string): string {
  return text.trim().split(/\s+/u).filter(Boolean).join(" ");
}

function normalizeOverlayText(text: string, maxLines: number): string {
  const lines = text
    .replace(/\r\n|\r|\u2028|\u2029|\\N/gu, "\n")
    .split("\n")
    .map((line) => normalizeText(line))
    .filter(Boolean);
  if (lines.length === 0) {
    return "";
  }
  const lineLimit = Math.max(1, Math.trunc(maxLines));
  if (lines.length > lineLimit) {
    return [
      ...lines.slice(0, lineLimit - 1),
      lines.slice(lineLimit - 1).join(" ")
    ].join("\n");
  }
  return lines.join("\n");
}

export function overlayCharacterWidth(character: string): number {
  const codePoint = character.codePointAt(0);
  if (codePoint === undefined) {
    return 0;
  }
  if (
    (codePoint >= 0x0300 && codePoint <= 0x036f) ||
    (codePoint >= 0x1ab0 && codePoint <= 0x1aff) ||
    (codePoint >= 0x1dc0 && codePoint <= 0x1dff) ||
    (codePoint >= 0x20d0 && codePoint <= 0x20ff) ||
    (codePoint >= 0xfe00 && codePoint <= 0xfe0f) ||
    (codePoint >= 0xfe20 && codePoint <= 0xfe2f) ||
    codePoint === 0x200d
  ) {
    return 0;
  }
  if (/\s/u.test(character)) {
    return 0.5;
  }
  if (codePoint <= 0x7f || (codePoint >= 0xff61 && codePoint <= 0xff9f)) {
    return 0.55;
  }
  if (
    (codePoint >= 0x1100 && codePoint <= 0x115f) ||
    (codePoint >= 0x2329 && codePoint <= 0x232a) ||
    (codePoint >= 0x2e80 && codePoint <= 0xa4cf) ||
    (codePoint >= 0xac00 && codePoint <= 0xd7a3) ||
    (codePoint >= 0xf900 && codePoint <= 0xfaff) ||
    (codePoint >= 0xfe10 && codePoint <= 0xfe19) ||
    (codePoint >= 0xfe30 && codePoint <= 0xfe6f) ||
    (codePoint >= 0xff01 && codePoint <= 0xff60) ||
    (codePoint >= 0xffe0 && codePoint <= 0xffe6) ||
    (codePoint >= 0x1f000 && codePoint <= 0x1faff) ||
    (codePoint >= 0x20000 && codePoint <= 0x3fffd)
  ) {
    return 1;
  }
  return 0.65;
}

export function overlayTextWidthUnits(text: string): number {
  return Array.from(text).reduce(
    (total, character) => total + overlayCharacterWidth(character),
    0
  );
}

function balancedOverlayLines(text: string, maxLines: number): string[] {
  const manualLines = text.split("\n");
  if (manualLines.length > 1 || maxLines <= 1) {
    return manualLines.slice(0, Math.max(1, maxLines));
  }
  const characters = Array.from(text);
  if (characters.length <= 1) {
    return [text];
  }

  const totalWidth = overlayTextWidthUnits(text);
  let bestIndex = 1;
  let bestScore = Number.POSITIVE_INFINITY;
  for (let index = 1; index < characters.length; index += 1) {
    const left = characters.slice(0, index).join("");
    const leftWidth = overlayTextWidthUnits(left);
    const rightWidth = totalWidth - leftWidth;
    const previous = characters[index - 1];
    const following = characters[index];
    let boundaryPenalty: number;
    if (PUNCTUATION_BREAKS.has(previous)) {
      boundaryPenalty = 0;
    } else if (/\s/u.test(previous) || /\s/u.test(following)) {
      boundaryPenalty = totalWidth * 0.02;
    } else if (SOFT_JA_BOUNDARIES.has(previous)) {
      boundaryPenalty = totalWidth * 0.04;
    } else {
      boundaryPenalty = totalWidth * 0.12;
    }
    const score =
      Math.max(leftWidth, rightWidth) +
      Math.abs(leftWidth - rightWidth) * 0.2 +
      boundaryPenalty;
    if (score < bestScore) {
      bestIndex = index;
      bestScore = score;
    }
  }
  return [
    characters.slice(0, bestIndex).join(""),
    characters.slice(bestIndex).join("")
  ];
}

function overlayMaxWidth(options: OverlayTextFitOptions): number {
  const outputWidth = Math.max(1, Math.trunc(options.outputWidth));
  const safeMargin = Math.max(
    Math.max(0, Math.trunc(options.marginX)),
    outputWidth * OVERLAY_HORIZONTAL_SAFE_RATIO
  );
  const leftEdge = safeMargin;
  const rightEdge = outputWidth - safeMargin;
  const anchorX =
    (outputWidth * Math.min(100, Math.max(0, options.xPercent))) / 100;
  const column = (Math.min(9, Math.max(1, Math.trunc(options.alignment))) - 1) % 3;
  let available: number;
  if (column === 0) {
    available = rightEdge - anchorX;
  } else if (column === 2) {
    available = anchorX - leftEdge;
  } else {
    available = 2 * Math.min(anchorX - leftEdge, rightEdge - anchorX);
  }
  const edgeEffect =
    2 * Math.max(0, Math.trunc(options.outlineWidth) + Math.trunc(options.shadow));
  return Math.max(1, available - edgeEffect);
}

export function fitOverlayPreviewText(
  text: string,
  options: OverlayTextFitOptions
): OverlayTextFit {
  const maxLines = Math.max(1, Math.trunc(options.maxLines ?? OVERLAY_MAX_LINES));
  const cleanText = normalizeOverlayText(text, maxLines);
  const requestedFontSize = Math.max(1, Math.trunc(options.fontSize));
  const maxWidthPx = overlayMaxWidth(options);
  if (!cleanText) {
    return {
      lines: [],
      effectiveFontSize: requestedFontSize,
      maxWidthPx,
      fits: true,
      overflowReason: null
    };
  }

  const fontSizeScale = Math.max(0.01, options.fontSizeScale);
  const oneLineWidth =
    overlayTextWidthUnits(cleanText) * requestedFontSize * fontSizeScale;
  const lines =
    !cleanText.includes("\n") && oneLineWidth <= maxWidthPx
      ? [cleanText]
      : balancedOverlayLines(cleanText, maxLines);
  const widestLineUnits = Math.max(...lines.map(overlayTextWidthUnits));
  const fittedFontSize =
    widestLineUnits <= 0
      ? requestedFontSize
      : Math.min(
          requestedFontSize,
          Math.floor(maxWidthPx / (widestLineUnits * fontSizeScale))
        );
  const defaultMinimum = Math.max(
    OVERLAY_MIN_FONT_SIZE_PX,
    Math.floor(requestedFontSize * OVERLAY_MIN_FONT_SIZE_RATIO + 0.5)
  );
  const resolvedMinimum = Math.min(
    requestedFontSize,
    Math.max(1, Math.trunc(options.minFontSize ?? defaultMinimum))
  );
  const fits = fittedFontSize >= resolvedMinimum;
  return {
    lines,
    effectiveFontSize: Math.max(resolvedMinimum, fittedFontSize),
    maxWidthPx,
    fits,
    overflowReason: fits ? null : "min_font_size"
  };
}

function roundMilliseconds(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function bestBreakIndex(
  characters: string[],
  limit: number,
  minimum?: number
): number {
  if (characters.length <= limit) {
    return characters.length;
  }

  const resolvedMinimum = minimum ?? Math.max(3, Math.trunc(limit * 0.45));
  const searchEnd = Math.min(limit, characters.length - 1);
  for (const breakCharacters of [
    PUNCTUATION_BREAKS,
    PHRASE_BREAKS,
    SOFT_JA_BOUNDARIES
  ]) {
    for (let index = searchEnd; index >= resolvedMinimum; index -= 1) {
      if (breakCharacters.has(characters[index])) {
        return index + 1;
      }
    }
  }
  if (characters.includes(" ")) {
    for (let index = searchEnd; index >= resolvedMinimum; index -= 1) {
      if (characters[index] === " ") {
        return index + 1;
      }
    }
  }
  return limit;
}

function splitSubtitleText(text: string, maxCharactersPerEvent: number): string[] {
  const cleanText = normalizeText(text);
  if (!cleanText) {
    return [];
  }

  const chunks: string[] = [];
  let remaining = Array.from(cleanText);
  while (remaining.length > 0) {
    if (remaining.length <= maxCharactersPerEvent) {
      chunks.push(remaining.join(""));
      break;
    }
    const breakIndex = bestBreakIndex(remaining, maxCharactersPerEvent);
    let chunk = remaining.slice(0, breakIndex).join("").trim();
    remaining = Array.from(remaining.slice(breakIndex).join("").trim());
    if (!chunk) {
      chunk = remaining.slice(0, maxCharactersPerEvent).join("").trim();
      remaining = Array.from(
        remaining.slice(maxCharactersPerEvent).join("").trim()
      );
    }
    chunks.push(chunk);
  }
  return chunks;
}

export function splitSubtitlePreviewLines(
  text: string,
  maxCharactersPerLine: number,
  maxLines = 2
): string {
  const explicitLines = text
    .replace(/\r\n|\r|\u2028|\u2029|\\N/gu, "\n")
    .split("\n");
  if (explicitLines.length > 1) {
    const resolvedMaxLines = Math.max(1, maxLines);
    const lines = explicitLines
      .slice(0, resolvedMaxLines)
      .map((line) => normalizeText(line));
    if (explicitLines.length > resolvedMaxLines) {
      lines[resolvedMaxLines - 1] = normalizeText(
        [lines[resolvedMaxLines - 1], ...explicitLines.slice(resolvedMaxLines)].join(
          " "
        )
      );
    }
    return lines.filter(Boolean).join("\n");
  }

  const cleanText = normalizeText(text);
  if (!cleanText) {
    return "";
  }

  const lineLimit = Math.max(1, maxCharactersPerLine);
  let remaining = Array.from(cleanText);
  const lines: string[] = [];
  for (let lineIndex = 0; lineIndex < Math.max(1, maxLines); lineIndex += 1) {
    if (remaining.length === 0) {
      break;
    }
    if (remaining.length <= lineLimit || lineIndex === maxLines - 1) {
      lines.push(remaining.join(""));
      break;
    }
    const remainingLineCount = maxLines - lineIndex;
    const minimum =
      remaining.length <= lineLimit * remainingLineCount
        ? Math.max(1, remaining.length - lineLimit * (remainingLineCount - 1))
        : undefined;
    const breakIndex = bestBreakIndex(remaining, lineLimit, minimum);
    lines.push(remaining.slice(0, breakIndex).join("").trim());
    remaining = Array.from(remaining.slice(breakIndex).join("").trim());
  }
  return lines.filter(Boolean).join("\n");
}

function eventsForSegment(
  segment: SubtitlePreviewSegment,
  options: SubtitlePreviewEventOptions
): SubtitlePreviewEvent[] {
  const text = normalizeText(segment.text);
  if (!text) {
    return [];
  }

  const duration = Math.max(0.01, segment.end - segment.start);
  const maxCharactersPerEvent = Math.max(
    1,
    options.maxCharsPerLine * options.maxLines
  );
  const maxEventsForDuration = Math.max(
    1,
    Math.floor(duration / options.minSubtitleDuration)
  );
  let eventCharacterLimit = maxCharactersPerEvent;
  let chunks = splitSubtitleText(text, eventCharacterLimit);
  const minEventsForMaxDuration = Math.max(
    1,
    Math.ceil(duration / options.maxSubtitleDuration)
  );
  if (
    chunks.length < minEventsForMaxDuration &&
    Array.from(text).length >= minEventsForMaxDuration * 4
  ) {
    eventCharacterLimit = Math.max(
      4,
      Math.ceil(Array.from(text).length / minEventsForMaxDuration)
    );
    chunks = splitSubtitleText(text, eventCharacterLimit);
  }
  if (chunks.length > maxEventsForDuration) {
    eventCharacterLimit = Math.max(
      maxCharactersPerEvent,
      Math.ceil(Array.from(text).length / maxEventsForDuration)
    );
    chunks = splitSubtitleText(text, eventCharacterLimit);
  }

  const totalWeight = chunks.reduce(
    (total, chunk) => total + Math.max(1, Array.from(chunk).length),
    0
  );
  let cursor = segment.start;
  const events: SubtitlePreviewEvent[] = [];
  chunks.forEach((chunk, index) => {
    let end: number;
    if (index === chunks.length - 1) {
      end = segment.end;
    } else {
      const weight = Math.max(1, Array.from(chunk).length);
      end = Math.min(cursor + (duration * weight) / totalWeight, segment.end);
    }
    if (end <= cursor) {
      end = Math.min(segment.end, cursor + 0.01);
    }
    events.push({
      ...(segment.style ? { style: segment.style } : {}),
      start: roundMilliseconds(cursor),
      end: roundMilliseconds(end),
      text: chunk
    });
    cursor = end;
  });
  return events.filter((event) => event.end > event.start && event.text);
}

function canMergeEvents(
  previous: SubtitlePreviewEvent,
  current: SubtitlePreviewEvent,
  options: SubtitlePreviewEventOptions
): boolean {
  const gap = current.start - previous.end;
  if (JSON.stringify(previous.style ?? null) !== JSON.stringify(current.style ?? null)) {
    return false;
  }
  if (gap < -0.01) {
    return false;
  }
  const combinedText = normalizeText(`${previous.text} ${current.text}`);
  const maxCharacters = options.maxCharsPerLine * options.maxLines;
  const combinedDuration = current.end - previous.start;
  const needsMoreTime =
    previous.end - previous.start < options.minSubtitleDuration ||
    current.end - current.start < options.minSubtitleDuration;
  return (
    gap <= options.minGapBetweenSubtitles + 0.05 &&
    combinedDuration <= options.maxSubtitleDuration &&
    Array.from(combinedText).length <= maxCharacters &&
    (needsMoreTime ||
      Array.from(previous.text).length + Array.from(current.text).length <=
        maxCharacters)
  );
}

function mergeAdjacentEvents(
  events: ReadonlyArray<SubtitlePreviewEvent>,
  options: SubtitlePreviewEventOptions
): SubtitlePreviewEvent[] {
  const merged: SubtitlePreviewEvent[] = [];
  events.forEach((event) => {
    const previous = merged.at(-1);
    if (previous && canMergeEvents(previous, event, options)) {
      merged[merged.length - 1] = {
        ...previous,
        start: previous.start,
        end: event.end,
        text: normalizeText(`${previous.text} ${event.text}`)
      };
      return;
    }
    merged.push({ ...event });
  });
  return merged;
}

function applyMinimumDisplayDuration(
  events: ReadonlyArray<SubtitlePreviewEvent>,
  candidateDuration: number,
  options: SubtitlePreviewEventOptions
): SubtitlePreviewEvent[] {
  return events.map((event, index) => {
    const nextStart = events[index + 1]?.start;
    const maxAllowedEnd =
      nextStart === undefined
        ? candidateDuration
        : nextStart - options.minGapBetweenSubtitles;
    const maxEnd = Math.max(
      event.start,
      Math.min(candidateDuration, maxAllowedEnd)
    );
    const targetEnd = Math.max(
      event.end,
      event.start + options.minSubtitleDuration
    );
    let end = maxEnd > event.start ? Math.min(targetEnd, maxEnd) : event.end;
    if (end <= event.start) {
      end = event.end;
    }
    return { ...event, end: roundMilliseconds(end) };
  });
}

export function subtitlePreviewEvents(
  options: SubtitlePreviewEventOptions
): SubtitlePreviewEvent[] {
  const candidateDuration = Math.max(
    0,
    options.candidateEnd - options.candidateStart
  );
  const rawEvents: SubtitlePreviewEvent[] = [];
  options.segments.forEach((segment) => {
    const start = Math.max(segment.start, options.candidateStart);
    const end = Math.min(segment.end, options.candidateEnd);
    const text = normalizeText(segment.text);
    if (end <= start || !text) {
      return;
    }
    rawEvents.push(
      ...eventsForSegment(
        {
          start: roundMilliseconds(start - options.candidateStart),
          ...(segment.style ? { style: segment.style } : {}),
          end: roundMilliseconds(end - options.candidateStart),
          text
        },
        options
      )
    );
  });

  const firstMerge = mergeAdjacentEvents(rawEvents, options);
  const firstAdjustment = applyMinimumDisplayDuration(
    firstMerge,
    candidateDuration,
    options
  );
  const secondMerge = mergeAdjacentEvents(firstAdjustment, options);
  const bodyEvents = applyMinimumDisplayDuration(
    secondMerge,
    candidateDuration,
    options
  );

  if (options.hookSceneDuration <= 0 && options.suppressionEnd <= 0) {
    return bodyEvents;
  }
  const outputDuration = candidateDuration + options.hookSceneDuration;
  const suppressionEnd = roundMilliseconds(
    Math.min(outputDuration, options.suppressionEnd)
  );
  return bodyEvents.flatMap((event) => {
    const shiftedStart = roundMilliseconds(event.start + options.hookSceneDuration);
    const shiftedEnd = roundMilliseconds(event.end + options.hookSceneDuration);
    if (shiftedEnd <= suppressionEnd) {
      return [];
    }
    return [
      {
        start: roundMilliseconds(
          Math.max(shiftedStart, suppressionEnd)
        ),
        end: Math.min(shiftedEnd, outputDuration),
        ...(event.style ? { style: event.style } : {}),
        text: event.text
      }
    ];
  });
}
