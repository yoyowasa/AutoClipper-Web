"use client";

import { useEffect, useRef, useState } from "react";
import { thumbnailCopyRequest } from "../lib/api";
import type { NormalThumbnailStyle, ResultExportItem, ThumbnailCopyText, ThumbnailCopyState, ThumbnailSubjectPlacement, ThumbnailTextRegions, ThumbnailTextStyles } from "../lib/types";
import { ThumbnailTextStyleEditor } from "./ThumbnailTextStyleEditor";
import type { ThumbnailDraft } from "./LiveThumbnailPreview";
import type { ThumbnailSubjectSelection } from "../lib/types";
import { ThumbnailAssetPicker } from "./ThumbnailAssetPicker";

export function ResultThumbnailEditor({ item, busy, onRender, onDraftChange, styles, setStyles, regions }: {
  item: ResultExportItem; busy?: boolean;
  onRender: (crop: "standard" | "close", styles: ThumbnailTextStyles, text: ThumbnailCopyText, advance: boolean, design: NormalThumbnailStyle["design"], selectWithCodex: boolean, placement: ThumbnailSubjectPlacement, selection?: ThumbnailSubjectSelection) => void;
  onDraftChange: (draft: ThumbnailDraft) => void;
  styles: ThumbnailTextStyles;
  setStyles: React.Dispatch<React.SetStateAction<ThumbnailTextStyles>>;
  regions: ThumbnailTextRegions | null;
}) {
  const [text, setText] = useState<ThumbnailCopyText>(() => ({ heading: item.thumbnailKicker ?? "", upper: item.thumbnailLine1 ?? "", lower: item.thumbnailLine2 ?? "" }));
  const [design, setDesign] = useState<NormalThumbnailStyle["design"]>(() => item.thumbnailDesign ?? "raden");
  const [subject, setSubject] = useState<ThumbnailSubjectSelection>(() => ({
    subjectSource: item.thumbnailSubjectSource ?? "video", characterAssetId: item.thumbnailCharacterAssetId ?? undefined,
    emotion: item.thumbnailEmotion ?? undefined,
  }));
  const subjectRevision = useRef(item.thumbnailRenderRevision);
  useEffect(() => {
    if (subjectRevision.current === item.thumbnailRenderRevision) return;
    subjectRevision.current = item.thumbnailRenderRevision;
    setSubject({ subjectSource: item.thumbnailSubjectSource ?? "video", characterAssetId: item.thumbnailCharacterAssetId ?? undefined,
      emotion: item.thumbnailEmotion ?? undefined });
  }, [item.thumbnailRenderRevision, item.thumbnailSubjectSource, item.thumbnailCharacterAssetId, item.thumbnailEmotion]);
  const [placement, setPlacement] = useState<ThumbnailSubjectPlacement>(
    () => item.thumbnailSubjectPlacement ?? { scale: 1, offsetX: 0, offsetY: 0 }
  );
  const [copy, setCopy] = useState<ThumbnailCopyState>({ state: "idle", suggestions: [] });
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const applyRequest = useRef<string | null>(null);
  const generating = copy.state === "queued" || copy.state === "generating";
  const locked = busy || item.thumbnailStatus === "generating" || generating || requesting;
  const endpoint = item.id;

  useEffect(() => { onDraftChange({ text, styles, design, subjectPlacement: placement, ...subject }); }, [text, styles, design, placement, subject, onDraftChange]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const next = await thumbnailCopyRequest(endpoint);
        if (cancelled) return;
        setCopy(next);
        if (next.state === "queued" || next.state === "generating") {
          applyRequest.current = next.requestId ?? null;
          timer = setTimeout(() => void load(), 1500);
        }
        if (next.state === "ready" && applyRequest.current === next.requestId) {
          const recommended = next.suggestions.find(s => s.id === next.recommendedId) ?? next.suggestions[0];
          if (recommended) { setText({ heading: recommended.heading, upper: recommended.upper, lower: recommended.lower }); setSelected(recommended.id); }
          applyRequest.current = null;
        }
      } catch { if (!cancelled) setError("文言候補を読み込めませんでした。再生成で再試行できます。"); }
    };
    void load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [endpoint, copy.requestId]);

  async function generate() {
    setRequesting(true); setError("");
    try {
      const next = await thumbnailCopyRequest(endpoint, true);
      applyRequest.current = next.requestId ?? null;
      setCopy(next);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "文言を生成できませんでした。"); }
    finally { setRequesting(false); }
  }

  return <section className="flex min-h-0 min-w-0 flex-col overflow-hidden border border-amber-300 bg-amber-50 p-3">
    <h3 className="text-sm font-semibold">サムネイルの調整</h3>
    <p className="mt-1 text-xs text-neutral-600">確定したこの動画の字幕から文言を生成します。動画内タイトル・フックが空欄でも使えます。</p>
    <div className="mt-3 grid min-h-0 min-w-0 flex-1 grid-cols-1 gap-3 overflow-y-auto overscroll-contain xl:grid-cols-2 xl:overflow-hidden">
    <div aria-label="サムネの文言編集" tabIndex={0} className="min-h-0 min-w-0 xl:overflow-y-auto xl:overscroll-contain">
    <button type="button" disabled={locked} onClick={() => void generate()}
      className="min-h-10 w-full border border-violet-700 bg-white px-3 text-sm font-semibold text-violet-900 disabled:text-neutral-400">
      {generating || requesting ? "文言３案を生成中…" : copy.suggestions.length ? "文言を３案作り直す" : "文言３案を生成"}
    </button>
    {(error || copy.error) && <p role="alert" className="mt-2 text-xs text-red-700">{error || copy.error}</p>}
    {copy.state === "ready" && <details open className="mt-3 min-w-0 border border-amber-300 bg-white">
      <summary className="cursor-pointer px-3 py-2 text-xs font-semibold">文言の候補（{copy.suggestions.length}案）</summary>
      <div aria-label="サムネ文言の候補一覧" tabIndex={0} className="grid max-h-64 gap-2 overflow-y-auto overscroll-contain border-t border-amber-200 p-2">
      {copy.suggestions.map((suggestion, index) => <div key={suggestion.id} className={`border bg-white p-2 text-xs ${selected === suggestion.id ? "border-sky-600 ring-1 ring-sky-600" : "border-neutral-300"}`}>
        <div className="flex items-center justify-between gap-2"><strong>案{index + 1}{copy.recommendedId === suggestion.id ? "・おすすめ" : ""}</strong>
          <button type="button" disabled={locked} className="min-h-8 border border-sky-700 px-3 text-sky-800 disabled:text-neutral-400"
            onClick={() => { setText({ heading: suggestion.heading, upper: suggestion.upper, lower: suggestion.lower }); setSelected(suggestion.id); }}>この案を使う</button></div>
        <dl className="mt-2 grid grid-cols-[3em_1fr] gap-x-2 gap-y-1">
          <dt className="text-neutral-500">見出し</dt><dd>{suggestion.heading || "非表示"}</dd>
          <dt className="text-neutral-500">上行</dt><dd className="font-bold">{suggestion.upper}</dd>
          <dt className="text-neutral-500">下行</dt><dd className="font-bold">{suggestion.lower || "非表示"}</dd>
        </dl>
        <details className="mt-2 text-neutral-600"><summary className="cursor-pointer">理由・根拠の字幕</summary>
          <p className="mt-1">{suggestion.reason}</p>{suggestion.evidence.map((evidence, i) => <p key={i} className="mt-1">「{evidence.quote}」</p>)}
        </details>
      </div>)}
      </div>
    </details>}
    <fieldset disabled={locked} className="mt-3 grid gap-2 border border-amber-300 bg-white p-3">
      <legend className="px-1 text-xs font-bold">使う文言（必要なら手直し）</legend>
      {([["heading", "見出し", 40], ["upper", "上行", 60], ["lower", "下行", 60]] as const).map(([role, label, max]) =>
        <label key={role} className="grid gap-1 text-xs">{label}
          <input aria-label={`サムネ文言 ${label}`} className="min-h-9 min-w-0 w-full border border-neutral-300 px-2 text-sm"
            maxLength={max} value={text[role]} onChange={e => { setText({ ...text, [role]: e.target.value }); setSelected(null); }} />
        </label>)}
      <p className="text-[11px] text-neutral-500">生成案をそのまま使用できます。空欄にした行は表示しません。</p>
    </fieldset>
    </div>
    <div aria-label="サムネの書式編集" tabIndex={0} className="min-h-0 min-w-0 xl:overflow-y-auto xl:overscroll-contain">
    <ThumbnailAssetPicker exportId={item.id} value={subject} onChange={setSubject} disabled={locked} />
    {subject.subjectSource === "asset" && subject.characterAssetId === item.thumbnailCharacterAssetId && <>
      {item.thumbnailWarnings?.map(warning => <p key={warning} role="status" className="mt-2 text-xs text-amber-800">{warning}</p>)}
      {item.thumbnailEmotionReason && <p className="mt-2 text-xs text-neutral-600">表情の選択理由: {item.thumbnailEmotionReason}</p>}
    </>}
    <fieldset disabled={locked} className="min-w-0 border border-amber-300 bg-white p-3">
      <legend className="px-1 text-xs font-bold">この動画のテンプレート</legend>
      <div className="grid grid-cols-2 gap-2 text-sm">
        {([ ["raden", "らでん"], ["sopia", "宙科"], ["plain", "単色"],
          ...(item.thumbnailCanUseCustomBackground ? [["custom", "カスタム背景"]] : [])
        ] as [NormalThumbnailStyle["design"], string][]).map(([value, label]) =>
          <button key={value} type="button" aria-pressed={design === value}
            onClick={() => setDesign(value)}
            className={`min-h-10 border px-2 ${design === value ? "border-sky-700 bg-sky-100 font-semibold" : "border-neutral-300 bg-white"}`}>
            {label}
          </button>)}
      </div>
      <p className="mt-2 text-xs text-neutral-600">この動画だけ切り替わります。プレビューで確認後、保存してください。</p>
    </fieldset>
    <fieldset disabled={locked} className="mt-3 min-w-0 border border-amber-300 bg-white p-3">
      <legend className="px-1 text-xs font-bold">人物の画角・位置</legend>
      <p className="text-xs text-neutral-600">{subject.subjectSource === "asset" ? "素材は顔を基準に胸から上を配置します。顔を検出できなかった素材も、大きさ・左右・上下で調整できます。" : "宙科テンプレでは切り抜きモデル導入時に人物だけを配置します。未導入時やほかのテンプレでは元映像の表示範囲を調整します。"}左のプレビューと保存画像は同じ配置になります。</p>
      <div className="mt-2 grid gap-2">
        {([
          ["scale", "大きさ", 0.5, 1.5, 0.05, `${Math.round(placement.scale * 100)}%`],
          ["offsetX", "左右", -300, 300, 5, `${placement.offsetX}px`],
          ["offsetY", "上下", -250, 250, 5, `${placement.offsetY}px`],
        ] as const).map(([key, label, min, max, step, display]) =>
          <label key={key} className="grid grid-cols-[3.5em_1fr_4em] items-center gap-2 text-xs">
            <span>{label}</span>
            <input aria-label={`人物の${label}`} type="range" min={min} max={max} step={step}
              value={placement[key]} onChange={e => setPlacement({ ...placement, [key]: Number(e.target.value) })}
              className="w-full accent-sky-700" />
            <output className="text-right tabular-nums">{display}</output>
          </label>)}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button type="button" className="min-h-9 border border-sky-700 bg-sky-50 text-xs font-semibold text-sky-900"
          onClick={() => setPlacement({ scale: 0.7, offsetX: -65, offsetY: 25 })}>小さく収める</button>
        <button type="button" className="min-h-9 border border-neutral-300 text-xs"
          onClick={() => setPlacement({ scale: 1, offsetX: 0, offsetY: 0 })}>配置をリセット</button>
      </div>
    </fieldset>
    <section aria-label="サムネの書式設定" className="min-w-0 border border-amber-300 bg-white p-3">
      <h4 className="text-sm font-semibold">書体・サイズ・色</h4>
      <div className="mt-3"><ThumbnailTextStyleEditor value={styles} onChange={setStyles} disabled={locked} texts={text} regions={regions} /></div>
    </section>
    <button type="button" disabled={locked || (subject.subjectSource === "asset" && !subject.characterAssetId)} onClick={() => onRender(item.thumbnailCropMode ?? "standard", styles, text, false, design, false, placement, subject)}
      className="mt-3 min-h-11 w-full bg-sky-700 px-3 text-sm font-semibold text-white disabled:bg-neutral-300">
      {item.thumbnailStatus === "generating" ? "サムネ更新中…" : "サムネを保存・更新"}
    </button>
    <p className="mt-2 text-xs text-neutral-600">プレビューは自動反映。保存するとサムネを確定します。</p>
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      <button type="button" disabled={locked || subject.subjectSource === "asset"} className="min-h-10 bg-amber-600 px-2 text-xs font-semibold text-white disabled:bg-neutral-300"
        onClick={() => onRender("standard", styles, text, true, design, false, placement, subject)}>別場面で更新（上半身）</button>
      <button type="button" disabled={locked || subject.subjectSource === "asset"} className="min-h-10 bg-neutral-950 px-2 text-xs font-semibold text-white disabled:bg-neutral-300"
        onClick={() => onRender("close", styles, text, true, design, false, placement, subject)}>別場面で更新（顔寄り）</button>
    </div>
    <button type="button" disabled={locked}
      className="mt-3 min-h-11 w-full border border-violet-700 bg-violet-50 px-3 text-sm font-semibold text-violet-900 disabled:text-neutral-400"
      onClick={() => onRender(item.thumbnailCropMode ?? "standard", styles, text, false, design, true, placement, { subjectSource: subject.subjectSource })}>
      {subject.subjectSource === "asset" ? "文言に合う表情を選び直す" : "Codexで文言に合う人物・場面を選び直す"}
    </button>
    <p className="mt-1 text-xs text-neutral-600">{subject.subjectSource === "asset" ? "登録済みの表情からCodexで選びます。表情が1種類ならそのまま使います。" : "元動画の８場面と近くの字幕を比較します。中央の人物も対象です。選んだ場面でサムネを保存し直します。"}</p>
    </div>
    </div>
  </section>;
}
