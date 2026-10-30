export type FinalInspectionProblem = { clipLabel: string; reason: string; repairCount: number };

export function finalInspectionProblems(details: Record<string, unknown>): FinalInspectionProblem[] {
  const value = details.finalInspection;
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is FinalInspectionProblem =>
    Boolean(item && typeof item === "object" && typeof item.clipLabel === "string" &&
      typeof item.reason === "string" && typeof item.repairCount === "number"));
}

export function FinalInspectionAttention({ details }: { details: Record<string, unknown> }) {
  const problems = finalInspectionProblems(details);
  if (!problems.length) return null;
  return <section role="alert" className="rounded border border-red-300 bg-red-50 p-4 text-red-900">
    <h2 className="font-semibold">完成検査で停止しました</h2>
    {problems.map((item, index) => <p className="mt-2 text-sm" key={index}>
      {item.reason}（自動修復 {item.repairCount}回）
    </p>)}
    <p className="mt-2 text-sm">確認・編集画面で対象の動画を直し、もう一度確定して書き出せます。</p>
  </section>;
}
