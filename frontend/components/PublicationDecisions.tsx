import type { PublicationSummary, PublicationDecision } from "../lib/types";
import { publicationLabel, publicationReasons } from "../lib/publicationDecisions";

export function PublicationDecisions({ summary, onKeep, disabled = false }: {
  summary: PublicationSummary | null; onKeep?: (decision: PublicationDecision) => void; disabled?: boolean;
}) {
  if (!summary) return null;
  const pending = summary.decisions.filter(d => d.decision !== "publish");
  if (!pending.length) return null;
  return <section className="rounded border border-amber-300 bg-amber-50 p-4 text-amber-950">
    <h2 className="font-semibold">{summary.outcome === "no_publication" ? "投稿なし（見送り）" :
      summary.outcome === "needs_review" ? "投稿可否の判定が必要な候補があります" : `素材が弱いため${summary.selectedCount}本を制作します`}</h2>
    <p className="mt-1 text-xs">見送り基準は未検証の運用基準です。見送った分を弱い候補で埋め直しません。判定不能は見送りと区別します。</p>
    <ul className="mt-3 space-y-3">{pending.map(d => <li key={d.candidateId}>
      <p className="text-sm font-semibold">{publicationLabel(d)}：{d.decision === "skip" ? "見送り" : "判定不能"} — {d.title}</p>
      <p className="text-sm">{d.reasons.map(r => publicationReasons[r] ?? "投稿可否を確認してください").join("。")}</p>
      {onKeep ? <button className="mt-2 rounded border border-amber-600 px-3 py-2 text-sm disabled:opacity-50"
        disabled={disabled} onClick={() => onKeep(d)} type="button">キープして採用</button> : null}
    </li>)}</ul>
    {onKeep ? <p className="mt-3 text-xs">キープまたは範囲の保存で見送り・判定不能から採用へ戻せます。採用時も既存の尺・品質の必須条件は検査します。</p> : null}
  </section>;
}
