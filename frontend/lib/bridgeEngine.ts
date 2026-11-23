import { API_BASE_URL } from "./api";

// Matches backend/app/bridge_engine.py.
export type BridgeEngineName = "codex" | "claude";
export type BridgeLane = "normal" | "analysis";
export type BridgeLaneSetting = { engine: BridgeEngineName; model: string; effort: string };
export type BridgeEngineSettings = Record<BridgeLane, BridgeLaneSetting>;
export type BridgeCatalogModel = { id: string; efforts: string[] };
export type BridgeEngineCatalog = Record<BridgeEngineName, BridgeCatalogModel[]>;
export type BridgeEngineState = {
  saved: BridgeEngineSettings;
  active: BridgeEngineSettings | null;
  catalog: BridgeEngineCatalog;
  catalogSource: "bridge" | "builtin";
  bridgeState: string | null;
};

export const BRIDGE_LANES: { lane: BridgeLane; label: string; note: string }[] = [
  { lane: "normal", label: "通常の作業", note: "選定・タイトル・フック・画角・最終検査" },
  { lane: "analysis", label: "自己分析", note: "チャンネルの定時分析" },
];
export const ENGINE_LABELS: Record<BridgeEngineName, string> = { codex: "Codex", claude: "Claude" };
const DEFAULT_MODELS: Record<BridgeEngineName, string> = { codex: "gpt-6.1-sol", claude: "claude-opus-5-5" };

async function call(init?: RequestInit): Promise<BridgeEngineState> {
  const response = await fetch(`${API_BASE_URL}/api/bridge-engine`, { ...init, cache: "no-store", credentials: "include" });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "AIの設定を処理できませんでした。");
  return data as BridgeEngineState;
}
export const getBridgeEngine = () => call();
export const saveBridgeEngine = (settings: BridgeEngineSettings) => call({
  method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings),
});

/** Keep a lane valid after one of its parts changed: an engine change picks that engine's default model and effort. */
export function choose(catalog: BridgeEngineCatalog, current: BridgeLaneSetting,
  change: Partial<BridgeLaneSetting>): BridgeLaneSetting {
  const engine = change.engine ?? current.engine;
  const models = catalog[engine];
  const wanted = change.model ?? (engine === current.engine ? current.model : DEFAULT_MODELS[engine]);
  const model = models.find((item) => item.id === wanted) ?? models.find((item) => item.id === DEFAULT_MODELS[engine]) ?? models[0];
  const wantedEffort = change.effort ?? current.effort;
  const effort = model.efforts.includes(wantedEffort) ? wantedEffort
    : model.efforts.includes("medium") ? "medium" : model.efforts[0];
  return { engine, model: model.id, effort };
}

export const sameLane = (a?: BridgeLaneSetting | null, b?: BridgeLaneSetting | null) =>
  Boolean(a && b && a.engine === b.engine && a.model === b.model && a.effort === b.effort);

export function laneText(setting: BridgeLaneSetting): string {
  return `${ENGINE_LABELS[setting.engine]} ${setting.model}・${setting.effort}`;
}

/** What the running bridge does compared with the saved choice. */
export function laneStatus(state: BridgeEngineState, lane: BridgeLane): string {
  if (!state.active) return state.bridgeState === "error" ? "中継がエラーで停止中" : "中継が起動していません（次の起動から使用）";
  return sameLane(state.active[lane], state.saved[lane]) ? "使用中" : `反映待ち（今は ${laneText(state.active[lane])}）`;
}
