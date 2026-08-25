type SubtitlePreviewSegment = {
  start: number;
  end: number;
  text: string;
};

export type SubtitlePreviewEvent = {
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

function normalizeText(text: string): string {
  return text.trim().split(/\s+/u).filter(Boolean).join(" ");
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
        text: event.text
      }
    ];
  });
}
