import type {
  ClipTextFontPreset,
  ClipTextStyle,
  ExportType
} from "./types";

export type ClipTextTarget = "title" | "hook" | "subtitle";

export type ClipTextFontOption = {
  value: ClipTextFontPreset;
  label: string;
  fontName: string;
  fontWeight: number;
};

export type ClipTextFontGroup = {
  label: string;
  options: ReadonlyArray<ClipTextFontOption>;
};

export const CLIP_TEXT_FONT_GROUPS: ReadonlyArray<ClipTextFontGroup> = [
  {
    label: "通常字幕向け",
    options: [
      {
        value: "noto_black",
        label: "Noto Sans JP Black",
        fontName: "Noto Sans JP Black",
        fontWeight: 900
      },
      {
        value: "sans_bold",
        label: "Noto Sans CJK JP Bold",
        fontName: "Noto Sans CJK JP",
        fontWeight: 800
      },
      {
        value: "heavy",
        label: "源ノ角ゴシック Heavy",
        fontName: "Source Han Sans JP Heavy",
        fontWeight: 900
      },
      {
        value: "mplus_extrabold",
        label: "M PLUS 1 ExtraBold",
        fontName: "M PLUS 1 ExtraBold",
        fontWeight: 800
      },
      {
        value: "mplus_rounded_extrabold",
        label: "M PLUS Rounded 1c ExtraBold",
        fontName: "Rounded Mplus 1c ExtraBold",
        fontWeight: 800
      }
    ]
  },
  {
    label: "特殊字幕向け（短い強調）",
    options: [
      {
        value: "chikara",
        label: "851チカラヅヨク",
        fontName: "851CHIKARA-DZUYOKU-KANA-A",
        fontWeight: 700
      },
      {
        value: "dela_gothic",
        label: "Dela Gothic One",
        fontName: "Dela Gothic One",
        fontWeight: 400
      },
      {
        value: "corporate_logo",
        label: "コーポレート・ロゴ Bold",
        fontName: "Corporate-Logo-Bold-ver3",
        fontWeight: 700
      }
    ]
  },
  {
    label: "補助書体",
    options: [
      {
        value: "sans",
        label: "Noto Sans CJK JP Regular",
        fontName: "Noto Sans CJK JP",
        fontWeight: 500
      },
      {
        value: "serif",
        label: "Noto Serif CJK JP",
        fontName: "Noto Serif CJK JP",
        fontWeight: 500
      },
      {
        value: "mono",
        label: "Noto Sans Mono CJK JP",
        fontName: "Noto Sans Mono CJK JP",
        fontWeight: 800
      }
    ]
  }
];

const CLIP_TEXT_FONT_OPTIONS = CLIP_TEXT_FONT_GROUPS.flatMap(
  (group) => group.options
);

const CLIP_TEXT_FONT_BY_PRESET = new Map(
  CLIP_TEXT_FONT_OPTIONS.map((option) => [option.value, option])
);

export const SUBTITLE_FONT_GROUPS = CLIP_TEXT_FONT_GROUPS.map((group) => ({
  label: group.label,
  options: group.options
    .filter((option) => option.value !== "sans")
    .map((option) => ({
      value: option.fontName,
      label: option.label
    }))
}));

const SHORT_DEFAULTS: Record<ClipTextTarget, ClipTextStyle> = {
  title: {
    fontPreset: "sans_bold",
    fontSize: 88,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 12.5
  },
  hook: {
    fontPreset: "sans_bold",
    fontSize: 88,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 18.75
  },
  subtitle: {
    fontPreset: "sans_bold",
    fontSize: 76,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 68.75
  }
};

const NORMAL_SUBTITLE_DEFAULT: ClipTextStyle = {
  fontPreset: "sans_bold",
  fontSize: 65,
  primaryColor: "#FFFFFF",
  outlineColor: "#000000",
  outlineWidth: 4,
  xPercent: 50,
  yPercent: 84
};

export function defaultClipTextStyle(
  target: ClipTextTarget,
  clipType: ExportType
): ClipTextStyle {
  const source =
    clipType === "normal" && target === "subtitle"
      ? NORMAL_SUBTITLE_DEFAULT
      : SHORT_DEFAULTS[target];
  return { ...source };
}

export function resolvedClipTextStyle(
  style: ClipTextStyle | null | undefined,
  target: ClipTextTarget,
  clipType: ExportType
): ClipTextStyle {
  return style ? { ...style } : defaultClipTextStyle(target, clipType);
}

export function clipTextFontFamily(fontPreset: ClipTextFontPreset): string {
  const option = CLIP_TEXT_FONT_BY_PRESET.get(fontPreset);
  return subtitleFontFamily(option?.fontName);
}

export function clipTextFontWeight(fontPreset: ClipTextFontPreset): number {
  return CLIP_TEXT_FONT_BY_PRESET.get(fontPreset)?.fontWeight ?? 800;
}

export function subtitleFontFamily(fontName: string | undefined): string {
  if (fontName === "Noto Serif CJK JP") {
    return '"Noto Serif CJK JP", "Yu Mincho", YuMincho, serif';
  }
  if (fontName === "Noto Sans Mono CJK JP") {
    return '"Noto Sans Mono CJK JP", "MS Gothic", monospace';
  }
  const bundledFont = CLIP_TEXT_FONT_OPTIONS.find(
    (option) => option.fontName === fontName
  );
  if (bundledFont) {
    return `"${bundledFont.fontName}", "Noto Sans CJK JP", "Yu Gothic", Meiryo, sans-serif`;
  }
  return '"Noto Sans CJK JP", "Yu Gothic", Meiryo, sans-serif';
}
