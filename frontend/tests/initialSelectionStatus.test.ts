import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { InitialSelectionStatusBanner } from "../components/InitialSelectionStatusBanner";
import { initialSelectionStatusDisplay } from "../lib/initialSelectionStatus";

const success = initialSelectionStatusDisplay({
  initialSelectionProvider: "codex",
  codexInitialSelectionStatus: "completed",
  codexInitialSelectionFallbackUsed: false,
  codexInitialSelectionRequestedNormalCount: 2,
  codexInitialSelectionRequestedShortCount: 5,
  codexInitialSelectionSelectedNormalCount: 2,
  codexInitialSelectionSelectedShortCount: 5
});
assert.equal(success?.state, "success");
assert.equal(success?.title, "Codex内容選定");
assert.equal(success?.detail, "通常 2/2・ショート 5/5");

const fallback = initialSelectionStatusDisplay({
  initialSelectionProvider: "codex",
  codexInitialSelectionStatus: "fallback",
  codexInitialSelectionFallbackUsed: true,
  codexInitialSelectionError: "codex_initial_selection_request_invalid"
});
assert.equal(fallback?.state, "fallback");
assert.equal(fallback?.title, "ローカル仮選定");
assert.equal(
  fallback?.description,
  "Codex選定に失敗したため、表示中はローカル仮選定です。おすすめ結果ではありません。"
);
assert.equal(fallback?.detail, "codex_initial_selection_request_invalid");
const fallbackMarkup = renderToStaticMarkup(
  createElement(InitialSelectionStatusBanner, {
    details: {
      initialSelectionProvider: "codex",
      codexInitialSelectionStatus: "fallback",
      codexInitialSelectionFallbackUsed: true
    },
    jobStatus: "awaiting_clip_review"
  })
);
assert.match(fallbackMarkup, /role="alert"/);
assert.match(fallbackMarkup, /data-initial-selection-state="fallback"/);
assert.match(fallbackMarkup, /ローカル仮選定/);
assert.match(fallbackMarkup, /おすすめ結果ではありません/);

const fallbackWithDiagnostics = initialSelectionStatusDisplay({
  initialSelectionProvider: "codex",
  codexInitialSelectionStatus: "fallback",
  codexInitialSelectionFallbackUsed: true,
  codexInitialSelectionErrorMessage: "Codex初期選定を実行できませんでした。",
  codexInitialSelectionErrorCode: "codex_initial_selection_host_failed",
  codexInitialSelectionHostErrorCode: "response_schema_contract_mismatch"
});
assert.equal(
  fallbackWithDiagnostics?.detail,
  "Codex初期選定を実行できませんでした。 — codex_initial_selection_host_failed / response_schema_contract_mismatch"
);

const retrying = initialSelectionStatusDisplay(
  {
    initialSelectionProvider: "codex",
    codexInitialSelectionStatus: "running",
    codexInitialSelectionAttemptCount: 2
  },
  "selecting_clips"
);
assert.equal(retrying?.state, "retrying");
assert.equal(retrying?.title, "Codex接続を再試行中");
assert.equal(retrying?.detail, "試行 2回目");

const legacy = initialSelectionStatusDisplay({ initialSelectionProvider: "legacy" });
assert.equal(legacy, null);

const missingSummary = initialSelectionStatusDisplay(
  {
    initialSelectionProvider: "codex",
    codexInitialSelectionSummaryAvailable: false
  },
  "awaiting_clip_review"
);
assert.equal(missingSummary?.state, "unknown");
assert.equal(missingSummary?.title, "選定方法を確認できません");
assert.equal(missingSummary?.tone, "warning");

console.log("initial selection status UI contract: passed");
