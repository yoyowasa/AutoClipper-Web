export type TextPositionMode = "short" | "normal";

export type TextPositionPreset = {
  id: string;
  label: string;
  percent: number;
  purpose: string;
};

export const HORIZONTAL_POSITION_PRESETS: ReadonlyArray<TextPositionPreset> = [
  { id: "left", label: "左寄り", percent: 30, purpose: "左側の被写体を避ける" },
  { id: "left_center", label: "やや左", percent: 40, purpose: "中央から少し左" },
  { id: "center", label: "中央", percent: 50, purpose: "標準" },
  { id: "right_center", label: "やや右", percent: 60, purpose: "中央から少し右" },
  { id: "right", label: "右寄り", percent: 70, purpose: "右側へ寄せる" }
];

const SHORT_VERTICAL_POSITION_PRESETS: ReadonlyArray<TextPositionPreset> = [
  { id: "title_top", label: "タイトル上", percent: 12.5, purpose: "Y 240" },
  { id: "hook_top", label: "フック上", percent: 18.75, purpose: "Y 360" },
  { id: "upper", label: "上寄り", percent: 33.85, purpose: "Y 650" },
  { id: "center", label: "中央", percent: 50, purpose: "Y 960" },
  { id: "punchline", label: "ツッコミ位置", percent: 57.3, purpose: "Y 1100" },
  { id: "dialogue", label: "会話字幕", percent: 68.75, purpose: "Y 1320" },
  {
    id: "dialogue_low",
    label: "会話字幕・低め",
    percent: 75.5,
    purpose: "Y 1450"
  }
];

const NORMAL_VERTICAL_POSITION_PRESETS: ReadonlyArray<TextPositionPreset> = [
  { id: "title_top", label: "タイトル上", percent: 12.5, purpose: "Y 135" },
  { id: "hook_top", label: "上部", percent: 20, purpose: "Y 216" },
  { id: "upper", label: "上寄り", percent: 34, purpose: "Y 367" },
  { id: "center", label: "中央", percent: 50, purpose: "Y 540" },
  { id: "punchline", label: "中央下", percent: 60, purpose: "Y 648" },
  { id: "dialogue", label: "会話字幕", percent: 72, purpose: "Y 778" },
  {
    id: "dialogue_low",
    label: "会話字幕・低め",
    percent: 84,
    purpose: "Y 907"
  }
];

export function verticalPositionPresets(
  mode: TextPositionMode
): ReadonlyArray<TextPositionPreset> {
  return mode === "short"
    ? SHORT_VERTICAL_POSITION_PRESETS
    : NORMAL_VERTICAL_POSITION_PRESETS;
}

export function outputDimensions(mode: TextPositionMode): {
  width: number;
  height: number;
} {
  return mode === "short"
    ? { width: 1080, height: 1920 }
    : { width: 1920, height: 1080 };
}

export function positionPixels(
  mode: TextPositionMode,
  xPercent: number,
  yPercent: number
): { x: number; y: number } {
  const dimensions = outputDimensions(mode);
  return {
    x: Math.round((dimensions.width * xPercent) / 100),
    y: Math.round((dimensions.height * yPercent) / 100)
  };
}

export function matchingPositionPreset(
  presets: ReadonlyArray<TextPositionPreset>,
  percent: number
): TextPositionPreset | null {
  return (
    presets.find((preset) => Math.abs(preset.percent - percent) < 0.05) ?? null
  );
}

export function legacySubtitleYPercent({
  mode,
  alignment,
  lowerMargin,
  fontSize
}: {
  mode: TextPositionMode;
  alignment: number;
  lowerMargin: number;
  fontSize: number;
}): number {
  if (alignment === 5) {
    return 50;
  }
  const { height } = outputDimensions(mode);
  const twoLineCenterOffset = fontSize * 1.28;
  const y =
    alignment === 8
      ? lowerMargin + twoLineCenterOffset
      : height - lowerMargin - twoLineCenterOffset;
  return Math.max(5, Math.min(95, (y / height) * 100));
}
