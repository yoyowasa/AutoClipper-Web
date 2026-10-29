import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { automationLabel } from "../lib/intelligence";
import { goalLabel, type NativeReport, type VideoGoal } from "../lib/intelligenceDashboard";
import type { AnalysisReview } from "../lib/channelAnalysis";
import type { ChoiceEvaluations as EvaluationData } from "../lib/productionPerformance";
import { AnalysisReviewText } from "../components/ChannelAnalysisSettings";
import { ChoiceEvaluations } from "../components/intelligence/ChoiceEvaluations";

Object.assign(globalThis, { React });
assert.match(automationLabel({ enabled: true, syncHourUtc: 3, analysisWeekday: 0, timezone: "UTC" }), /毎日12:00.*月曜/);
assert.match(automationLabel({ enabled: true, syncHourUtc: 23, analysisWeekday: 0, timezone: "UTC" }), /毎日8:00.*火曜/);
assert.match(automationLabel({ enabled: false, syncHourUtc: 3, analysisWeekday: 0, timezone: "UTC" }), /無効.*手動/);
assert.match(automationLabel(undefined), /未取得/);
const report: NativeReport = { source: "youtube_analytics", start: "2026-09-02", end: "2026-10-01",
  observedAt: "2026-10-03T00:00:00Z", metrics: { views: { value: null, missingReason: "NO_ROWS", observedSubtotal: null } },
  reason: "NO_ROWS", expected: null, returned: null, format: "shorts" };
const goal: VideoGoal = { video_id: "video000001", format: "shorts", target_views: 1000000, status: "pending",
  reason: "FIRST30_NOT_READY", evidence_ids: [], first7: report, first30: report };
assert.match(goalLabel(goal), /未判定.*30日/);
assert.match(goalLabel({ ...goal, status: "insufficient_data", reason: "NO_ROWS" }), /データ不足.*返っていません/);
assert.match(goalLabel({ ...goal, status: "below_target" }), /未達.*失敗とは判定しません/);
assert.match(goalLabel({ ...goal, status: "reached" }), /到達/);
const raw: AnalysisReview = { id: "analysis_one", channel_id: 1, batch_run_id: "sync_one", title: "分析", summary: "観測の仮説です",
  goals: { normal_views: 100000, short_views: 1000000, window_days: 30, interim_days: 7 },
  recommendation_framework_version: null, reviewed_material: "statistics_and_titles", limitations: [], findings: [], proposals: [] };
assert.match(renderToStaticMarkup(React.createElement(AnalysisReviewText, { review: raw })), /30日目標：通常10万・ショート100万/);
assert.match(renderToStaticMarkup(React.createElement(AnalysisReviewText, { review: { ...raw, goals: null, goal_views: 1000000 } })), /旧版の分析/);
const data: EvaluationData = { source: "independent_aggregation", label: "独自集計", minimum_group_videos: 5,
  window_days: 30, interim_days: 7, linked_videos: 1, excluded_reasons: {}, groups: [{
    id: "group", character_preset_name: "キャラ", format: "short", kind: "framing", role: "", source: "fallback",
    policy_version: "v1", count: 1, judged_count: 0, sufficient: false, effect: "unconfirmed", target_views: 1000000,
    option_values: { shortLayout: "face_tracking_crop" },
    median_views: null, reached_count: 0, attainment_rate: null, video_ids: [goal.video_id], observations: [{
      record_id: "exp", record_family_id: "exp", choice_id: "choice", video_id: goal.video_id, kind: "framing", role: "",
      source: "fallback", policy_version: "v1", value_hash: "hash", selected_ids: ["face_tracking_crop"], evaluation: goal,
      values: { shortLayout: "face_tracking_crop" }, values_omitted: false,
    }],
  }] };
const html = renderToStaticMarkup(React.createElement(ChoiceEvaluations, { data }));
assert.match(html, /独自集計/);
assert.match(html, /fallback（代替）.*v1/);
assert.match(html, /データ不足・効果未確認/);
assert.match(html, /中央値：未取得/);
assert.match(html, /観測：/);
assert.match(html, /未判定/);
assert.match(renderToStaticMarkup(React.createElement(ChoiceEvaluations, { data: { ...data, groups: [] } })), /データ不足/);
console.log("Daily/weekly schedule, fixed 30-day goals, legacy reviews and choice provenance render without invented zeroes");
