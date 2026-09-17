"use client";

import { CharacterPresetManager } from "./CharacterPresetManager";
import { CharacterThumbnailSettings } from "./CharacterThumbnailSettings";
import type { ClipSettings } from "../lib/types";
import { hashtagsFromText, tagsFromText } from "../lib/youtubePosting";

type Props = {
  disabled?: boolean;
  settings: ClipSettings;
  onChange: (settings: ClipSettings) => void;
};

const inputClassName =
  "mt-1 min-h-9 w-full border border-[#cfcfcb] bg-white px-2.5 py-2 text-xs text-[#252522] outline-none focus:border-sky-600 disabled:bg-[#eeeeeb]";

export function YouTubePostingSettingsPanel({
  disabled = false,
  settings,
  onChange
}: Props) {
  const profile = settings.youtubePostingProfile;
  const updateProfile = (updates: Partial<typeof profile>) => {
    onChange({
      ...settings,
      youtubePostingProfile: { ...profile, ...updates }
    });
  };

  return (
    <>
    <CharacterPresetManager settings={settings} disabled={disabled} onChange={onChange} />
    <details className="border-t border-[#d5d5d2] bg-white" open>
      <summary className="cursor-pointer px-3 py-3 text-xs font-bold text-[#282825]">
        YouTube投稿情報
        <span className="ml-2 text-[10px] font-normal text-[#73736e]">
          上のキャラ設定でまとめて保存
        </span>
      </summary>
      <div className="grid gap-3 border-t border-[#e2e2df] p-3">
        <label className="text-[11px] font-bold text-[#4b4b47]">投稿先チャンネル名（管理用）
          <input className={inputClassName} disabled={disabled} maxLength={120} value={settings.channelName ?? ""}
            onChange={(event) => onChange({ ...settings, channelName: event.target.value })} />
        </label>
        <label className="text-[11px] font-bold text-[#4b4b47]">
          ぶいすぽっ！許諾番号
          <input
            className={inputClassName}
            disabled={disabled}
            maxLength={80}
            placeholder="入力すると説明欄の元配信の上に表示"
            value={profile.vspoPermissionNumber ?? ""}
            onChange={(event) => updateProfile({ vspoPermissionNumber: event.target.value })}
          />
        </label>
        <label className="text-[11px] font-bold text-[#4b4b47]">
          元配信タイトル
          <input
            className={inputClassName}
            disabled={disabled}
            maxLength={300}
            placeholder="動画ファイル名から自動入力。必要なら修正"
            value={settings.youtubeSourceTitle}
            onChange={(event) =>
              onChange({ ...settings, youtubeSourceTitle: event.target.value })
            }
          />
        </label>
        <label className="text-[11px] font-bold text-[#4b4b47]">
          元配信URL
          <input
            className={inputClassName}
            disabled={disabled}
            inputMode="url"
            maxLength={500}
            placeholder="https://www.youtube.com/watch?v=..."
            value={settings.youtubeSourceUrl}
            onChange={(event) =>
              onChange({ ...settings, youtubeSourceUrl: event.target.value })
            }
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-[11px] font-bold text-[#4b4b47]">
            出演者
            <input
              className={inputClassName}
              disabled={disabled}
              maxLength={120}
              placeholder="出演者・キャラ名"
              value={profile.performerName}
              onChange={(event) => updateProfile({ performerName: event.target.value })}
            />
          </label>
          <label className="text-[11px] font-bold text-[#4b4b47]">
            所属
            <input
              className={inputClassName}
              disabled={disabled}
              maxLength={160}
              placeholder="グループ名・所属（任意）"
              value={profile.affiliation}
              onChange={(event) => updateProfile({ affiliation: event.target.value })}
            />
          </label>
        </div>
        <label className="text-[11px] font-bold text-[#4b4b47]">
          固定ハッシュタグ
          <input
            className={inputClassName}
            disabled={disabled}
            placeholder="#キャラ名 #切り抜き"
            value={profile.baseHashtags.join(" ")}
            onChange={(event) =>
              updateProfile({ baseHashtags: hashtagsFromText(event.target.value) })
            }
          />
        </label>
        <label className="text-[11px] font-bold text-[#4b4b47]">
          ショート用ハッシュタグ
          <input
            className={inputClassName}
            disabled={disabled}
            placeholder="#shortsfunny"
            value={profile.shortHashtags.join(" ")}
            onChange={(event) =>
              updateProfile({ shortHashtags: hashtagsFromText(event.target.value) })
            }
          />
        </label>
        <label className="text-[11px] font-bold text-[#4b4b47]">
          固定タグ
          <textarea
            className={`${inputClassName} min-h-20 resize-y`}
            disabled={disabled}
            placeholder="キャラ名,グループ名,切り抜き"
            value={profile.baseTags.join(",")}
            onChange={(event) => updateProfile({ baseTags: tagsFromText(event.target.value) })}
          />
        </label>
      </div>
    </details>
    <CharacterThumbnailSettings settings={settings} disabled={disabled} onChange={onChange} />
    </>
  );
}
