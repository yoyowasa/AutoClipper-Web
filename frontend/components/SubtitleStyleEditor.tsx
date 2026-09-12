"use client";

import { useState } from "react";
import type { ClipTextTarget } from "../lib/clipTextStyle";
import { bannerAssetUrl } from "../lib/shortBanners";
import { uploadDefaultTextStyle, uploadTextStyleKey, withUploadTextStyle } from "../lib/uploadTextStyles";
import type { ClipSettings, ExportType } from "../lib/types";
import { ClipTextStyleEditor } from "./ClipTextStyleEditor";
import { SubtitleStylePresetManager } from "./SubtitleStylePresetManager";

type SubtitleStyleEditorProps = {
  settings: ClipSettings;
  disabled?: boolean;
  onChange: (settings: ClipSettings) => void;
};

export function SubtitleStyleEditor({ settings, disabled = false, onChange }: SubtitleStyleEditorProps) {
  const [mode, setMode] = useState<ExportType>("short");
  const [target, setTarget] = useState<ClipTextTarget>("subtitle");
  const styles = {
    title: settings[uploadTextStyleKey(mode, "title")] ?? null,
    hook: settings[uploadTextStyleKey(mode, "hook")] ?? null,
    subtitle: settings[uploadTextStyleKey(mode, "subtitle")] ?? null
  };
  const defaults = {
    title: uploadDefaultTextStyle(settings, mode, "title"),
    hook: uploadDefaultTextStyle(settings, mode, "hook"),
    subtitle: uploadDefaultTextStyle(settings, mode, "subtitle")
  };
  return (
    <section className="border-t border-neutral-200 pt-5 md:col-span-2">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold text-neutral-950">字幕・フック・タイトルのスタイル</h2>
        <div aria-label="字幕スタイルの対象" className="inline-flex border border-neutral-300 bg-neutral-100 p-1" role="group">
          {([ ["short", "ショート 9:16"], ["normal", "通常 16:9"] ] as const).map(([value, label]) => (
            <button key={value} aria-pressed={mode === value} disabled={disabled} type="button"
              className={`min-h-9 px-3 text-sm font-medium ${mode === value ? "bg-neutral-950 text-white" : "text-neutral-600"}`}
              onClick={() => setMode(value)}>{label}</button>
          ))}
        </div>
      </div>
      <SubtitleStylePresetManager disabled={disabled} settings={settings} onChange={onChange} />
      <ClipTextStyleEditor
        clipType={mode} disabled={disabled} selectedTarget={target}
        scopeDescription={`${mode === "short" ? "ショート" : "通常切り抜き"}の初期書式。確認画面で個別に変更できます。`}
        styles={styles} resolvedStyles={defaults} defaultResolvedStyles={defaults}
        subtitleMaxCharsPerLine={mode === "short" ? settings.maxCharsPerLineShort : settings.maxCharsPerLineNormal}
        subtitleMaxLines={settings.maxLines}
        shortTitleOutputEnabled={settings.shortOverlayTitleMode !== "never"}
        shortTopBannerEnabled={settings.shortTopBannerEnabled}
        shortBottomBannerEnabled={settings.shortBottomBannerEnabled}
        shortTopBannerUrl={settings.shortTopBannerEnabled ? bannerAssetUrl(settings.shortTopBannerAssetId ?? "raden-top") : undefined}
        shortBottomBannerUrl={settings.shortBottomBannerEnabled ? bannerAssetUrl(settings.shortBottomBannerAssetId ?? "raden-bottom") : undefined}
        titleText="切り抜きのタイトル" hookText="このあと、まさかの展開！" subtitleText="この瞬間が一番おもしろい！"
        onSelectedTargetChange={setTarget}
        onChange={(nextTarget, style) => onChange(withUploadTextStyle(settings, mode, nextTarget, style))}
      />
    </section>
  );
}
