export type BoundaryTimeParts = {
  hours: string;
  minutes: string;
  seconds: string;
};

export function splitBoundaryTime(value: number): BoundaryTimeParts {
  const safe = Math.max(0, value);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = Math.round((safe % 60) * 1000) / 1000;
  return {
    hours: String(hours),
    minutes: String(minutes),
    seconds: String(seconds)
  };
}

export function combineBoundaryTime(parts: BoundaryTimeParts): number | null {
  if (
    parts.hours.trim() === "" ||
    parts.minutes.trim() === "" ||
    parts.seconds.trim() === ""
  ) {
    return null;
  }
  const hours = Number(parts.hours);
  const minutes = Number(parts.minutes);
  const seconds = Number(parts.seconds);
  if (
    !Number.isInteger(hours) ||
    !Number.isInteger(minutes) ||
    !Number.isFinite(seconds) ||
    hours < 0 ||
    minutes < 0 ||
    minutes >= 60 ||
    seconds < 0 ||
    seconds >= 60
  ) {
    return null;
  }
  return Math.round((hours * 3600 + minutes * 60 + seconds) * 1000) / 1000;
}

export function clampStartBoundary(value: number, end: number | null): number {
  const upperBound = end === null ? Number.POSITIVE_INFINITY : Math.max(0, end - 1);
  return Math.round(Math.min(Math.max(0, value), upperBound) * 1000) / 1000;
}

export function clampEndBoundary(
  value: number,
  start: number | null,
  sourceDuration: number | null
): number {
  const lowerBound = start === null ? 1 : start + 1;
  const upperBound = sourceDuration ?? Number.POSITIVE_INFINITY;
  return (
    Math.round(Math.min(Math.max(lowerBound, value), upperBound) * 1000) / 1000
  );
}
