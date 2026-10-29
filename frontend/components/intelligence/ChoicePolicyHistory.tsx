"use client";
import { useCallback, useEffect, useState } from "react";
import { getChoicePolicies, restoreChoicePolicy, policyReason, type ChoicePolicy, type PolicyCohort } from "../../lib/choicePolicies";
import { youtubeSyncTime } from "../../lib/intelligence";

function CohortEvidence({ data, onVideo }: { data?: PolicyCohort | null; onVideo?: (id: string) => void }) {
  if (!data) return null;
  return <div className="my-2 rounded border p-2 text-sm"><p>集計: {data.id}</p>
    <p>{data.band} ／ 判定済み{data.count}本 ／ 到達率{data.rate == null ? "未取得" : `${Math.round(data.rate * 100)}%`}
      ／ 中央値{data.median?.toLocaleString() ?? "未取得"}再生</p><p>観測: {youtubeSyncTime(data.observed_at)}</p>
    {data.first7_count ? <p>7日途中評価: {data.first7_count}本 ／ 中央値{data.first7_median?.toLocaleString() ?? "未取得"}（警告用）</p> : null}
    {data.video_ids.map((id, index) => <button type="button" key={id} onClick={() => onVideo?.(id)}
      className="mr-3 underline">根拠動画{index + 1}</button>)}</div>;
}

export function ChoicePolicyHistory({ channelId, onVideo }: { channelId: number; onVideo?: (id: string) => void }) {
  const [items, setItems] = useState<ChoicePolicy[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    try { setItems(await getChoicePolicies(channelId)); setError(""); }
    catch { setError("選び方の版を読み込めませんでした。"); }
  }, [channelId]);
  useEffect(() => {
    let active = true;
    getChoicePolicies(channelId).then(value => { if (active) { setItems(value); setError(""); } })
      .catch(() => { if (active) setError("選び方の版を読み込めませんでした。"); });
    return () => { active = false; };
  }, [channelId]);
  async function restore(item: ChoicePolicy) {
    if (!window.confirm("次に開始するジョブから、直前の選び方へ戻します。進行中のジョブは変わりません。")) return;
    setBusy(true);
    try { await restoreChoicePolicy(channelId, item); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "直前の版へ戻せませんでした。"); }
    finally { setBusy(false); }
  }
  return <section aria-label="選び方の版と自動更新" className="space-y-3 rounded border border-emerald-200 bg-emerald-50 p-5">
    <h2 className="font-bold">選び方の版と自動更新</h2>
    <p className="text-sm">自動由来・同形式・同じ尺帯で各5本以上の30日評価を比較します。
      到達率が下がらず中央値が20%以上改善した場合だけ、1項目を最大10%変更します。
      30日の中央値が20%以上悪化すると直前の版へ戻します。7日は警告のみ。因果効果の証明ではありません。</p>
    <button type="button" onClick={() => void refresh()} className="underline">版と履歴を読み直す</button>
    {error ? <p role="alert">{error}</p> : null}
    <ChoicePolicyItems items={items} busy={busy} restore={item => void restore(item)} onVideo={onVideo} />
  </section>;
}

export function ChoicePolicyItems({ items, busy, restore, onVideo }: {
  items: ChoicePolicy[]; busy: boolean; restore: (item: ChoicePolicy) => void; onVideo?: (id: string) => void;
}) {
  return <>
    {!items.length ? <p>版はまだありません。自己分析の後、評価が不足していれば保留理由を記録します。</p> : items.map(item => {
      const active = item.versions.find(v => v.id === item.currentId);
      return <article key={item.id} className="space-y-2 rounded border bg-white p-3">
        <h3 className="font-semibold">{item.character} ／ {item.format === "short" ? "ショート" : "通常"}</h3>
        <p>現在の版: {item.currentId}（{youtubeSyncTime(active?.createdAt ?? null)}）</p>
        <button type="button" disabled={busy || !active?.previousId} onClick={() => void restore(item)}
          className="rounded border px-3 py-1 disabled:opacity-50">直前の版に戻す</button>
        <details><summary>現在の優先度・重み</summary><pre className="overflow-auto text-xs">{JSON.stringify(active?.values, null, 2)}</pre></details>
        {item.decisions.map(event => <details key={event.id} className="border-t pt-2">
          <summary>{youtubeSyncTime(event.createdAt)}：{policyReason[event.reason] ?? event.reason}</summary>
          <p className="text-sm">{event.fromId} → {event.toId}</p>
          {event.evidence ? <><CohortEvidence data={event.evidence.before} onVideo={onVideo} />
            <CohortEvidence data={event.evidence.after} onVideo={onVideo} />
            {event.evidence.cohorts?.map(group => <CohortEvidence key={`${group.id}:${group.band}`} data={group} onVideo={onVideo} />)}
            {event.evidence.omitted_cohorts ? <p>ほか{event.evidence.omitted_cohorts}グループ（省略）</p> : null}
          </> : <p>根拠の保持期限が切れています。</p>}
        </details>)}
      </article>;
    })}
  </>;
}
