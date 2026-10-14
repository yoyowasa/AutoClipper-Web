export function normalizeYoutubeHashtags(values: string[]): string[] {
  return Array.from(
    new Set(
      values
        .flatMap((value) => value.split(/[\s,、]+/u))
        .map((value) => value.trim())
        .filter(Boolean)
        .map((value) => (value.startsWith("#") ? value : `#${value}`))
    )
  ).slice(0, 12);
}

export function hashtagsFromText(value: string): string[] {
  return normalizeYoutubeHashtags([value]);
}

export function postCopyText(title: string, description: string, hashtags: string[]): string {
  return [title.trim(), description.trim(), normalizeYoutubeHashtags(hashtags).join(" ")]
    .filter(Boolean)
    .join("\n\n");
}

export function postMetadataSourceForProvider(provider: string | null | undefined): string | null {
  if (provider === "codex") {
    return "codex";
  }
  if (provider) {
    return "manual";
  }
  return null;
}
