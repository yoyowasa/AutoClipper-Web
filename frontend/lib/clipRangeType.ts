import { effectiveShortMax, validateClipDuration } from "./durationRules";
import type { ExportType } from "./types";

export function clipRangeType(preferred: ExportType, duration: number, shortMax: number, allowChange = true): {
  type: ExportType; error: string | null;
} {
  const maximum = effectiveShortMax(shortMax);
  const error = validateClipDuration(preferred, duration, maximum);
  if (!error || !allowChange) return { type: preferred, error };
  const other = preferred === "short" ? "normal" : "short";
  const otherError = validateClipDuration(other, duration, maximum);
  if (!otherError) return { type: other, error: null };
  return { type: preferred, error: `どちらの種類でも保存できません。${error} ${otherError}` };
}
