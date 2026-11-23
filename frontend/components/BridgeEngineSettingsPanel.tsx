"use client";

import { useEffect, useState } from "react";
import {
  BRIDGE_LANES, ENGINE_LABELS, choose, getBridgeEngine, laneStatus, sameLane, saveBridgeEngine,
  type BridgeEngineName, type BridgeEngineSettings, type BridgeEngineState, type BridgeLane,
} from "../lib/bridgeEngine";

const selectClassName =
  "mt-1 min-h-9 w-full border border-[#cfcfcb] bg-white px-2 py-1.5 text-xs text-[#252522] outline-none focus:border-sky-600 disabled:bg-[#eeeeeb]";

export function BridgeEngineForm({ state, draft, busy, onChange, onSave }: {
  state: BridgeEngineState; draft: BridgeEngineSettings; busy: boolean;
  onChange: (lane: BridgeLane, change: Partial<BridgeEngineSettings[BridgeLane]>) => void; onSave: () => void;
}) {
  const changed = BRIDGE_LANES.some(({ lane }) => !sameLane(draft[lane], state.saved[lane]));
  return <div className="grid gap-3 border-t border-[#e2e2df] p-3">
    {BRIDGE_LANES.map(({ lane, label, note }) => {
      const setting = draft[lane];
      const models = state.catalog[setting.engine];
      const efforts = models.find((item) => item.id === setting.model)?.efforts ?? [];
      return <fieldset key={lane} className="grid gap-1" aria-label={`${label}のAI`}>
        <legend className="text-xs font-bold text-[#282825]">{label}
          <span className="ml-2 text-[10px] font-normal text-[#73736e]">{note}</span></legend>
        <div className="grid grid-cols-[5.5rem_minmax(0,1fr)_5rem] gap-2">
          <label className="text-[10px] font-bold text-[#555550]">AI
            <select className={selectClassName} disabled={busy} value={setting.engine}
              onChange={(event) => onChange(lane, { engine: event.target.value as BridgeEngineName })}>
              {(Object.keys(ENGINE_LABELS) as BridgeEngineName[]).map((engine) =>
                <option key={engine} value={engine}>{ENGINE_LABELS[engine]}</option>)}
            </select></label>
          <label className="text-[10px] font-bold text-[#555550]">モデル
            <select className={selectClassName} disabled={busy} value={setting.model}
              onChange={(event) => onChange(lane, { model: event.target.value })}>
              {models.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}
            </select></label>
          <label className="text-[10px] font-bold text-[#555550]">深さ
            <select className={selectClassName} disabled={busy} value={setting.effort}
              onChange={(event) => onChange(lane, { effort: event.target.value })}>
              {efforts.map((effort) => <option key={effort} value={effort}>{effort}</option>)}
            </select></label>
        </div>
        <p className="text-[10px] text-[#5f5f5a]">{laneStatus(state, lane)}</p>
      </fieldset>;
    })}
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" disabled={busy || !changed} onClick={onSave}
        className="min-h-9 bg-sky-700 px-3 text-xs font-bold text-white hover:bg-sky-800 disabled:cursor-not-allowed disabled:bg-[#d2d2cf]">
        保存（次の依頼から切り替え）</button>
      <span className="text-[10px] text-[#73736e]">処理中の依頼はそのまま。中継の再起動は不要。</span>
    </div>
    {state.catalogSource === "builtin" ?
      <p className="text-[10px] text-amber-800">中継から選択肢を取得できないため、既定の選択肢だけ表示しています。</p> : null}
  </div>;
}

export function BridgeEngineSettingsPanel() {
  const [state, setState] = useState<BridgeEngineState | null>(null);
  const [draft, setDraft] = useState<BridgeEngineSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => getBridgeEngine().then((next) => {
      if (!alive) return;
      setState(next);
      setDraft((current) => current ?? next.saved);
    }).catch((error: Error) => alive && setMessage(error.message));
    load();
    const timer = window.setInterval(load, 15000);  // shows when the bridge has picked the change up
    return () => { alive = false; window.clearInterval(timer); };
  }, []);

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setMessage(null);
    try {
      const next = await saveBridgeEngine(draft);
      setState(next);
      setDraft(next.saved);
      setMessage("保存しました。次の依頼から使います。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存できませんでした。");
    } finally {
      setBusy(false);
    }
  };

  return <details className="border-t border-[#d5d5d2] bg-white">
    <summary className="cursor-pointer px-3 py-3 text-xs font-bold text-[#282825]">
      AIの設定
      {state ? <span className="ml-2 text-[10px] font-normal text-[#73736e]">
        通常 {ENGINE_LABELS[state.saved.normal.engine]}・分析 {ENGINE_LABELS[state.saved.analysis.engine]}</span> : null}
    </summary>
    {state && draft ? <BridgeEngineForm state={state} draft={draft} busy={busy} onSave={save}
      onChange={(lane, change) => setDraft({ ...draft, [lane]: choose(state.catalog, draft[lane], change) })} /> : null}
    {message ? <p role="status" className="px-3 pb-3 text-xs text-[#3e3e3a]">{message}</p> : null}
  </details>;
}
