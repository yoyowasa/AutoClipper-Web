"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { toBrowserApiUrl } from "../lib/api";
import {
  adoptCandidate, candidateRequest, groupedCandidates, harvestCandidates, rejectCandidate,
  type CandidateList, type CharacterAssetCandidate, type HarvestVideo
} from "../lib/characterAssetCandidates";
import { CHARACTER_EMOTIONS, getCharacterAssets, type CharacterAssetList, type CharacterEmotion } from "../lib/characterAssets";

const LABELS = { joy: "喜", anger: "怒", sorrow: "哀", fun: "楽", neutral: "平静", unclassified: "判定なし" };
const ISSUE_LABELS: Record<string, string> = {
  blur: "ブレ", eyes_closed: "閉じた目", occluded: "隠れ", other_character: "別のキャラ", cut_off: "見切れ"
};

export function CandidateCard({ candidate, assets, disabled, onAdopt, onReject }: {
  candidate: CharacterAssetCandidate; assets: CharacterAssetList | null; disabled: boolean;
  onAdopt: (emotion: CharacterEmotion, slot?: number) => void; onReject: () => void;
}) {
  const initial = candidate.suggestedEmotion;
  const [emotion, setEmotion] = useState<CharacterEmotion | "">(initial && initial !== "neutral" ? initial : "");
  const [slot, setSlot] = useState("");
  const full = emotion !== "" && (assets?.emotions[emotion].length ?? 0) >= 5;
  return <article className="grid gap-2 rounded border border-neutral-300 bg-white p-2">
    <a href={toBrowserApiUrl(candidate.imageUrl)} target="_blank" rel="noopener noreferrer" aria-label="素材候補を拡大">
      <Image src={toBrowserApiUrl(candidate.imageUrl)} alt="動画から集めた素材候補" width={300} height={400}
        unoptimized className="h-52 w-full object-contain" />
    </a>
    <p>{candidate.sourceSecond}秒 / {candidate.score === null ? "判定なし" : `品質 ${Math.round(candidate.score * 100)}%`}</p>
    {candidate.usable === false && <p>Codex: 素材に不向き</p>}
    {candidate.sameCharacter === false && <p>Codex: 参照と別のキャラ</p>}
    {candidate.status === "rejected" && <p>不採用にした候補</p>}
    {[...candidate.issues.map(issue => ISSUE_LABELS[issue] ?? issue), ...candidate.warnings].map(text =>
      <p key={text} className="text-amber-800">{text}</p>)}
    <label>表情を変えて採用
      <select aria-label="採用する表情" value={emotion} disabled={disabled} className="ml-1 border p-1"
        onChange={event => { setEmotion(event.target.value as CharacterEmotion | ""); setSlot(""); }}>
        <option value="">表情を選択</option>
        {CHARACTER_EMOTIONS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select>
    </label>
    {full && <label>5枚保存済み：入れ替える枠
      <select aria-label="入れ替える素材枠" value={slot} disabled={disabled} onChange={event => setSlot(event.target.value)}>
        <option value="">枠を選択</option>
        {assets?.emotions[emotion as CharacterEmotion].map(item => <option key={item.id} value={item.slot}>{item.slot}番</option>)}
      </select>
    </label>}
    <div className="flex gap-2">
      <button type="button" className="bg-sky-800 px-3 py-2 text-white disabled:opacity-40"
        disabled={disabled || !assets || !emotion || (full && !slot)} onClick={() => {
          if (!emotion) return;
          if (full && !window.confirm(`${LABELS[emotion]}の${slot}番の素材を入れ替えます。よろしいですか？`)) return;
          onAdopt(emotion, full ? Number(slot) : undefined);
        }}>採用</button>
      <button type="button" className="border px-3 py-2" disabled={disabled || candidate.status === "rejected"}
        onClick={onReject}>不採用</button>
    </div>
  </article>;
}

export function CharacterAssetCandidatesPanel({ presetId, disabled, revision = 0, onAssetsChange, onBusyChange }: {
  presetId: string; disabled?: boolean; revision?: number; onAssetsChange: () => void; onBusyChange: (busy: boolean) => void;
}) {
  const [data, setData] = useState<CandidateList>({ candidates: [], harvests: [] });
  const [videos, setVideos] = useState<HarvestVideo[]>([]);
  const [videoId, setVideoId] = useState("");
  const [assets, setAssets] = useState<CharacterAssetList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const [result, sources, registered] = await Promise.all([
          candidateRequest<CandidateList>(presetId, "/asset-candidates"),
          candidateRequest<HarvestVideo[]>(presetId, "/harvest-videos"), getCharacterAssets(presetId)
        ]);
        if (cancelled) return;
        setData(result); setVideos(sources); setAssets(registered); setError("");
        if (result.harvests.some(item => item.state === "running" || item.state === "queued")) timer = setTimeout(load, 3000);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "素材候補を読み込めません。");
      }
    }
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [presetId, reload, revision]);

  async function act(operation: () => Promise<unknown>, adopted = false) {
    setBusy(true); onBusyChange(true); setError("");
    try { await operation(); setReload(value => value + 1); if (adopted) onAssetsChange(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "素材候補の操作に失敗しました。"); }
    finally { setBusy(false); onBusyChange(false); }
  }
  function renderGroups(needsReview: boolean) {
    return groupedCandidates(data.candidates, needsReview).filter(group => group.candidates.length > 0).map(group =>
      <section key={group.emotion} className="grid gap-2">
        <h4 className="font-semibold">{LABELS[group.emotion]}（{group.candidates.length}枚）</h4>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {group.candidates.map(candidate => <CandidateCard key={candidate.id} candidate={candidate} assets={assets}
            disabled={!!disabled || busy} onAdopt={(emotion, slot) => void act(() => adoptCandidate(presetId, candidate.id, emotion, slot), true)}
            onReject={() => void act(() => rejectCandidate(presetId, candidate.id))} />)}
        </div>
      </section>);
  }
  const activeForVideo = data.harvests.some(item => item.videoId === videoId && (item.state === "queued" || item.state === "running"));
  return <section aria-label="素材候補" className="grid gap-3 border-t border-sky-200 pt-3">
    <h3 className="text-sm font-semibold">動画から集めた素材候補</h3>
    <p>元動画全体を走査し、胸から上が映るコマを最大48枚集めます。採用したものだけ表情素材に保存します。</p>
    <label>処理済みの元動画
      <select aria-label="素材を集める元動画" value={videoId} className="block max-w-full border p-2"
        disabled={disabled || busy} onChange={event => setVideoId(event.target.value)}>
        <option value="">動画を選択</option>
        {videos.map(video => <option key={video.id} value={video.id}>{video.filename} ({video.id.slice(-6)})</option>)}
      </select>
    </label>
    {videos.length === 0 && <p>保存されている処理済みの元動画がありません。</p>}
    <button type="button" className="w-fit bg-sky-800 px-3 py-2 text-white disabled:opacity-40"
      disabled={disabled || busy || !videoId || activeForVideo}
      onClick={() => void act(() => harvestCandidates(presetId, videoId))}>動画から素材を集める</button>
    <button type="button" className="w-fit underline" disabled={busy} onClick={() => setReload(value => value + 1)}>一覧を再読込</button>
    {data.harvests.map(item => <p key={item.id} role="status">{videos.find(video => video.id === item.videoId)?.filename ?? item.videoId}：
      {item.state === "running" ? "走査・判定中 / " : item.state === "queued" ? "待機中 / " : ""}{item.message}</p>)}
    {renderGroups(false)}
    <details><summary>素材に不向き・別キャラ・不採用の候補</summary><div className="grid gap-3 pt-2">{renderGroups(true)}</div></details>
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </section>;
}
