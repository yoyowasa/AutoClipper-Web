"use client";

import { useEffect, useState } from "react";
import { youtubeSyncTime } from "../lib/intelligence";
import { getProductionLinks, reconcileProductionLinks, setProductionLink, type ProductionLinks } from "../lib/productionLinks";

export function ProductionLinkList({ data, busy, choices, onChoose, onLink, onUnlink }: {
  data: ProductionLinks; busy: boolean; choices: Record<string, string>;
  onChoose: (familyId: string, videoId: string) => void;
  onLink: (familyId: string, videoId: string) => void; onUnlink: (familyId: string) => void;
}) {
  return <>
    <p className="text-sm" aria-live="polite">結び付き {data.linkedCount}件 ／ 未結び付けの制作記録 {data.unlinkedRecordCount}件
      ／ 未結び付けの動画 {data.unlinkedVideoCount}件</p>
    {data.issues.length > 0 ? <p className="text-sm text-amber-800">読み取れない、または枝分かれした制作記録が
      {data.issues.length}件あります。これらは自動照合しません。</p> : null}
    <h3 className="font-semibold">結び付き</h3>
    <ul className="space-y-2">{data.links.map(link => <li key={link.familyId} className="border bg-white p-3 text-sm">
      <p>{link.record?.publicationTitle ?? link.recordId} → {link.video.title ?? link.video.id}</p>
      <p className="text-xs text-neutral-600">{link.mode === "manual" ? "手動" : "自動"} ／
        公開: {youtubeSyncTime(link.video.publishedAt)} ／ 記録: {link.recordId}</p>
      <button type="button" disabled={busy} onClick={() => onUnlink(link.familyId)}
        className="mt-2 border px-3 py-1 disabled:opacity-40">結び付きを外す</button>
    </li>)}</ul>
    <h3 className="font-semibold">未結び付けの制作記録</h3>
    <ul className="space-y-2">{data.unlinkedRecords.map(record => <li key={record.familyId} className="border bg-white p-3 text-sm">
      <p>{record.publicationTitle}</p>
      <p className="text-xs text-neutral-600">{record.type === "short" ? "ショート" : "通常"} ／
        書き出し: {youtubeSyncTime(record.createdAt)} ／ {record.recordId}</p>
      {record.mode === "manual_unlinked" ? <p className="text-xs">手動で解除済み（自動照合では結び直しません）</p> : null}
      {record.ambiguous ? <p className="text-amber-800">記録が枝分かれしているため選べません。</p> : null}
      <div className="mt-2 flex flex-wrap gap-2">
        <select aria-label={`${record.publicationTitle}に結ぶ動画`} className="min-w-0 max-w-full flex-1 border p-2"
          value={choices[record.familyId] ?? ""} disabled={busy || record.ambiguous}
          onChange={event => onChoose(record.familyId, event.target.value)}>
          <option value="">YouTube動画を選ぶ</option>
          {data.unlinkedVideos.map(video => <option key={video.id} value={video.id}>
            {video.title ?? "タイトル未取得"} ／ {youtubeSyncTime(video.publishedAt)} ／ {video.id}
          </option>)}
        </select>
        <button type="button" disabled={busy || record.ambiguous || !choices[record.familyId]}
          className="border px-3 py-2 disabled:opacity-40" onClick={() => onLink(record.familyId, choices[record.familyId])}>結ぶ</button>
      </div>
    </li>)}</ul>
    {data.unlinkedRecordCount === 0 ? <p className="text-sm">未結び付けの制作記録はありません。</p> : null}
    <details className="text-sm"><summary>未結び付けの動画（{data.unlinkedVideoCount}件）</summary>
      <ul>{data.unlinkedVideos.map(video => <li key={video.id} className="mt-2">
        {video.title ?? video.id} ／ {youtubeSyncTime(video.publishedAt)}
      </li>)}</ul>
    </details>
  </>;
}

export function ProductionLinkSettings() {
  const [data, setData] = useState<ProductionLinks | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    getProductionLinks().then(value => { if (active) setData(value); })
      .catch(() => { if (active) setError("制作記録の結び付きを取得できませんでした。"); });
    return () => { active = false; };
  }, []);
  async function perform(action: () => Promise<ProductionLinks>) {
    setBusy(true); setError(null);
    try { setData(await action()); setChoices({}); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "結び付きを更新できませんでした。"); }
    finally { setBusy(false); }
  }
  return <section className="space-y-3 border-t pt-6" aria-labelledby="production-link-heading">
    <h2 id="production-link-heading" className="text-xl font-bold">制作記録の結び付け</h2>
    <p className="text-sm">投稿タイトルと公開日時で1対1に一致した動画だけを自動で結びます。
      手動で結んだものと、手動で外したものは自動照合で変更しません。</p>
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
    <div className="flex gap-2">
      <button type="button" disabled={busy} className="border px-3 py-2 disabled:opacity-40"
        onClick={() => void perform(reconcileProductionLinks)}>照合し直す</button>
      <button type="button" disabled={busy} className="border px-3 py-2 disabled:opacity-40"
        onClick={() => void perform(getProductionLinks)}>一覧を更新</button>
    </div>
    {data ? <ProductionLinkList data={data} busy={busy} choices={choices}
      onChoose={(familyId, videoId) => setChoices(previous => ({ ...previous, [familyId]: videoId }))}
      onLink={(familyId, videoId) => void perform(() => setProductionLink(familyId, videoId))}
      onUnlink={familyId => void perform(() => setProductionLink(familyId, null))} /> : <p>制作記録を確認中…</p>}
  </section>;
}
