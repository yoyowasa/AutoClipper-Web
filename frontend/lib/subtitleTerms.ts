import { API_BASE_URL } from "./api";

export type SubtitleTerm = { src: string; dst: string; count: number; jobs: number; kept: number; reversed: number;
  active: boolean; disabled: boolean };
export type CharacterSubtitleTerms = { id: string; character: string; terms: SubtitleTerm[] };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/subtitle-terms${path}`, { ...init, cache: "no-store", credentials: "include" });
  if (response.status === 204) return undefined as T;
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "字幕の学習済みの語を処理できませんでした。");
  return data as T;
}
export const getSubtitleTerms = () => call<CharacterSubtitleTerms[]>("");
export const switchSubtitleTerm = (characterId: string, term: SubtitleTerm, disabled: boolean) => call<void>(
  `/${encodeURIComponent(characterId)}/${disabled ? "disable" : "enable"}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ src: term.src, dst: term.dst }),
  });
export function termStatus(term: SubtitleTerm): string {
  if (term.disabled) return "使わない設定";
  if (term.active) return "次の動画から自動で置換";
  if (term.reversed >= 2) return "元に戻されたため停止";
  if (term.kept > 0 && term.count / (term.count + term.kept) < 0.8) return "直さず残す例が多いため保留";
  return "学習中（3回、または1本で5回の修正で有効）";
}
