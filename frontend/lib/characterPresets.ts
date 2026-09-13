import type { ClipSettings, NormalThumbnailStyle } from "./types";
import { applySubtitleStyle, captureSubtitleStyle, SUBTITLE_STYLE_KEYS, type SubtitleStyleSnapshot } from "./subtitleStylePresets";

export const PLAIN_THUMBNAIL: NormalThumbnailStyle = {
  design: "plain", backgroundColor: "#20242B", titleColor: "#FFFFFF", secondTitleColor: "#FFD84A", outlineColor: "#111111"
};
export const CHARACTER_KEYS = ["channelName", "youtubePostingProfile", "normalTitleSuffix", "normalThumbnailStyle",
  "shortTopBannerAssetId", "shortBottomBannerAssetId", "shortTopBannerEnabled", "shortBottomBannerEnabled",
  "shortBannerPresetName", "normalClipCount", "shortCount"] as const satisfies readonly (keyof ClipSettings)[];
export type CharacterSnapshot = Partial<Pick<ClipSettings, typeof CHARACTER_KEYS[number]>> & SubtitleStyleSnapshot;
export type CharacterPreset = { name: string; settings: CharacterSnapshot };
export type CharacterPresetDocument = { presets: CharacterPreset[]; selectedName: string; legacyImport?: boolean };

export function captureCharacter(settings: ClipSettings): CharacterSnapshot {
  const snapshot: CharacterSnapshot = {
    ...captureSubtitleStyle(settings), normalTitleSuffix: settings.normalTitleSuffix ?? "",
    normalThumbnailStyle: settings.normalThumbnailStyle ?? { ...PLAIN_THUMBNAIL }
  };
  for (const key of CHARACTER_KEYS) {
    if (settings[key] !== undefined && settings[key] !== null) Object.assign(snapshot, { [key]: settings[key] });
  }
  return structuredClone(snapshot);
}

export function newCharacter(settings: ClipSettings): ClipSettings {
  const cleared = applySubtitleStyle(settings, {});
  return { ...cleared, characterPresetName: "", channelName: "", normalTitleSuffix: "",
    normalThumbnailStyle: { ...PLAIN_THUMBNAIL }, normalClipCount: 0, shortCount: 3,
    normalClipTimeRanges: [], shortClipTimeRanges: [],
    youtubePostingProfile: { performerName: "", affiliation: "", baseHashtags: [], shortHashtags: ["#shortsfunny"], baseTags: [] },
    shortTopBannerEnabled: false, shortBottomBannerEnabled: false,
    shortTopBannerAssetId: "raden-top", shortBottomBannerAssetId: "raden-bottom", shortBannerPresetName: "" };
}

export function applyCharacter(settings: ClipSettings, preset: CharacterPreset): ClipSettings {
  const next = newCharacter(settings);
  const snapshot = structuredClone(preset.settings);
  for (const key of [...CHARACTER_KEYS, ...SUBTITLE_STYLE_KEYS]) {
    if (snapshot[key] !== undefined && snapshot[key] !== null) Object.assign(next, { [key]: snapshot[key] });
  }
  return { ...next, characterPresetName: preset.name };
}
