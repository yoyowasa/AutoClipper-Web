"use client";

import { useEffect, useState } from "react";
import { getSubtitleTerms, switchSubtitleTerm, termStatus, type CharacterSubtitleTerms, type SubtitleTerm } from "../lib/subtitleTerms";

export function SubtitleTermList({ items, busy, onSwitch }: {
  items: CharacterSubtitleTerms[]; busy: boolean; onSwitch: (characterId: string, term: SubtitleTerm, disabled: boolean) => void;
}) {
  if (!items.length) return <p className="text-sm">学習した語はまだありません。字幕を直すと、同じ直しが重なった語がここに並びます。</p>;
  return <>{items.map(item => <article key={item.id} className="space-y-2 border bg-white p-3">
    <h3 className="font-semibold">{item.character}</h3>
    <ul className="space-y-2">{item.terms.map(term => <li key={`${term.src}\t${term.dst}`} className="text-sm">
      <p><span className="font-semibold">{term.src}</span> → <span className="font-semibold">{term.dst}</span>
        （修正{term.count}回／{term.jobs}本{term.kept > 0 ? `／直さず残した${term.kept}回` : ""}）</p>
      <p className="text-xs text-neutral-600">{termStatus(term)}</p>
      <button type="button" disabled={busy} onClick={() => onSwitch(item.id, term, !term.disabled)}
        className="mt-1 border px-3 py-1 disabled:opacity-40">{term.disabled ? "また使う" : "使わない"}</button>
    </li>)}</ul>
  </article>)}</>;
}

export function SubtitleTermRules() {
  const [items, setItems] = useState<CharacterSubtitleTerms[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    getSubtitleTerms().then(value => { if (active) setItems(value); })
      .catch(() => { if (active) setError("学習した字幕の語を取得できませんでした。"); });
    return () => { active = false; };
  }, []);
  async function change(characterId: string, term: SubtitleTerm, disabled: boolean) {
    setBusy(true); setError(null);
    try { await switchSubtitleTerm(characterId, term, disabled); setItems(await getSubtitleTerms()); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "設定を変更できませんでした。"); }
    finally { setBusy(false); }
  }
  return <section className="space-y-3 border-t pt-6" aria-labelledby="subtitle-term-heading">
    <h2 id="subtitle-term-heading" className="text-xl font-bold">字幕の語の学習（キャラ別）</h2>
    <p className="text-sm">字幕で同じ語を何度も直すと、次の動画から同じ語を自動で置き換えます（3回、または1本で5回の修正が目安）。
      置き換えるのは、あなたが実際に直した語と完全に同じ文字列だけです。意味の判断や新しい語の追加はしません。
      字幕の確認と最終修正はこれまでどおり人が行います。</p>
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
    {items ? <SubtitleTermList items={items} busy={busy} onSwitch={(id, term, disabled) => void change(id, term, disabled)} /> : <p>読み込み中…</p>}
  </section>;
}
