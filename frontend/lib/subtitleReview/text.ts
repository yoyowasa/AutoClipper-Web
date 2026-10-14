export function normalizeReviewTitle(value: string): string {
  return limitToTwoTextLines(value)
    .split("\n")
    .map((line) => line.trim().split(/\s+/u).filter(Boolean).join(" "))
    .filter(Boolean)
    .join("\n");
}

export function limitToTwoTextLines(value: string): string {
  const [firstLine = "", ...remainingLines] = value
    .replace(/\r\n|\r|\u2028|\u2029|\\N/gu, "\n")
    .split("\n");
  if (remainingLines.length === 0) {
    return firstLine;
  }
  return `${firstLine}\n${remainingLines.join(" ")}`;
}
