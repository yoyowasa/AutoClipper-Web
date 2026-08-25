import type { ClipSettings } from "../lib/types";

type UploadActionBarProps = {
  actionLabel: string;
  disabled: boolean;
  file: File | null;
  isSubmitting: boolean;
  mode: "new" | "manual" | "reedit";
  settings: ClipSettings;
};

function formatFileSize(size: number): string {
  const gibibyte = 1024 ** 3;
  const mebibyte = 1024 ** 2;
  if (size >= gibibyte) {
    return `${(size / gibibyte).toFixed(2)} GiB`;
  }
  return `${(size / mebibyte).toFixed(1)} MiB`;
}

function outputSummary(settings: ClipSettings): string {
  const outputs = [
    settings.normalClipCount > 0 ? `通常 ${settings.normalClipCount}本` : null,
    settings.shortCount > 0 ? `ショート ${settings.shortCount}本` : null
  ].filter((value): value is string => value !== null);
  return outputs.join(" / ");
}

function manualSubtitleSummary(settings: ClipSettings): string {
  if (settings.manualSubtitleMode === "none") {
    return "字幕なし";
  }
  if (settings.manualSubtitleMode === "manual") {
    return "字幕を手入力";
  }
  return "自動字幕";
}

export function UploadActionBar({
  actionLabel,
  disabled,
  file,
  isSubmitting,
  mode,
  settings
}: UploadActionBarProps) {
  return (
    <div
      className="hidden border-t border-[#cfcfcb] bg-white p-3 xl:flex xl:shrink-0 xl:items-center xl:justify-between xl:gap-4"
      data-testid="top-action-bar"
    >
      <div className="min-w-0">
        <p className={`truncate text-xs font-bold ${file ? "text-[#20201e]" : "text-[#777772]"}`}>
          {file ? file.name : "動画が選択されていません"}
        </p>
        <p className="mt-1 text-[11px] text-[#6d6d68]">
          {file
            ? isSubmitting
              ? "処理を準備しています。この画面を閉じずにお待ちください。"
              : mode === "reedit"
                ? `完成MP4を照合して元の編集データを開きます・${formatFileSize(file.size)}`
                : mode === "manual"
                  ? `元動画から手動で範囲を作成・${manualSubtitleSummary(settings)}・${formatFileSize(file.size)}`
                : `${outputSummary(settings)}・${formatFileSize(file.size)}`
            : "左の入力欄で動画を選ぶと処理を開始できます。"}
        </p>
      </div>
      <button
        className="mt-3 min-h-11 w-full bg-sky-700 px-5 text-sm font-bold text-white hover:bg-sky-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:cursor-not-allowed disabled:bg-[#d2d2cf] disabled:text-white xl:mt-0 xl:w-auto xl:min-w-72"
        data-testid="top-primary-action"
        disabled={disabled}
        type="submit"
      >
        {actionLabel}
      </button>
    </div>
  );
}
