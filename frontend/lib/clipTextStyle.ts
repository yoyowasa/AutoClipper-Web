import type {
  ClipTextFontPreset,
  ClipTextStyle,
  ExportType,
  ResolvedClipTextStyle
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
    label: "追加書体（通常・ショート共通）",
    options: [
      { value: "chikara_yowaku", label: "851チカラヨワク", fontName: "851CHIKARA-YOWAKU", fontWeight: 400 },
      { value: "keifont", label: "けいふぉんと！", fontName: "Keifont", fontWeight: 400 },
      { value: "mushin", label: "無心（むしん）", fontName: "Mushin", fontWeight: 400 },
      { value: "ankoku_zonji", label: "暗黒ゾン字", fontName: "AnkokuZombic", fontWeight: 400 },
      { value: "killgo_nb", label: "キルゴUかなNB（ローカル導入）", fontName: "GN-KMBFont-UB-NewstyleKanaB", fontWeight: 400 },
      { value: "tanuki_magic", label: "たぬき油性マジック", fontName: "Tanuki Permanent Marker", fontWeight: 400 }
    ]
  },
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

export type AssPreviewFontMetrics = {
  fontSizeScale: number;
  lineHeight: number;
};

const DEFAULT_ASS_PREVIEW_FONT_METRICS: AssPreviewFontMetrics = {
  fontSizeScale: 1000 / 1448,
  lineHeight: 1448 / 1000
};

// libass normalizes ASS Fontsize against the font's Windows ascent/descent,
// while CSS font-size uses the em square. Keep these metrics paired so the
// live browser overlay has the same glyph size and line pitch as FFmpeg.
const ASS_PREVIEW_FONT_METRICS = new Map<string, AssPreviewFontMetrics>([
  ["851CHIKARA-YOWAKU", { fontSizeScale: 1, lineHeight: 1 }],
  ["Keifont", { fontSizeScale: 1024 / 1134, lineHeight: 1134 / 1024 }],
  ["Mushin", { fontSizeScale: 1, lineHeight: 1 }],
  ["AnkokuZombic", { fontSizeScale: 1, lineHeight: 1 }],
  ["GN-KMBFont-UB-NewstyleKanaB", { fontSizeScale: 1024 / 1230, lineHeight: 1230 / 1024 }],
  ["Tanuki Permanent Marker", { fontSizeScale: 1, lineHeight: 1 }],
  ["Noto Sans CJK JP", DEFAULT_ASS_PREVIEW_FONT_METRICS],
  ["Noto Sans Mono CJK JP", DEFAULT_ASS_PREVIEW_FONT_METRICS],
  ["Noto Sans JP Black", DEFAULT_ASS_PREVIEW_FONT_METRICS],
  ["Source Han Sans JP Heavy", DEFAULT_ASS_PREVIEW_FONT_METRICS],
  ["M PLUS 1 ExtraBold", DEFAULT_ASS_PREVIEW_FONT_METRICS],
  ["Dela Gothic One", DEFAULT_ASS_PREVIEW_FONT_METRICS],
  [
    "Noto Serif CJK JP",
    { fontSizeScale: 1000 / 1437, lineHeight: 1437 / 1000 }
  ],
  [
    "Rounded Mplus 1c ExtraBold",
    { fontSizeScale: 1000 / 1395, lineHeight: 1395 / 1000 }
  ],
  [
    "Corporate-Logo-Bold-ver3",
    { fontSizeScale: 1000 / 1400, lineHeight: 1400 / 1000 }
  ],
  [
    "851CHIKARA-DZUYOKU-KANA-A",
    { fontSizeScale: 1, lineHeight: 1 }
  ]
]);

export function assPreviewFontMetrics(
  fontName: string | undefined
): AssPreviewFontMetrics {
  const metrics = ASS_PREVIEW_FONT_METRICS.get(fontName?.trim() ?? "");
  return metrics ?? DEFAULT_ASS_PREVIEW_FONT_METRICS;
}

const SHORT_DEFAULTS: Record<ClipTextTarget, ClipTextStyle> = {
  title: {
    fontPreset: "sans_bold",
    fontName: null,
    bold: null,
    fontSize: 88,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 12.5,
    positionMode: "explicit"
  },
  hook: {
    fontPreset: "sans_bold",
    fontName: null,
    bold: null,
    fontSize: 88,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 18.75,
    positionMode: "explicit"
  },
  subtitle: {
    fontPreset: "sans_bold",
    fontName: null,
    bold: null,
    fontSize: 76,
    primaryColor: "#FFFFFF",
    outlineColor: "#000000",
    outlineWidth: 5,
    xPercent: 50,
    yPercent: 68.75,
    positionMode: "explicit"
  }
};

const NORMAL_SUBTITLE_DEFAULT: ClipTextStyle = {
  fontPreset: "sans_bold",
  fontName: null,
  bold: null,
  fontSize: 65,
  primaryColor: "#FFFFFF",
  outlineColor: "#000000",
  outlineWidth: 4,
  xPercent: 50,
  yPercent: 84,
  positionMode: "explicit"
};

const NORMAL_TITLE_DEFAULT: ClipTextStyle = {
  fontPreset: "sans_bold",
  fontName: null,
  bold: null,
  fontSize: 76,
  primaryColor: "#FFFFFF",
  outlineColor: "#000000",
  outlineWidth: 4,
  xPercent: 50,
  yPercent: 8,
  positionMode: "explicit"
};

const NORMAL_HOOK_DEFAULT: ClipTextStyle = {
  fontPreset: "sans_bold",
  fontName: null,
  bold: null,
  fontSize: 76,
  primaryColor: "#FFFFFF",
  outlineColor: "#000000",
  outlineWidth: 4,
  xPercent: 50,
  yPercent: 8,
  positionMode: "explicit"
};

export function defaultClipTextStyle(
  target: ClipTextTarget,
  clipType: ExportType
): ClipTextStyle {
  const source =
    clipType === "normal" && target === "subtitle"
      ? NORMAL_SUBTITLE_DEFAULT
      : clipType === "normal" && target === "title"
        ? NORMAL_TITLE_DEFAULT
      : clipType === "normal" && target === "hook"
        ? NORMAL_HOOK_DEFAULT
      : SHORT_DEFAULTS[target];
  return { ...source };
}

export function resolvedClipTextStyle(
  style: ClipTextStyle | null | undefined,
  effectiveStyle: ResolvedClipTextStyle | null | undefined,
  target: ClipTextTarget,
  clipType: ExportType
): ResolvedClipTextStyle {
  const defaultStyle = defaultClipTextStyle(target, clipType);
  const defaultPreset = defaultStyle.fontPreset ?? "sans_bold";
  const fallback: ResolvedClipTextStyle = effectiveStyle
    ? { ...effectiveStyle }
    : {
        ...defaultStyle,
        fontPreset: defaultPreset,
        fontName: clipTextFontName(defaultPreset),
        bold: clipTextFontWeight(defaultPreset) >= 700,
        shadow: 2,
        alignment: 5,
        marginX: 0,
        marginV: 0,
        positionOverride: true
      };
  if (!style) {
    return fallback;
  }

  const preset = style.fontPreset;
  const explicitPosition = style.positionMode === "explicit";
  return {
    ...fallback,
    fontPreset: preset,
    fontName:
      style.fontName?.trim() ||
      (preset ? clipTextFontName(preset) : fallback.fontName),
    bold:
      style.bold ??
      (preset ? clipTextFontWeight(preset) >= 700 : fallback.bold),
    fontSize: style.fontSize,
    primaryColor: style.primaryColor,
    outlineColor: style.outlineColor,
    outlineWidth: style.outlineWidth,
    outerOutlineWidth: style.outerOutlineWidth ?? 0,
    outerOutlineColor: style.outerOutlineColor ?? "#FFFFFF",
    xPercent: explicitPosition ? style.xPercent : fallback.xPercent,
    yPercent: explicitPosition ? style.yPercent : fallback.yPercent,
    alignment: explicitPosition ? 5 : fallback.alignment,
    marginX: explicitPosition ? 0 : fallback.marginX,
    marginV: explicitPosition ? 0 : fallback.marginV,
    positionMode: style.positionMode,
    positionOverride: explicitPosition ? true : fallback.positionOverride
  };
}

export function clipTextFontName(fontPreset: ClipTextFontPreset): string {
  return CLIP_TEXT_FONT_BY_PRESET.get(fontPreset)?.fontName ?? "Noto Sans CJK JP";
}

export function clipTextFontFamily(fontPreset: ClipTextFontPreset): string {
  const option = CLIP_TEXT_FONT_BY_PRESET.get(fontPreset);
  return subtitleFontFamily(option?.fontName);
}

export function clipTextFontWeight(fontPreset: ClipTextFontPreset): number {
  return CLIP_TEXT_FONT_BY_PRESET.get(fontPreset)?.fontWeight ?? 800;
}

export function subtitleFontFamily(fontName: string | undefined): string {
  const normalizedFontName = fontName?.trim();
  if (normalizedFontName === "Noto Serif CJK JP") {
    return '"Noto Serif CJK JP", "Yu Mincho", YuMincho, serif';
  }
  if (normalizedFontName === "Noto Sans Mono CJK JP") {
    return '"Noto Sans Mono CJK JP", "MS Gothic", monospace';
  }
  const bundledFont = CLIP_TEXT_FONT_OPTIONS.find(
    (option) => option.fontName === normalizedFontName
  );
  if (bundledFont) {
    return `"${bundledFont.fontName}", "Noto Sans CJK JP", "Yu Gothic", Meiryo, sans-serif`;
  }
  if (normalizedFontName) {
    const escapedFontName = normalizedFontName
      .replaceAll("\\", "\\\\")
      .replaceAll('"', '\\"');
    return `"${escapedFontName}", "Noto Sans CJK JP", "Yu Gothic", Meiryo, sans-serif`;
  }
  return '"Noto Sans CJK JP", "Yu Gothic", Meiryo, sans-serif';
}
