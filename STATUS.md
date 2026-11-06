# AutoClipper Web Status

## 運用メモ

日付のない既存節は初期の記録を原文のまま残しています。現在の運用では以下と10月以降の記録を参照してください。

- 有料のOpenAI Platform APIは使わず、AI選定・文言生成はChatGPTログインのCodex経路を使います。冒頭に残るAPI採点・キー受け渡しの記述は当時の状態です。[元の記録（task-166）](docs/status_archive/STATUS_2026-09.md#2026-09-30-jst-有料platform-apiの呼び出し経路を削除task-166)。
- キルゴUかなNBはローカル限定で、別PCへの同梱やイメージ配布をしません。[元の記録（ローカル限定フォント）](docs/status_archive/STATUS_2026-09.md#2026-09-07-字幕1件ごとの書式二重縁取りショート顔アップ)。
- 同じ元動画の使用済み区間の台帳はジョブ削除後も残ります。過去と動画尺が1秒超異なる場合は`source_history_timeline_changed`で停止します。同じ尺の編集による時間ずれは検出対象外です。[元の記録（使用済み区間）](docs/status_archive/STATUS_2026-09.md#2026-09-11-同じ元動画の再アップロード時に使用済み区間を除外)。
- 字幕確認から尺調整へ戻る際、未保存の変更があると移動できません。保存済みの字幕・タイトル・フック・書式を保持し、尺が変わったclipの確認状態とプレビューを更新します。[元の記録（尺調整）](docs/status_archive/STATUS_2026-09.md#2026-09-28-jst-字幕編集から尺調整へ戻る導線を追加)。

## 目的

AutoClipper Web の開発状態、実装履歴、修正履歴、仕様変更、未解決事項をタスク単位で記録する。

## 現在状態

- Task 01 Repository scaffold の実装完了。
- Git repository 初期化と GitHub remote 接続完了。
- GitHub Actions backend ruff F401 修正完了。
- Docker Desktop 導入と docker compose 起動検証完了。
- Task 17 Runtime verification and real video E2E hardening の実装完了。
- Task 18 Real sample video E2E validation の実装完了。
- Task 19 Real spoken-video E2E without fixture transcript の実装完了。
- Task 20 Add early failure for silent or unusable audio の実装完了。
- Task 21 Add generation diagnostic summaries の実装完了。
- Task 22 Make normal clip duration settings configurable from UI/API の実装完了。
- 初期 FastAPI backend data model / API routes の実装完了。
- RQ worker と real AutoClipper pipeline の実装完了。
- Next.js frontend upload flow の実装完了。
- FFmpeg / ffprobe wrapper の実装完了。
- faster-whisper transcription wrapper の実装完了。
- scene/audio feature extraction wrapper の実装完了。
- candidate generation の実装完了。
- rule-based scoring / candidate deduplication の実装完了。
- OpenAI Structured Outputs candidate scoring の実装完了。
- quality gate / final candidate selection の実装完了。
- ASS subtitle generation の実装完了。
- selected normal candidates to FFmpeg rendering の実装完了。
- automatic short rendering の実装完了。
- app hardening の実装完了。
- CI / Codex運用ルール の実装完了。
- OpenAI API key の docker compose pass-through 設定完了。
- 実動画処理のend-to-end worker pipeline連結を実装済み。

## 実装履歴

- 2026-06-28: GitHub repo 初期化、remote接続、初回pushを実施。`.gitignore` に `*.tsbuildinfo` を追加。
- 2026-06-28: Next.js + TypeScript + Tailwind frontend scaffold を作成。
- 2026-06-28: FastAPI backend scaffold と `/health` / `/api/health` を作成。
- 2026-06-28: `docker-compose.yml` に backend / frontend / redis を定義。
- 2026-06-28: `storage/uploads`, `storage/temp`, `storage/outputs` を作成。
- 2026-06-28: SQLite-backed `Video` / `Job` / `ExportItem` モデルと初期 API routes を作成。
- 2026-06-28: RQ worker と dummy AutoClipper job を作成。fake exports と ZIP を生成。
- 2026-06-28: `/upload`、`/jobs/[jobId]`、`/results/[jobId]` と upload flow components を作成。
- 2026-06-28: FFmpeg / ffprobe wrappers を作成。metadata probe、audio extraction、normal render、short render の command construction を追加。
- 2026-06-28: faster-whisper transcription wrapper と transcription engine interface を作成。
- 2026-06-28: scene detection、silence detection、audio features、black screen quality wrappers を作成。
- 2026-06-28: short / normal candidate generation と boundary merge helper を作成。
- 2026-06-28: rule-based scoring と candidate deduplication を作成。
- 2026-06-28: OpenAI Structured Outputs scoring、retry、cache、batch scoring を作成。
- 2026-06-28: quality gate と final candidate selection、`selected_clips.json` 保存を作成。
- 2026-06-28: ASS subtitle generation を作成。選定済み clip ごとの ASS 保存に対応。
- 2026-06-28: selected normal candidates をFFmpeg renderへ接続し、`ExportItem` 作成に対応。
- 2026-06-28: automatic short rendering を作成。face tracking / center crop / blur background fallback と `ExportItem` 作成に対応。
- 2026-06-28: dummy worker enqueue を real AutoClipper pipeline enqueue へ差し替え。中間JSON、render、metadata、ZIP生成を連結。
- 2026-06-28: known failure error codes、upload validation、temp cleanup、OpenAI fallback、failed UI表示を追加。
- 2026-06-28: GitHub Actions CI、backend ruff、frontend build、Codex運用ルールを追加。
- 2026-06-28: `OPENAI_API_KEY` を backend / worker コンテナへ渡す docker compose 設定を追加。
- 2026-06-28: Docker Desktop を導入し、`docker compose up -d --build` で backend / frontend / redis / worker 起動を確認。
- 2026-06-28: `scripts/smoke_runtime.py` と runtime README を追加し、Docker runtime / ffmpeg / ffprobe / shared storage smoke を実装。
- 2026-06-28: `scripts/generate_sample_video.py` と `scripts/e2e_sample_video.py` を追加し、synthetic MP4 の real runtime E2E 導線を実装。
- 2026-06-28: `scripts/e2e_real_video.py` を追加し、ユーザー supplied spoken video の faster-whisper E2E 導線を実装。
- 2026-06-28: silent / unusable audio と unusable transcript の早期失敗を worker pipeline に追加。
- 2026-06-28: completed / failed job の generation diagnostic summary JSON 出力を追加。
- 2026-06-28: normal / short duration settings を API schema、UI、E2E script から指定可能にした。

## 修正履歴

- 2026-06-28: GitHub Actions backend ruff F401 failure を修正。
- 2026-06-28: Git 初回commit対象から TypeScript incremental build artifact を除外。
- 2026-06-28: `OPENAI_API_KEY` が `.env` にある前提で、`docker-compose.yml` の backend / worker environment に `${OPENAI_API_KEY}` を追加。

## 仕様変更履歴

未記録。

## 未解決事項

- `npm audit --omit=dev` は Next.js 最新 `16.2.9` 内包 PostCSS 由来の moderate 警告あり。現時点で通常更新では解消不可。

## 更新ルール

- 変更時は必ずこのファイルを更新する。
- 新しい作業は `## YYYY-MM-DD ...` 見出しで追記する。
- 目的、変更ファイル、検証結果、未解決事項を短く残す。
- 秘密情報、API key、個人情報は書かない。

## アーカイブ索引

2026-09-30以前の作業記録を月別に保存しています。各月の見出し一覧は元の記録順です。

### [2026-06（40件）](docs/status_archive/STATUS_2026-06.md)

<details>
<summary>見出し一覧（40件）</summary>

- [2026-06-28 Task 01 Repository scaffold](docs/status_archive/STATUS_2026-06.md#2026-06-28-task-01-repository-scaffold)
- [2026-06-28 Initial FastAPI data model and API routes](docs/status_archive/STATUS_2026-06.md#2026-06-28-initial-fastapi-data-model-and-api-routes)
- [2026-06-28 RQ worker and dummy AutoClipper job](docs/status_archive/STATUS_2026-06.md#2026-06-28-rq-worker-and-dummy-autoclipper-job)
- [2026-06-28 Next.js frontend upload flow](docs/status_archive/STATUS_2026-06.md#2026-06-28-nextjs-frontend-upload-flow)
- [2026-06-28 FFmpeg and ffprobe wrappers](docs/status_archive/STATUS_2026-06.md#2026-06-28-ffmpeg-and-ffprobe-wrappers)
- [2026-06-28 faster-whisper transcription wrapper](docs/status_archive/STATUS_2026-06.md#2026-06-28-faster-whisper-transcription-wrapper)
- [2026-06-28 Scene and audio feature extraction](docs/status_archive/STATUS_2026-06.md#2026-06-28-scene-and-audio-feature-extraction)
- [2026-06-28 Candidate generation](docs/status_archive/STATUS_2026-06.md#2026-06-28-candidate-generation)
- [2026-06-28 Rule scoring and candidate deduplication](docs/status_archive/STATUS_2026-06.md#2026-06-28-rule-scoring-and-candidate-deduplication)
- [2026-06-28 OpenAI Structured Outputs candidate scoring](docs/status_archive/STATUS_2026-06.md#2026-06-28-openai-structured-outputs-candidate-scoring)
- [2026-06-28 Quality gate and final candidate selection](docs/status_archive/STATUS_2026-06.md#2026-06-28-quality-gate-and-final-candidate-selection)
- [2026-06-28 ASS subtitle generation](docs/status_archive/STATUS_2026-06.md#2026-06-28-ass-subtitle-generation)
- [2026-06-28 Selected normal candidates to FFmpeg rendering](docs/status_archive/STATUS_2026-06.md#2026-06-28-selected-normal-candidates-to-ffmpeg-rendering)
- [2026-06-28 Automatic short rendering](docs/status_archive/STATUS_2026-06.md#2026-06-28-automatic-short-rendering)
- [2026-06-28 Real AutoClipper worker pipeline](docs/status_archive/STATUS_2026-06.md#2026-06-28-real-autoclipper-worker-pipeline)
- [2026-06-28 App hardening](docs/status_archive/STATUS_2026-06.md#2026-06-28-app-hardening)
- [2026-06-28 CI and Codex operation rules](docs/status_archive/STATUS_2026-06.md#2026-06-28-ci-and-codex-operation-rules)
- [2026-06-28 GitHub initial repository setup](docs/status_archive/STATUS_2026-06.md#2026-06-28-github-initial-repository-setup)
- [2026-06-28 CI ruff F401 fix](docs/status_archive/STATUS_2026-06.md#2026-06-28-ci-ruff-f401-fix)
- [2026-06-28 Docker Desktop install and compose verification](docs/status_archive/STATUS_2026-06.md#2026-06-28-docker-desktop-install-and-compose-verification)
- [2026-06-28 Task 17 Runtime verification and real video E2E hardening](docs/status_archive/STATUS_2026-06.md#2026-06-28-task-17-runtime-verification-and-real-video-e2e-hardening)
- [2026-06-28 Task 18 Real sample video E2E validation](docs/status_archive/STATUS_2026-06.md#2026-06-28-task-18-real-sample-video-e2e-validation)
- [2026-06-28 Task 19 Real spoken-video E2E without fixture transcript](docs/status_archive/STATUS_2026-06.md#2026-06-28-task-19-real-spoken-video-e2e-without-fixture-transcript)
- [2026-06-28 Task 20 Add early failure for silent or unusable audio](docs/status_archive/STATUS_2026-06.md#2026-06-28-task-20-add-early-failure-for-silent-or-unusable-audio)
- [2026-06-28 Task 21 Add generation diagnostic summaries](docs/status_archive/STATUS_2026-06.md#2026-06-28-task-21-add-generation-diagnostic-summaries)
- [2026-06-28 Task 22 Make normal clip duration settings configurable from UI/API](docs/status_archive/STATUS_2026-06.md#2026-06-28-task-22-make-normal-clip-duration-settings-configurable-from-uiapi)
- [2026-06-29 Task 23 Separate Hard Gate and Soft Score Selection](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-23-separate-hard-gate-and-soft-score-selection)
- [2026-06-29 Task 24 10-minute real video E2E validation](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-24-10-minute-real-video-e2e-validation)
- [2026-06-29 Task 25 OpenAI Structured Outputs scoring real API validation](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-25-openai-structured-outputs-scoring-real-api-validation)
- [2026-06-29 OpenAI scoring default model correction](docs/status_archive/STATUS_2026-06.md#2026-06-29-openai-scoring-default-model-correction)
- [2026-06-29 Task 26 30-minute real video E2E validation](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-26-30-minute-real-video-e2e-validation)
- [2026-06-29 Task 27 Improve selection count fulfillment and overlap diversity](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-27-improve-selection-count-fulfillment-and-overlap-diversity)
- [2026-06-29 Task 28: 30-minute high_quality limited OpenAI scoring E2E](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-28-30-minute-high_quality-limited-openai-scoring-e2e)
- [2026-06-29 Task 29: Ensure OpenAI scoring affects final selection](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-29-ensure-openai-scoring-affects-final-selection)
- [2026-06-29 Task 30: Add low_cost vs high_quality comparison report](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-30-add-low_cost-vs-high_quality-comparison-report)
- [2026-06-29 Task 31: Bounded streaming candidate generation for long videos](docs/status_archive/STATUS_2026-06.md#2026-06-29-task-31-bounded-streaming-candidate-generation-for-long-videos)
- [2026-06-30 Task 32: 58-minute full render E2E validation](docs/status_archive/STATUS_2026-06.md#2026-06-30-task-32-58-minute-full-render-e2e-validation)
- [2026-06-30 Task 33: Output quality audit and review report](docs/status_archive/STATUS_2026-06.md#2026-06-30-task-33-output-quality-audit-and-review-report)
- [2026-06-30 Task 35: Improve subtitle readability and reduce subtitle density warnings](docs/status_archive/STATUS_2026-06.md#2026-06-30-task-35-improve-subtitle-readability-and-reduce-subtitle-density-warnings)
- [2026-06-30 Task 35b: Validate subtitle burn-in after readability improvements](docs/status_archive/STATUS_2026-06.md#2026-06-30-task-35b-validate-subtitle-burn-in-after-readability-improvements)

</details>

### [2026-07（74件）](docs/status_archive/STATUS_2026-07.md)

<details>
<summary>見出し一覧（74件）</summary>

- [2026-07-01 Task 35c: Validate overlay title burn-in for high_quality shorts](docs/status_archive/STATUS_2026-07.md#2026-07-01-task-35c-validate-overlay-title-burn-in-for-high_quality-shorts)
- [2026-07-01 Task 34: Fix title fallback and propagation](docs/status_archive/STATUS_2026-07.md#2026-07-01-task-34-fix-title-fallback-and-propagation)
- [2026-07-01 Task 36a: Move subtitle sidecar files away from rendered MP4 files](docs/status_archive/STATUS_2026-07.md#2026-07-01-task-36a-move-subtitle-sidecar-files-away-from-rendered-mp4-files)
- [2026-07-02 Task 36: Improve abrupt start and end boundaries](docs/status_archive/STATUS_2026-07.md#2026-07-02-task-36-improve-abrupt-start-and-end-boundaries)
- [2026-07-02 Task 37: Clarify short overlay title policy and audit semantics](docs/status_archive/STATUS_2026-07.md#2026-07-02-task-37-clarify-short-overlay-title-policy-and-audit-semantics)
- [2026-07-02 Task 38: Display clip metadata and audit warnings in results UI](docs/status_archive/STATUS_2026-07.md#2026-07-02-task-38-display-clip-metadata-and-audit-warnings-in-results-ui)
- [2026-07-03 Task 39 v1 release smoke checklist](docs/status_archive/STATUS_2026-07.md#2026-07-03-task-39-v1-release-smoke-checklist)
- [2026-07-04 Task 40 v1 release smoke execution](docs/status_archive/STATUS_2026-07.md#2026-07-04-task-40-v1-release-smoke-execution)
- [2026-07-04 v1 implementation status confirmation](docs/status_archive/STATUS_2026-07.md#2026-07-04-v1-implementation-status-confirmation)
- [2026-07-04 high_quality OpenAI smoke execution](docs/status_archive/STATUS_2026-07.md#2026-07-04-high_quality-openai-smoke-execution)
- [2026-07-04 Task 41 short composition improvement](docs/status_archive/STATUS_2026-07.md#2026-07-04-task-41-short-composition-improvement)
- [2026-07-04 Task 42 subtitle mistranscription post-processing](docs/status_archive/STATUS_2026-07.md#2026-07-04-task-42-subtitle-mistranscription-post-processing)
- [2026-07-05 Task 43 no-face short composition fallback improvement](docs/status_archive/STATUS_2026-07.md#2026-07-05-task-43-no-face-short-composition-fallback-improvement)
- [2026-07-05 Task 44 subject-aware short composition](docs/status_archive/STATUS_2026-07.md#2026-07-05-task-44-subject-aware-short-composition)
- [2026-07-05 Task 45 person-aware short composition](docs/status_archive/STATUS_2026-07.md#2026-07-05-task-45-person-aware-short-composition)
- [2026-07-05 Task 46 dialogue-aware short composition](docs/status_archive/STATUS_2026-07.md#2026-07-05-task-46-dialogue-aware-short-composition)
- [2026-07-07 Task 47-75 local sample editing triage](docs/status_archive/STATUS_2026-07.md#2026-07-07-task-47-75-local-sample-editing-triage)
- [2026-07-07 Task 48 configurable subtitle style](docs/status_archive/STATUS_2026-07.md#2026-07-07-task-48-configurable-subtitle-style)
- [2026-07-07 Task 49 subtitle style UI](docs/status_archive/STATUS_2026-07.md#2026-07-07-task-49-subtitle-style-ui)
- [2026-07-07 Task 49b duration input validation fix](docs/status_archive/STATUS_2026-07.md#2026-07-07-task-49b-duration-input-validation-fix)
- [2026-07-07 Task 50 breath-cut deliverable script triage](docs/status_archive/STATUS_2026-07.md#2026-07-07-task-50-breath-cut-deliverable-script-triage)
- [2026-07-07 Task 51 insert-image deliverable script triage](docs/status_archive/STATUS_2026-07.md#2026-07-07-task-51-insert-image-deliverable-script-triage)
- [2026-07-08 Task 52 deliverable helper actual render validation](docs/status_archive/STATUS_2026-07.md#2026-07-08-task-52-deliverable-helper-actual-render-validation)
- [2026-07-09 Task 53 transcript work triage](docs/status_archive/STATUS_2026-07.md#2026-07-09-task-53-transcript-work-triage)
- [2026-07-10 Task 54 normal clip quality warning improvements](docs/status_archive/STATUS_2026-07.md#2026-07-10-task-54-normal-clip-quality-warning-improvements)
- [2026-07-10 Task 55 normal clip warning reduction](docs/status_archive/STATUS_2026-07.md#2026-07-10-task-55-normal-clip-warning-reduction)
- [2026-07-10 Task 56 representative normal warning regeneration check](docs/status_archive/STATUS_2026-07.md#2026-07-10-task-56-representative-normal-warning-regeneration-check)
- [2026-07-10 Task 58 subtitle font selector](docs/status_archive/STATUS_2026-07.md#2026-07-10-task-58-subtitle-font-selector)
- [2026-07-10 Task 59 transcription accuracy benchmark](docs/status_archive/STATUS_2026-07.md#2026-07-10-task-59-transcription-accuracy-benchmark)
- [2026-07-11 Task 60 OpenAI subtitle correction](docs/status_archive/STATUS_2026-07.md#2026-07-11-task-60-openai-subtitle-correction)
- [2026-07-11 Task 61 subtitle correction progress reporting](docs/status_archive/STATUS_2026-07.md#2026-07-11-task-61-subtitle-correction-progress-reporting)
- [2026-07-12 Task 62 local transcript suspicion filter](docs/status_archive/STATUS_2026-07.md#2026-07-12-task-62-local-transcript-suspicion-filter)
- [2026-07-16 Task 62 final 58-minute API replay retry](docs/status_archive/STATUS_2026-07.md#2026-07-16-task-62-final-58-minute-api-replay-retry)
- [2026-07-16 Task 62 excluded-change classification](docs/status_archive/STATUS_2026-07.md#2026-07-16-task-62-excluded-change-classification)
- [2026-07-16 Task 62 P2 targeted rescue signals](docs/status_archive/STATUS_2026-07.md#2026-07-16-task-62-p2-targeted-rescue-signals)
- [2026-07-17 Task 62 P2 OpenAI API connectivity probe](docs/status_archive/STATUS_2026-07.md#2026-07-17-task-62-p2-openai-api-connectivity-probe)
- [2026-07-17 Task 62 P2 final real-API validation](docs/status_archive/STATUS_2026-07.md#2026-07-17-task-62-p2-final-real-api-validation)
- [2026-07-18 Task 63 Windows launcher MVP refresh](docs/status_archive/STATUS_2026-07.md#2026-07-18-task-63-windows-launcher-mvp-refresh)
- [2026-07-18 Task 64 subtitle correction model / reasoning benchmark](docs/status_archive/STATUS_2026-07.md#2026-07-18-task-64-subtitle-correction-model--reasoning-benchmark)
- [2026-07-18 Task 65 default vs none long-form quality audit preparation](docs/status_archive/STATUS_2026-07.md#2026-07-18-task-65-default-vs-none-long-form-quality-audit-preparation)
- [2026-07-19 Task 67 GPU transcription benchmark](docs/status_archive/STATUS_2026-07.md#2026-07-19-task-67-gpu-transcription-benchmark)
- [2026-07-20 Task 66 compact subtitle response schema rejection](docs/status_archive/STATUS_2026-07.md#2026-07-20-task-66-compact-subtitle-response-schema-rejection)
- [2026-07-20 Task 68 local subtitle correction model benchmark](docs/status_archive/STATUS_2026-07.md#2026-07-20-task-68-local-subtitle-correction-model-benchmark)
- [2026-07-21 Task 69 launcher GPU recommended profile](docs/status_archive/STATUS_2026-07.md#2026-07-21-task-69-launcher-gpu-recommended-profile)
- [2026-07-23 Task 70 Windows distribution acceptance](docs/status_archive/STATUS_2026-07.md#2026-07-23-task-70-windows-distribution-acceptance)
- [2026-07-23 Task 71 large-video upload limit](docs/status_archive/STATUS_2026-07.md#2026-07-23-task-71-large-video-upload-limit)
- [2026-07-23 Task 72 upload feedback and subtitle preview](docs/status_archive/STATUS_2026-07.md#2026-07-23-task-72-upload-feedback-and-subtitle-preview)
- [2026-07-23 Task 73 subtitle review workflow](docs/status_archive/STATUS_2026-07.md#2026-07-23-task-73-subtitle-review-workflow)
- [2026-07-23 Task 74 Source Han Sans JP Heavy font](docs/status_archive/STATUS_2026-07.md#2026-07-23-task-74-source-han-sans-jp-heavy-font)
- [2026-07-23 Task 75 output selection and per-type subtitle styles](docs/status_archive/STATUS_2026-07.md#2026-07-23-task-75-output-selection-and-per-type-subtitle-styles)
- [2026-07-23 Task 76 clip-based subtitle review workspace](docs/status_archive/STATUS_2026-07.md#2026-07-23-task-76-clip-based-subtitle-review-workspace)
- [2026-07-23 Task 77 guided clip selection](docs/status_archive/STATUS_2026-07.md#2026-07-23-task-77-guided-clip-selection)
- [2026-07-24 Task 78 subtitle review preview proxies](docs/status_archive/STATUS_2026-07.md#2026-07-24-task-78-subtitle-review-preview-proxies)
- [2026-07-24 Task 79 manual clip time ranges](docs/status_archive/STATUS_2026-07.md#2026-07-24-task-79-manual-clip-time-ranges)
- [2026-07-24 Task 80 clip plan review stage](docs/status_archive/STATUS_2026-07.md#2026-07-24-task-80-clip-plan-review-stage)
- [2026-07-25 Task 81 subtitle style presets](docs/status_archive/STATUS_2026-07.md#2026-07-25-task-81-subtitle-style-presets)
- [2026-07-25 Task 82 clip plan boundary adjustment](docs/status_archive/STATUS_2026-07.md#2026-07-25-task-82-clip-plan-boundary-adjustment)
- [2026-07-26 Task 82 範囲調整欄の表示位置修正](docs/status_archive/STATUS_2026-07.md#2026-07-26-task-82-範囲調整欄の表示位置修正)
- [2026-07-26 Task 82 入力範囲の文字起こし同期](docs/status_archive/STATUS_2026-07.md#2026-07-26-task-82-入力範囲の文字起こし同期)
- [2026-07-26 Task 82 予定確認画面の文字起こし配置](docs/status_archive/STATUS_2026-07.md#2026-07-26-task-82-予定確認画面の文字起こし配置)
- [2026-07-26 Task 83 clip別タイトル・冒頭フック編集](docs/status_archive/STATUS_2026-07.md#2026-07-26-task-83-clip別タイトル冒頭フック編集)
- [2026-07-26 Task 84 完成jobの再編集・再レンダリング](docs/status_archive/STATUS_2026-07.md#2026-07-26-task-84-完成jobの再編集再レンダリング)
- [2026-07-27 Task 85 完成MP4の再アップロード再編集](docs/status_archive/STATUS_2026-07.md#2026-07-27-task-85-完成mp4の再アップロード再編集)
- [2026-07-28 Task 86 clip別タイトル・フック・字幕スタイル](docs/status_archive/STATUS_2026-07.md#2026-07-28-task-86-clip別タイトルフック字幕スタイル)
- [2026-07-28 Task 86 推奨字幕フォント分類](docs/status_archive/STATUS_2026-07.md#2026-07-28-task-86-推奨字幕フォント分類)
- [2026-07-28 Task 86 文字位置プリセット](docs/status_archive/STATUS_2026-07.md#2026-07-28-task-86-文字位置プリセット)
- [2026-07-28 Task 87 ショート冒頭への見せ場複製](docs/status_archive/STATUS_2026-07.md#2026-07-28-task-87-ショート冒頭への見せ場複製)
- [2026-07-28 Task 88 字幕スタイル設定の横長レイアウト化](docs/status_archive/STATUS_2026-07.md#2026-07-28-task-88-字幕スタイル設定の横長レイアウト化)
- [2026-07-28 Task 89 破損動画の事前検出とエラー表示改善](docs/status_archive/STATUS_2026-07.md#2026-07-28-task-89-破損動画の事前検出とエラー表示改善)
- [2026-07-28 Task 90 文字起こし品質検出とGPU自動再試行](docs/status_archive/STATUS_2026-07.md#2026-07-28-task-90-文字起こし品質検出とgpu自動再試行)
- [2026-07-29 Task 91 再編集画面の文字スタイル操作改善](docs/status_archive/STATUS_2026-07.md#2026-07-29-task-91-再編集画面の文字スタイル操作改善)
- [2026-07-29 Task 92 小型文字スタイルプレビューの縮尺修正](docs/status_archive/STATUS_2026-07.md#2026-07-29-task-92-小型文字スタイルプレビューの縮尺修正)
- [2026-07-29 Task 93 字幕確認ヘッダーの省スペース化](docs/status_archive/STATUS_2026-07.md#2026-07-29-task-93-字幕確認ヘッダーの省スペース化)
- [2026-07-29 Task 95 字幕確認画面の全幅領域削減](docs/status_archive/STATUS_2026-07.md#2026-07-29-task-95-字幕確認画面の全幅領域削減)

</details>

### [2026-08（59件）](docs/status_archive/STATUS_2026-08.md)

<details>
<summary>見出し一覧（59件）</summary>

- [2026-08-02 Task 96 YouTube人気区間sidecar連携](docs/status_archive/STATUS_2026-08.md#2026-08-02-task-96-youtube人気区間sidecar連携)
- [2026-08-03 Task 97 GPU workerのCUDAライブラリ欠落修正](docs/status_archive/STATUS_2026-08.md#2026-08-03-task-97-gpu-workerのcudaライブラリ欠落修正)
- [2026-08-03 Task 98 切り抜き予定画面の動画優先配置](docs/status_archive/STATUS_2026-08.md#2026-08-03-task-98-切り抜き予定画面の動画優先配置)
- [2026-08-03 Task 99 切り抜き予定画面の全幅化](docs/status_archive/STATUS_2026-08.md#2026-08-03-task-99-切り抜き予定画面の全幅化)
- [2026-08-03 Task 100 切り抜き予定画面の一画面4列配置](docs/status_archive/STATUS_2026-08.md#2026-08-03-task-100-切り抜き予定画面の一画面4列配置)
- [2026-08-04 Task 101 デスクトップ一括起動](docs/status_archive/STATUS_2026-08.md#2026-08-04-task-101-デスクトップ一括起動)
- [2026-08-04 Task 102 TOP画面の高密度ワークスペース化](docs/status_archive/STATUS_2026-08.md#2026-08-04-task-102-top画面の高密度ワークスペース化)
- [2026-08-04 Task 103 TOP画面の情報整理](docs/status_archive/STATUS_2026-08.md#2026-08-04-task-103-top画面の情報整理)
- [2026-08-04 Task 104 切り抜き予定画面の重複整理と文字起こし誤認識補正](docs/status_archive/STATUS_2026-08.md#2026-08-04-task-104-切り抜き予定画面の重複整理と文字起こし誤認識補正)
- [2026-08-04 Task 105 切り抜き調整パネルの縦幅圧縮](docs/status_archive/STATUS_2026-08.md#2026-08-04-task-105-切り抜き調整パネルの縦幅圧縮)
- [2026-08-05 Task 106 JSON区間モード](docs/status_archive/STATUS_2026-08.md#2026-08-05-task-106-json区間モード)
- [2026-08-06 Task 107 文字起こし言語の日本語固定](docs/status_archive/STATUS_2026-08.md#2026-08-06-task-107-文字起こし言語の日本語固定)
- [2026-08-10 Task 108 ショート上下帯のON/OFF](docs/status_archive/STATUS_2026-08.md#2026-08-10-task-108-ショート上下帯のonoff)
- [2026-08-10 Task 109 上部柄帯OFF時のタイトル保持](docs/status_archive/STATUS_2026-08.md#2026-08-10-task-109-上部柄帯off時のタイトル保持)
- [2026-08-11 Task 110 再選定時のJSON区間モード切替](docs/status_archive/STATUS_2026-08.md#2026-08-11-task-110-再選定時のjson区間モード切替)
- [2026-08-17 Task 111 長尺文字起こし自動復旧と1クリック再処理](docs/status_archive/STATUS_2026-08.md#2026-08-17-task-111-長尺文字起こし自動復旧と1クリック再処理)
- [2026-08-17 Task 112 完成表示一致プレビューと通常・ショート編集分離](docs/status_archive/STATUS_2026-08.md#2026-08-17-task-112-完成表示一致プレビューと通常ショート編集分離)
- [2026-08-17 Task 113 Chrome低高さ表示のプレイヤー操作列修正](docs/status_archive/STATUS_2026-08.md#2026-08-17-task-113-chrome低高さ表示のプレイヤー操作列修正)
- [2026-08-17 Task 114 字幕スタイルの即時プレビュー復旧](docs/status_archive/STATUS_2026-08.md#2026-08-17-task-114-字幕スタイルの即時プレビュー復旧)
- [2026-08-18 Task 115 メインプレイヤーへの即時文字編集統合](docs/status_archive/STATUS_2026-08.md#2026-08-18-task-115-メインプレイヤーへの即時文字編集統合)
- [2026-08-18 Task 116 即時確認後の一括OK保存](docs/status_archive/STATUS_2026-08.md#2026-08-18-task-116-即時確認後の一括ok保存)
- [2026-08-22 Task 117 即時文字プレビューのlibass寸法補正](docs/status_archive/STATUS_2026-08.md#2026-08-22-task-117-即時文字プレビューのlibass寸法補正)
- [2026-08-23 Task 118 通常切り抜きのタイトル・冒頭フック編集](docs/status_archive/STATUS_2026-08.md#2026-08-23-task-118-通常切り抜きのタイトル冒頭フック編集)
- [2026-08-24 Task 119 通常切り抜きの動画内タイトル編集](docs/status_archive/STATUS_2026-08.md#2026-08-24-task-119-通常切り抜きの動画内タイトル編集)
- [2026-08-24 Task 120 通常切り抜き用YouTubeサムネ2枚](docs/status_archive/STATUS_2026-08.md#2026-08-24-task-120-通常切り抜き用youtubeサムネ2枚)
- [2026-08-24 Task 121 normal_01の縦型ショート切り出し](docs/status_archive/STATUS_2026-08.md#2026-08-24-task-121-normal_01の縦型ショート切り出し)
- [2026-08-25 Task 122 元動画から手動作成](docs/status_archive/STATUS_2026-08.md#2026-08-25-task-122-元動画から手動作成)
- [2026-08-25 Task 123 派生ショート専用実装の撤回](docs/status_archive/STATUS_2026-08.md#2026-08-25-task-123-派生ショート専用実装の撤回)
- [2026-08-25 Task 124 字幕確認中のAIタイトル・フック選定](docs/status_archive/STATUS_2026-08.md#2026-08-25-task-124-字幕確認中のaiタイトルフック選定)
- [2026-08-27 Task 125 手動ショートの画角変更と自動人物優先](docs/status_archive/STATUS_2026-08.md#2026-08-27-task-125-手動ショートの画角変更と自動人物優先)
- [2026-08-27 Task 126 完成動画の1本限定再編集・通常からショートへの変換](docs/status_archive/STATUS_2026-08.md#2026-08-27-task-126-完成動画の1本限定再編集通常からショートへの変換)
- [2026-08-27 Task 127 旧再編集Jobの1本分離互換](docs/status_archive/STATUS_2026-08.md#2026-08-27-task-127-旧再編集jobの1本分離互換)
- [2026-08-27 Task 128 ショート帯の安全領域とclip別画角調整](docs/status_archive/STATUS_2026-08.md#2026-08-27-task-128-ショート帯の安全領域とclip別画角調整)
- [2026-08-27 Task 129 字幕編集previewの重なり解消・タイトル／フック手動2行](docs/status_archive/STATUS_2026-08.md#2026-08-27-task-129-字幕編集previewの重なり解消タイトルフック手動2行)
- [2026-08-28 storage容量整理](docs/status_archive/STATUS_2026-08.md#2026-08-28-storage容量整理)
- [2026-08-28 完了済みJobのsource-only整理](docs/status_archive/STATUS_2026-08.md#2026-08-28-完了済みjobのsource-only整理)
- [2026-08-28 完成済みID146 project退避](docs/status_archive/STATUS_2026-08.md#2026-08-28-完成済みid146-project退避)
- [2026-08-28 Git履歴MP4除去](docs/status_archive/STATUS_2026-08.md#2026-08-28-git履歴mp4除去)
- [2026-08-28 新規作業前source-only全整理](docs/status_archive/STATUS_2026-08.md#2026-08-28-新規作業前source-only全整理)
- [2026-08-28 AutoClipper保存ライフサイクル改善](docs/status_archive/STATUS_2026-08.md#2026-08-28-autoclipper保存ライフサイクル改善)
- [2026-08-28 Docker Desktop更新後の再確認](docs/status_archive/STATUS_2026-08.md#2026-08-28-docker-desktop更新後の再確認)
- [2026-08-28 loopback容量表示・archive filename修復](docs/status_archive/STATUS_2026-08.md#2026-08-28-loopback容量表示archive-filename修復)
- [2026-08-28 Windows LauncherのGPU起動待機短縮](docs/status_archive/STATUS_2026-08.md#2026-08-28-windows-launcherのgpu起動待機短縮)
- [2026-08-29 Codex初期clip選定をアップロード工程へ統合](docs/status_archive/STATUS_2026-08.md#2026-08-29-codex初期clip選定をアップロード工程へ統合)
- [2026-08-29 ショート候補の重複防止と自動補充](docs/status_archive/STATUS_2026-08.md#2026-08-29-ショート候補の重複防止と自動補充)
- [2026-08-29 自動化モード契約と判断manifest（Phase 1）](docs/status_archive/STATUS_2026-08.md#2026-08-29-自動化モード契約と判断manifestphase-1)
- [2026-08-29 Guarded品質ゲート（Phase 2）](docs/status_archive/STATUS_2026-08.md#2026-08-29-guarded品質ゲートphase-2)
- [2026-08-29 内容確認証拠と再レンダー排他（Phase 3）](docs/status_archive/STATUS_2026-08.md#2026-08-29-内容確認証拠と再レンダー排他phase-3)
- [2026-08-29 投稿用タイトル群・YouTube説明欄の自動生成](docs/status_archive/STATUS_2026-08.md#2026-08-29-投稿用タイトル群youtube説明欄の自動生成)
- [2026-08-29 frontend依存脆弱性の解消](docs/status_archive/STATUS_2026-08.md#2026-08-29-frontend依存脆弱性の解消)
- [2026-08-30 完全自動化 Phase 4 と68分実動画受入](docs/status_archive/STATUS_2026-08.md#2026-08-30-完全自動化-phase-4-と68分実動画受入)
- [2026-08-30 YouTube説明欄テンプレートと投稿タグ](docs/status_archive/STATUS_2026-08.md#2026-08-30-youtube説明欄テンプレートと投稿タグ)
- [2026-08-31 `normal_01` YouTubeサムネイル作成](docs/status_archive/STATUS_2026-08.md#2026-08-31-normal_01-youtubeサムネイル作成)
- [2026-08-31 `normal_02` YouTubeサムネイル作成](docs/status_archive/STATUS_2026-08.md#2026-08-31-normal_02-youtubeサムネイル作成)
- [2026-08-31 `normal_02` サムネイル文字訴求強化](docs/status_archive/STATUS_2026-08.md#2026-08-31-normal_02-サムネイル文字訴求強化)
- [2026-08-31 `normal_02` サムネイル斜め文字化](docs/status_archive/STATUS_2026-08.md#2026-08-31-normal_02-サムネイル斜め文字化)
- [2026-08-31 `normal_01` サムネイル斜め文字強化](docs/status_archive/STATUS_2026-08.md#2026-08-31-normal_01-サムネイル斜め文字強化)
- [2026-08-31 通常切り抜き公開タイトルの固定末尾](docs/status_archive/STATUS_2026-08.md#2026-08-31-通常切り抜き公開タイトルの固定末尾)
- [2026-08-31 YouTube説明欄の内容要約・チャプター強化](docs/status_archive/STATUS_2026-08.md#2026-08-31-youtube説明欄の内容要約チャプター強化)

</details>

### [2026-09（134件）](docs/status_archive/STATUS_2026-09.md)

<details>
<summary>見出し一覧（134件）</summary>

- [2026-09-01 切り抜き境界の時分秒入力と双方向調整](docs/status_archive/STATUS_2026-09.md#2026-09-01-切り抜き境界の時分秒入力と双方向調整)
- [2026-09-01 予定確認でショート1本を通常切り抜きへ変更](docs/status_archive/STATUS_2026-09.md#2026-09-01-予定確認でショート1本を通常切り抜きへ変更)
- [2026-09-01 動画内タイトルの空欄保存・非表示対応](docs/status_archive/STATUS_2026-09.md#2026-09-01-動画内タイトルの空欄保存非表示対応)
- [2026-09-01 動画内タイトル空欄時の保存ボタン修正](docs/status_archive/STATUS_2026-09.md#2026-09-01-動画内タイトル空欄時の保存ボタン修正)
- [2026-09-01 再編集後Resultsから元の完成動画一覧へ戻る導線](docs/status_archive/STATUS_2026-09.md#2026-09-01-再編集後resultsから元の完成動画一覧へ戻る導線)
- [2026-09-01 Chrome ERR_BLOCKED_BY_CLIENTの同一オリジンダウンロード対応](docs/status_archive/STATUS_2026-09.md#2026-09-01-chrome-err_blocked_by_clientの同一オリジンダウンロード対応)
- [2026-09-01 高校美術・美学切り抜き用YouTubeサムネイル](docs/status_archive/STATUS_2026-09.md#2026-09-01-高校美術美学切り抜き用youtubeサムネイル)
- [2026-09-01 高校美術サムネイルv2・文字階層と背景修正](docs/status_archive/STATUS_2026-09.md#2026-09-01-高校美術サムネイルv2文字階層と背景修正)
- [2026-09-01 高校美術サムネイルv3・参照画像に合わせた文字バランス修正](docs/status_archive/STATUS_2026-09.md#2026-09-01-高校美術サムネイルv3参照画像に合わせた文字バランス修正)
- [2026-09-01 高校美術サムネイルv4・行間圧縮と主見出し強調](docs/status_archive/STATUS_2026-09.md#2026-09-01-高校美術サムネイルv4行間圧縮と主見出し強調)
- [2026-09-01 高校美術サムネイルv5・文字重なり解消](docs/status_archive/STATUS_2026-09.md#2026-09-01-高校美術サムネイルv5文字重なり解消)
- [2026-09-01 高校美術サムネイルv6・主見出し斜め配置](docs/status_archive/STATUS_2026-09.md#2026-09-01-高校美術サムネイルv6主見出し斜め配置)
- [2026-09-01 分かりやすく話す2つのこと・YouTubeサムネイル](docs/status_archive/STATUS_2026-09.md#2026-09-01-分かりやすく話す2つのことyoutubeサムネイル)
- [2026-09-01 らでんだけ見てて・YouTubeサムネイル](docs/status_archive/STATUS_2026-09.md#2026-09-01-らでんだけ見ててyoutubeサムネイル)
- [2026-09-02 完成時サムネイル自動生成](docs/status_archive/STATUS_2026-09.md#2026-09-02-完成時サムネイル自動生成)
- [2026-09-03 JSONを人気度参考へ限定した内容選定](docs/status_archive/STATUS_2026-09.md#2026-09-03-jsonを人気度参考へ限定した内容選定)
- [2026-09-03 Codex選定失敗の可視化とBridge互換性復旧](docs/status_archive/STATUS_2026-09.md#2026-09-03-codex選定失敗の可視化とbridge互換性復旧)
- [2026-09-03 尺収束廃止・通常Short分離・長尺二段階Codex選定](docs/status_archive/STATUS_2026-09.md#2026-09-03-尺収束廃止通常short分離長尺二段階codex選定)
- [2026-09-03 通常サムネの実績テンプレ化と単体再生成](docs/status_archive/STATUS_2026-09.md#2026-09-03-通常サムネの実績テンプレ化と単体再生成)
- [2026-09-03 通常サムネの胴体誤検出修正・顔寄り選択](docs/status_archive/STATUS_2026-09.md#2026-09-03-通常サムネの胴体誤検出修正顔寄り選択)
- [2026-09-07 承認済み旧Jobの容量整理](docs/status_archive/STATUS_2026-09.md#2026-09-07-承認済み旧jobの容量整理)
- [2026-09-07 字幕1件ごとの書式・二重縁取り・ショート顔アップ](docs/status_archive/STATUS_2026-09.md#2026-09-07-字幕1件ごとの書式二重縁取りショート顔アップ)
- [2026-09-08 字幕個別書式のPUSH・再起動試行](docs/status_archive/STATUS_2026-09.md#2026-09-08-字幕個別書式のpush再起動試行)
- [2026-09-08 Docker実行用ソケット復旧・更新版起動](docs/status_archive/STATUS_2026-09.md#2026-09-08-docker実行用ソケット復旧更新版起動)
- [2026-09-10 Codex更新後の投稿案生成エラー対策](docs/status_archive/STATUS_2026-09.md#2026-09-10-codex更新後の投稿案生成エラー対策)
- [2026-09-11 保存時に投稿用セットが欠落する不具合](docs/status_archive/STATUS_2026-09.md#2026-09-11-保存時に投稿用セットが欠落する不具合)
- [2026-09-11 同じ元動画の再アップロード時に使用済み区間を除外](docs/status_archive/STATUS_2026-09.md#2026-09-11-同じ元動画の再アップロード時に使用済み区間を除外)
- [2026-09-12 アップロード設定の10枠保存・字幕/フック/タイトル書式](docs/status_archive/STATUS_2026-09.md#2026-09-12-アップロード設定の10枠保存字幕フックタイトル書式)
- [2026-09-12 外縁カラーを色欄へ移動](docs/status_archive/STATUS_2026-09.md#2026-09-12-外縁カラーを色欄へ移動)
- [2026-09-12 名前付きショート帯の保存と確認・長さ設定の横並び](docs/status_archive/STATUS_2026-09.md#2026-09-12-名前付きショート帯の保存と確認長さ設定の横並び)
- [2026-09-12 キャラ別の投稿情報・帯・タイトル末尾・サムネイル一括保存](docs/status_archive/STATUS_2026-09.md#2026-09-12-キャラ別の投稿情報帯タイトル末尾サムネイル一括保存)
- [2026-09-12 キャラ設定・アップロード設定と未送信修正のPUSH](docs/status_archive/STATUS_2026-09.md#2026-09-12-キャラ設定アップロード設定と未送信修正のpush)
- [2026-09-12 帯単独の呼び出し・保存UIを削除](docs/status_archive/STATUS_2026-09.md#2026-09-12-帯単独の呼び出し保存uiを削除)
- [2026-09-13 字幕修正画面で選択語句を一括修正](docs/status_archive/STATUS_2026-09.md#2026-09-13-字幕修正画面で選択語句を一括修正)
- [2026-09-13 文字起こしを既定で全角へ統一](docs/status_archive/STATUS_2026-09.md#2026-09-13-文字起こしを既定で全角へ統一)
- [2026-09-13 選定画面の文字起こしスクロールを維持](docs/status_archive/STATUS_2026-09.md#2026-09-13-選定画面の文字起こしスクロールを維持)
- [2026-09-13 動画種別の切替を選定画面へ集約](docs/status_archive/STATUS_2026-09.md#2026-09-13-動画種別の切替を選定画面へ集約)
- [2026-09-13 字幕確認の作業配置と区間編集](docs/status_archive/STATUS_2026-09.md#2026-09-13-字幕確認の作業配置と区間編集)
- [2026-09-13 通常サムネイルの３段書式設定](docs/status_archive/STATUS_2026-09.md#2026-09-13-通常サムネイルの３段書式設定)
- [2026-09-13 サムネ文言の生成・選択・手動編集を結果画面へ集約](docs/status_archive/STATUS_2026-09.md#2026-09-13-サムネ文言の生成選択手動編集を結果画面へ集約)
- [2026-09-13 サムネのプレビュー・文言・書式を横並びに変更](docs/status_archive/STATUS_2026-09.md#2026-09-13-サムネのプレビュー文言書式を横並びに変更)
- [2026-09-13 サムネ編集中の画像と画面全体を固定](docs/status_archive/STATUS_2026-09.md#2026-09-13-サムネ編集中の画像と画面全体を固定)
- [2026-09-13 サムネの文言・書式を保存前に自動プレビュー](docs/status_archive/STATUS_2026-09.md#2026-09-13-サムネの文言書式を保存前に自動プレビュー)
- [2026-09-13 サムネの手動サイズが自動縮小で変化しない問題を修正](docs/status_archive/STATUS_2026-09.md#2026-09-13-サムネの手動サイズが自動縮小で変化しない問題を修正)
- [2026-09-13 ショート画角を枠の直接操作と即時プレビューで調整](docs/status_archive/STATUS_2026-09.md#2026-09-13-ショート画角を枠の直接操作と即時プレビューで調整)
- [2026-09-13 編集画面修正のコミット準備](docs/status_archive/STATUS_2026-09.md#2026-09-13-編集画面修正のコミット準備)
- [2026-09-13 編集画面修正をPUSH](docs/status_archive/STATUS_2026-09.md#2026-09-13-編集画面修正をpush)
- [2026-09-14 main統合と日本語Windows導入手順](docs/status_archive/STATUS_2026-09.md#2026-09-14-main統合と日本語windows導入手順)
- [2026-09-15 画角・基本配置の試し表示で再生成待ちを減らす](docs/status_archive/STATUS_2026-09.md#2026-09-15-画角基本配置の試し表示で再生成待ちを減らす)
- [2026-09-15 画角調整に標準上下帯の目安を表示](docs/status_archive/STATUS_2026-09.md#2026-09-15-画角調整に標準上下帯の目安を表示)
- [2026-09-15 投稿案生成のhost bridge停止から復旧](docs/status_archive/STATUS_2026-09.md#2026-09-15-投稿案生成のhost-bridge停止から復旧)
- [2026-09-15 人気度JSONの空データを選択時に明示](docs/status_archive/STATUS_2026-09.md#2026-09-15-人気度jsonの空データを選択時に明示)
- [2026-09-15 編集再開したジョブでも帯画像を変更](docs/status_archive/STATUS_2026-09.md#2026-09-15-編集再開したジョブでも帯画像を変更)
- [2026-09-15 字幕確認でキャラ別一括設定を呼び出す](docs/status_archive/STATUS_2026-09.md#2026-09-15-字幕確認でキャラ別一括設定を呼び出す)
- [2026-09-15 ショート画角再生成の重複処理削減と編集映像拡大](docs/status_archive/STATUS_2026-09.md#2026-09-15-ショート画角再生成の重複処理削減と編集映像拡大)
- [2026-09-15 ショートのタイトル・フック欄のホイール停止を修正](docs/status_archive/STATUS_2026-09.md#2026-09-15-ショートのタイトルフック欄のホイール停止を修正)
- [2026-09-15 編集再開・画角プレビュー修正のPUSH準備](docs/status_archive/STATUS_2026-09.md#2026-09-15-編集再開画角プレビュー修正のpush準備)
- [2026-09-16 基本配置・画角の保存をクリップごとに分離](docs/status_archive/STATUS_2026-09.md#2026-09-16-基本配置画角の保存をクリップごとに分離)
- [2026-09-15 文字色テンプレートを10色へ拡張](docs/status_archive/STATUS_2026-09.md#2026-09-15-文字色テンプレートを10色へ拡張)
- [2026-09-15 内縁の色テンプレートの追加漏れを修正](docs/status_archive/STATUS_2026-09.md#2026-09-15-内縁の色テンプレートの追加漏れを修正)
- [2026-09-16 結果画面で説明欄とタグをまとめてコピー](docs/status_archive/STATUS_2026-09.md#2026-09-16-結果画面で説明欄とタグをまとめてコピー)
- [2026-09-16 説明欄ボタンへ一括コピーを統合](docs/status_archive/STATUS_2026-09.md#2026-09-16-説明欄ボタンへ一括コピーを統合)
- [2026-09-16 Codex初期選定の時刻丸めによる入力エラーを修正](docs/status_archive/STATUS_2026-09.md#2026-09-16-codex初期選定の時刻丸めによる入力エラーを修正)
- [2026-09-16 キャラ文字書式を含むプレビューの生成失敗を修正](docs/status_archive/STATUS_2026-09.md#2026-09-16-キャラ文字書式を含むプレビューの生成失敗を修正)
- [2026-09-16 色欄にユーザー保存パレットを追加](docs/status_archive/STATUS_2026-09.md#2026-09-16-色欄にユーザー保存パレットを追加)
- [2026-09-16 古い投稿案による字幕保存の拒否を修正](docs/status_archive/STATUS_2026-09.md#2026-09-16-古い投稿案による字幕保存の拒否を修正)
- [2026-09-17 再選定で提示済み区間を避ける設定を追加](docs/status_archive/STATUS_2026-09.md#2026-09-17-再選定で提示済み区間を避ける設定を追加)
- [2026-09-17 候補キープと残りだけ再選定](docs/status_archive/STATUS_2026-09.md#2026-09-17-候補キープと残りだけ再選定)
- [2026-09-17 指定5本・実候補4本で全キープすると不足1本を再選定できない問題](docs/status_archive/STATUS_2026-09.md#2026-09-17-指定5本実候補4本で全キープすると不足1本を再選定できない問題)
- [2026-09-17 ぶいすぽっ！許諾番号入力](docs/status_archive/STATUS_2026-09.md#2026-09-17-ぶいすぽっ許諾番号入力)
- [2026-09-17 キープ再選定で新候補が繰り返し0件になる原因修正](docs/status_archive/STATUS_2026-09.md#2026-09-17-キープ再選定で新候補が繰り返し0件になる原因修正)
- [2026-09-17 通常動画の字幕確認プレビュー拡大](docs/status_archive/STATUS_2026-09.md#2026-09-17-通常動画の字幕確認プレビュー拡大)
- [2026-09-17 字幕確認の上部clip切替・字幕欄縮小・黒余白除去](docs/status_archive/STATUS_2026-09.md#2026-09-17-字幕確認の上部clip切替字幕欄縮小黒余白除去)
- [2026-09-17 字幕確認の通常編集を4列へ再配置](docs/status_archive/STATUS_2026-09.md#2026-09-17-字幕確認の通常編集を4列へ再配置)
- [2026-09-17 通常字幕画面の書式設定を映像下へ配置](docs/status_archive/STATUS_2026-09.md#2026-09-17-通常字幕画面の書式設定を映像下へ配置)
- [2026-09-17 通常プレビュー左右の空白を黒帯表示](docs/status_archive/STATUS_2026-09.md#2026-09-17-通常プレビュー左右の空白を黒帯表示)
- [2026-09-17 PUSH前検証](docs/status_archive/STATUS_2026-09.md#2026-09-17-push前検証)
- [2026-09-17 通常動画の投稿案生成を復旧](docs/status_archive/STATUS_2026-09.md#2026-09-17-通常動画の投稿案生成を復旧)
- [2026-09-17 Codex連携の例外停止対策と診断記録](docs/status_archive/STATUS_2026-09.md#2026-09-17-codex連携の例外停止対策と診断記録)
- [2026-09-17 16:55 JST 連携の親プロセス寿命依存を修正](docs/status_archive/STATUS_2026-09.md#2026-09-17-1655-jst-連携の親プロセス寿命依存を修正)
- [2026-09-18 JST タイトル・フック生成プロンプトの試用](docs/status_archive/STATUS_2026-09.md#2026-09-18-jst-タイトルフック生成プロンプトの試用)
- [2026-09-18 JST サムネイル文言生成プロンプトの試用](docs/status_archive/STATUS_2026-09.md#2026-09-18-jst-サムネイル文言生成プロンプトの試用)
- [2026-09-21 JST Codex選定・生成をSol highに統一](docs/status_archive/STATUS_2026-09.md#2026-09-21-jst-codex選定生成をsol-highに統一)
- [2026-09-21 JST 画角保存時の動画再生成を停止](docs/status_archive/STATUS_2026-09.md#2026-09-21-jst-画角保存時の動画再生成を停止)
- [2026-09-21 JST URLによる文字起こし設定の意図しない低下を修正](docs/status_archive/STATUS_2026-09.md#2026-09-21-jst-urlによる文字起こし設定の意図しない低下を修正)
- [2026-09-21 18:28 JST 画角変更後の編集画面で動画を確認可能に修正](docs/status_archive/STATUS_2026-09.md#2026-09-21-1828-jst-画角変更後の編集画面で動画を確認可能に修正)
- [2026-09-21 20:07 JST 編集中のDocker停止を復旧](docs/status_archive/STATUS_2026-09.md#2026-09-21-2007-jst-編集中のdocker停止を復旧)
- [2026-09-21 AutoClipper × Clip Intelligence 構想 v0.1 既存仕様比較](docs/status_archive/STATUS_2026-09.md#2026-09-21-autoclipper--clip-intelligence-構想-v01-既存仕様比較)
- [2026-09-21 AutoClipper × Clip Intelligence 統合目標の解釈更新](docs/status_archive/STATUS_2026-09.md#2026-09-21-autoclipper--clip-intelligence-統合目標の解釈更新)
- [2026-09-23 AutoClipper × Clip Intelligence 統合構想 v1 大枠合意版を保存](docs/status_archive/STATUS_2026-09.md#2026-09-23-autoclipper--clip-intelligence-統合構想-v1-大枠合意版を保存)
- [2026-09-24 JST 編集後ショートの時間上限超過を保存可能に修正](docs/status_archive/STATUS_2026-09.md#2026-09-24-jst-編集後ショートの時間上限超過を保存可能に修正)
- [2026-09-24 JST カスタム帯付き再編集のレンダリング失敗を修正](docs/status_archive/STATUS_2026-09.md#2026-09-24-jst-カスタム帯付き再編集のレンダリング失敗を修正)
- [2026-09-25 JST 長すぎる文字起こし区間と字幕行の追加・削除を修正](docs/status_archive/STATUS_2026-09.md#2026-09-25-jst-長すぎる文字起こし区間と字幕行の追加削除を修正)
- [2026-09-25 JST 字幕分割・結合後のプレビュー待ちを短縮](docs/status_archive/STATUS_2026-09.md#2026-09-25-jst-字幕分割結合後のプレビュー待ちを短縮)
- [2026-09-25 JST 字幕分割後に保持プレビューが404になる不具合を修正](docs/status_archive/STATUS_2026-09.md#2026-09-25-jst-字幕分割後に保持プレビューが404になる不具合を修正)
- [2026-09-25 JST ショート用タイトル・フック生成基準を強化](docs/status_archive/STATUS_2026-09.md#2026-09-25-jst-ショート用タイトルフック生成基準を強化)
- [2026-09-25 JST 現行仕様と統合後の到達仕様を整理](docs/status_archive/STATUS_2026-09.md#2026-09-25-jst-現行仕様と統合後の到達仕様を整理)
- [2026-09-25 JST 未コミット変更の整理とmain統合前検証](docs/status_archive/STATUS_2026-09.md#2026-09-25-jst-未コミット変更の整理とmain統合前検証)
- [2026-09-25 JST 源暎フォント3書体を追加](docs/status_archive/STATUS_2026-09.md#2026-09-25-jst-源暎フォント3書体を追加)
- [2026-09-25 JST 851ゴチカクットとNikkyou Sansを追加](docs/status_archive/STATUS_2026-09.md#2026-09-25-jst-851ゴチカクットとnikkyou-sansを追加)
- [2026-09-26 JST 話題選定のブロックID混入による全件仮選定を修正](docs/status_archive/STATUS_2026-09.md#2026-09-26-jst-話題選定のブロックid混入による全件仮選定を修正)
- [2026-09-27 JST 宙科そぴあ用の通常サムネイルテンプレ](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-宙科そぴあ用の通常サムネイルテンプレ)
- [2026-09-27 JST 宙科サムネ背景を明るいロケット案へ変更](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-宙科サムネ背景を明るいロケット案へ変更)
- [2026-09-27 JST 完成動画ごとの通常サムネテンプレ切り替え](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-完成動画ごとの通常サムネテンプレ切り替え)
- [2026-09-27 JST Codexによる通常サムネの人物・場面選別](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-codexによる通常サムネの人物場面選別)
- [2026-09-27 JST 宙科サムネの人物が画角から切れる問題を修正](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-宙科サムネの人物が画角から切れる問題を修正)
- [2026-09-26 JST HyperFrames検討チェックリストを保存](docs/status_archive/STATUS_2026-09.md#2026-09-26-jst-hyperframes検討チェックリストを保存)
- [2026-09-27 JST タイトル案の再生成で同案が繰り返される問題を修正](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-タイトル案の再生成で同案が繰り返される問題を修正)
- [2026-09-27 JST 選定・本数・尺の確定事項を別文書に保存](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-選定本数尺の確定事項を別文書に保存)
- [2026-09-27 JST 通常サムネ新機能をローカル稼働環境へ反映](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-通常サムネ新機能をローカル稼働環境へ反映)
- [2026-09-27 JST サムネ人物画角修正のローカル稼働反映](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-サムネ人物画角修正のローカル稼働反映)
- [2026-09-27 JST 宙科サムネの人物検出と切り抜き配置を修正](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-宙科サムネの人物検出と切り抜き配置を修正)
- [2026-09-27 JST 通常サムネの人物が出る時刻を動画全体から探索](docs/status_archive/STATUS_2026-09.md#2026-09-27-jst-通常サムネの人物が出る時刻を動画全体から探索)
- [2026-09-28 JST 再生停止位置から字幕の欠落行を追加](docs/status_archive/STATUS_2026-09.md#2026-09-28-jst-再生停止位置から字幕の欠落行を追加)
- [2026-09-28 JST 字幕編集時のプレビュー更新による作業中断を軽減](docs/status_archive/STATUS_2026-09.md#2026-09-28-jst-字幕編集時のプレビュー更新による作業中断を軽減)
- [2026-09-28 JST 通常サムネの文字位置をフォント・サイズから独立](docs/status_archive/STATUS_2026-09.md#2026-09-28-jst-通常サムネの文字位置をフォントサイズから独立)
- [2026-09-28 JST 通常サムネの枠線整合と文字の直接配置](docs/status_archive/STATUS_2026-09.md#2026-09-28-jst-通常サムネの枠線整合と文字の直接配置)
- [2026-09-28 JST 字幕編集から尺調整へ戻る導線を追加](docs/status_archive/STATUS_2026-09.md#2026-09-28-jst-字幕編集から尺調整へ戻る導線を追加)
- [2026-09-28 JST 添付プレビュー動画の文字起こし](docs/status_archive/STATUS_2026-09.md#2026-09-28-jst-添付プレビュー動画の文字起こし)
- [2026-09-29 JST 未使用の字幕確認APIを整理（task-156）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-未使用の字幕確認apiを整理task-156)
- [2026-09-29 JST 未使用の全job字幕確認reopenを整理（task-157）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-未使用の全job字幕確認reopenを整理task-157)
- [2026-09-29 JST 保留中の記録と資料をmainへ整理（task-158）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-保留中の記録と資料をmainへ整理task-158)
- [2026-09-29 JST 旧reopen状態のテスト準備を共通化（task-159）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-旧reopen状態のテスト準備を共通化task-159)
- [2026-09-29 JST OpenAIキーの既定Compose受け渡しを停止（task-160）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-openaiキーの既定compose受け渡しを停止task-160)
- [2026-09-29 JST 未使用コードを整理（task-161）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-未使用コードを整理task-161)
- [2026-09-29 JST CIのPythonとfrontendテスト範囲を拡大（task-162）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-ciのpythonとfrontendテスト範囲を拡大task-162)
- [2026-09-29 JST JSON保存を共通の原子的書き込みへ変更（task-163）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-json保存を共通の原子的書き込みへ変更task-163)
- [2026-09-29 JST clip plan操作のjob状態を先に確保（task-164）](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-clip-plan操作のjob状態を先に確保task-164)
- [2026-09-29 JST 再選定の過去候補除外OFFと通常候補8〜10分の再生成](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-再選定の過去候補除外offと通常候補810分の再生成)
- [2026-09-29 JST 長尺再選定でほぼ同じ場面を再提示する問題](docs/status_archive/STATUS_2026-09.md#2026-09-29-jst-長尺再選定でほぼ同じ場面を再提示する問題)
- [2026-09-30 JST 添付ショート動画の全文文字起こし](docs/status_archive/STATUS_2026-09.md#2026-09-30-jst-添付ショート動画の全文文字起こし)
- [2026-09-30 JST 長尺再選定の過去提案重複防止を完成（task-165）](docs/status_archive/STATUS_2026-09.md#2026-09-30-jst-長尺再選定の過去提案重複防止を完成task-165)
- [2026-09-30 JST 有料Platform APIの呼び出し経路を削除（task-166）](docs/status_archive/STATUS_2026-09.md#2026-09-30-jst-有料platform-apiの呼び出し経路を削除task-166)
- [2026-09-30 JST 候補確認・再選定の処理を分割（task-167）](docs/status_archive/STATUS_2026-09.md#2026-09-30-jst-候補確認再選定の処理を分割task-167)

</details>

### [2026-10（89件）](docs/status_archive/STATUS_2026-10.md)

<details>
<summary>見出し一覧</summary>

- [2026-10-01 JST 切り抜きの尺ルールを統一（task-168）](docs/status_archive/STATUS_2026-10.md#2026-10-01-jst-切り抜きの尺ルールを統一task-168)
- [2026-10-01 JST 不採用理由の記録と再選定への反映（task-169）](docs/status_archive/STATUS_2026-10.md#2026-10-01-jst-不採用理由の記録と再選定への反映task-169)
- [2026-10-01 task-170 合計本数とAIによる形式配分](docs/status_archive/STATUS_2026-10.md#2026-10-01-task-170-合計本数とaiによる形式配分)
- [2026-10-01 JST PyAVの互換性を固定（task-171）](docs/status_archive/STATUS_2026-10.md#2026-10-01-jst-pyavの互換性を固定task-171)
- [2026-10-01 JST キャラごとの表情素材の登録・管理（task-172）](docs/status_archive/STATUS_2026-10.md#2026-10-01-jst-キャラごとの表情素材の登録管理task-172)
- [2026-10-01 JST 元動画全体からのキャラ素材候補収集（task-173）](docs/status_archive/STATUS_2026-10.md#2026-10-01-jst-元動画全体からのキャラ素材候補収集task-173)
- [2026-10-02 JST テスト起動時のDB・storage隔離（task-176）](docs/status_archive/STATUS_2026-10.md#2026-10-02-jst-テスト起動時のdbstorage隔離task-176)
- [2026-10-02 JST 表情素材を通常動画のサムネに適用（task-174）](docs/status_archive/STATUS_2026-10.md#2026-10-02-jst-表情素材を通常動画のサムネに適用task-174)
- [2026-10-02 JST 素材画像全体を人物枠に収める構図（task-177）](docs/status_archive/STATUS_2026-10.md#2026-10-02-jst-素材画像全体を人物枠に収める構図task-177)
- [2026-10-02 JST 動画の半身候補を優先し、表情素材を予備にする（task-178）](docs/status_archive/STATUS_2026-10.md#2026-10-02-jst-動画の半身候補を優先し表情素材を予備にするtask-178)
- [2026-10-02 JST task-178の稼働環境への反映（運用）](docs/status_archive/STATUS_2026-10.md#2026-10-02-jst-task-178の稼働環境への反映運用)
- [2026-10-02 JST backend依存のロック（task-179）](docs/status_archive/STATUS_2026-10.md#2026-10-02-jst-backend依存のロックtask-179)
- [2026-10-02 JST 完成後のプレビュー整理と管理コマンド（task-181）](docs/status_archive/STATUS_2026-10.md#2026-10-02-jst-完成後のプレビュー整理と管理コマンドtask-181)
- [2026-10-02 JST task-181の反映・dry-run・承認後の実削除（運用）](docs/status_archive/STATUS_2026-10.md#2026-10-02-jst-task-181の反映dry-run承認後の実削除運用)
- [2026-10-02 task-182: 投稿用タイトルでの保存・投稿セット・都度ZIP](docs/status_archive/STATUS_2026-10.md#2026-10-02-task-182-投稿用タイトルでの保存投稿セット都度zip)
- [2026-10-02 task-180: 主フォルダでのruffの誤検出を除外](docs/status_archive/STATUS_2026-10.md#2026-10-02-task-180-主フォルダでのruffの誤検出を除外)
- [2026-10-02 task-183 内容に応じた通常切り抜きの長尺](docs/status_archive/STATUS_2026-10.md#2026-10-02-task-183-内容に応じた通常切り抜きの長尺)
- [2026-10-02 運用: main b0f6402（task-183）の稼働環境への反映](docs/status_archive/STATUS_2026-10.md#2026-10-02-運用-main-b0f6402task-183の稼働環境への反映)
- [2026-10-03 task-184: サムネ文言に話の中心人物名を残す](docs/status_archive/STATUS_2026-10.md#2026-10-03-task-184-サムネ文言に話の中心人物名を残す)
- [2026-10-03 task-184 の稼働環境への反映（運用作業）](docs/status_archive/STATUS_2026-10.md#2026-10-03-task-184-の稼働環境への反映運用作業)
- [2026-10-03 task-185: 人物名をサムネの主見出しに入れる](docs/status_archive/STATUS_2026-10.md#2026-10-03-task-185-人物名をサムネの主見出しに入れる)
- [2026-10-03 task-185 の稼働環境への反映（運用作業）](docs/status_archive/STATUS_2026-10.md#2026-10-03-task-185-の稼働環境への反映運用作業)
- [2026-10-03 task-187: 字幕確認で音ありの空白区間を示す](docs/status_archive/STATUS_2026-10.md#2026-10-03-task-187-字幕確認で音ありの空白区間を示す)
- [2026-10-03 task-186: 同じ元動画で文字起こし5方式を比較](docs/status_archive/STATUS_2026-10.md#2026-10-03-task-186-同じ元動画で文字起こし5方式を比較)
- [2026-10-05 task-188: サムネ候補が見つかると保存に失敗する不具合を修正](docs/status_archive/STATUS_2026-10.md#2026-10-05-task-188-サムネ候補が見つかると保存に失敗する不具合を修正)
- [2026-10-05 task-189 文字起こしの音あり空白を1回補修](docs/status_archive/STATUS_2026-10.md#2026-10-05-task-189-文字起こしの音あり空白を1回補修)
- [2026-10-05 task-188 の稼働環境への反映（運用作業）](docs/status_archive/STATUS_2026-10.md#2026-10-05-task-188-の稼働環境への反映運用作業)
- [2026-10-05 task-189 の稼働環境への反映（運用作業）](docs/status_archive/STATUS_2026-10.md#2026-10-05-task-189-の稼働環境への反映運用作業)
- [2026-10-06 task-191 ショート冒頭評価とキャラ別認知度](docs/status_archive/STATUS_2026-10.md#2026-10-06-task-191-ショート冒頭評価とキャラ別認知度)
- [2026-10-06 task-192 知名度低モードのタイトル・フック](docs/status_archive/STATUS_2026-10.md#2026-10-06-task-192-知名度低モードのタイトルフック)
- [2026-10-06 task-191・192 稼働環境への反映（運用）](docs/status_archive/STATUS_2026-10.md#2026-10-06-task-191192-稼働環境への反映運用)
- [2026-10-07 task-193 RQで失敗した仕事と孤立ジョブの状態同期](docs/status_archive/STATUS_2026-10.md#2026-10-07-task-193-rqで失敗した仕事と孤立ジョブの状態同期)
- [2026-10-08 task-194 ショート親区間の比率補正](docs/status_archive/STATUS_2026-10.md#2026-10-08-task-194-ショート親区間の比率補正)
- [2026-10-09 task-195 人物素材の自動・手動収集を削除](docs/status_archive/STATUS_2026-10.md#2026-10-09-task-195-人物素材の自動手動収集を削除)
- [2026-10-13 task-196 同一文字・単語の暴走も方式Dで読み直す](docs/status_archive/STATUS_2026-10.md#2026-10-13-task-196-同一文字単語の暴走も方式dで読み直す)
- [2026-10-13 task-197 ショートの本編上限とフック映像を分離](docs/status_archive/STATUS_2026-10.md#2026-10-13-task-197-ショートの本編上限とフック映像を分離)
- [2026-10-14 task-198 完成動画ごとの制作記録](docs/status_archive/STATUS_2026-10.md#2026-10-14-task-198-完成動画ごとの制作記録)
- [2026-10-14 task-199 backfillのcreatedAtを書き出し時刻へ修正](docs/status_archive/STATUS_2026-10.md#2026-10-14-task-199-backfillのcreatedatを書き出し時刻へ修正)
- [2026-10-14 task-200 古い作業記録を月別アーカイブへ移動](docs/status_archive/STATUS_2026-10.md#2026-10-14-task-200-古い作業記録を月別アーカイブへ移動)
- [2026-10-14 task-201 字幕確認画面の補助関数と型をlibへ切り出す](docs/status_archive/STATUS_2026-10.md#2026-10-14-task-201-字幕確認画面の補助関数と型をlibへ切り出す)
- [2026-10-15 task-202 字幕確認画面の本体をコンポーネントとフックへ分割](docs/status_archive/STATUS_2026-10.md#2026-10-15-task-202-字幕確認画面の本体をコンポーネントとフックへ分割)
- [2026-10-15 task-203 字幕空白の確認操作と一覧表示を廃止](docs/status_archive/STATUS_2026-10.md#2026-10-15-task-203-字幕空白の確認操作と一覧表示を廃止)
- [2026-10-15 task-204 字幕確認を下書き編集と1回の確定へ変更](docs/status_archive/STATUS_2026-10.md#2026-10-15-task-204-字幕確認を下書き編集と1回の確定へ変更)
- [2026-10-15 task-205 Clip Intelligence統合① YouTube接続と自チャンネル同期](docs/status_archive/STATUS_2026-10.md#2026-10-15-task-205-clip-intelligence統合①-youtube接続と自チャンネル同期)
- [2026-10-15 task-206 YouTube動画別日次の分割と一時障害の扱い](docs/status_archive/STATUS_2026-10.md#2026-10-15-task-206-youtube動画別日次の分割と一時障害の扱い)
- [2026-10-15 task-207 制作記録とYouTube動画のDB内結び付け](docs/status_archive/STATUS_2026-10.md#2026-10-15-task-207-制作記録とyoutube動画のdb内結び付け)
- [2026-10-16 task-208 Clip Intelligence統合③ Codexによる自己分析](docs/status_archive/STATUS_2026-10.md#2026-10-16-task-208-clip-intelligence統合③-codexによる自己分析)
- [2026-10-16 task-208追加 同期・自己分析の専用worker分離](docs/status_archive/STATUS_2026-10.md#2026-10-16-task-208追加-同期自己分析の専用worker分離)
- [2026-10-16 task-208追加② Codex中継の分析レーン](docs/status_archive/STATUS_2026-10.md#2026-10-16-task-208追加②-codex中継の分析レーン)
- [2026-10-17 task-208 PR #142のマージと稼働環境への反映](docs/status_archive/STATUS_2026-10.md#2026-10-17-task-208-pr-142のマージと稼働環境への反映)
- [2026-10-17 task-209 YouTube形式判定と自己分析の部分採用・診断](docs/status_archive/STATUS_2026-10.md#2026-10-17-task-209-youtube形式判定と自己分析の部分採用診断)
- [2026-10-17 task-210 伸びた単語の読み直しと発話時刻による字幕分割](docs/status_archive/STATUS_2026-10.md#2026-10-17-task-210-伸びた単語の読み直しと発話時刻による字幕分割)
- [2026-10-18 task-211 切り抜きの範囲と種類を同時に保存](docs/status_archive/STATUS_2026-10.md#2026-10-18-task-211-切り抜きの範囲と種類を同時に保存)
- [2026-10-18 task-212 字幕確認を破棄して切り抜き確認へ戻る](docs/status_archive/STATUS_2026-10.md#2026-10-18-task-212-字幕確認を破棄して切り抜き確認へ戻る)
- [2026-10-18 task-213 Windows共有フォルダで切り抜き確認へ戻れない不具合](docs/status_archive/STATUS_2026-10.md#2026-10-18-task-213-windows共有フォルダで切り抜き確認へ戻れない不具合)
- [2026-10-18 task-215 文字起こしの言いよどみ記号を統一](docs/status_archive/STATUS_2026-10.md#2026-10-18-task-215-文字起こしの言いよどみ記号を統一)
- [2026-10-19 task-214 字幕確認の空白マーカーを削除](docs/status_archive/STATUS_2026-10.md#2026-10-19-task-214-字幕確認の空白マーカーを削除)
- [2026-10-21 task-216 自己分析の入力を要約し、動画増加時も文字数を制限](docs/status_archive/STATUS_2026-10.md#2026-10-21-task-216-自己分析の入力を要約し動画増加時も文字数を制限)
- [2026-10-21 task-217 統合④ 制作属性の独自集計と実績ヒント](docs/status_archive/STATUS_2026-10.md#2026-10-21-task-217-統合④-制作属性の独自集計と実績ヒント)
- [2026-10-22 task-218 統合⑤ チャンネル分析画面と改善試験](docs/status_archive/STATUS_2026-10.md#2026-10-22-task-218-統合⑤-チャンネル分析画面と改善試験)
- [2026-10-22 task-219 現行・到達仕様の更新と残り作業の順序固定](docs/status_archive/STATUS_2026-10.md#2026-10-22-task-219-現行到達仕様の更新と残り作業の順序固定)
- [2026-10-22 task-220 運用ルールの更新と残り作業1のタスク分割案](docs/status_archive/STATUS_2026-10.md#2026-10-22-task-220-運用ルールの更新と残り作業1のタスク分割案)
- [2026-10-22 task-221 残り作業1-A 制作記録の選択履歴](docs/status_archive/STATUS_2026-10.md#2026-10-22-task-221-残り作業1-a-制作記録の選択履歴)
- [2026-10-23 task-222 残り作業1-B 自動決定から人の字幕確認へ](docs/status_archive/STATUS_2026-10.md#2026-10-23-task-222-残り作業1-b-自動決定から人の字幕確認へ)
- [2026-10-23 task-223 通常サムネの最終決定（残り作業1-C）](docs/status_archive/STATUS_2026-10.md#2026-10-23-task-223-通常サムネの最終決定残り作業1-c)
- [2026-10-23 task-224 既存の画角・文字収まりと演出なしの記録（残り作業1-D）](docs/status_archive/STATUS_2026-10.md#2026-10-23-task-224-既存の画角文字収まりと演出なしの記録残り作業1-d)
- [2026-10-23 task-225 残り作業1-E：一連の動作と制作記録の受入確認](docs/status_archive/STATUS_2026-10.md#2026-10-23-task-225-残り作業1-e一連の動作と制作記録の受入確認)
- [2026-10-24 task-222 確定済みclipの共有字幕を保護](docs/status_archive/STATUS_2026-10.md#2026-10-24-task-222-確定済みclipの共有字幕を保護)
- [2026-10-24 task-226: 新規autoをclipごとの字幕確定から自動書き出しへつなぐ（PR1）](docs/status_archive/STATUS_2026-10.md#2026-10-24-task-226-新規autoをclipごとの字幕確定から自動書き出しへつなぐpr1)
- [2026-10-24 task-227 字幕確定後の画角・文字サイズ・行別強調の自動決定（PR2）](docs/status_archive/STATUS_2026-10.md#2026-10-24-task-227-字幕確定後の画角文字サイズ行別強調の自動決定pr2)
- [2026-10-24 task-227 PR #162追加修正：設定した文字サイズを維持](docs/status_archive/STATUS_2026-10.md#2026-10-24-task-227-pr-162追加修正設定した文字サイズを維持)
- [2026-10-24 task-228 PR3：採用履歴から文言基準と通常サムネ候補を修正](docs/status_archive/STATUS_2026-10.md#2026-10-24-task-228-pr3採用履歴から文言基準と通常サムネ候補を修正)
- [2026-10-25 task-229: 新autoの選定品質検査と字幕確認への注意の引き継ぎ](docs/status_archive/STATUS_2026-10.md#2026-10-25-task-229-新autoの選定品質検査と字幕確認への注意の引き継ぎ)
- [2026-10-26 task-230：自動画角の追従証拠と安全な画角への再書き出し](docs/status_archive/STATUS_2026-10.md#2026-10-26-task-230自動画角の追従証拠と安全な画角への再書き出し)
- [2026-10-26 task-229 追加：字幕確定後の状態表示を1行に整理](docs/status_archive/STATUS_2026-10.md#2026-10-26-task-229-追加字幕確定後の状態表示を1行に整理)
- [2026-10-26 task-231: 字幕確定で未変更の値を手動選択として記録しない](docs/status_archive/STATUS_2026-10.md#2026-10-26-task-231-字幕確定で未変更の値を手動選択として記録しない)
- [2026-10-26 task-232：確定字幕と代表コマからショートの画角を選ぶ](docs/status_archive/STATUS_2026-10.md#2026-10-26-task-232確定字幕と代表コマからショートの画角を選ぶ)
- [2026-10-27 task-232追加修正：内容による画角判断の失敗時も既存の選択で続行](docs/status_archive/STATUS_2026-10.md#2026-10-27-task-232追加修正内容による画角判断の失敗時も既存の選択で続行)
- [2026-10-28 task-233：字幕確定後だけ手動画角を受け付け、人の承認と対象clipの再書き出しを記録する](docs/status_archive/STATUS_2026-10.md#2026-10-28-task-233字幕確定後だけ手動画角を受け付け人の承認と対象clipの再書き出しを記録する)
- [2026-10-29 task-233追加：手動画角を明示操作で自動に戻す](docs/status_archive/STATUS_2026-10.md#2026-10-29-task-233追加手動画角を明示操作で自動に戻す)
- [2026-10-29 task-234：定時同期・自己分析と、制作上の選択ごとの30日評価](docs/status_archive/STATUS_2026-10.md#2026-10-29-task-234定時同期自己分析と制作上の選択ごとの30日評価)
- [2026-10-29 task-235：30日観測で許可した選び方だけを更新し、版固定と悪化時の巻き戻しを行う](docs/status_archive/STATUS_2026-10.md#2026-10-29-task-23530日観測で許可した選び方だけを更新し版固定と悪化時の巻き戻しを行う)
- [2026-10-30 task-236：完成MP4の独立検査と上限付き局所修復](docs/status_archive/STATUS_2026-10.md#2026-10-30-task-236完成mp4の独立検査と上限付き局所修復)
- [2026-10-31 task-237 弱い素材の投稿見送りと根拠の永続記録](docs/status_archive/STATUS_2026-10.md#2026-10-31-task-237-弱い素材の投稿見送りと根拠の永続記録)
- [2026-10-27 運用：PR #167・#168の反映と手動選択の誤記録16件の修復](docs/status_archive/STATUS_2026-10.md#2026-10-27-運用pr-167168の反映と手動選択の誤記録16件の修復)
- [2026-10-29 運用：PR #169（task-233）のマージと反映](docs/status_archive/STATUS_2026-10.md#2026-10-29-運用pr-169task-233のマージと反映)
- [2026-10-29 運用：PR #170（task-234）のマージと反映](docs/status_archive/STATUS_2026-10.md#2026-10-29-運用pr-170task-234のマージと反映)
- [2026-10-29 task-235 稼働反映（PR #171）](docs/status_archive/STATUS_2026-10.md#2026-10-29-task-235-稼働反映pr-171)
- [2026-10-30 task-236 稼働反映（PR #172）](docs/status_archive/STATUS_2026-10.md#2026-10-30-task-236-稼働反映pr-172)

</details>

## 2026-11-01 task-238：未保存・確定済みでも字幕を追加・訂正する

- 目的: 字幕のみ確認autoで「未保存なので追加不可→保存には確定が必要→確定すると編集不可」となる行き止まりを解消する。字幕の追加のために保存・確定・自動処理解除を要求しない。
- 原因とAPI: `useSubtitleEditing.ts` の未保存／重複拒否と、字幕にも共用していた確定後の `isEditable` を分離。既存の構成変更APIへ任意の `edits`、字幕一括更新APIへ任意の `clipId` を追加し、楽観ロックの `before` を全件検証して下書きと構成変更を一括保存する。古いリクエストは従来どおり受け付ける。
- 文字の保護: `subtitle_insert.py` で重なる既存字幕の文字を残して時間を分割する。既存文字は一度だけ残し、区間全体を覆う場合は追加字幕と既存字幕へ時間を分配する。0.1秒ずつに分けられない極小区間は文字を改行で併記し、文字の消失と重なるcueを作らない。手動の行スタイルも分割後の区間へ引き継ぐ。未確定clipの追加は確定・自動決定を開始しない。
- 確定後: `api/subtitle_editing.py`、`subtitle_review_edits.py` と既存copy-on-writeを使い、autoの確定済みclipは選んだclipだけ編集して確認済みのまま保つ。他の確定済み・未確定clipの字幕、正式プレビュー、手動指定値を保護する。未確定同士の共有と一括修正の対象制限は維持し、追加欄にも反映先を表示する。
- 自動処理: `subtitle_decision_inputs.py` に既存生成処理の入力ハッシュを記録し、字幕・タイトル等の入力が変わる処理だけ既存の `confirmed_clip_decisions` で更新する。タイトル／フック／投稿文、サムネ文言、内容による画角、行強調を必要に応じて更新する。範囲だけに依存するサムネ動画コマの再走査は行わず、文字サイズの上限とmanualDecisionFieldsを保持する。自動値を先に消さず、処理結果が揃ってから対象clipだけ差し替え、正式プレビューを更新する。プレビューのキュー登録失敗でも字幕の確定を解除せず、プレビューだけ失敗表示として再処理できるようにする。
- 書き出しとの競合: 実行中の書き出しスナップショットは変更せず、`paths.py` 経由の `subtitle_review_pending_edits.json` に原子的に変更を保存する。GETには変更を重ね、書き出しの終了後／既存worker保守処理で世代を照合して字幕だけ反映する。完成済みの場合は既存 `renderClipIds` で対象だけ再書き出す。新しいworker・キュー・DBテーブルは追加しない。
- 画面と下書き: 字幕用の編集可否を独立させ、確定後の文字訂正は600msの入力待ちで自動保存する。全clip確定後も「字幕を編集」で開け、確定操作の直後は編集欄を保つ。「字幕を直し直す」は明示的な解除用として残す。背景のタイトル・画角更新では入力中の字幕を消さず、変更していない内容欄だけ新しい自動値へ追従させる。サーバーで字幕そのものが変わった場合の下書き無効化は維持する。
- 回帰検証: 未保存の重なる／離れた行の一括保存、確定後の追加・修正・分割・結合・削除、他clipの字幕・正式プレビュー・ASSの不変、手動スタイル、入力依存の判定、完成後の部分再書き出し・制作記録更新、書き出し中の変更保持と世代違いの不適用をテストした。frontendは実際のaction・リクエスト・SSRの編集可否・共有先表示・下書きの追従を検証した。
- 隔離した画面確認: 専用DB／storage、API18340・Next.js18341と10秒の合成MP4で、文字を手直し→重なる停止位置に追加→確定→確定後にもう一度追加→確定後の文字訂正の自動保存を操作した。追加前の保存・追加前の確定・確定解除は要求されず、他clipの字幕は元のまま。画面は実APIを使用し、Codex／RQ実行は接続せず登録先をスタブ化した。実Codexと実素材での生成・再書き出しの受入は未確認。検証サーバーは停止した。
- 検証結果: Ruff 0.16.10成功、backend全件2543件成功・2件skip、その後の最終関連backend193件成功、frontend47ファイルのtest・lint・typecheck・build成功。backend全件とCIの結果はPR本文に記載する。稼働DBのサイズ・更新時刻と主フォルダの既存STATUS.mdのSHA256は開始時と一致。主フォルダの未コミット運用記録はこのPRへ混ぜない。
- 制限: 品質・尺・根拠の検証と最終検査は維持。launcher・Codex契約・プロンプト・依存・DB構造の変更なし。中継再起動は不要。CI成功後もPRをマージせず、Dockerへ反映しない。


## 2026-11-01 task-238追補：字幕入力中の自動保存と入力ロックを解消

- 原因: PR #174の600ms待ち保存は、文章の途中や日本語変換中の間にも送信を始め、`isSavingBulkCorrection`→`hasReviewMutationInFlight`→`isSubtitleEditable`でtextareaまで無効にしていた。さらに保存応答で送信対象の下書きを無条件に消し、共有字幕のcopy-on-writeによるID変更で入力欄を作り直していた。前回の追加・確定の画面確認には、文章を打ち続けるケースと遅い応答の検証が不足していた。
- 変更: `useConfirmedSubtitleAutosave.ts` の600msタイマーを廃止。auto確定済みclipでも、字幕欄にフォーカスがある間とIME変換中は送信しない。字幕欄を離れた時点でまとめて保存する。追加・分割等の操作へ移るときは、その操作に下書きを同梱する既存の仕組みを使う。未確定・旧モードの保存タイミングは変えない。
- 入力の保護: 保存中の状態を字幕の入力可否から分離し、HTTP待ちの間も入力できるようにした。`useCaptionDraftState.ts` で最新の入力を同期的に保持し、`captionAutosave.ts` で送信後に入力された続き・取り消しを応答後にも残す。COWでIDが変わっても区間の同一性でtextareaを維持し、カーソル・フォーカスを失わせない。構成変更・確定との並行送信は引き続き制限する。保存先のjobIdも照合する。
- 画面確認: 専用DB／storage、API18344・Next.js18345、10秒の合成MP4で実APIを操作した。入力を途中で休んでもフォーカス中の保存は0件。欄を離れたときだけ1回保存し、応答を4秒遅らせた間と、共有字幕のID変更後にも、日本語の続きを入力できた。全文・フォーカス・カーソルが維持され、書きかけを含む字幕追加も成功。最後の文章が保存され、他clipの元の字幕と確定状態は不変だった。Codex／RQは登録記録のスタブを使用し、実生成は起動していない。Windows実IMEによる変換操作の自動検証は未実施で、変換状態の送信抑止は単体テストで検証した。
- テスト: 新しい `subtitleTypingAutosave.test.ts` と既存の `subtitleAnytime.test.ts` で、フォーカス／変換中の送信抑止、遅い応答と入力の継続、COWのID変更、送信中のundo、他clipの下書き、保存中のtextareaの有効状態、従来の追加を検証。backend全件2545成功・2skip、Ruff 0.16.10成功。frontend48ファイルのtest・lint・typecheck・build成功。CIの結果は追補PRに記載する。
- 範囲と未反映: frontendとこの記録だけ変更。backend・launcher・API契約・依存・品質検証は変更せず、稼働DB／ジョブ・コンテナ・Codex中継を操作していない。主フォルダの未コミット運用記録は保護し、このPRに混ぜない。追補PRのCI成功後にレビュー待ちで止め、今回の指摘を前のPRの反映許可だけで新しいPRのマージ・Docker反映の許可とは扱わない。


## 2026-11-01 task-238追補：確定後の字幕の一括修正を復旧

- 原因: 個別の字幕編集を確定後にも許可した一方、一括修正欄は内容全体の`isEditable`に接続したままで、`bulkEditableSegments`も確定済みclipを一律に除外していた。さらに、確定後の下書きはclip別キーなのに、一括修正は共通キーだけを読み書きしていた。PR #175では文字入力の保存割り込みを直したが、この一括修正の経路の確認が不足していた。
- 変更: autoの確定済みclipを開いているときは、そのclip内だけを一括修正できるようにした。字幕用の入力可否とclip別下書きを使い、対象clip名・件数と「他のclipは変更しない」を表示する。未確定clipからの一括修正は従来の未確定clip全体、旧モードは従来の範囲のまま。他の確定済みclipの保護は維持する。
- 保存と取り消し: 一括修正の入力・確認中は字幕編集と同じフォーカス領域として扱い、入力途中に自動保存を始めない。確定後の反映は既存の字幕保存APIとcopy-on-writeを利用し、確定解除を要求しない。下書きへの反映直後も「取り消す」を使えるようにし、保存で共有字幕のIDが変わった場合も同じ時刻・番号の区間だけを追従する。区間が変わった／曖昧な場合は推測して取り消さず、別の文字に変わった場合も上書きしない。取り消しはjob、選んだ確定済みclip、未確定clip全体という対象範囲が変わったら引き継がない。
- 回帰検証: `subtitleBulkAnytime.test.ts`は修正前mainで失敗し、修正後成功。実際のコンポーネントの入力欄・ボタンの有効状態、編集中の文章を使った一致判定、clip別下書き、他の確定／未確定clipの保護、従来の共有対象、COW後の取り消し対象と曖昧な区間の拒否を確認した。
- 隔離画面: 専用DB／storage、API18346・Next.js18347、10秒の合成MP4で、確定済みショートの「アカネ」2か所を選択・一括修正・保存・取り消し・再適用まで操作した。書きかけの文末を保持し、共有する通常clipの2行と双方の確定状態は変わらない。置換語の入力中の保存割り込みはなく、保存リクエストは反映・取り消し・再適用の3回だった。API応答は4秒遅延し、Codex／RQは登録記録のみのスタブ。実生成・再書き出し・稼働ジョブの編集は行っていない。検証用サーバーは停止した。
- 検証結果: Ruff 0.16.10成功、backend全件2545成功・2skip、frontend49ファイルのtest・lint・typecheck・build成功。CI結果はPR本文に記載する。frontendとこの記録のみ変更し、backend・launcher・API・依存・品質検証は変えない。主フォルダの未コミット運用記録は保護してこのPRへ混ぜない。CI成功後にレビュー待ちで止め、マージ・Docker反映は行わない。


## 2026-11-01 task-238追補：確定済みclipの字幕を確定ボタンから保存できるように修正

- 症状と原因: ユーザーの画像では、確定済みautoの通常clipで「未保存の変更4件」があるのに「この動画の字幕を確定」が無効だった。`ReviewClipActions`が字幕用ではなく内容全体の`isEditable`で確定ボタンを止め、確定済みautoは常にfalseになるため。直前の調査でAPIの200だけを確認して、画面上の保存ボタンの問題を特定できていなかった。画像の確定ボタンが保存操作であることを踏まえ、入力欄を離れる自動保存とは別に、そのボタンからも保存できるようにした。
- 修正: `ReviewActions.tsx`で、autoの確定済みclipに字幕の変更があれば、同じボタンを「字幕の変更を保存」として有効にする。字幕以外の保存・構成変更が実行中なら引き続き無効にし、二重送信を防ぐ。保存中は「字幕を保存中…」、変更がなくなれば「このclipは確定済み」を表示する。未確定clipの確定、旧モード、失敗した自動決定の再試行は従来どおり。
- 保存経路: `useReviewConfirmation.ts`から既存の`saveConfirmedSubtitles`へ渡し、選択clipの字幕だけをPATCHする。applyでclip全体を再確定せず、タイトル・フック・画角など別の下書きを送信・破棄しない。確定状態、manualDecisionFields、他clipの字幕の保護と、変更後の自動処理・プレビュー・部分書き出しは既存経路を維持する。API・backend・launcher・依存・尺／品質検証は変更していない。
- 回帰検証: 新しい`confirmedCaptionSaveButton.test.ts`は修正前mainで失敗し、修正後成功。通常／ショート、字幕確認待ち／書き出し待ち／書き出し中／完了の確定済みclipで変更4件のボタンが有効になること、字幕だけのPATCH、共有字幕のCOW、並行送信の拒否、別の内容下書きの保護、保存失敗時の4件の保持とボタンからの再試行を確認した。
- 隔離画面: 専用DB／storage、API18348・Next.js18349、10秒の合成MP4と4行を共有する通常／ショートで、通常の4行を修正し、画像と同じ未保存4件から保存ボタンを押した。4件が一度に保存され、応答を4秒遅らせた間の追加入力も残り、同じボタンで続きを保存できた。最終的に未保存0件、双方の確定状態を維持し、他方のショートの元の4行は不変。Codex／RQ登録はスタブで、実生成・書き出しの検証とは区別する。検証用サーバーは停止済み。
- 検証結果と範囲: Ruff 0.16.10成功、backend全件2545成功・2skip、frontend50ファイルのtest・lint・typecheck・build成功。frontend2ファイルと回帰テスト、この記録だけ変更。CI結果はPR本文へ記載し、CI成功後は未マージ・未反映でレビュー待ちとする。主フォルダの未コミット運用記録と稼働ジョブの字幕は変更していない。

## 2026-11-02 task-238追補：字幕保存後の下書き同期と編集用映像の更新条件を修正

- 症状と再現: `job_ac031265d2224d82b1d5535fcd944b8a` のDB・字幕確認JSON・プレビューをコピーして検証。通常1には他clipと共有する字幕が3行あり、投稿文／タイトル案の根拠にも使われていた。修正前は字幕PATCHが200でも未保存2件が残り、自動決定でフックが変わると動画URLが変わって再生も停止した。前のボタン修正の合成データには投稿文の根拠・タイトル案がなく、キュー登録もスタブだったため、この条件を確認できていなかった。
- 下書きの原因と変更: COWが字幕IDと投稿文／タイトル案の根拠IDを変更するが、自分の保存応答では内容下書きのrebaseを省略していた。`usePersistedReviewDrafts`で自分の応答も未変更の内容だけ保存済み値へ同期する。既にブラウザへ残った古い根拠IDも、同じindex・時刻・元字幕indicesを持つ一意のCOW先だけへ置換する。字幕や手で書いたタイトル等は破棄せず、曖昧な根拠は推測しない。未保存表示を隠す変更ではない。
- 動画の原因と変更: 編集用の文字なしMP4にもフックを焼き込み、その区間をキャッシュキーへ含めていた。加えてプレイヤーがフックの変更で再生成・pause・先頭seekを行っていた。編集用映像を本編だけの`live-subtitle-review-v5`とし、既存のブラウザ再生時計で本編からフックを再生する。時計の区間更新では本編の元映像時刻と再生／停止状態を維持する。書き出し待ち／書き出し中への遷移でも編集プレイヤーを切り替えず、完成後は従来どおり正式動画を表示する。
- 互換と検証の維持: `livePreviewHookDurationSeconds`を追加（新しい映像は0、項目のない旧映像は既存のフック長）。実際の再生元と再開用キーを同じ解決結果から作る。範囲・画角・元動画などが変わればキャッシュを更新する。正式プレビュー／完成動画のフック・尺・字幕・品質検査は変更しない。初回のv5映像生成までは旧映像の時刻を保持し、フック付きShortsで正式版と本編映像の両方を新規作成するときは別々に生成する（既にある本編は再利用する）。launcher／Codex契約／依存は変更せず、中継再起動は不要。
- 隔離画面の結果: API18350・Next.js18351、コピーDB/storageで通常1の共有字幕1行を保存→未保存0件、続けて共有字幕2行をまとめて保存→未保存0件を確認。実際の自動決定関数も実行し、フック2.58秒→3秒の更新後も編集用動画のURLが変わらず再生が継続した。停止中の複数行保存でも元映像の128.322218秒を維持した。字幕の確定状態と他clipの字幕・内容は維持。コピーでは元動画の参照とプレビューキーを隔離先へ変更している。Codex・サムネ抽出・正式動画の再生成はモックであり、実Codex／本番の書き出し受入とは区別する。
- 隔離の訂正と稼働データ: 初回のフロント起動でメディア用プロキシの環境変数が不足し、稼働APIへGET1件が届いて404となった。停止後、公開APIとプロキシの両方を隔離APIへ設定して再開。対象ジョブのJSON全件のSHA-256、コピー取得時と現在のjobs／export_items／source_clip_usage／clip_rejectionsの行の一致、全件テスト前後の稼働DBのサイズ・更新時刻の不変を確認した。稼働字幕の編集・ジョブの再試行・サービス反映は行っていない。検証サーバーは停止済み。
- 検証: Ruff 0.16.10、backend全件2547成功・2skipと追加のCOW根拠保護回帰1件が成功。frontend51ファイルのtest・lint・typecheck・buildも成功（CI結果はPR本文に記録）。COW後の下書き／古い根拠IDの回復／本当の手直しの保持／本編映像の再利用／実際の範囲変更での更新／旧フック時刻互換を回帰テストで固定。主フォルダの未コミットSTATUS運用記録は保護し、このPRには混ぜない。CI成功後も未マージ・Docker未反映でレビュー待ちとする。
## 2026-11-02 task-238追補：旧下書きの復元による未保存の再発を解消

- 原因と再現: PR #178で保存応答の根拠IDと編集映像を修正したが、旧ブラウザ下書きの`content`は詳細設定の全量で、ポーリングによって`baseContent`だけが新しくなり、自動更新と人の編集を区別できなかった。対象ジョブ`job_ac031265d2224d82b1d5535fcd944b8a`の旧・現行JSONを使い、実Reactフックで公開タイトル・タイトル候補・表示タイトル・サムネ文言2項目・字幕強調の6項目が保存応答後も未保存に残る経路を隔離環境で再現した。稼働ブラウザの現在の下書き自体は取得しておらず、その内容まで確認済みとはしない。
- 修正: `contentDraftSync.ts`と下書きフックで、操作時に変更した項目をブラウザ専用の`_editedFields`へ記録する。確定済みautoの保存応答・背景処理・ポーリングでは、未編集の値はサーバーに追従し、実際の手入力だけを保護する。保存と一致した項目は編集印も解除する。APIへは既存の明示的な項目だけを送信し、API・DB・launcherは変更しない。未保存件数と保存可否の比較も同じ関数へ揃える。
- 旧下書きの保護: 出所を判別できない旧詳細値は、字幕・元の比較基準・画角を含む下書き全体を同じブラウザのjob/clip別保護領域へ退避し、字幕の未保存入力は通常どおり引き継ぐ。詳細編集には保護した値を明示的に復元する欄を置き、復元は既存の編集可能条件に従う。退避に失敗した場合は入力を破棄せずエラーを出す。手動・未確定の旧編集経路は移行しない。他ジョブの下書きは触らない。
- 隔離画面: API18352・Next.js18353、コピーDB/storage、実ジョブJSONとコピーしたMP4を使用。旧下書きの字幕を復元→字幕を入力して保存→実際の`run_confirmed_clip_decisions`の結果を取得するまで操作し、保存した文字と「未保存の変更0件」を確認した。編集用MP4のURLと停止位置125.1秒も維持した。Codex・サムネ抽出・動画再生成はモックであり、実Codex/本番書き出しの受入ではない。旧詳細値を保護欄から復元できること、新しく手入力したタイトルが背景更新後も残ることも確認した。証拠は`.codex_tmp/q238sync3/`。一時画面・検証サーバーは撤去・停止済み。
- 検証: Ruff 0.16.10の`check . ../launcher ../scripts`、backend全件2548成功・2skip、frontend52ファイルのtest・lint・typecheck・build成功。旧全量下書き・退避と重複防止・退避失敗・手編集の保持・保存応答/取り消し・旧モードの不変・job別破棄を回帰テストで固定。全件pytestの前後で稼働DBのサイズと更新時刻は不変。稼働環境・ユーザーの画面・稼働データは変更していない。
- 状態: CIはPRで確認し、成功後もマージ・Docker反映せずレビュー待ちで止める。主フォルダの未コミットSTATUS運用記録は保護し、この変更には混ぜない。
## 2026-11-02 task-236追補：完成検査のフレーム時刻とフック継ぎ目の誤判定を修正

- 症状・調査: `job_ac031265d2224d82b1d5535fcd944b8a`は2026-11-01 19:01:58 UTCに`final_output_incomplete`で字幕確認へ戻っていた。両RQキュー・実行中登録は0件。全7本が字幕画素不一致、通常1・ショート1/5は冒頭音声も不一致。各1回の同一条件再書き出しでも同じ出力ハッシュと不合格が残っていた。停止した未公開MP4は既存の後片付けで削除されている。
- 字幕の原因・修正: 従来は実MP4だけ`fps=5`で変換し、参照は0.2秒間隔の別時計で描いていた。実データの7.4秒の字幕は一致率1.0だが、旧検査が選んだ約7.5秒のコマは切替後で0.01997となることを再現。`inspection/subtitles.py`で選んだ実フレームを分岐し、同じPTSの透明面に確定字幕を描く方式へ変更した。NUT/PyAVでPTSを保持し、Windowsのpipeは前方読み取りだけを公開する。字幕切替±1msのlibass丸めでは内部サンプルを検証し、短いcueは中点へ1回シークして追加照合。検査時間上限は全サンプル共通。画素RGB差60・各色群72%以上は不変で、観測できないcueを合格にしない。
- 音声の原因・修正: 小数秒フックのconcatで、音声が映像の端数フレームへパディングされる。通常1/ショート1/5は本編先頭の約3.375/10/6.625msを揃えると同じ音声と確認できた。`inspection/media.py`では本編の比較だけ正方向の最大1出力フレーム・50ms以下でPCMを整列し、相関0.90は維持。フック自身・フック無しの冒頭は整列しない。生の相関、整列量、上限を検査根拠へ追加した。字幕・映像・設定値は書き換えない。
- コピー検証: DB/JSONのコピーと、読み取り専用にマウントした保存済み正式プレビュー7本・元音声を、CPU上限2/ネットワークなしの独立コンテナで照合。今回停止した字幕画素・冒頭音声の検査は全7本で通った。検査時間は通常1約44秒、通常2約143秒、ショート約8〜13秒（ショート2の短いcueは追加サンプル1件）。証拠は`.codex_tmp/q238inspection/`。これは保存済みプレビューの当該検査であり、削除済みの最終MP4・全技術検査・実Codex内容検査・公開完了の受入ではない。稼働ジョブの再試行、DB/字幕の編集、Docker反映は行っていない。対象の主要JSON4ファイルのSHA-256と稼働DBのサイズ/更新時刻は不変。
- 検証: Ruff 0.16.10成功、backend全件2556成功・2skipに加え、最後の境界/追加サンプル処理を含む関連62件が成功。25/59.94/60fpsで隣接字幕の切替、小数秒フック4条件、誤った場面・整列上限、短い字幕の追加観測と欠落検出、観測不能、既存の局所修復・手動値保護を確認。frontend52ファイルのtest・lint・typecheck・buildも成功（ビルドは作業ツリーへlock通りの依存を導入して実施）。最終版の全件CIはPRで確認する。
- 範囲・状態: 完成検査の契約文書へ時刻保持と整列の根拠を追記。launcher/Codex契約/依存は変更せず、中継再起動は不要。主フォルダの未コミット運用記録は混ぜない。PRを作成し、CI成功後もマージ・反映・稼働ジョブの再試行はせずレビュー待ちで止める。


## 2026-11-05 task-240 確定済み字幕の個別書式を保存

- 原因: 個別書式ボタン・書式タブが clip 全体の isEditable に従い、確定後の字幕 PATCH は文字だけを保存していた。
- 変更: 個別字幕の編集だけ isSubtitleEditable を使用。共通書式・タイトル・フック・画角等の編集可否は維持。既存 segments PATCH に clipId、subtitleStyles、beforeSubtitleStyles を追加し、空の文字差分でも書式だけを保存できる。変更前書式の一致・対象字幕の区間・区間重複の禁止を検証する。
- 保存: 書式は既存の clip 別 subtitleStyles に保存。文字との同時保存は従来の copy-on-write、処理中は pending_edits、完成後は renderClipIds を利用。確定・他 clip の字幕/書式/正式プレビュー・manualDecisionFields を維持する。
- 書式だけの変更は自動決定の対象を空にし、既存 worker で正式プレビューと部分再書き出しだけを継続する。進行中の自動決定は中断せず pending に保存し、完了後に反映する。
- 回帰検証: 修正前 main 0b77cd5 で backend 5件と frontend の有効ボタン検査が失敗し、変更後は関連検査が成功。隔離 DB/storage・18440/13440 の画面で確定済みショート1行を Noto Serif CJK JP / #FF4040 に変更し保存。再読み込み後も確認済み・未保存0件、プレビュー ASS と書き出し用 ASS への反映、他 clip・共有字幕の不変を確認した。
- 検証: backend 全件 2537 passed / 30 skipped、追加7件・既存関連テスト、Ruff 0.16.10、frontend test/lint/typecheck/build 成功。最終 CI 結果は [PR #181](https://github.com/yoyowasa/AutoClipper-Web/pull/181) を参照。
- 制限: 画面は合成動画の隔離環境、書き出しの継続は偽エンジンの統合テストで確認。稼働環境への反映・実ジョブの操作は行わない。launcher・Codex契約は変更なし、中継の再起動不要。

## 2026-11-05 task-241：帯・安全範囲からはみ出す文字の自動修復と、個別書式の継承

- 目的: 個別書式で色だけを変えた字幕行に、当時の標準書式（縦位置75.5%・110px）が一式保存されて手の指定扱いになり、自動調整から外れて下の帯にかかり、`overlay_layout_outside_safe_area` で止まっていた（job_969023d3… のショート3本・計18行、人は色だけを変更）。原因に関係なく、はみ出しをシステムが自動で直して先へ進める。
- 正本との差分（ユーザー承認済み）: 手の指定がある書式でも、帯・安全範囲に収めるための位置・サイズの補正は自動で行う。色・フォント・縁取り・手で入れた改行・文字は変えない。
- 自動修復: `jobs/overlay_layout_repair.py` で、品質ゲートと同じ幾何計算（`overlay_geometry.py` に共通化）ではみ出す字幕行・タイトル・フックを特定し、①文字サイズを下限まで下げる、②それでも収まらなければ縦位置を最小量だけ動かす。自動の見た目決定・保存・プレビュー・最終検査の修復の前に実行し、修復後に同じ計算で検査し直す。検査の基準は変えない。修復できない行だけ失敗として残す。修復は choiceHistory（`overlay-layout-repair-v1`）と clip の `overlayLayoutNotices` に記録する。
- 個別書式の継承: 行の書式は人が変えた項目だけを保存し（`styleVersion: 2`）、未指定の項目は clip の自動調整後の字幕書式から継承する（`cue_styles.py`）。旧来の一式保存は読み込み時に、保存時の標準書式と一致する項目を未指定へ移行する。manualDecisionFields は `subtitle_styles.primaryColor` のように変えた項目だけを記録する。
- 画面: `OverlayLayoutNotices.tsx` で、修復した行・修復できない行を clip・秒数・文字・内容（縮小px／移動px／はみ出し量と相手）で一覧表示し、押すとその時刻と行の書式を開く。書式エディタは行の変更を差分だけ保存する。
- 実データのコピーでの確認: job_969023d3ad7e4f93aea2d9159c7708e5 の字幕確認JSONをscratchへコピーして読み込み・修復・品質ゲートを実行。ショート2・3・5の色（#9BFF9B 等）は保持され、行の縦位置は clip と同じ72.92%に揃い、2行の下端は最大1548px（許容1560px）で overlay_layout は pass。手の指定は `subtitle_styles.primaryColor` だけになった。稼働DB・storageは変更していない。
- 検証: backend 全件 2547 passed / 30 skipped、Ruff 0.16.10 成功、frontend test・lint・typecheck・build 成功。CI 結果は PR を参照。
- 制限: 隔離環境の実画面での操作確認と、実ジョブの再処理は未実施。既存の job_969023d3… は反映後にユーザーの指示で再処理する。launcher・Codex契約・依存の変更なし、中継の再起動不要。

## 2026-11-06 task-243：人の字幕修正の学習（キャラ別・完全一致の語のみ）

- 目的: 字幕は人の修正が最も多く、同じ語の直しが繰り返される（実データ: 923行中121行を修正。「ラデン→らでん」15回、「リグロス→ＲｅＧＬＯＳＳ」5回、「ソピ→そぴ」3回など）。人が実際に直した語だけを、次回の字幕生成時に自動で置換する。
- 正本（現行・到達仕様§3.3-3）の例外として、2026-11-06にユーザー承認（キャラ単位）。詳細は [字幕の語の学習](docs/SUBTITLE_TERM_LEARNING.md)。意味・文脈・タイミングの補正や新しい語の提案は行わない。
- 学習: `subtitle_terms.py`。字幕保存時（`write_subtitle_review`）に、人が直した行の差分から「元の語→直した語」を取り、ジョブごとの状態として `storage/subtitle_terms/<キャラ>.json` へ保存（idempotent）。レビュー文書に `characterPresetName` を追加。
- 有効条件: 3回以上（2本以上、または1本だけなら5回以上）、直し先の最多が80%以上、直さず残した例を含めて80%以上、元へ戻された回数2回未満、「使わない」でない。※1本だけの扱い（5回）は、承認された「3回」に加えた安全側の条件。
- 適用: `run_autoclipper_job` が字幕レビュー作成の直前に、そのキャラの有効な語を1パスで置換（長い語優先、単語時刻も更新）。置換は人の修正として数えず、`learned_subtitle_terms.json` に記録。失敗しても元の文字起こしで続行。
- 画面・API: 設定画面に「字幕の語の学習（キャラ別）」、GET `/api/subtitle-terms` と POST `.../disable|enable`（Origin確認）。語ごとに止められる。
- 検証: backend `test_subtitle_terms.py` 14件（語の抽出、3回/5回の条件、キャラ別、残した例、戻し、無効化、長い語優先と連鎖なし、単語時刻、保存時の学習・outputs外では学習しない、runner適用と記録、置換が人の修正にならない、API とOrigin）、frontend `subtitleTerms.test.ts`。実データの字幕レビュー（コピーせず読み取りのみ、学習先はscratch）で学習を実行: 現時点で有効になる語は「ラデン→らでん」（らでんキャラ・そぴあキャラ）と「リグロス→ＲｅＧＬＯＳＳ」。稼働の storage は変更していない。
- 制限: 確認していない行は「残した」と数えない。誤置換はキャラ別一覧から語ごとに止められるが、効果は未確認。launcher・Codex契約・DB構造の変更なし、中継の再起動不要。
## 2026-11-06 task-242：手動の選択・人の修正も選び方の学習に使う

- 目的: 手で直した動画を、動画ごと学習から外していた（`MIXED_PROVENANCE`）のをやめる。ch1 は手直しが混在するという理由で判定が保留されていた。人の修正そのものも、30日を待たずに許可リストの1項目へ反映する。
- 正本（docs/INTELLIGENCE_CHOICE_POLICIES.md）の変更（2026-11-06ユーザー承認）: 基準1を「自動・手動・fallbackのすべてを使用、出所は群の属性として保存・表示」へ、基準5「人の修正から学習」を追加、「手動と自動の混在は次回評価から外す」を「項目ごとの出所として記録し評価に使う」へ変更。
- 比較群: `choice_policy_evidence.py` で動画単位の除外（mixed）を廃止し、`pure` は出所が自動／手動／fallbackの群を使う。出所未記録の群は使わない。30日評価・20%改善・到達率・最小5本・1項目最大10%・重み0.5〜2.0・巻き戻し・再採用防止は不変。
- 人の修正: `choice_evaluation.py` の `record_corrections` が、制作記録の選択履歴から「自動の適用値→手動の最終値」の変更を集める（タイトルは推薦案と選択案のintent、文字スタイルはbold、画角・演出・範囲は既存の許可項目）。色やフォント名など許可リストに対応しない差は設定値にならず、`key` なしで記録だけ残る。集計 `choice_evaluations.corrections` に保存される。
- 反映: `choice_policy_corrections.py`。同じチャンネル・キャラ・形式で、前回更新以降の同じ方向の修正が5本以上そろったとき、`choice_policy_engine.py` が1項目を最大10%動かす（理由 `HUMAN_CORRECTIONS`）。他の更新と同じ「1回の分析で1項目」の上限と、巻き戻した組み合わせの再採用防止、同じ根拠の再更新防止を適用。修正由来の版は、その版で作った動画（30日判定済み5本以上）と他の版の動画の中央値で判定し、20%以上悪化したら直前の版へ戻す。5本そろうまでは次の更新を保留する。
- 画面: 分析画面の「選び方の版」に、比較群の出所（自動／手動／代替）と、修正由来の更新の根拠（変更前→変更後）を表示する。旧 `MIXED_PROVENANCE` の履歴は「旧基準」と表示する。
- 検証: backend `test_choice_policies.py` に、manual/fallbackが根拠になること、別項目の手動で動画が除外されないこと、5本の同方向修正で1項目だけ+10%、4本・色のみ・自動→自動では動かないこと、悪化判定と巻き戻し後の再採用防止を追加（旧テストの「manualは保留」は新基準に更新）。frontend `choicePolicies.test.ts` を更新。稼働DBのコピーで分析を実行した結果、ch1・ch2とも `hold / INSUFFICIENT_OR_UNCONFIRMED`（MIXED_PROVENANCEは解消。30日判定済み動画がまだなく、ch1の修正は5本未満: タイトル→factual 2件）。
- 制限: 修正由来の学習は、公開して制作記録と結び付いた動画に限る（結び付く前の修正は数えない）。許可リストに対応する修正だけが対象で、1人の操作者の癖が反映される。実際の30日後の効果は未確認。launcher・Codex契約・DB構造の変更なし、中継の再起動不要。

## 2026-11-06 task-244：既存ジョブの字幕修正も学習する（キャラ名の補完）

- 症状: task-243の反映前に作った字幕確認の文書は `characterPresetName` を持たず、作業中の7件で字幕を直しても学習されなかった。
- 変更: `subtitle_review.py` の学習フックが、文書にキャラ名がなければジョブの設定（`characterPresetName`）から補い、文書にも保存する。ジョブ・キャラ名がなければ従来どおり学習しない。保存済みの修正（`edited` 行）は次の保存で一度に取り込まれる。
- 検証: `test_subtitle_terms.py` に、キャラ名のない文書が保存時にジョブ設定から補われて学習されること、ジョブがなければ補わないことを追加。backend `test_subtitle_terms.py`・`test_subtitle_review.py` 35件成功、Ruff成功。backend 全件 2567 passed / 30 skipped。frontend は変更なし。
## 2026-11-01 運用：PR #174（task-238）のマージとDocker反映

- 許可とマージ: ユーザーの「merge commitでマージして、いつもの手順でDockerへ反映」に従い実施。Python3.11／3.12・frontendのCI成功を確認したhead `3efa131` をPR #174からmerge commit `24c460a` でmainへ取り込み、ブランチは削除していない。mainのtreeはCI成功headと一致。
- 事前確認: 主フォルダの未コミットSTATUS.mdの運用記録47行を原文・追記部分・SHA256付きで保全し、取り込みとbuild時はmain・未コミット変更なしを確認。切り抜き／分析の両RQキュー・実行中登録・scheduled／deferred／intermediateは0件、DBの実行中ジョブなし、中継requests／processingも0件。実行コンテナのCompose作業フォルダとstorageのbind mountが主フォルダを参照することを確認した。
- バックアップ: SQLiteのConnection.backup()で `storage/backups/autoclipper-20261101-025922-before-pr174.db` を作成。integrity_check=ok、jobs16件・export_items11件が元DBと一致。
- 反映: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker intelligence-worker frontend` 成功。4サービスを再作成。backendはhealthy、worker／intelligence-worker／frontendはrunning。RedisはコンテナIDと起動時刻が不変。
- 動作とコード: backendの `/health`・`/api/health`、frontendの `/upload`・`/settings` が200。workerのav18.1.0／faster-whisper1.2.1を確認。backend／worker／intelligence-worker各15ファイル、frontend17ファイルの変更対象ソースがmainの作業ツリーとSHA256一致。照合スクリプトは最初に誤った `/app/app` を指定して失敗したため、Dockerfileと実際のmodule位置 `/app/backend/app` を確認して指定を直し、全件照合し直した。アプリの起動後ログではERROR／CRITICAL／Traceback／Exceptionは0件。
- データと中継: jobs16件（切り抜き確認待ち7・字幕確認待ち7・completed2）とexport_items11件はバックアップと全行・全項目一致、DBのintegrity_check=ok。両キュー・実行中登録、中継requests／processingは反映後も0件。Codex中継は再起動せず、ready・PID21444の生存・契約／コードの指紋とmainの一致・反映前からの不変を確認。
- 記録の保護: 退避した既存の運用記録47行をバイト単位で維持してmainのSTATUS.mdへ戻し、この記録だけ追記した。既存記録は削除・改変・コミットしていない。照合結果は `.codex_tmp/pr174-deploy/` に保存。
- 未確認・実施しないこと: 状態更新を伴い得るジョブGET・字幕確認GET・結果GET、実ジョブの新規実行／再試行、字幕編集・確定・再生成は呼んでいない。稼働ジョブでの字幕追加・自動決定・部分再書き出しの受入はユーザー操作で今後確認する。アプリコードの追加変更なし。今回の差分は未コミットの運用記録だけとする。


## 2026-11-01 運用：PR #175のマージと字幕入力の修正の反映

- 許可と反映元: ユーザー指示によりPR #175をmerge commit `53513e6`でマージし、mainをDockerへ反映した。CIはPython 3.11／3.12各2543成功・4skip、frontend成功。アプリコードの追加修正は行っていない。
- 事前確認: main `24c460a`、未コミット変更は既存のSTATUS.md運用記録59行だけ。原文と追記分を`.codex_tmp/pr175-deploy/`へ保護し、main更新後に追記分をバイト一致で復元した。両RQキューのqueued／running／scheduled／deferred／intermediateはすべて0、実行中のアプリジョブ・同期・分析はなし、中継requests／processingも0だった。
- バックアップ: SQLiteのbackup()で`storage/backups/autoclipper-20261031-185724-before-pr175.db`を作成（ファイル名の時刻はUTC）。integrity_check=ok、jobs 16件／export_items 11件で元DBと一致。
- Docker: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker intelligence-worker frontend`成功。frontendを再作成し、変更のないbackend／worker／intelligence-workerはビルドキャッシュと既存コンテナを利用。RedisのID・起動時刻は不変。全サービスrunning、backend healthy。
- 反映確認: `/health`・`/api/health`・`/upload`・`/settings`は200。変更したfrontendソース10ファイルのSHA-256がmainと一致。workerのav 18.1.0／faster-whisper 1.2.1。反映後のログ検査にエラーなし。Codex中継はready、PID 21444・契約／コード指紋はmainと一致し、再起動していない。
- データと残る確認: jobs 16件（切り抜き確認待ち7、字幕確認待ち7、completed 2）とexport_items 11件は全行のハッシュが反映前と一致。両キューと中継依頼は反映後も0。状態更新を起こし得るジョブ／字幕確認API、実ジョブの再試行・編集は実行していない。入力と遅い応答の確認はPR #175の隔離環境で実施済みだが、稼働環境での実IME入力は未確認。既存の運用記録を保持し、この追記も未コミットで残す。


## 2026-11-01 運用：PR #176のマージと字幕の一括修正の反映

- 許可と反映元: ユーザー指示によりPR #176をmerge commit `c3d5aec`でマージし、mainをDockerへ反映した。CIはPython 3.11／3.12各2543成功・4skip、frontend成功。マージ後のtreeはCI済みhead `377cb45`と一致する。アプリコードの追加変更は行っていない。
- 事前確認と文書保護: main `53513e6`、未コミット変更は既存のSTATUS.md運用記録69行のみ。原文と追記分を`.codex_tmp/pr176-deploy/`へ保護し、main更新後に追記分をバイト一致で復元した。切り抜き／分析の両RQキューのqueued／running／scheduled／deferred／intermediateはすべて0。実行中のアプリジョブ・同期・分析はなく、中継requests／processingも0だった。
- DBバックアップ: SQLiteのbackup()で`storage/backups/autoclipper-20261101-084439-before-pr176.db`を作成（日本時間のファイル名）。integrity_check=ok、jobs 16件／export_items 11件で元DBと一致した。
- 反映: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker intelligence-worker frontend`成功。frontendを再作成し、変更のないbackend／worker／intelligence-workerはビルドキャッシュと既存コンテナを利用した。RedisのID・起動時刻は不変。全サービスrunning、backend healthy。
- 反映後の確認: `/health`・`/api/health`・`/upload`・`/settings`は200。変更したfrontendソース5ファイルのSHA-256がmainと一致し、workerのavは18.1.0、faster-whisperは1.2.1。反映後のログ検査にエラーなし。中継はreadyでPID 21444・契約／コード指紋は不変かつmainと一致し、再起動していない。
- データと受入の区別: jobs 16件（切り抜き確認待ち7、字幕確認待ち7、completed 2）とexport_items 11件は全行のハッシュが反映前と一致。両キューと中継依頼は反映後も0。状態更新を起こし得るジョブ／字幕確認APIや、実ジョブの編集・再試行は実行していない。一括修正・取り消し・再適用の操作確認はPR #176の隔離環境で実施済みで、稼働ジョブ上の操作受入は未実施。既存の運用記録を保ち、この追記も未コミットで残す。


## 2026-11-01 運用：PR #177のマージと字幕保存ボタンの修正の反映

- 許可と反映元: ユーザー指示によりPR #177をmerge commit `0ebfbd2`でマージし、mainをDockerへ反映した。CIはPython 3.11／3.12各2543成功・4skip、frontend成功。マージ後のtreeはCI済みhead `61745c6`と一致。アプリコードの追加変更はない。
- 事前確認と文書保護: main `c3d5aec`、未コミット変更は既存のSTATUS.md運用記録79行のみ。原文と追記分を`.codex_tmp/pr177-deploy/`へ保護し、main更新後に追記分をバイト一致で復元した。切り抜き／分析の両RQキューのqueued／running／scheduled／deferred／intermediateはすべて0。実行中のアプリジョブ・同期・分析はなく、中継requests／processingも0だった。
- DBバックアップ: SQLiteのbackup()で`storage/backups/autoclipper-20261101-235706-before-pr177.db`を作成（日本時間のファイル名）。integrity_check=ok、jobs 16件／export_items 11件で元DBと一致した。
- 反映: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker intelligence-worker frontend`成功。frontendを再作成し、変更のないbackend／worker／intelligence-workerはビルドキャッシュと既存コンテナを利用。RedisのID・起動時刻は不変。全サービスrunning、backend healthy。
- 反映後の確認: `/health`・`/api/health`・`/upload`・`/settings`は200。変更したfrontendソース2ファイルのSHA-256がmainと一致。workerのavは18.1.0、faster-whisperは1.2.1。反映後のログ検査にエラーなし。中継はreadyでPID 21444・契約／コード指紋は不変かつmainと一致し、再起動していない。
- データと受入の区別: jobs 16件（切り抜き確認待ち7、字幕確認待ち7、completed 2）とexport_items 11件は全行のハッシュが反映前と一致。両キューと中継依頼は反映後も0。状態更新を起こし得るジョブ／字幕確認API、実ジョブの保存・再試行は実行していない。保存ボタンの操作確認はPR #177の隔離環境で実施済みで、稼働ジョブでの保存受入とは区別する。既存の運用記録を保ち、この追記も未コミットで残す。


## 2026-11-02 運用：PR #178のマージと字幕保存・編集映像の同期修正の反映

- 許可と反映元: ユーザーの「マージして反映」に従い、Python 3.11／3.12各2546成功・4skip、frontendのCI成功head `448c320` をmerge commit `f3a3fdc`でmainへ取り込んだ。マージ後のtreeはCI済みheadと一致。アプリコードの追加変更は行っていない。
- 事前確認と文書保護: main `0ebfbd2`、未コミット変更は既存STATUS運用記録89行だけ。`.codex_tmp/pr178-deploy/`へ原文・追記分・SHA-256を保護し、main更新・build開始時は変更なしにした。反映後に89行をバイト一致で復元した。両RQキューのqueued／running／scheduled／deferred／intermediate、DBの実行中ジョブ・同期・分析、中継requests／processingは事前にすべて0。Compose作業フォルダと3サービスのstorage bind mountが主フォルダを参照することも確認した。
- DBバックアップ: SQLiteのbackup()で`storage/backups/autoclipper-20261102-011008-before-pr178.db`を作成（日本時間）。integrity_check=ok、jobs16件／export_items11件が元DBと一致。
- Docker: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker intelligence-worker frontend`が成功。4サービスを再作成し、backend healthy、他サービスrunning。RedisのID・起動時刻は不変。
- 反映確認: `/health`・`/api/health`・`/upload`・`/settings`は200。backend／worker／intelligence-workerそれぞれ変更ソース3ファイル、frontend7ファイルのSHA-256がmainと一致。workerの編集映像rendererはv5、av18.1.0／faster-whisper1.2.1。4サービスの起動後ログにERROR／例外なし。Codex中継は再起動せず、ready・PID21444・契約／コード指紋のmainとの一致と反映前からの不変を確認した。
- 反映後のキューの変化: 最終のidle確認は切り抜きキュー6待ち・1実行中で停止した。読み取り調査で、起動直後から続く`job_ac031265d2224d82b1d5535fcd944b8a`の字幕確認GETにより、新しいv5編集映像を用意するプレビュー7件が登録されたことを確認。PRに記載した初回の作成に当たり、新規ジョブ／再選定ではない。処理を止めたり取消・再試行したりせず、正常起動とコード照合を別途確認した。確認時点では1件完了、5待ち・1実行中、分析キューは0。反映後キュー0件の確認が通ったとは記録しない。
- データと受入の区別: jobs16件（切り抜き確認待ち7・字幕確認待ち7・completed2）とexport_items11件は全行・全項目のハッシュが反映前と一致、DBのintegrity_check=ok。こちらから状態更新を起こすジョブ／字幕確認API、実ジョブの保存・再試行は行っていない。稼働中のプレビュー初回生成の完了と、稼働画面での字幕保存の受入は未確認。コピー環境での保存0件・再生継続の検証と区別する。既存の運用記録を保ち、この追記も未コミットで残す。


## 2026-11-02 運用：PR #179をマージしてDockerへ反映

- 許可・マージ: ユーザー指示でPR #179をmerge commitでマージ。CIはPython 3.11/3.12・frontend全3件成功、head `5357ef5`を確認し、mainは`686e7a1d78d0ead7b581e57605e1219517539b17`。launcher/Codex契約に変更はなく、中継の再起動は行っていない。
- 事前確認: 通常1の正式プレビュー1件が実行中だったため、終了を待って再確認した。両キューのqueued/running/scheduled/deferred/intermediate、DBの実行中ジョブ・同期/分析、中継requests/processingはすべて0件。未コミットSTATUSの運用記録100行は`.codex_tmp/pr179-deploy/`へSHA-256付きで保護し、main更新後に同じバイト列のまま戻した。既存の運用記録はコミットへ混ぜていない。
- バックアップ: SQLiteのbackup()で`storage/backups/autoclipper-20261102-020927-before-pr179.db`を作成。integrity_check=ok、元とjobs 16件・export_items 11件で一致。
- 反映: GPU構成で`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker intelligence-worker frontend`成功。変更のあるfrontendを再作成し、変更のないbackend/worker/intelligence-workerはビルドキャッシュ・既存コンテナを利用した。RedisのコンテナID・起動時刻は不変。
- 反映後: 4サービスrunning、backend healthy。backend `/health`・`/api/health`、frontend `/upload`・`/settings`は200。変更したfrontendソース9ファイルのSHA-256がmainと一致。workerはav 18.1.0/faster-whisper 1.2.1、編集映像はlive-subtitle-review-v5。ログのエラー0件、両キューと実行中登録は0件。
- データ・中継: DBのintegrity_check=ok。jobs/export_itemsの全行ハッシュ・件数・状態内訳は反映前後で不変（切り抜き確認待ち7、字幕確認待ち7、completed 2）。中継はready、pid 21444と契約/コード指紋は不変でmainと一致。ジョブ取得API・字幕取得API・再試行は呼ばず、ユーザーのブラウザの下書きにも触れていない。稼働画面での保存操作そのものの受入は未実施（コピー環境の確認とは区別する）。


## 2026-11-02 運用：PR #180の反映と対象ジョブ7本の再書き出し完了

- 許可・マージ: ユーザー指示でPR #180をmerge commitでマージし、main `0b77cd57f0ee3f059270c51b0ffd388d9b15b511`を反映。CIはhead `e95256b`のPython 3.11/3.12・frontend全3件成功。Codex中継の再起動は行っていない。
- 事前確認・保護: 両RQキューのqueued/running/scheduled/deferred/intermediate、DB実行状態・同期/分析、中継requests/processingは0件。未コミットSTATUS運用記録110行をSHA-256付きで退避し、main更新後に同じバイト列で復元した。既存記録はコミットに混ぜていない。
- バックアップ: SQLite backup()で`storage/backups/autoclipper-20261102-050152-before-pr180.db`を作成。integrity_check=ok、元とjobs 16件・export_items 11件で一致。対象ジョブのJSON115ファイルも`storage/backups/pr180-job_ac031265d2224d82b1d5535fcd944b8a-20261102-050152/`へ相対パスで退避し、SHA-256を照合。
- 反映: GPU構成の`up -d --build backend worker intelligence-worker frontend`成功。backend/worker/intelligence-workerを再作成し、変更のないfrontendは既存コンテナを利用。全サービスrunning、backend healthy。backend `/health`・`/api/health`、frontend `/upload`・`/settings`は200。変更した検査コード2ファイルのSHA-256は3サービスともmainと一致。av 18.1.0/faster-whisper 1.2.1を確認。起動ログのエラー0件。反映前後のjobs/export_items全行は不変。
- 再書き出し: `job_ac031265d2224d82b1d5535fcd944b8a`について、退避後に字幕確認JSONが変わっていないことと、全7本の字幕確定・自動決定readyを確認。既存の`POST /api/jobs/{id}/subtitle-review/finalize`を1回呼び出し、202で再開。2026-11-01 20:04:04 UTCに開始し、20:19:05 UTCにcompleted/100%/error_codeなしで完了した（約15分）。
- 完成物: 通常2本・ショート5本のMP4、サムネ7枚、制作記録7件を確認。各MP4のSHA-256は最新検査記録と一致し、7本とも修正前に誤判定されたMP4とも同一だった。全15項目×7本（実Codexの内容/サムネ判定を含む）がpassで、今回の追加修復は0回。サムネは画像として読み取り検証、制作記録のrecordId/jobId/完成尺はExportItemと一致。結果APIは200で通常2本・ショート5本を返す。
- 不変と稼働: 確定字幕の文字/区間/対象clip、タイトル・フック・画角・文字スタイル・投稿文・manualDecisionFieldsは退避時と一致。他15ジョブと既存11書き出しの全行も不変。DBはjobs 16件・export_items 18件、状態は切り抜き確認待ち7・字幕確認待ち6・completed 3。終了後は両キュー/実行中登録/中継依頼0件。RedisのID/起動時刻と、中継のready・pid 21444・契約/コード指紋は不変。証拠は`.codex_tmp/pr180-deploy/`。この1ジョブの実運用確認と、他の動画での検査精度の一般的な受入は区別する。


## 2026-11-05 PR #181 反映（task-240 確定済み字幕の個別書式）

- PR #181 を merge commit でマージし、main `1271170` を backend / worker / intelligence-worker / frontend へ GPU 構成で再build・反映。Redis と Codex中継は再起動していない。
- 事前・事後: 両 RQ キューと実行中/待機登録は0、DBに実行中ジョブ・同期/分析なし、中継 requests/processing は0、ready と指紋・PIDの不変を確認。
- SQLite backup(): `storage/backups/autoclipper-20261105-150746-before-pr181.db`。integrity_check=ok、jobs=17 / export_items=7 が一致。反映前後の両テーブル全行ハッシュも一致。
- 反映後: backend healthy、他3サービス稼働、/health・/api/health・/upload・/settings は200、worker av=18.1.0、起動ログのエラー0。変更対象 frontend 7ファイル、backend 4ファイル（3サービス）の SHA-256 が main と一致。字幕個別書式の保存フィールドが稼働APIで利用可能。
- 既存の未コミット運用記録121行はバイト単位で保護・復元。稼働ジョブの字幕/個別書式の書き換え・再実行は行っていない。実画面での個別書式操作は先の隔離検証まで。

## 2026-11-05 PR #182（task-241）反映

- 反映前: 両キューLLEN/WIP 0、実行中ジョブ・同期・分析なし、Codex中継のrequests/processing空。SQLite backup() で `storage/backups/autoclipper_pre_task241_deploy_20261105T135037Z.db`（integrity ok・主要表の件数一致）。
- マージ: PR #182 を merge commit（a218256）。初回CIは `test_overflow_repairs_instead_of_stopping_before_export` が実Redisへ書き出しを登録して失敗。ローカル実行時にはテスト用ジョブID宛ての書き出し依頼3件が稼働Redisへ入り、稼働workerが `job not found` で即失敗（DB・storageの変化なし、RQの失敗記録が3件増えたのみ）。テストで登録をスタブ化して再CI成功。
- 反映: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`。5コンテナ running、/health ok、/settings・/intelligence・字幕確認画面 200、worker/backendで新モジュールのimport成功、直近ログにエラーなし。
- Codex中継: ensure が False だったため stop→ensure で再起動し ready（14:00Z）。待ち依頼なし。※訂正: False は「すでに準備完了で起動不要」の意味で、status.jsonのupdatedAtは起動時の時刻。停止ではなく、再起動は不要だった。
- 未実施: job_969023d3ad7e4f93aea2d9159c7708e5 の再処理（ユーザー指示待ち）。

## 2026-11-06 Codex上限回復後の書き出し再試行（運用）

- 対象: `job_969023d3ad7e4f93aea2d9159c7708e5`。ユーザーの上限回復連絡を受け、保存済みの確定内容で subtitle-review/finalize を再実行。コード変更・Docker反映・中継再起動なし。
- 直前確認: 両RQキューと実行中登録は0件。5clipとも confirmed / automaticDecisionState=ready / previewState=ready。
- バックアップ: `storage/backups/before-codex-review-retry-20261105-151014/autoclipper.db`（SQLite backup、integrity_check=ok）と同フォルダの `subtitle_review.json`。
- 結果: 2026-11-06 00:15:30 JST に completed（100%）、書き出し5件。完成検査5本すべて pass、エラーなし。字幕セグメントは再試行前と一致。前回のCodex失敗が利用上限によるものだったかは記録不足のため未確定。

## 2026-11-06 PR #183（task-242）・PR #184（task-243）反映

- 反映前: 両キューLLEN/WIP 0、実行中ジョブ・同期・分析なし、Codex中継のrequests/processing空。SQLite backup() で `storage/backups/autoclipper_pre_task242_243_20261106T040743Z.db`（integrity ok・主要表の件数一致）。
- マージ: PR #183（選び方の学習: 手動も使う・人の修正）を merge commit。PR #184（字幕の語の学習）はSTATUS.mdが競合したため、mainを取り込んで両方の記録を残し（b27acfc）、CI再実行で成功後に merge commit（f040bf3）。
- 反映: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`。5コンテナ running、/health ok、/settings・/intelligence・字幕確認画面 200、`GET /api/subtitle-terms` は `[]`（学習済みの語は反映後の字幕保存から溜まる）、worker/backendで新モジュールのimport成功、直近ログにエラーなし。
- Codex中継: ensure が False だったため stop→ensure で再起動し ready。待ち依頼なし。※訂正: False は「すでに準備完了で起動不要」の意味で、再起動は不要だった。
- 注意: 既存ジョブの字幕レビューは `characterPresetName` を持たないため、反映前に作った字幕の修正は学習されない。学習は反映後に作ったジョブから始まる。

## 2026-11-06 PR #185（task-244）反映

- 反映前: 両キューLLEN/WIP 0、実行中ジョブ・同期・分析なし、Codex中継のrequests/processing空。SQLite backup() で `storage/backups/autoclipper_pre_task244_20261106T044149Z.db`（integrity ok・主要表の件数一致）。
- マージ: PR #185 を merge commit（66c4ebd）。CI 3件成功。
- 反映: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`。backend/worker/intelligence-worker を再作成（frontendは変更なしで継続）。/health ok、/settings・/intelligence・字幕確認画面 200、worker/backendで `_job_character` のimport成功、直近ログにエラーなし。
- Codex中継: ensure は False（`codex_bridge_ready()` が真で起動不要）、PID 58336 の稼働を確認。再起動はしていない。待ち依頼なし。
- 未実施: 既存ジョブの修正の取り込みは、そのジョブの次の字幕保存で行われる。一括取り込みは実施していない。

## 2026-11-06 字幕の語の学習：既存ジョブの取り込み

- ユーザー指示で、字幕確認待ち7件と完成済み2件（job_ac031265…、job_969023d3…）の修正を `storage/subtitle_terms/` へ取り込んだ。字幕の文書は変更なし（ハッシュ一致）。キュー投入なし。
- 有効になった語: 儒烏風亭らでん「ラデン→らでん」15回・「リグロス→ＲｅＧＬＯＳＳ」5回、宙科そぴあ「ラデン→らでん」5回。「ソピ→そぴ」は3回・1本のため学習中。

## 2026-11-07 task-245 リポジトリ棚卸・10月記録アーカイブ（削除は一部停止）

- 目的: Git管理漏れ、統合済みworktreeと古い一時作業物を整理し、10月の作業記録を月別アーカイブへ移す。
- Git管理: `.gitignore` の Runtime storage に `storage/subtitle_terms/` を追加。主フォルダの未コミット運用記録166行は、内容を変えず本ブランチへ写して先にコミットした。主フォルダの `STATUS.md` と `storage/subtitle_terms/` は作業前後でバイト列・ファイルハッシュが一致。
- worktree: 指定27本は各解除直前に `git rev-list --count main..HEAD` が0、`git status --porcelain --untracked-files=all` が空であることを確認し、`git worktree remove` で解除。27ブランチは全て元のHEADのまま残存。指定対象外5本も登録を維持した。
- リンク: task145の `frontend/node_modules` と `.next/standalone/frontend/node_modules` のjunction、他worktreeのworkspaceリンクを先に外した。古い作業物の `task65_xlsx/node_modules` もリンクだけを外した。リンク先へ再帰削除していない。
- 古い作業物: 再走査で日付・非worktree・参照・明示除外条件に該当する候補は351項目（棚卸時348項目と差あり）。`STATUS.md` / `docs` が参照する `.codex_tmp/storage` は追加保護。削除済み334項目の全名称をPR本文に記録、残り17項目は未実施。明示除外27項目は全て残存。
- **削除判定の不備・未解決**: 対象外の「フォント」を古い一時作業物にも適用すべきところ、`font-downloads` / `fonts-20260907` / `font_add_20260925` / `genei_fonts` の4フォルダ（計41ファイル、108,578,042 bytes）を削除対象に含めてしまった。認識時点で削除を停止。削除前のファイル別一覧・復元用コピーはなく、完全復元は保証できない。復元未実施。主フォルダの `frontend/public/fonts` と `storage/fonts` は残存し、そこへの削除操作はしていない。残りの削除は再開しない。
- 容量: 解除worktree内の通常ファイル合計 17,701,076,093 bytes、削除済み古い作業物 1,469,495,903 bytes、合計 19,170,571,996 bytes（17.854 GiB）。リンク先は集計から除外。これは削除ファイルの論理サイズであり、ディスク空き容量の実増分は未計測。
- node_modules: 作業直前/直後とも主フォルダは41項目（ファイル27）、Codex実行環境側は9,340項目（ファイル8,531）。主フォルダは棚卸時22,076件とは一致しないが、今回の作業前後の件数は不変。
- アーカイブ: `docs/status_archive/STATUS_2026-10.md` へ89節を移動し索引追加。本文は相対リンク7か所の修正だけを除きバイト単位で一致。10月見出しは89→89、STATUS内は0。元の全見出しと11月本文、冒頭の運用メモ・現在状態は保持。相対リンク/アンカー413件に不達なし。
- 検証: `git check-ignore storage/subtitle_terms/probe.json`、worktree/ブランチ照合、非リンク走査、保護対象の残存確認、本文・見出し・リンクのスクリプト照合、`git diff --check`。ローカルのアプリ全件テストは文書・ignore変更のため省略。CIはPRで確認する。
- 制限: 削除対象外フォント取得用フォルダの削除があり、タスク全体は完了扱いにしない。Docker操作・稼働反映・マージなし。
