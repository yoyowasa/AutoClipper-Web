import { CLIP_TEXT_FONT_GROUPS } from "./clipTextStyle";
import type { NormalThumbnailStyle, ThumbnailFontPreset, ThumbnailTextStyles } from "./types";

const PRESETS: ThumbnailFontPreset[] = ["noto_black", "heavy", "mplus_extrabold", "mplus_rounded_extrabold",
  "chikara", "chikara_yowaku", "keifont", "mushin", "ankoku_zonji", "tanuki_magic",
  "genei_kiwami_go", "genei_mono_go", "genei_antique", "dela_gothic", "corporate_logo"];
export const THUMBNAIL_FONTS = PRESETS.map(preset => CLIP_TEXT_FONT_GROUPS.flatMap(group => group.options)
  .find(option => option.value === preset)!);

export function thumbnailTextDefaults(style?: NormalThumbnailStyle | null): ThumbnailTextStyles {
  return structuredClone(style?.textStyles ?? {
    heading: { fontPreset: "noto_black", fontSize: 46, color: "#E0C57B" },
    upper: { fontPreset: "noto_black", fontSize: 155, color: style?.titleColor ?? "#FFFFFF" },
    lower: { fontPreset: "noto_black", fontSize: 112, color: style?.secondTitleColor ?? "#FFD84A" }
  });
}
