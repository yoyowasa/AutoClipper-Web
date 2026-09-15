export const EMPTY_HEATMAP_MESSAGE = "JSONは読み込めましたが、人気度データが入っていません。『人気度JSONを参考にする』をOFFにすると字幕・会話内容で選定できます。";

// This is an early content check; the server still validates the complete
// contract and the video's filename, size and SHA-256.
export function heatmapContentIssue(text: string): string | null {
  let data;
  try { data = JSON.parse(text.replace(/^\uFEFF/, "")); }
  catch { return "JSONの形式を読み取れません。Downloaderが出力したJSONを選び直してください。"; }
  if (!data || typeof data !== "object" || !Array.isArray(data.heatmap) || typeof data.heatmap_available !== "boolean") {
    return "人気度JSONの形式ではありません。Downloaderが出力した .heatmap.json を選択してください。";
  }
  if (!data.heatmap_available || !data.heatmap.some((segment: { value?: unknown } | null) =>
    segment && typeof segment.value === "number" && Number.isFinite(segment.value) && segment.value > 0)) {
    return EMPTY_HEATMAP_MESSAGE;
  }
  return null;
}

export async function readHeatmapContentIssue(file: File): Promise<string | null> {
  try { return heatmapContentIssue(await file.text()); }
  catch { return "JSONファイルを読み込めません。ファイルを選び直してください。"; }
}
