const YOUTUBE_ID_PATTERN = /[\[(]([A-Za-z0-9_-]{11})[\])](?!.*[\[(][A-Za-z0-9_-]{11}[\])])/;

export function parseYouTubeSourceFromFilename(
  filename: string
): { title: string; url: string } | null {
  const basename = filename.replace(/\.[^.]+$/, "").trim();
  const match = basename.match(YOUTUBE_ID_PATTERN);
  if (!match) {
    return null;
  }
  const title = basename
    .replace(match[0], "")
    .replace(/[\s._-]+$/, "")
    .trim();
  return {
    title,
    url: `https://www.youtube.com/watch?v=${match[1]}`
  };
}

export function hashtagsFromText(value: string): string[] {
  const seen = new Set<string>();
  return value
    .split(/[\s,、]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => (item.startsWith("#") ? item : `#${item}`))
    .filter((item) => {
      const key = item.toLocaleLowerCase();
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
}

export function tagsFromText(value: string): string[] {
  const seen = new Set<string>();
  return value
    .split(/[,、\n]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => {
      const key = item.toLocaleLowerCase();
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
}

export function descriptionWithHashtags(
  description: string,
  hashtags: string[]
): string {
  return [description.trim(), hashtags.map((item) => item.trim()).filter(Boolean).join(" ")]
    .filter(Boolean)
    .join("\n\n");
}

export function youtubeTagsText(tags: string[]): string {
  return tags.map((item) => item.trim()).filter(Boolean).join(",");
}
