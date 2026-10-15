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

## 2026-10-01 JST 切り抜きの尺ルールを統一（task-168）

- 目的: 2026-09-27確定・2026-09-30補足の尺ルールを、AI選定・再選定と人による編集に共通で適用する。
- ルール: 通常切り抜きは90〜600秒。ショートの最低尺は強制せず、上限は既定75秒・設定可能範囲1〜180秒。shortMinDurationは0以上かつ上限以下の探索目安で、Codexにも最低尺の制限ではないと伝える。ショートは冒頭に複製するフック映像を含めた完成尺で判定する。
- 変更ファイル: `backend/app/duration_rules.py`、`api/{clip_plan.py,_job_common.py}`、`schemas.py`、`candidates/{merge_boundaries.py,boundary_refinement.py,codex_initial_selection.py,select_candidates.py}`、`jobs/{runner.py,clip_plan_runner.py,pipeline_common.py,subtitle_review.py}`。共通判定へ置き換えて参照がなくなった旧`jobs/hook_scene.py`を削除。frontendは`lib/{durationRules.ts,clipBoundaryTime.ts,manualClipRanges.ts}`、`components/{SettingsPanel,ClipReselectionPanel,ClipBoundaryEditor,ManualClipPlanEditor,ManualClipRangeEditor,ClipHookSceneEditor}.tsx`、upload・clips・subtitlesの各page。backendの既存10テストと新規`test_duration_rules.py`・`test_duration_rules_api.py`・共通定数fixture、frontendの境界時刻テストと新規`durationRules.test.ts`、本ファイル。
- 適用箇所: JobSettings・再選定依頼の設定検証、手動アップロード範囲、Codexの尺帯と返却候補、境界補正前後の候補、通常のルール選定、clip planの境界変更・手動作成/更新・形式変更・フック編集・手動確定、workerの境界/フック更新。字幕確認から尺調整へ戻った後も同じ検証を通す。字幕確認のフック編集・applyにも完成尺の上限を適用し、別画面からの回避を防ぐ。違反候補はduration_out_of_rangeで記録して採用せず、本数不足を短い通常clipで埋めない。
- 画面: 各入力に範囲外の理由を表示し、upload・再選定・境界/手動保存・形式変更・フック編集の送信を止める。ショートの1秒未満の編集を可能にするため、境界調整の1秒制限を取り除き、手動範囲の秒入力にも小数を使えるようにした。ショートの上限は時間指定中も変更でき、入力した範囲を消さずに調整できる。
- 既存データ: 保存済み設定は読み取り専用のvalidation contextで旧値を受け入れ、GET・retryで422/500にしない。ディスクとDBの設定は書き換えず、生成に使うコピーだけ現行ルール内へ収める。新規保存・再選定は通常の厳しい検証を行う。既存clipの元の長さで拒否せず、変更後の範囲・完成尺が適合すれば修正できる。
- 自動補足: 過去提案の説明に残り文字数が足りない場合は、範囲一覧0件＋「過去の提案範囲がほかN件あります」まで縮め、それも入らなければ補足を省略する。既存の自動補足・ユーザー指示・重複判定用の全範囲は保持する。
- 検証: Python 3.11.9の全件python -m pytestは1234 passed・1 skipped（移動後1175件に今回の59件を追加）。通常89/90/600/601秒、ショート上限0/1/180/181秒、min>max、0.5秒のショート、各編集窓口の422とファイル不変・キュー未登録、範囲外の既存clipの修正、字幕確認からの再編集、旧設定のGET・retry、Codex候補の補正前後の却下・フック追加後の上限、狭い文字数予算と全範囲の保持、backend/frontend定数一致を確認。frontend全17テスト・lint・typecheck・build成功。backend/app・backend/tests・launcherのruffとgit diff --check成功。
- lintの環境差: 主作業フォルダのruff check . ../launcher ../scriptsは、Git管理外のscripts/make_plotwith_solar_finished_variants.pyの既存F841で失敗する。このファイルとruff設定は変更せず、実装コミットad4a054のクリーンなcheckoutで指定コマンドが成功したことを確認。
- CI: PR #102のコミット71586daでbackend（Python 3.11・3.12）とfrontendがすべて成功。
- 未確認: 稼働Dockerの実動画生成・映像品質・ブラウザでの実操作。Dockerのbuild・再起動・反映、実ジョブの再実行は行っていない。


## 2026-10-01 JST 不採用理由の記録と再選定への反映（task-169）

- 目的: キープしない候補の人の判断を永続記録し、同じ場面の再提示を理由に応じて抑える。理由はclipごとに1つ（no_content / missing_context / weak_highlight / other / unspecified）。理由を推定・置換せず、未指定はunspecified。任意の補足は500文字以内で、全理由で記録してCodexへユーザー補足として渡す。
- 変更ファイル: backend/app/{models.py,schemas.py,clip_rejections.py}、api/clip_plan.py、candidates/{user_rejections.py,used_ranges.py,codex_initial_selection.py}、jobs/{clip_plan_runner.py,pipeline_common.py}、backend/tests/{test_clip_rejections.py,test_clip_plan_split_contract.py,test_real_pipeline.py}、frontend/app/jobs/[jobId]/clips/page.tsx、components/{ClipRejectionEditor.tsx,ClipReselectionPanel.tsx}、lib/{clipRejections.ts,types.ts,api.ts}、tests/clipRejections.test.ts、本ファイル。
- 台帳: clip_rejectionsの列はid、job_id、video_id、source_key、clip_plan_revision、clip_id、clip_type、start、end、reason、note、created_at。source_keyはsource_clip_historyと同じ関数で算出し、識別不能時はNULL。ジョブ・動画への削除連動を持たず、追記のみ。init_db/create_allで既存DBにもテーブルを追加し、storage lifecycleのジョブ・動画・ファイル掃除後も保持する。
- 保存順: 再選定の状態を取得し、理由全件を_rejectedRangesへ保存、clip plan保存・キュー登録が成功した後に台帳へ追記する。保存/キュー登録前の失敗では台帳へ書かず、worker失敗時には理由全件と最新の有効なキープIDを復元した設定に残す。以降の依頼ではDB台帳から全件を再構築する。現在のclip以外・キープ済みclip・同一clipの重複指定・500文字超は422。
- 補足決定3点: no_contentは通常/Shortsの形式をまたいで避ける。50%判定は「不採用にした元区間の長さ」に対する候補との重なり率（50%以上を却下）。補足文は理由未指定を含む全理由でCodexへ渡す。
- 再選定: weak_highlightは同じ形式で50%以上を避け、より見どころの強い別の場面を指示する。missing_context初回は元区間を含む尺ルール内の拡張候補を優先検討するよう指示し、広げないほぼ同じ区間は既存の90%判定で却下する。同じ形式・90%以上重なる区間で2回目になると50%以上を避けるが、記録上の理由はmissing_contextのまま。other/unspecifiedは従来のほぼ同じ場面の判定を使い、手動指定区間の従来の扱いを維持する。理由による除外は過去候補を避ける設定がOFFでも有効。初回文脈不足の拡張用区間はONでも一律除外から外すが、既存書き出しとキープ場面の除外は維持する。
- 採用判定: 候補の境界補正前後と手動候補の統合後に理由を確認し、rejected_by_user_*をrejectedCandidatesへ記録する。キープは再判定対象に混ぜず保存する。全台帳は保持し、CodexのcontextGuidanceは1000文字以内の区間・理由・補足、溢れる場合は件数の要約、それも入らなければ省略して失敗させない。
- 画面: キープしていない候補ごとに4理由のボタンと任意補足欄、未選択時の理由未指定を表示。DB台帳をGET /api/jobs/{job_id}/clip-plan/rejectionsから取得し、折りたたみの区間・形式・理由・補足一覧を表示。新しいrevisionでは入力した理由をリセットし、再利用されたclip IDへ以前の理由を自動付与しない。worker失敗による同じrevisionの復元では入力を保持する。
- Codex中継: launcher/codex_bridge.pyは変更しない。既存のcontextGuidanceに文面を追加するだけで、入力・応答スキーマの形は変更していない。固定値は応答スキーマのハッシュであり、両段階のbackend契約との一致テストが成功したため更新不要。今回の変更のためのホスト側Codex中継の再起動は不要。
- 検証: 実装コミット942f34dのクリーンcheckoutで、ruff check . ../launcher ../scriptsと全件python -m pytestが成功（Python 3.11.9、1269 passed・1 skipped。既存1234件に今回の35件を追加）。理由別の形式・50%境界値、小数秒、補正前後の却下理由、Codex候補プール、文脈不足の拡張と2回目、OFF時、旧形式・不正IDの422、補足500/501文字、保存/キュー登録失敗、worker失敗後の台帳・キープ保持、DB追加・掃除後の保持、補足の上限縮退を確認。frontend全18テスト・lint・typecheck・build、git diff --check成功。
- lintの環境差: 主作業フォルダのruff check . ../launcher ../scriptsは、Git管理外のscripts/make_plotwith_solar_finished_variants.pyの既存F841で失敗。このファイルとruff設定は変更しない。
- CI: PR #103の実装コミット54ce800でbackend（Python 3.11・3.12）とfrontendがすべて成功（run 36740956833）。
- 未確認: 実動画によるCodex選定の意味的な品質、稼働ブラウザでの実操作は未確認。Dockerのbuild・再起動・反映、稼働DBへの台帳追加、実ジョブの再実行は行っていない。


## 2026-10-01 task-170 合計本数とAIによる形式配分

- 目的・仕様: 新規画面ではclipAllocationMode=ai、合計totalClipCount（1〜36）と任意の最低minNormalClipCount（0〜12）・minShortCount（0〜24、既定0）を指定する。最低の合計は合計本数以下。固定配分を選ぶUIは追加しない。通常とShortsで同じ場面を使えるが、Shortsは単体で内容と見どころが成立するものに限る。別動画からの補完は実装しない。
- 変更ファイル: backend/app/clip_allocation.pyを新設し、schemas.py、candidates/{select_candidates,codex_initial_selection,manual_ranges,used_ranges,user_rejections}.py、jobs/{runner,clip_plan_runner,pipeline_common,reselection_keep,clip_plan,quality_gate,summaries}.py、api/clip_plan.pyへ適用。frontend/lib/{clipAllocation,types,manualClipRanges}.ts、components/{SettingsPanel,ManualClipRangeEditor,ClipSelectionEditor,ClipReselectionPanel}.tsx、app/upload/page.tsx・app/jobs/[jobId]/clips/page.tsx、launcher/codex_bridge.py、backend/tests/{test_clip_allocation,test_real_pipeline}.py、frontend/tests/clipAllocation.test.ts、本ファイル。
- 選び方: 尺ルール・不採用理由・使用済み区間・同形式の重複の判定後、(1)手動・キープを確定、(2)形式ごとの最低に足りない分をその形式の順位順に選択、(3)残りを形式をまたいだCodex confidence・既存スコア順に選択する。同順位は開始・終了・形式・ID順で決める。弱い候補による穴埋めはしない。各形式の探索プールは未確定枠から決め、従来どおり最大24候補。手動指定がある形式でも残りはAI選定でき、同区間をキープした手動候補は二重計上しない。
- 不足: requestedTotal・selectedTotal・selectedByType・shortfallReasons（却下理由の件数と強い候補の不足数）・minimumShortfallをselection summaryとclip planへ保存。1本以上なら不足でも失敗にせず候補確認へ進む（autoモードでも停止して確認）。0本は従来のno_candidates_found/no_usable_selection等の理由付き失敗。最低本数を満たせない場合も不足を明記する。再選定ではキープを合計と最低へ数え、新しい候補が0本でもキープがあれば候補確認へ進む。
- 画面: アップロードは合計・最低本数へ変更し、不正な入力は理由を表示して送信を止める。確認画面では「10本中7本（通常3・ショート4）」形式の表示と不足の理由、再選定欄ではキープを差し引いた残り枠を表示する。手動作業の追加本数は合計を超えると422とし、clip plan保存時に実数を更新する。
- fixed互換: totalClipCountがない設定はfixedとしてnormalClipCount・shortCountを従来どおり使う。保存済みジョブを自動で書き換えず、GET・retryは元設定を維持する。再選定も新しい配分キーを指定しない限り追加せず、形式別本数の挙動を維持する。e2e_real_video.py・e2e_sample_video.pyの旧指定は合計を送らないのでfixedとなり、CLIオプションは変更しない。
- Codex中継: プロンプト版をcodex_initial_selection_v6へ更新。依頼へ合計・最低・手動/キープ確定本数を追加し、場面ごとの最適形式とShortsの単体成立、両形式での利用を指示する。応答のpromptVersionの固定値が変わるため、話題選定・初期選定の2種類の応答スキーマハッシュをlauncherへ反映した。ホスト側のCodex中継の再起動が必要。今回再起動は行っていない。
- 検証: 実装コミット50b6f82のクリーンcheckoutでruff check . ../launcher ../scriptsとpython -m pytestが成功（Python 3.11、1297 passed・1 skipped。既存1269件から新規24件と既存テストのAI配分パラメータ4件を追加）。合計0/1/36/37・最低本数、最低優先後の全体順位、同じ場面の両形式、却下理由と不足の保存、autoでも候補確認、0本失敗、手動のみ/手動＋AI、キープだけ残る再選定、キープの両形式利用、fixedのGET・再選定・retry、Codex中継の契約一致を確認。frontend全19テスト・lint・typecheck・build、git diff --check成功。CI結果は次項に記録する。
- CI: PR #104の実装コミットa935930でbackend（Python 3.11・3.12）とfrontendがすべて成功（run 36750199115）。
- lintの環境差: 主作業フォルダのruffはGit管理外scripts/make_plotwith_solar_finished_variants.pyの既存F841で失敗。このファイル・ruff設定は変更せず、クリーンcheckoutで上記コマンドの成功を確認した。
- 未確認: 実動画を使ったCodexの配分・Shortsの意味的な成立、稼働ブラウザでの操作は未確認。Dockerのbuild・再起動・反映、ホスト側Codex中継の再起動、既存稼働DBの更新は行っていない。


## 2026-10-01 JST PyAVの互換性を固定（task-171）

- 目的・原因: Dockerの依存解決でPyAVが18.xから19.0.0へ上がり、faster-whisper 1.2.1のdecode_audioがav.openへ渡すmetadata_errors引数を受け付けず、文字起こしがtranscription_failedになる。変更前の稼働worker（av 19.0.0 / faster-whisper 1.2.1）で、モデルを読み込まない0.5秒の無音WAVのdecode_audioが同じTypeErrorになることを再現した。
- 変更ファイル: backend/pyproject.toml、backend/tests/test_transcribe_faster_whisper.py、本ファイル。
- 依存の制限: av>=11.0.0,<19.0.0を直接の依存へ追加する。faster-whisperの版・文字起こし処理は変更しない。
- 回帰テスト: 16kHz・モノラル・16bit・0.5秒の無音WAVをテスト内で生成し、実際のfaster_whisper.decode_audioが8000サンプルのfloat32配列（全て0）を返すことを確認する。モデルの読み込み・ダウンロードは行わない。
- 上流確認（2026-10-01）: PyPIの最新版は1.2.1で、同版のaudio.pyにはmetadata_errors引数が残っている。GitHubのmasterにはPyAV 19以降でこの引数を渡さない修正があるが、修正版はまだPyPIへリリースされていない。確認元: https://pypi.org/project/faster-whisper/ 、https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/audio.py 、https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/audio.py 。
- 検証: ruff check . ../launcher ../scripts成功。frontend全19テスト・lint・typecheck・build成功。ローカルはPython 3.11.9 / av 18.0.0 / faster-whisper 1.2.1。python -m pytestは1298 passed・1 skipped（96.81秒）。PR #105のCI（run 36792365163、コミット0359609）でPython 3.11・3.12・frontendがすべて成功。CI両版のPyAVは18.1.0。merge commit f208a0e69b4a6df1ae481d07fe56aec8d8be3d65でmainへ取り込み済み。
- 反映（運用記録）: mainのHEADがf208a0e、追跡ファイルの未コミット変更なし、RQキュー・実行中登録0件、DBの実行中ジョブ0件、中継requests/processing空を確認してから、docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend workerを実行し成功。既存のGit管理外storage/backupsは保存し、今回はDBバックアップを作成していない。反映後のworkerはav 18.1.0 / faster-whisper 1.2.1で、同じ無音WAVのdecode_audioが8000サンプルのfloat32配列（全て0）を返した。backendはhealthy、workerはrunning・キュー待機中で起動エラー0件、/health・/api/healthは200。反映後もRQキュー・実行中登録は0件。frontend/redisのコンテナID・開始時刻・再起動回数、Codex中継のpid・ready状態・契約fingerprintが変更前と一致し、pidの生存を確認。指定ジョブはfailed / transcription_failedのままupdated_atも変更なし。マージ後に作成したローカルの運用記録を、指示に従いtask-173のPRに含めて保存する。
- 未確認: 実動画・モデルを使う文字起こし全体の再実行。job_79f82ac1603f4dc68cea4461e0f1afdbは再試行しておらず、ユーザーが画面から行う。


## 2026-10-01 JST キャラごとの表情素材の登録・管理（task-172）

- 目的: キャラ設定ごとに喜(joy)・怒(anger)・哀(sorrow)・楽(fun)の素材を各5枚まで登録・管理する。サムネ生成への適用はtask-173で行い、今回の生成処理は変更しない。
- 変更ファイル: backend/app/{character_asset_rules.py,character_assets.py,models.py,main.py}、api/{character_assets.py,character_presets.py}、storage/paths.py、backend/tests/{test_character_assets.py,test_clip_plan_split_contract.py}、frontend/components/{CharacterAssetsManager.tsx,CharacterPresetManager.tsx}、lib/{characterAssets.ts,characterPresets.ts}、tests/characterAssets.test.ts、.gitignore、本ファイル。
- 保存: StoragePathsで設定されたstorageルートからcharacter_assets/<preset_id>/<emotion>/<asset_id>.pngを組み立て、処理後のPNGだけを保存する。元ファイル・EXIF等の元画像メタデータは保存しない。素材のディレクトリはGit管理外とする。
- DB: character_assetsはid、preset_id、emotion、slot(1〜5)、file_path（storageからの相対パス）、width、height、face_box、has_alpha、created_atに加え、登録時の注意文を再処理なしで表示するためwarnings(JSON)を持つ。同じpreset_id・emotion・slotの一意制約とslot/表情の制約を設け、storageの共通ロックで同時登録を直列化する。6枚目は422、削除後は最小の空き番号を再利用。init_db/create_allで既存DBに追加でき、既存のキャラ設定データは維持する。
- キャラIDの互換性: 名前だけだった既存キャラには、GET時に名前から安定したIDを補完する（読み込みで保存済みJSONを書き換えない）。新規保存はUUIDのID、上書きは既存IDを維持。旧形式のIDなしPUTも既存名のIDと素材を維持し、現在の画面も上書き時にIDを引き継ぐ。
- 登録時の処理: PNG・JPEG・WebP、1枚20MBまで。訂正後の画質基準「短い辺300px以上」をapp/character_asset_rules.pyの定数・判定関数に集約し、将来の自動採用にも使用できる。EXIFの向きを補正し、既存detect_anime_faceの中心座標を正規化した左上x/yとw/hへ変換して保存する。顔が無ければ保存した上で「顔を検出できません（配置を手で調整してください）」と表示する。
- 透過・切り抜き: 実際に透過がある画像は再度切り抜かない。透過がない画像はstorage/models/isnet-anime.onnxの既存anime_character_maskで1回切り抜く。顔未検出の場合は最大の前景成分を使い、face_boxは未検出のまま。モデルが無ければ不透明なPNGとして保存し「背景付き（切り抜きモデル未導入）」を表示する。人物を切り抜けなかった場合も背景付きと理由を表示する。注意文は登録結果として保存し、一覧・画像配信でモデル処理を繰り返さない。
- API・画面: /api/character-presets/{preset_id}/assetsのGET/POST、同/assets/{asset_id}のDELETE、/api/character-assets/{asset_id}/imageのGETを追加。管理画面に4列×5枠の画像プレビュー・削除・単枚/複数アップロードを追加し、利用条件の1行注意書き、画像の条件、未検出・背景付きの注意、処理結果を表示する。登録中はキャラの切替・削除を止め、失敗した素材の理由と成功した枚数を示す。PNG保存やDB commitが失敗したときは新規ファイルを片付け、削除のcommit失敗時はファイルを戻す。
- キャラ削除時: 既存のキャラ削除は設定の保存一覧から外すだけで、作成済み動画・画像は残す仕様。今回も表情素材のDB行・PNGを残し、素材削除のAPIで個別に消す。削除したキャラの通常一覧APIは404だが既存素材の画像URLは残る。この扱いを画面の削除結果にも明記する。
- 保全: character_assetsはジョブのoutputs/temp/uploads/heatmaps掃除の対象外。Dockerのbackend/workerはstorage全体をbind mountしており、GPU構成のモデルキャッシュ追加でも維持される。既存の移行・バックアップ手順でstorage全体をコピーすればPNGも含まれる。SQLiteだけのバックアップには画像ファイルは入らないため、素材の保全にはstorage全体も必要。
- 検証: Python 3.11.9のpython -m pytestは1320 passed・1 skipped（今回22件追加、82.44秒）。実PNG/JPEG/WebPの登録・配信・削除、背景付き/透過済み、モデルなし、顔座標の変換・保存、既存anime_character_maskとの連携（推論結果をテスト用sessionで代用）、同時登録時の5枚制限、299/300px、20MB超/不正画像、空き枠再利用、既存DBへのテーブル追加、旧形式のIDなし保存・画像の維持、ジョブ掃除とstorageコピー後の画像保持、commit失敗の巻き戻しを確認。frontend全20テスト（4表情×5枠の複数ファイル入力・API multipart・削除・エラー表示の契約を含む）、lint・typecheck・build成功。backend/app・tests・launcherのruffとgit diff --check成功。
- lintの環境差: 主フォルダのruff check . ../launcher ../scriptsはGit管理外scripts/make_plotwith_solar_finished_variants.pyの既存F841で失敗。同ファイルは変更しない。実装コミット66afce8のクリーンなコピーでruff check . ../launcher ../scripts成功。PR #106のコミット2261981でCI（run 36836739911）のPython 3.11・3.12・frontendがすべて成功。
- 未確認: 実際のisnet-anime重みを使った人物切り抜きの品質、ブラウザでの実操作、Dockerへの反映。ブラウザ確認用の独立したローカルサーバー起動は自動承認レビューがblocked by policyで拒否したため実施できず、API・UI契約テストまで確認した。Dockerの再build・再起動と実キャラへの素材登録は行っていない。実DBへのテーブル追加については、全件pytestの起動処理による追加を見落としていたため2026-10-02に訂正（task-176参照）。前回task-171のローカル運用記録はstashへ保全し、作業後に戻す。 自動承認レビューが検証用クリーンコピーの削除もblocked by policyで拒否したため、Git管理外.codex_tmp/task172-checkにコピーを残す（PRには含まない）。


## 2026-10-01 JST 元動画全体からのキャラ素材候補収集（task-173）
- 目的: 処理済みの元動画全体から胸から上が映る候補を集め、Codexの判定を見て人が採用したものだけをtask-172の表情枠へ保存する。mainからcodex/task-173-harvest-character-assetsを作成。Dockerへの反映は行わない。
- 変更ファイル: backend/app/jobs/character_asset_frames.py・character_asset_harvest.py・character_asset_harvest_state.py、scoring/character_asset_classify.py、api/character_asset_candidates.py、storage/character_asset_cleanup.pyを追加。models.py・schemas.py・storage/paths.py・lifecycle.py・character_assets.py・api/character_presets.py・review_character_settings.py・jobs/queue.py・runner.py・worker.py・main.py・scoring/codex_title_hook_suggestions.pyを連携。frontendのCharacterAssetCandidatesPanel.tsx・lib/characterAssetCandidates.tsを追加し、CharacterPresetManager・CharacterAssetsManager・characterPresets.ts・types.tsを更新。launcher/codex_bridge.py、backend/frontendの関連テスト、.github/workflows/ci.yml、.gitignore、STATUS.mdも更新。
- 走査: ffmpegを1回起動し、元動画を順番に1秒1枚・幅960pxのRGBフレームとして読む。detect_anime_faceで顔の高さが画面の12%以上、顔上の余白が顔高の0.3倍以上、顔下が顔高の2倍以上あるものを残す。顔領域のラプラシアン分散80以上をブレの基準とし、点数は顔高の割合×min(分散,2000)。時刻差10秒以内、または顔の64bit知覚差分ハッシュの距離6以下なら点数が高い1枚を残し、全体の上位48枚までとする。動画フレームは保持せず、選別用の時刻・顔座標・点数・ハッシュだけを保持する。
- 切り出し: 選別した時刻をffmpeg -ssで元解像度から再取得し、顔を再検出して余白・胸元の条件を再確認。顔基準で3:4の胸から上を切り出す。短い辺300px以上はtask-172と共通の判定を使い、引き伸ばして満たすことはしない。既存isnet-animeモデルがあれば透過PNGへ処理し、未導入なら背景付きのPNGと注意文を保存。正規化したface_boxも保存する。採用時には処理済みPNGを複製し、顔検出・切り抜きは再実行しない。
- Codex: 新しい仕事character_asset_classify（character-assets-v1）。最大8枚ずつの一覧画像と、採用済み素材があるときだけ参照1枚を渡す。emotion（joy/anger/sorrow/fun/neutral）、usable、issues（blur/eyes_closed/occluded/other_character/cut_off）、score（0〜1）、same_characterを検証する。参照ありはsame_characterの真偽値、参照なしはnullを要求し、候補番号の重複・欠落も拒否。判定の失敗時は先に保存したPNGを判定なしで残し、人が表情を指定して採用できる。ホスト側のCodex中継の再起動が必要。今回は再起動していない。
- 起動・状態: 手動POSTはRQに登録するだけで動画を処理しない。処理済みで元ファイルが残る動画から選ぶ。キャラ設定のautoHarvestCharacterAssetsは既定ONで、完成したジョブのキャラID（旧ジョブは名前）と設定を使って自動登録する。収集失敗で完成動画の状態を失敗へ戻さない。queued/runningは再登録せず、再走査の新しい試行IDで古いRQ失敗通知から状態を守る。候補0件の理由やキュー登録の失敗も画面に返す。
- 保存: character_asset_candidatesにid/preset_id/video_id/source_second/file_path/face_box/suggested_emotion/usable/issues/score/same_character/status/created_atと採用用の画像寸法・透過・注意文を保存。preset_id/video_id/source_secondを一意にして、同じ秒を重複保存しない。保存先はStoragePathsからstorage/character_asset_candidates/<preset_id>/<video_id>/を組み立てる。候補0件を含む動画単位の待機・実行・完了・失敗・件数・理由をcharacter_asset_harvestsに保存。両テーブルはinit_dbのcreate_allで追加する。
- 保持期間: pending/rejectedは作成から30日で既存ストレージ掃除とRQ workerの定期メンテナンス（既定600秒、稼働中の処理終了後または待機中）で削除する。adoptedの候補コピーも30日で削除できるが、表情素材へ複製したcharacter_assetsは残す。実行中の収集の候補・元動画・一時作業領域は掃除から守る。
- 画面・削除: 判定ごとに点数順で並べ、素材に不向き・別キャラ・不採用の候補は折りたたむ。判定なし・neutralも表情を選んで採用できる。各表情が5枚なら入れ替える枠を選び確認する。キャラ削除前には素材と候補の枚数を表示して確認し、件数が変わった場合は409で再確認を求める。確定後は対象キャラの設定・素材・候補・収集状態のDB行と素材/候補ファイルを削除する。旧PUTで素材を持つキャラを確認なしで消す操作は409で止める。採用・削除のDB commitが失敗すればファイルと行を元へ戻す。
- 既存データ: 実DBを読み取り専用で確認し、character_assetsは0件、候補テーブルは未作成、素材PNG・候補PNGは0件。持ち主のいない素材はDB行・ファイルとも0件で、自動削除は実施していない。.gitignoreへstorage/backups/と候補の保存先を追加し、既存バックアップ1件は保持。前回の未コミットSTATUS運用記録もこのPRに含める。
- 検証: Python 3.11.9でpython -m pytestは1359 passed・2 skipped（94.70秒）。手元はffmpeg/ffprobeがPATHに無いため、既存FFmpeg統合テストと今回の連続走査/元解像度切り出しテストをskip。判定条件・ブレ・間引き・48枚・Codexの8枚単位/参照/契約/失敗時保存・採用/入れ替え/不採用・30日/自動掃除・旧DBテーブル追加・完了フック/ONOFF・HTTPで登録だけ・同じ秒の再走査・DB失敗の復元・RQの実際のID/Callback検証を確認。frontend全21テスト・lint・typecheck・build成功。docker compose -f docker-compose.yml -f docker-compose.gpu.yml config --quietとgit diff --check成功（起動・buildはしていない）。
- lintの環境差: 主フォルダのruff check . ../launcher ../scriptsはGit管理外scripts/make_plotwith_solar_finished_variants.pyの既存F841で失敗。同ファイルを変更せず、PRに入るファイルのクリーンなコピーで同じruffコマンドが成功。backend/app・tests・launcherも直接確認して成功。
- CI: PR #107の実装コミットf2b5c88で、run 36842901984のPython 3.11・3.12・frontendがすべて成功。各Python版は1357 passed・4 skipped。最初のCIにはffmpegがなく走査テストがskipされたため、ci.ymlにffmpegの導入手順を追加。修正後は今回の連続走査/元解像度3:4切り出しと既存FFmpeg統合テストがskipされず成功した。判定一覧画像はバッチごとに別ファイルにし、タイムアウトした古い依頼が次の8枚を参照しないこともテストで確認。
- 未確認: 実配信動画を走査した候補の品質・閾値80の調整、実モデルの透過品質、実Codexの表情/同一キャラ判定、ブラウザでの実操作、Dockerへの反映は未実施。今回の検証はAPI・ローカル画像処理・生成したテスト動画・RQ登録・UI契約・ビルドまで。

## 2026-10-02 JST テスト起動時のDB・storage隔離（task-176）

- 目的・変更ファイル: main 174a862からcodex/task-176-test-db-isolationを作成。backend/tests/conftest.pyとtest_test_db_isolation.pyを追加し、起動処理を含むテストが稼働DB・storageへ接続しないようにする。アプリ本体・frontend・Docker構成は変更しない。本ファイルでtask-172の誤記も訂正する。
- 原因: test_manual_workflow.pyのtest_manual_clip_crud_and_approve_preserve_user_valuesとtest_manual_subtitle_modes_skip_audio_and_prepare_reviewはwith TestClient(app)でlifespanを実行する。get_dbの差し替えはAPIの依存解決だけであり、init_dbが使うapp.db.engineには効かない。backendからの全件pytestで既定の../storage/autoclipper.dbへcreate_all・使用済み区間の補完・commitが走った。task-172（10月1日17:23 JST）とtask-173（18:14・18:19 JST）の実行記録に該当テストの成功が残る。task-172の「実DBへのテーブル追加は行っていない」はこの副作用を見落とした誤記だった。
- 隔離: pytest_sessionstartでテスト収集・appのimportより前に、セッション単位のpytest一時ディレクトリを作りDATABASE_URL・STORAGE_ROOTを設定する。get_settingsのlru_cacheを消し、設定前にapp.db/app.mainがimport済みなら収集前に停止する。engineとSessionLocalがこの一時DBを使うことを回帰テストで確認。環境変数・キャッシュ・イベントの設定はpytest終了時に片付ける。
- 安全装置: autouse fixtureでengineとSessionLocalの接続先を確認。セッション全体のSQLite do_connectイベントで物理接続より前に、Engine before_cursor_executeイベントでSQLより前に、リポジトリのstorage配下への接続をpytest.failで拒否する。一時的に差し替えたengineや既存プールの接続、相対パス・SQLite URIにも適用する。稼働ファイルの作成・変更を起こす前に止める。
- 回帰テスト: セッション設定とengine/SessionLocalの一致、with TestClient(app)後も見立てた稼働DBが未作成のまま/既存ファイルの更新時刻・内容が不変、危険な接続先の事前拒否、起動処理のengineだけを差し替えた場合の拒否、プール済み接続の拒否、独自の一時DBとの併用、相対パス・URIの判定の10件を追加。既存の独自DB・storage・init_dbテストも含めて確認する。
- 稼働台帳の調査（読み取り専用）: storage/backups/autoclipper-20261001-031413.dbのsource_clip_usageは116行、現在は121行。idを照合した全列の比較で追加5行・削除0行・既存行の変更0行。5行はすべてjob_8b672f77079a4a0da02990b42f560697（通常2・ショート3）で、作成時刻は10月1日06:54:28 UTC（15:54:28 JST）、実ジョブのcompleted更新時刻と対応し、task-172・173のテストより前。これらのテストのinit_dbによる補完で増えた行は見つからない。厳密なテーブル作成時刻はSQLiteに監査記録がないため未特定。稼働DB・バックアップは変更しない。
- ローカル検証: Python 3.11.9でpython -m pytestは1369 passed・2 skipped（123.22秒、追加10件）。全件実行の前後で稼働DBのmtime_ns・サイズ・SHA-256が一致し、ファイル不変を確認。2件のskipはホストにffmpeg/ffprobeがないための動画統合テスト。frontend全21テスト・lint・typecheck・build成功、git diff --check成功。
- lint・CI: 主フォルダのruff check . ../launcher ../scriptsはGit管理外scripts/make_plotwith_solar_finished_variants.pyの既存F841で失敗。このファイルは変更しない。PR対象のクリーンコピーで同じruffコマンドは成功。PR #108の実装コミット8e4421eのCI（run 36953253092）はPython 3.11・3.12・frontendがすべて成功。両Python版で1367 passed・4 skipped（Windows専用テスト）となり、FFmpeg統合テストも実行して成功した。
- 運用: テストだけの変更のためDockerへの反映・コンテナの再build・Codex中継の再起動は行わない。task-174のサムネ適用は今回に含めない。

## 2026-10-02 JST 表情素材を通常動画のサムネに適用（task-174）

- 目的・変更ファイル: 作成済みcodex/task-174-character-asset-thumbnailsへtask-176マージ後のmain 0486456を取り込み、通常サムネに登録済み表情素材を使う。backendのapi/exports.py・api/jobs.py・schemas.py、jobs/thumbnail_character_assets.py（新規）・thumbnails.py・thumbnail_regeneration.py・thumbnail_preview.py・runner.py、render/character_asset_layout.py（新規）・render_thumbnail.py、scoring/thumbnail_emotion.py（新規）・Codex依頼の共通型、main.pyの公開ヘッダー、launcher/codex_bridge.py、frontendの結果画面・サムネ編集/プレビュー・ThumbnailAssetPicker（新規）・API/型、関連テストと本記録を変更。
- 表情の選択: 新しい仕事thumbnail_emotion_selectを追加。サムネ文言・公開動画タイトル・選んだ場面に近い字幕・登録済み表情の一覧だけを渡し、画像は送らない。中継側でもこの仕事への画像添付を拒否する。返答emotion/reasonを検証し、未登録の表情を採用しない。表情が1種類ならCodexを呼ばずその表情を使う。利用不可・失敗・不正な返答の場合は登録済み順（喜・怒・哀・楽）の先頭を仮に使い、「表情を自動で選べませんでした（仮に◯を使用）」を結果画面と編集欄に表示する。
- 素材と履歴: 選んだ表情の素材を、同じキャラの書き出しメタデータに保存した使用日時から、未使用→最も古い使用順に選ぶ。同じ書き出しバッチ内の未公開素材も数え、連続して同じ素材を選ばない。asset_id・キャラID・emotion・理由・選択元（codex/single_emotion/fallback/manual）・使用日時・実拡大率・注意表示をメタデータへ保存。キャラIDの無い旧ジョブは設定名から照合する。素材が無ければ従来の動画のコマを使い、Shortsのサムネは変更しない。
- 構図: 処理済みPNGのface_box（正規化した左上x/y・w/h）を使い、顔の中心を人物枠の上から30%へ配置。顔の中心から顔高2.75倍下を胸元の切り出し下端とし、画像の下端を越えないようにする。素材には動画用min_crop_height_ratio・再度の顔検出・切り抜きを適用しない。顔座標なしは画像の上から35%・左右中央を仮の顔中心とする。実拡大率が2倍を超える場合は「素材の解像度が足りず粗くなります」をプレビューと結果に表示する。幅320×高さ430pxの素材・720px高の人物枠では、テストの顔座標で約1.674倍となり警告なし。らでん・宙科の双方で確認。
- 編集: 「素材 / 動画のコマ」、登録済み表情の切り替え、素材一覧からの直接選択を追加。未登録表情は選択不可。大きさ・左右・上下は素材にも反映し、プレビューと保存JPEGは同じ配置処理を使う。素材のプレビュー準備はRQでPNGをキャッシュし、HTTP内で動画を処理しない。動画のコマへ戻すと従来の場面選択を使い、素材専用メタデータと注意を消す。生成したMP4は変更しない。
- ローカル検証: Python 3.11.9のpython -m pytestは1388 passed・2 skipped（119.62秒）。素材あり/なしの自動生成、1表情でCodex省略、登録済み表情だけの採用、失敗時の仮選択と結果APIの注意、近くの字幕と画像なしの依頼、履歴と未公開バッチの素材交替、両テンプレの胸元配置・顔なしの仮配置・2倍以下/超過、プレビューと保存JPEGの一致、手動選択・動画へ戻す操作・所有者/表情違いの422・キュー失敗時の復元・中継契約を確認。今回15ケース追加。2件はホストにffmpeg/ffprobeがないため動画統合テストをskip。frontend全22テスト・lint・typecheck・build成功、git diff --check成功。
- DBとlint: task-176の隔離と安全装置を使い、全件実行前後で稼働DBの更新時刻（2026-10-02 01:44:02.0370453 UTC）とサイズ446464 bytesが一致。SHA-256の取得は他プロセスによるファイル使用で失敗したため、内容ハッシュの一致は未確認。主フォルダのruff check . ../launcher ../scriptsはGit管理外scripts/make_plotwith_solar_finished_variants.pyの既存F841で失敗。このファイルは変更せず、PR対象のクリーンコピーで同じruffコマンドが成功。
- Codex中継・運用: 受け付ける仕事・返答schemaの固定ハッシュを更新したため、ホスト側のCodex中継の再起動が必要。今回Dockerへの反映・再build・中継の再起動は行わず、task-175と合わせた後の反映指示を待つ。
- CI・最終調整: PR #109の実装コミット76e1c1aのCI（run 36956589432）はPython 3.11・3.12・frontendがすべて成功。手元のテストPNGを使った配置画像も確認した。最終確認で、編集時の拡大警告に保存済みの値が残る問題を修正し、編集画面では現在のプレビューによる警告だけを表示する（結果一覧は保存済み画像の警告を表示）。この調整後もfrontend全22テスト・lint・typecheck・build成功。調整と本記録のコミットについても、CI成功を確認してからマージする。
- 未確認: 実キャラ素材・実動画での見た目、実Codexによる表情選択、ブラウザでの実操作、稼働コンテナでの生成は未実施。検証は隔離DB・生成したテストPNG・API/RQ・同一JPEGの比較・画面/API契約・ビルドまで。

## 2026-10-02 JST 素材画像全体を人物枠に収める構図（task-177）

- 目的・退避: ユーザー決定でtask-175を中止。変更10ファイル・新規5ファイルと中止記録を、ローカルのcodex/task-175-asset-face-positionへ7330783（WIP: task-175 中止時点の退避）として保存した。push・PR・マージはしていない。main 873e514へ戻り、未コミット変更がないことを確認してcodex/task-177-asset-fit-layoutを作成。
- 変更ファイル: backend/app/render/character_asset_layout.py、backend/tests/test_thumbnail_character_assets.py。frontendのCharacterAssetsManager・ThumbnailAssetPicker・ResultThumbnailEditor・ResultVideoCard、lib/characterAssets.tsと関連する2テスト、本ファイル。
- 構図: 素材PNGの画像全体を縦横比を保って縮小・拡大し、下端の切り落としを廃止。基本は枠の高さに合わせ、横がはみ出す場合は左右の幅で縮小する。ユーザー確認により、中心位置をface_target_xに保ち、左右それぞれの端までの距離から収まる幅を計算する方式を採用。下端は人物枠の下に揃える。320×430pxの素材は、らでんで約1.384倍・宙科で約1.674倍。scaleとoffset_x/offset_yはこの配置へ適用し、手動で拡大・移動した結果の枠外部分は従来どおり見切れる。実拡大率が2倍を超えるASSET_ROUGH_WARNINGは維持。
- 既存データ・表示: face_box引数は互換性のため受け取るが配置には使わず、保存済みの値を削除・更新しない。登録時の顔検出、背景切り抜き、動画の毎秒走査は変更しない。素材欄に「胸から上が写った画像を登録してください」を追加。顔未検出の旧注意は素材管理・サムネ素材選択・サムネ編集・結果の表示から除外し、保存データ自体は残す。背景付き・表情選択失敗・拡大率の注意は引き続き表示する。
- 検証: Python 3.11.9でpython -m pytestの全件実行が終了コード0（1396件収集）。両テンプレで縦長・横長・正方形の画像全体と下端のマーカーが残ることを、リサイズした元画像との全ピクセル比較で確認。中心位置・下端揃え・高さ優先・scale/offset・face_boxの有無による同一配置・2倍ちょうど/超過の注意、プレビューと書き出しJPEGの一致を確認した。frontend全22テスト・lint・typecheck・build、git diff --check成功。隔離したブラウザ画面でも説明の追加・旧顔警告の非表示・背景付きの注意の維持を確認。
- lint・DB: 主フォルダのruff check . ../launcher ../scriptsは、Git管理外scripts/make_plotwith_solar_finished_variants.py:197の既存F841で失敗。そのファイルは変更せず、PR対象をgit archiveで複製したコピーでは同じruffコマンドが成功。全件テスト前後で稼働DBの更新時刻2026-10-02 01:44:02.0370453 UTC・サイズ446464 bytesが一致。テストはtask-176の一時DBと接続先の安全装置を使う。
- 未確認・運用: 実素材・実動画での見た目と稼働コンテナでの生成は未実施。CIのPython 3.11・3.12・frontendはPR作成後に確認し、すべて成功してからmerge commitでマージする。Dockerへの反映・再build・Codex中継の再起動は行わない。素材を動画のコマの予備として使う自動生成の変更はtask-178の対象。

## 2026-10-02 JST 動画の半身候補を優先し、表情素材を予備にする（task-178）

- 目的: main 20aec7dからcodex/task-178-video-bust-firstを作成。通常サムネの自動生成は「このclipから半身を抜き出せる動画候補 → 登録済みの予備素材 → 従来の動画のコマ」の順にした。thumbnail_subject_source（video / asset / legacy）とthumbnail_subject_reasonを保存し、結果画面で表示する。
- 主な変更ファイル: backend/app/jobs/thumbnail_candidates.py（新規）、thumbnail_preview.py・thumbnail_regeneration.py・thumbnails.py・codex_thumbnail_frame_selection.py・queue.py・runner.py、render/video_subject_layout.py（新規）・render_thumbnail.py・character_asset_layout.py、api/exports.py・api/jobs.py・schemas.py。frontendはThumbnailFramePicker（新規）、ResultThumbnailEditor・LiveThumbnailPreview・ResultThumbnailWorkspace・ResultVideoCard・ThumbnailAssetPicker・CharacterAssetsManager、results/page.tsx、lib/api.ts・types.ts。関連するbackend/frontendテストと本ファイル。
- 抽出: clipの開始〜終了だけをFFmpegで順次2fps・幅960pxにして走査し、detect_anime_faceを使う。元解像度で半身にでき、調整前の拡大率が2倍以内、顔のラプラシアン分散40以上のコマを候補にする。顔の高さ、胸元・頭上の余白、鮮明さ、中央への近さで採点。3秒以内かつ顔の64bit差分ハッシュ距離12以下の類似コマは高得点側を残し、上位12件まで保存する。上位コマだけ元解像度で取り出し直して顔と構図を再確認し、原寸JPEG・幅240px/高さ135px以内の一覧用JPEGを保存。thumbnail_frame_candidatesにはclip内の秒、顔の中心/大きさ、得点、画像サイズ、顔のアップ可否を保存する。
- 保存・実行経路: 候補画像の保存先はcandidate_directoryに集約し、job出力内のthumbnails/frames/<export IDのハッシュ>/を使う。再レンダリング時も候補画像を既存の公開・巻き戻し対象に加える。古い書き出しの編集開始ではRQで1回だけ抽出し、候補0件でも完了印を残して繰り返さない。HTTPはキュー登録・保存済み画像の配信/プレビューだけ。走査用ロックと状態取得用ロックを分け、走査中の状態取得は走査完了を待たない。抽出失敗は表示し、利用者が明示的に再試行できる。メタデータ更新には共通のwrite_json_atomicを使い、抽出結果の保存とサムネ更新の登録/公開は同じ短いロックで保護する。
- 動画の構図: standardを半身、closeを顔のアップとして扱う。半身は顔の中心を枠上から30%、下端を顎から顔の高さ2倍下に置く。顔のアップは顔の高さが切り出しの45%。保存候補の構図ではtemplateのmin_crop_height_ratioを使わず、元画像に対する拡大率2倍以内で適否を決める。顔のアップ不可の候補はボタンを無効化し、API/workerでも拒否する。大きさ・左右・上下の調整は維持。保存済みstandard/closeの値や素材のface_boxを読み取りだけで書き換えない。どちらも使えない場合のlegacyだけは従来の動画のコマの描画処理を残す。
- 編集・Codex: 保存済み候補の画像一覧をクリックして選び、半身/顔のアップをプレビューへ反映。「別場面」は一覧の次の候補に切り替えるだけで探索し直さない。「動画から / 予備の素材から」、素材側の表情/個別素材選択、既存の位置調整を維持。Codexのthumbnail_frame_rankは保存済み上位8件のJPEGだけを使い、動画を読み直さない。8件未満は保存済み候補を繰り返して既存の8枠の契約を保つ。仕事ID・返答schema・プロンプトの変更は無く、Codex中継のハッシュ更新・再起動は不要。
- 予備素材の配置変更: 高さ優先で下端を枠の下に揃え、左右のはみ出しは枠内で切り取る。高さ合わせ後の幅が枠幅の1.2倍を超える横長画像だけ幅に合わせる。face_target_xの中心、縦横比、scale/offset、2倍超のASSET_ROUGH_WARNINGを維持。1047×1117pxは両テンプレで高さ720px（約0.645倍）、320×430pxは約1.674倍。素材欄の説明も高さ優先に合わせた。
- 検証: Python 3.11でpython -m pytest全件は1410 passed・3 skipped（111.47秒）。候補の採点・類似間引き・12件上限・画像保存、半身/顔のアップと2倍の境界、3段階の優先と理由保存、古い書き出しの1回だけの抽出と0件理由、走査中の状態取得、候補だけを使うプレビュー/別場面/Codex順位付け、素材への切り替え、公開時の候補画像の移動と巻き戻しを確認。新しいFFmpegの実走査テストも追加したが、ホストにffmpeg/ffprobeが無いためローカルではskip（既存2件と合わせ3件）。frontend全23テスト・lint・typecheck・build、git diff --check成功。
- lint・DB: 主フォルダからのruff check . ../launcher ../scriptsはGit管理外scripts/make_plotwith_solar_finished_variants.py:197の既存F841で失敗。このファイルは変更せず、Git管理対象と今回の新規ファイルだけを複製したコピーで同じコマンドが成功。全件実行前後の稼働DBは446464 bytes・更新時刻2026-10-02 01:44:02.0370453 UTCのまま。task-176の一時DBと接続先の安全装置を使用。
- 画面確認・未確認: 稼働DBに接続しないモック画面で、候補一覧・選択、顔のアップ不可/可、別場面で次候補になること、構図/候補IDを保存操作に渡すこと、予備素材の表情一覧への切り替えを操作して確認した。実動画での走査・実キャラの見た目・実Codexによる順位付け・稼働コンテナでの生成は未確認。CIのPython 3.11・3.12・frontendすべての成功をマージ条件とし、merge commitで取り込む。Dockerへの反映・再build・中継再起動は行わない。

## 2026-10-02 JST task-178の稼働環境への反映（運用）

- 目的・許可: ユーザーが反映を承認。main c1f83314750c99c02e69d302dfd7b25f22289ac7・未コミット変更なしを確認し、backend・worker・frontendをGPU composeで再buildした。アプリのコードは変更せず、本運用記録だけを追記する。Redisは再作成していない。
- 事前確認・保全: RQのキュー・実行中登録は0件、DBの実行中ジョブは0件、Codex中継のrequests/processingは空。SQLite backup()でstorage/backups/autoclipper-20261002-133629-before-task178-deploy.dbへ複製し、integrity_check=ok、jobs 22件・export_items 52件が元と一致した。
- 反映確認: backend healthy、worker/frontend起動、/health・/api/healthは200、frontendの/は/uploadへ転送され200。backend/workerにthumbnail_candidates.pyがあり、候補APIのコードが反映されていることを確認。workerのavは18.1.0、faster-whisperは1.2.1で、0.5秒の無音WAVをdecode_audioで読み込めた。
- Codex中継: task-174で追加した表情選択を含むmainと、稼働中継の契約指紋が不一致だった。依頼が空のままであることを確認し、LauncherController.stop_codex_bridge→ensure_codex_bridge_runningで再起動。ready、mainと同じcontractFingerprint、PID 25420の生存を確認した。実Codexの呼び出しは行っていない。
- 実画面: job_8b672f77079a4a0da02990b42f560697の通常書き出しexp_3203811cb75a4a86be42837cfdd7dd13でサムネ編集を開き直し、「動画から/予備の素材から」「半身/顔のアップ」の新しい欄を確認。初回のRQ候補抽出はreadyで完了したが、条件に合う候補は0件で、半身にできる場面がない旨を画面に表示した。サムネの保存・更新は実行していない。動画候補の見た目・選び直し・実Codex順位付けの受入確認は未実施。
- DB確認: 反映後もjobs 22件・export_items 52件、状態内訳（候補確認9・字幕確認4・完成7・失敗2）は反映前と一致。

## 2026-10-02 JST backend依存のロック（task-179）

- 目的・変更ファイル: main c1f8331からcodex/task-179-lock-backend-depsを作成。backend/requirements.lock（実行用）・requirements-dev.lock（実行用＋dev extra）・requirements-runtime-constraints.txt（稼働版の制約）を追加し、backend/Dockerfile・Dockerfile.gpu・.github/workflows/ci.yml・README.mdをロックからの導入へ変更。backend/tests/test_test_db_isolation.pyのURL比較を修正。本記録と前回の未コミットのtask-178運用記録を保存する。アプリ本体・pyproject.tomlの依存範囲は変更しない。
- 基準: 稼働workerとbackendのpip freezeを比較し、55パッケージの版がすべて一致した。編集可能なアプリ自身の-e行は制約から外し、導入時に--no-deps -e .で別に入れる。av 18.1.0・faster-whisper 1.2.1・ctranslate2 4.8.2・onnxruntime 1.30.0・NumPy 2.5.3を含む全55件をPython 3.12/Linuxのロックとbuild済み両イメージで照合し、差分0件。
- Python・OSの例外: 稼働版NumPy 2.5.3のRequires-Pythonが>=3.12で、同じ版のまま3.11を含むuniversal解決は失敗した。ユーザー承認により「3.11 は NumPy 2.4.6（開発・CI用）、本番の 3.12 は 2.5.3」として条件付きで固定。3.11/Linuxで版が変わるのはNumPyだけで、NumPyに引きずられた別パッケージの版変更は0件。Windowsでは既存依存のOS条件によりuvloop 0.23.0を入れずcolorama 0.4.6を追加する。3.11/Windowsの新規仮想環境でも、devロックの条件に合う59パッケージが全件同じ版で導入された。
- 作成・更新: OSSのuv 0.12.22を使用。backendからuv pip compile pyproject.toml --universal --python-version 3.11 --constraint requirements-runtime-constraints.txt --output-file requirements.lockで作成し、devは--extra devと--constraint requirements.lockを加える。先頭のコマンドコメントを--custom-compile-commandで固定し、READMEにも同じ実行コマンドを記載。版を上げる場合はpyprojectの範囲と対象の基準制約を更新し、両ロックを再生成・差分確認→新しい仮想環境でテスト/lint→Docker buildを行う。devのみの更新は--upgrade-packageを使う。
- CI: Python 3.11/3.12ともrequirements-dev.lock→--no-deps -e .の順に導入する。uvの版を固定し、両ロックを同じコマンドで再生成してgit diff --exit-codeで差分を拒否する手順を追加。手元で再生成後に両ファイルの全バイトが一致し、隔離コピーで依存を追加すると差分が出ることを確認。CIの実行結果はPR作成後に確認する。
- Docker確認: docker compose -f docker-compose.yml -f docker-compose.gpu.yml build backend workerが成功。docker run --rmの一時コンテナでav/faster_whisper/ctranslate2/onnxruntimeのimport成功と全55件の一致を確認。backend・worker・frontend・redisのコンテナID、実行中イメージID、起動時刻はbuild前後で一致し、稼働コンテナの作り直し・Codex中継の再起動は行っていない。
- テストの互換修正: ロックから作ったWindows Python 3.11環境の初回全件は1 failed・1409 passed・3 skipped。SQLAlchemy 2.1.2がWindowsのDB URLをC%3Aと表記し、設定のC:表記との文字列比較だけが失敗した。make_urlで解析したURL同士を比較し、同じDB接続先であるという検証内容を保つ。個別のDB隔離テストは10 passed。稼働DBの更新時刻2026-10-02 01:44:02.0370453 UTC・サイズ446464 bytesは初回全件の前後で一致。
- 検証・未確認: 新規Python 3.11仮想環境の修正後のpython -m pytestは1410 passed・3 skipped（108.10秒）。3件はホストにFFmpeg/ffprobeが無いための既存動画統合テスト。再実行後も稼働DBの更新時刻・サイズは一致。pip check、ruff check . ../launcher ../scripts、frontend全23テスト・lint・typecheck・build、git diff --checkが成功。Python 3.12での全件テストとロック再生成はCIで確認し、全チェック成功後にmerge commitでマージする。実動画ジョブの実行と稼働環境への反映は行わない。

## 2026-10-02 JST 完成後のプレビュー整理と管理コマンド（task-181）

- 目的・変更ファイル: main 46d03a5からcodex/task-181-storage-cleanupを作成。backend/app/storage/completed_previews.py・app/maintenance.pyを追加し、jobs/runner.py・api/_job_common.py・api/jobs.py・api/clip_plan.py、候補/字幕確認画面、関連テスト・READMEを更新。完成済みの確認用動画を整理し、指定ジョブを安全に削除する管理手段を作る。
- 自動整理: 初回書き出しと字幕確認後の書き出しの両方で、ZIP作成・completedのDB確定・再公開の確定後に、そのjobのsubtitle_review_previews（候補確認・正確な字幕確認・簡易編集の動画を含む）とmanual_source_preview.mp4だけを削除する。subtitle_review.json・完成MP4/ZIP・サムネ・thumbnails/framesは保持。storage_mutation_lockと既存の安全な_delete_pathを使用し、失敗はログ警告だけでcompletedを維持する。完成後に残ったRQのプレビュー仕事は再生成しない。
- 参照経路の確認: 完成済みでも字幕確認・候補確認・手動編集のプレビューGETと画面参照が残っていた。削除後の字幕/候補プレビューGETはcandidate_idに対応する完成MP4を返し、元の完成済み確認記録を保持して字幕確認画面で再生できる。完成動画が無い場合と手動編集のproxyは200の完成済み案内を返し、完成済みの候補確認画面は結果画面へ案内する。GETでプレビューをキューに積まず、保存済みreviewデータを書き換えない。既存のプレビューがまだある場合の字幕確認再生も維持する。
- 管理: python -m app.maintenance prune-completed-previews / delete-jobs --job-id <id> ... は既定がdry-run（--dry-runも明示できる）。対象ID・ファイル/フォルダ・サイズをJSONで出力し、--executeだけが削除する。storage_mutation_lock、パス/識別子の検証、未解決の公開状態の拒否、DBの条件付きUPDATEによる状態の再確認を使用。実行中・未知の状態は拒否する。delete-jobsは対象のexports/job、非共有のVideo、出力/作業フォルダ・heatmapを削除し、参照の無い元動画を既存の_delete_path/_prune_unlinked_blobsで整理する。他のVideo行が同じ元ファイルを参照している場合も残し、関係の無い孤立blobは消さない。稼働中の素材採集が使うVideoも残す。source_clip_usage・clip_rejectionsとキャラ素材/素材候補は消さない。
- 検証: ロック由来のPython 3.11環境でruff check . ../launcher ../scriptsとpython -m pytestは1438 passed・3 skipped（109.10秒）。3件はホストにFFmpeg/ffprobeが無い既存動画テスト。共有動画（同じVideo/別Video行で同じファイル）、台帳保持、dry-run、CLI既定、稼働中の拒否と状態の競合、対象外blobの保持、完成時の削除成功/失敗と完成MP4再生、遅れたプレビュー仕事を確認。最終のheatmapのパス修正も管理用24件の再実行で成功。frontend全23テスト・lint・typecheck・build、git diff --check成功。全件テスト前後の稼働DBは446464 bytes・更新時刻2026-10-02 01:44:02.0370453 UTCで一致。
- 未確認・運用: Python 3.11/3.12とfrontendのCI成功を確認してmerge commitでマージする。CI後に事前確認→SQLite backup→backend/worker/frontendへ反映し、指定の2コマンドをコンテナ内でdry-runする。既存データの実削除はdry-runの結果を報告してユーザーの承認を得るまで実行しない。Codex中継のコード/契約は変更しておらず再起動は不要。実データの削除対象・容量、バックアップ・反映結果は運用段階で確認する。

## 2026-10-02 JST task-181の反映・dry-run・承認後の実削除（運用）

- マージ・検証: PR #113のCIはPython 3.11・3.12・frontendすべて成功し、merge commit e6e7e096f5fa5cacbf66341dd49e05df000f2fddとしてmainへ取り込んだ。main・同HEAD・未コミット変更なしで運用を開始した。
- 事前確認・バックアップ: RQのキュー/実行中登録、DBの実行中ジョブ、Codex中継requests/processingは0件。storage/backups/autoclipper-20261002-151600-before-task181-deploy.dbへSQLite backup()で複製し、integrity_check=ok、jobs 22件・export_items 52件が元と一致。
- 反映: GPU composeでbackend/worker/frontendをup -d --buildし、backend healthy・worker/frontend起動、/health・/api/health・frontendの200を確認。RedisのコンテナIDは変わっていない。backendのmaintenance.pyのSHA256はmainのファイルと一致。workerのav 18.1.0・faster-whisper 1.2.1・NumPy 2.5.3を確認。worker起動ログにエラーはなくCUDA preflightも成功。Codex中継は変更/再起動していない。
- プレビューdry-run: 完成済みjob_3e382e32e3d947d68d227c003ddd9bd4、job_48bff760f1484ec08ee5dfdeaa6a785e、job_4bd40f89fabc41c4964781f0d6caea32、job_7b3f8d7f162c4d9d8fe9562c80902a57、job_7f0fc2d8508e4117bc6cfa729253b1b7、job_8b672f77079a4a0da02990b42f560697、job_fcd2f96438524e38a2611b4cf1e5b014の7件で15,517,667,532 bytes（15.52 GB / 14.45 GiB）。該当するmanual_source_preview.mp4は無かった。DBとsubtitle_review.jsonのcompletedはともに7件で、指示背景の8件とは1件違うが、容量は約14.5 GiBという想定に一致。
- 指定ジョブdry-run: job_c5d81f7163424ab08eae763bff2426d7、job_8715fba76abd44a0b2a5013903eda0b0、job_b1796a0a155a4764acbe79d8645ffc71、job_12504e9baec64c5c8d5d83edac44797c、job_eccfea6d16d8450481283cddbe6d1c98、job_a9c19090e7944402b29135996e43c999、job_042a8423975d4ec8a4d0f9af753e59a3の7件。Video行7件を削除予定だが、共有元ファイルを保持するため、物理的な元動画は4本だけが対象（15,048,613,667 bytes = 15.05 GB / 14.02 GiB）。出力/作業ファイル/heatmap等815,148,645 bytesを合わせ15,863,762,312 bytes（14.77 GiB）。想定の4本・約13.9 GiBから大きな差は無い。
- 実削除前の状態: 両dry-runはerrors=[]、対象は重複せず合計31,381,429,844 bytes（31.38 GB / 29.23 GiB）。GET /api/storage/statusは78,987,588,475 bytes（78.99 GB / 73.56 GiB）。全て削除できれば約47.61 GB / 44.34 GiBになる見込みで、実測の削減量ではない。反映/dry-run後もjobs 22・export_items 52・videos 22・source_clip_usage 121・clip_rejections 10、状態内訳（候補確認9・字幕確認4・完成7・失敗2）は一致。実動画の実行・再選定・実データの削除はしていない。
- dry-run時点の停止点: ユーザーの指示Bに従って結果を報告し、--executeの承認待ちで停止した。この時点の実削除は0件で、運用記録はローカルの未コミット変更として保持した。

- 実削除（ユーザー承認後）: 実行直前にRQのキュー/実行中登録とDBの実行中ジョブが0件、Codex中継requests/processingが空であることを再確認。もう一度両dry-runを実行し、承認した7件のID・対象ファイル・サイズが前回と完全に一致することを確認してから、backendコンテナ内でprune-completed-previews --execute → 上記のdelete-jobs --job-id（同じ7件）--executeの順で実行した。両コマンドはerrors=[]で終了し、一覧の対象ファイル/フォルダが消えたことを確認。
- 実測容量: GET /api/storage/statusは削除前78,987,588,475 bytes → プレビュー整理後63,469,920,943 bytes → 指定ジョブ削除後47,606,158,631 bytes。実際に消えたプレビューは15,517,667,532 bytes、指定ジョブ/元動画等は15,863,762,312 bytes、合計31,381,429,844 bytes（31.38 GB / 29.23 GiB）。最終合計47.61 GB / 44.34 GiBで、設定の保存上限53,687,091,200 bytes（50 GiB）を下回った。バックアップは保持した。
- DB・保護対象: jobs 22→15で承認した7件だけが減り、残った各jobの状態は削除前と一致。内訳はawaiting_clip_review 9→4、awaiting_subtitle_review 4→3、completed 7→7、failed 2→1。Video行22→15、物理的な元動画は承認した非共有4本を削除。export_itemsは52→52で残った完成版を書き出した行は保持。source_clip_usageは121→121、clip_rejectionsは10→10で、全行内容のSHA256も前後で一致。完成済み7件の出力570ファイル（プレビュー以外）はサイズ・更新時刻が一致して残っていることを確認した。
- 完成済み結果の確認: GET /api/jobs/job_3e382e32e3d947d68d227c003ddd9bd4/resultsはHTTP 200、通常3件・Shorts5件。確認後もRQのキュー/実行中登録、実行中ジョブと中継の依頼は0件。実動画の新規ジョブ・再選定は実行しなかった。
- 記録の保存: main e6e7e09からcodex/task-181-storage-cleanup-operationsを作成し、前回の未コミット運用記録にこの結果を追記する。変更ファイルはSTATUS.mdのみ。アプリ本体・設定・Docker・Codex中継の変更は無い。git diff --checkを確認し、小さなmain向けPRでコミットする。CIの結果はPR作成後に確認する。

## 2026-10-02 task-182: 投稿用タイトルでの保存・投稿セット・都度ZIP

- 目的: 結果画面から保存した動画を、ファイル名の手直しなしでYouTube Studioへ渡し、動画とサムネを同じ名前で対応付ける。
- 保存名: 公開用タイトル（ExportItem.title）をbackendの `app/downloads.py` で変換する。Windows禁止文字は対応する全角文字へ置換し、制御文字と末尾の空白・ピリオドを除去する。Windows予約名は先頭に `_` を付けて回避し、最大100文字（Unicodeコードポイント）に収める。公開用タイトルが空なら元の連番名を使う。結果API・MP4/サムネのContent-Disposition・ZIP内の名前に同じ関数を使用し、公開用タイトルや実ファイルは書き換えない。切り詰めた場合は画面に表示する。
- 投稿セット: 各動画のMP4・JPEG/PNGサムネ・タイトル/説明/タグ/ハッシュタグのUTF-8投稿文を保存する。投稿文名は `<同じ名前>_投稿文.txt`。showDirectoryPicker対応ブラウザでは初回に選んだフォルダへストリームで書き込み、以降も再利用する（IndexedDBにハンドルを保存し、再利用時は権限を確認）。保存先の変更と同名ファイルの上書き確認があり、複数カードからの書き込みも直列化する。非対応ブラウザは3ファイル入りのZIPを1つ保存する。サムネが無い場合は不完全なセットを作らず、画面で保存不可の理由を示す。既存の動画/サムネ単独保存は残し、保存先選択に非対応のブラウザでも通常のダウンロードを使える。
- 全体ZIP: workerの完成時には作成しない。ZIPダウンロード時にジョブ単位のプロセス間ロックを取り、storage/tempにリクエスト固有の一時ZIPを作成する。送信完了・送信失敗・作成失敗で削除する。既存download.zipはそのまま配信する。同じ保存名になる動画が複数ある全体ZIPではclipごとのサブフォルダで区別し、ファイル名自体は変えない。従来の字幕/メタデータ/投稿文も収録する。
- 完成・復旧: 完成判定のZIP依存を公開済みMP4へ置き換える。状態値packaging_zipは既存データ互換のため残し、進捗の文言をFinalizing outputsへ変更する。旧状態の同一ジョブ再書き出しでは、旧ZIPを動画と一緒に退避し、公開失敗時は復元する。成功した場合は古い内容のZIPを無効化し、次回ダウンロードで作成する。完成時のプレビュー削除・素材収集の導線は維持する。
- 主な変更ファイル: backend/app/downloads.py（新規）、api/jobs.py、api/exports.py、jobs/runner.py、jobs/status.py、schemas.py、frontend/components/SavePostingSetButton.tsx（新規）、ResultVideoCard.tsx、SaveFileButton.tsx、frontend/lib/postingSetSave.ts（新規）、types.ts、README.md。保存/ZIPの回帰テストを新規追加し、既存のZIP完成前提のテストとAPI一覧の契約を更新した。
- 検証: Python 3.11のロック済み環境で `cd backend; ruff check . ../launcher ../scripts` 成功、`python -m pytest -q` は1467 passed / 3 skipped（既存のスキップあり）。全件実行前後で稼働DBの更新時刻は同一。frontendはtest全24本・lint・typecheck・buildが成功。日本語のContent-Disposition、JPEG/PNGと動画の同名、予約名/100文字/タイトル無し、3ファイルの投稿セット、フォルダ再利用/上書き拒否/同時保存/権限拒否/キャンセル/書込失敗、ZIP同時作成の直列化、作成/送信失敗時の後片付け、旧ZIP配信、旧ZIPの巻き戻し、ZIP無しの完成済みジョブの再実行を確認した。
- CI: PRでPython 3.11・3.12とfrontendを確認し、全て成功した後にmerge commitでマージする。実行結果はPRのchecksを参照する。
- 未確認事項: 実ブラウザのネイティブのフォルダ選択・IndexedDBからの再読込復元・実際のYouTube Studioへのアップロードは未実施（フォルダ書込はAPI差し替えテスト）。Dockerの再build・コンテナの作り直し・稼働環境への反映は行っていない。稼働中のbackend healthy、worker/frontend起動は読み取りで確認した。

## 2026-10-02 task-180: 主フォルダでのruffの誤検出を除外

- 目的: 主フォルダで `cd backend; ruff check . ../launcher ../scripts` を実行したとき、Git管理外（.gitignore済み）の `scripts/make_plotwith_*.py` の既存F841で失敗する状態を解消する。CIには影響しない。
- 変更ファイル: `backend/pyproject.toml`（`[tool.ruff]` に `extend-exclude = ["../scripts/make_plotwith_*.py"]` を追加）、本ファイル。コードの変更なし。
- 検証: 主フォルダで `cd backend; ruff check . ../launcher ../scripts` が成功（ruff 0.15.4）。`--show-files` で、scripts配下の検査対象は17件、make_plotwith_* は0件。Git管理下のscriptsが引き続き検査されることを、一時的な違反ファイル（`import os` のみ）で検出を確認してから削除した。backend全件 `python -m pytest -q` は1467 passed / 3 skipped（既存のスキップ）。frontendのtest・lint・typecheck・buildも成功。
- 未確認事項: なし（設定のみの変更）。Codexの利用制限のため、本タスクはClaude Codeが実施した。

## 2026-10-02 task-183 内容に応じた通常切り抜きの長尺

- 目的・条件: 通常は90秒〜10分を基本とし、人物紹介、一連の企画・ゲームの区切り、途切れずに続く1テーマなど、内容上まとまった長さが必要な場合だけCodexが最長30分を選べる。探索設定normalMinDuration/normalMaxDurationは90〜600秒のまま。Shortsの既定75秒・設定1〜180秒は変更しない。
- 変更ファイル: backendのduration_rules、candidates（codex_initial_selection・merge_boundaries・select_candidates・boundary_refinement・user_rejections）、jobs（clip_plan・clip_plan_runner・quality_gate・queue・thumbnail_candidates・新規timeouts）、api/clip_plan、関連テストと共通定数fixture。frontendのdurationRules・clipAllocation・types・候補確認画面・境界/手動範囲編集と関連テスト。launcher/codex_bridgeと本ファイル。
- AIの理由: 600秒を超える通常候補はlongformReasonを必須とし、空白のみを含む理由なしはlongform_without_reason、1800秒超はduration_out_of_rangeとして却下を記録する。選定後の境界補正・品質判定・文脈不足からの再選定にも適用する。Candidate.longform_reasonとclip planのlongformReasonに保存し、旧データは空として読める。600秒以下・Shortsでは理由を空にする。不足理由は画面で「長尺にする理由が不足」と表示する。話題選定ではreasonに長さが必要な理由を書かせ、次段階でlongformReasonとして具体化する。
- 人の調整: 境界変更、手動候補の作成/変更、形式変更、字幕確認から戻った境界変更は90〜1800秒を保存でき、理由の入力は不要。1801秒は422「通常切り抜きは最長30分です」。画面は600秒超に「長尺（10分超）」とAIの理由を表示し、1800秒を超える保存は無効にする。
- 処理時間とRQ: 30分clipを固定の3600秒に収める保証はないため、確認動画・字幕確認プレビュー・本番書き出しをclip合計尺×6＋600秒（最低3600秒）の予算へ変更。1本30分は11400秒＝190分、2本は22200秒＝370分。想定はエンコードに尺の4倍、走査/入出力等に2倍、準備に10分を確保する計画値であり、実動画の実測値ではない。初期選定・再選定は選定前なので元動画の長さと依頼本数から最長30分の候補に備え、再選定前の短いclipだけで時間枠を決めない。
- サムネ抽出: 尺×3＋600秒（最低600秒）へ変更。30分で6000秒＝100分（1秒2枚の3600枚、各コマ最大1秒＋実時間相当のデコード＋準備10分の予算）。走査ロックの期限も連動する。隔離した一時コンテナ（2 CPU・ネットワークなし・backend読取専用・稼働storage未接続）で、1080p/30fps/30分の単色合成MP4をFFmpegで走査し、3600枚を80.700秒で完了（顔なし・候補0件）。別途960pxのノイズ合成画像300枚の顔検出部分は3.969秒、3600枚換算47.624秒。3600枚を処理し上位12件と小画像を保存する回帰テストも成功した。
- 検証: Python 3.11.9の全件python -m pytestは1492 passed / 3 skipped（既存のスキップ）。ruff check . ../launcher ../scripts成功。frontendのtest（24ファイル）・lint・typecheck・build成功。600/601の理由有無、1800/1801、却下記録、理由保存/旧データ、文脈不足の拡張、人の各窓口と字幕確認からの復帰、画面の長尺/上限表示、RQ時間枠、Codex中継の契約一致を確認した。CIはPRで3.11・3.12・frontendの成功を確認してからmerge commitでマージする。
- Codex中継: promptVersionをcodex_initial_selection_v7へ更新し、話題選定・初期選定の固定schemaハッシュを更新した。ホスト側のCodex中継の再起動が必要。
- 未確認事項: 実際に顔が写る30分動画での抽出・12枚の高解像度再抽出、字幕付き30分プレビュー/本番エンコードの実測、Codexでの実選定、稼働画面での確認は未実施。時間予算はCPU/GPUや入力によって十分とは限らない。Dockerへの反映とCodex中継の再起動は行わず、別途の指示で実施する。

## 2026-10-02 運用: main b0f6402（task-183）の稼働環境への反映

- 目的: task-183の内容をbackend・worker・frontendへ反映し、選定の返答変更に合わせてホスト側Codex中継を再起動する。アプリのコード変更は無し。
- 事前確認: main / HEAD b0f6402c4359bcf6fe21230528feecae07632fec / 未コミット変更無し。RQキュー・実行中登録は各0件、中継requests・processingは空。DBは17ジョブ・45書き出し。指定された例外job_ea68be9806884d25aaa3dbd62a259f24だけdetecting_scenes（updated_at: 2026-10-02 10:27:32.691989）で、ユーザーの指示により実行中から除外し変更しない。
- バックアップ: sqlite3.Connection.backup()でstorage/backups/autoclipper-20261002-123935-before-task183-deploy.dbを作成（ファイル名の時刻はUTC）。PRAGMA integrity_checkはok、jobs 17件・export_items 45件は元DBと一致。
- 反映: docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker frontend成功。RedisのコンテナID・起動時刻は変わらず、再作成・再起動していない。
- Codex中継: LauncherController.stop_codex_bridge()→ensure_codex_bridge_running()成功。PID 25420→32304、state=ready、PID生存確認。contractFingerprint=ba9207fc8b68e44d0a5f70a40811982146f29ba028c8dfa1ca7c76b1bf739554、bridgeBuildFingerprint=9c597efd455ddde5f33a1e70d584cd379d6fd9eb755d4b2478f3cfa12553a12eがmainの値と一致。
- 事後確認: backend healthy、worker・frontend running。GET http://localhost:8000/healthとhttp://localhost:3000/uploadは200。workerのavは18.1.0。RQは引き続き各0件。DB件数・状態内訳は変化無し（awaiting_clip_review 6 / awaiting_subtitle_review 3 / completed 6 / detecting_scenes 1 / failed 1）。例外ジョブの状態・updated_atは変化無し。
- 未実施: GET /api/jobs/{id}・字幕確認の取得、実動画の選定・再選定・書き出しは行っていない。変更ファイルは運用記録のSTATUS.mdのみで、記録は未コミット。

## 2026-10-03 task-184: サムネ文言に話の中心人物名を残す

- 目的・原因: 人物紹介のサムネ3案から人物名が抜ける問題を修正する。従来のプロンプトは「対象を隠す」「情報ギャップ」を強く勧め、人物名の検証も無かった。キャラ設定の出演者名は入力に追加しない。
- プロンプト: thumbnail_copy_v2に更新。人物紹介・ゲスト・本人の自己紹介など特定の人物が中心の場合は、字幕か公開タイトルにある表記をsubjectNameに入れ、全3案のheadingまたはupperにも入れる。人物名は隠さず、その人の何が意外か・何が起きたかで引き込む。中心人物がいない場合はsubjectNameを空にする。字幕にない人物を足さない決まりと不確かな固有名詞の禁止を維持し、字幕・公開タイトルに実在する名前の表記は不確かに当たらないことを明記した。
- 検証・作り直し: subjectNameが空でなければ字幕か公開タイトルへの完全一致の部分文字列と、全3案のheading/upperへの挿入を確認する。違反時は同じ字幕・タイトルと前の返答・修正理由を渡して1回だけ作り直す。2回目も違反、または名前を空にして回避した場合はfailed・候補0件とし、理由を既存の画面のエラー表示へ返す。初回からsubjectNameが空なら名前は要求せず、人物が中心かの判断はCodexに委ねる。
- 互換性: 保存済みのsubjectName無しの返答・状態は空として読み込み、GETでは書き換えない。生成の入力ハッシュにプロンプト版を含め、新たな生成依頼では旧版の候補をキャッシュとして再利用しない。
- 変更ファイル: backend/app/scoring/thumbnail_copy.py、backend/app/jobs/thumbnail_copy.py、backend/tests/test_thumbnail_copy.py、frontend/lib/types.ts、launcher/codex_bridge.py、STATUS.md。前回の未コミットのtask-183反映記録も保持した。
- ローカル検証: Python 3.11.9でpython -m pytest全件1509 passed / 3 skipped（既存のスキップ）、ruff check . ../launcher ../scripts成功。frontendのtest（24ファイル）・lint・typecheck・build成功。人物名の字幕/タイトルでの表記一致、各案での名前抜け・下行のみの名前、1回の作り直し成功/失敗、空の名前、旧形式の読み込み、中継の固定schemaとbackendの一致を確認した。失敗理由はGET応答で確認し、画面の既存role=alertがこのerrorを表示することをコードで確認した。
- Codex中継: thumbnail_copy_suggestionsの返答schemaにsubjectNameを追加し、固定schemaハッシュを更新した。ホスト側のCodex中継の再起動が必要。
- 未確認事項: 実際のCodexによる人物中心の判断と3案の生成、稼働画面での表示は未実施。実ジョブ・保存済み文言は変更していない。Dockerへの反映と中継の再起動は行わない。CIはPRで3.11・3.12・frontendの成功を確認してからmerge commitでマージする。

## 2026-10-03 task-184 の稼働環境への反映（運用作業）

- 目的: main `b524e13`（サムネ文言で話の中心の人物名を隠さない）を稼働環境へ反映する。Codexの代わりにClaude Codeが実施。
- 事前確認: main・HEAD `b524e13`、未コミット変更なし。RQのキュー0件・実行中の登録0件。Codex中継のrequests・processingは空。処理中の状態のジョブは、10/02にRQの時間切れで強制終了済みの `job_ea68be9806884d25aaa3dbd62a259f24`（DB上は detecting_scenes のまま、変更していない）のみ。
- 実施: DBバックアップ `storage/backups/autoclipper-20261003-140951-before-task184-deploy.db`（integrity_check ok、jobs 17・export_items 51で元と一致）。`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker frontend`。Codex中継を `stop_codex_bridge` → `ensure_codex_bridge_running` で再起動。
- 確認: backend healthy、`/health` 200、`/upload` 200、workerの av 18.1.0、稼働中のbackendに subjectName の処理が入っていることを確認。Codex中継は ready、契約の指紋がmainと一致。workerの起動ログにエラーなし。GET /api/jobs/{id} などの状態を変えうる取得は行っていない。
- 未確認事項: 実際のCodexでのサムネ文言の生成結果（ユーザーが画面で確認する）。

## 2026-10-03 task-185: 人物名をサムネの主見出しに入れる

- 目的・理由: task-184では人物名が小さいheadingにだけ置かれても検証を通り、らでんテンプレの大きい主見出しで誰の話か分かりにくかった。全3案のupperかlowerに人物名を入れる決まりへ変更する。
- 変更: THUMBNAIL_COPY_PROMPTをthumbnail_copy_v3へ更新。subjectNameがある場合はupper/lowerへの名前を必須とし、headingだけでは不可と明記。headingには人物名を繰り返さず、人物の補足や話題の切り口を置く。例も主見出しにイヴ・クラインを入れる形へ差し替えた。backendの検証と作り直し依頼も同じ決まりへ変更した。
- 検証の扱い: 名前の字幕・公開タイトルでの表記一致、違反時に1回だけ作り直すこと、直らなければ候補を出さず理由付きfailedにすることはtask-184から維持。subjectNameが空なら人物名を要求しない。保存済みの旧返答は読めるまま残し、新たな生成依頼はv3の入力ハッシュによりv2のheadingのみの案をキャッシュとして再利用しない。
- Codex中継: 返答schemaは変えず、thumbnail_copy_suggestionsの固定schemaハッシュ401d21265de2de201f89a4260b3f04980c564c94204ae25c59f109d6c35dd5eaとbackendの一致を確認。launcher/codex_bridge.pyは変更無し。プロンプトはbackendから依頼ごとに渡すため、このタスクによるホスト側Codex中継の再起動は不要。
- 変更ファイル: backend/app/scoring/thumbnail_copy.py、backend/app/jobs/thumbnail_copy.py、backend/tests/test_thumbnail_copy.py、STATUS.md。既存の未コミットのtask-184反映記録もそのまま収録する。
- ローカル検証: ruff check . ../launcher ../scripts成功。Python 3.11.9でpython -m pytest全件1511 passed / 3 skipped（既存のスキップ）。関連27件でheadingだけの案の拒否・1回の作り直し成功/失敗、upper/lowerそれぞれでの採用、空のsubjectName、旧形式の読み込み、旧v2キャッシュの再生成、中継の固定schema一致を確認。frontendのtest（24ファイル）・lint・typecheck・build成功。
- 未確認事項: 実際のCodexでの生成、稼働画面での主見出しの見え方は未実施。保存済みの文言・実ジョブは変更しない。Dockerへの反映は行わない。CIはPRで3.11・3.12・frontendの成功を確認してからmerge commitでマージする。

## 2026-10-03 task-185 の稼働環境への反映（運用作業）

- 目的: main `4f8da8f`（人物名をサムネの主見出しに必須化）を稼働環境へ反映する。Claude Codeが実施。
- 事前確認: main・HEAD `4f8da8f`、未コミット変更なし。RQのキュー0件・実行中の登録0件。Codex中継のrequests・processingは空。処理中の状態のジョブは、RQの時間切れで強制終了済みの `job_ea68be9806884d25aaa3dbd62a259f24` のみ（変更していない）。
- 実施: DBバックアップ `storage/backups/autoclipper-20261003-143425-before-task185-deploy.db`（integrity_check ok、jobs 17・export_items 51で元と一致）。`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker frontend`。返答の形とlauncherに変更が無いため、Codex中継は再起動していない（ready、契約の指紋がmainと一致を確認）。
- 確認: backend healthy、`/health` 200、`/upload` 200、workerの av 18.1.0、稼働中のbackendに新しいプロンプトの決まりが入っていることを確認。workerの起動ログにエラーなし。
- 未確認事項: 実際のCodexでのサムネ文言の生成結果（ユーザーが画面で確認する）。

## 2026-10-03 task-187: 字幕確認で音ありの空白区間を示す

- 目的: 文字起こしの取りこぼしや字幕編集で空いた区間を、字幕確認で見つけて確認・追加できるようにする。本番の文字起こし方式は変更しない。
- 判定: clip内の非空字幕が覆っていない連続区間が3秒以上、silence_segments.jsonから算出した非無音の割合が60%以上ならgapsに追加する。無音の重複は結合し、clipの端で区間を切る。無音データが無い・読めない場合は判定しない。ショートの冒頭フック映像と、フック文言によって意図的に字幕を隠す区間は対象外。gapsのstart/endはフック映像の長さを含むプレイヤー内の時刻、sourceStart/sourceEndは元動画の時刻。
- 保存・API: clip.gapsはレビューの読み込み・保存時に再計算する。各区間のsource/player時刻から作ったIDが同じときだけ確認済みを引き継ぎ、字幕追加や境界変更で区間が変われば再び未確認にする。確認状態はsubtitle_review.jsonへ保存する。PATCH /api/jobs/{job_id}/subtitle-review/clips/{clip_id}/gaps/{gap_id}を追加し、確認保存では字幕本文・clip確定・プレビューやキュー登録を変更しない。旧JSONにgapsが無くても読める。
- 画面: 再生バーに橙色の区間、字幕一覧に「字幕なし（音あり）」の時系列行、clip見出しに未確認件数を表示する。クリックでその位置に移動して停止し、既存の停止位置からの字幕追加を使える。確認済みにすると印・行・件数から外す。確認APIの応答はgapsだけ反映し、字幕・タイトル・画角の未保存編集を維持する。
- 字幕追加の整合: 空文字の既存行も判定対象となるため、そこへの追加時は重なる空行を残余へ分割して新字幕1行に置き換える。元のsourceIndices・共有clip・字幕の書式を保ち、非空字幕との重複は従来の1ms許容で拒否する。画面の個別書式も新しい区間へ移し、未保存の書式の変更・追加・削除や他の区間・タイトルの編集を維持する。挿入範囲に重なる未保存の字幕本文は先に保存を促し、下書きを失わないようにした。
- 変更ファイル: backend/app/jobs/subtitle_gaps.py（新規）、subtitle_review.py、subtitle_structure.py、backend/app/api/jobs.py、schemas.py、backend/tests/test_subtitle_gaps.py（新規）、test_clip_plan_split_contract.py。frontendの字幕確認page、SubtitleGapMarkers.tsx（新規）、lib/subtitleGaps.ts（新規）、subtitleStructureDrafts.ts（新規）、subtitlePauseInsert.ts、api.ts、types.ts、tests/subtitleGaps.test.ts（新規）、subtitleStructure.test.ts、STATUS.md。
- ローカル検証: Python 3.11.9でpython -m pytest全件1539 passed / 3 skipped、ruff check . ../launcher ../scripts成功。最初のsandbox内全件実行は既存Windows Job Objectテストだけ権限制約で失敗し、sandbox外の最終全件実行では成功した。稼働DBの更新時刻とサイズは最終全件実行の前後で一致。frontendのtest（25ファイル）・lint・typecheck・通常build成功。判定の3秒/60%境界、フック除外、無音データ欠如、編集後の再計算、確認保存、単一/複数空行への追加と共有clip・書式保護、未保存編集の保護を確認した。
- 制限・未確認事項: 無音検出は発話検出ではなく、BGMだけでも「音あり」になり得るため、マーカーは確認用の目印とする。稼働画面と実動画での操作は未実施。稼働DB・ジョブファイルは変更していない。Dockerへの反映は行わない。CIはPRでPython 3.11・3.12・frontendの成功を確認してからmerge commitでマージする。

## 2026-10-03 task-186: 同じ元動画で文字起こし5方式を比較

- 目的: 約30秒の読み飛ばし・時刻のずれ・定番文の誤認識を踏まえ、本番の方式を切り替える判断材料を作る。本番runner・文字起こしエンジン・設定・ジョブのファイルは変更しない。
- 変更ファイル: backend/app/audio/transcription_comparison.py、backend/tests/test_transcription_comparison.py（新規）、docs/TRANSCRIPTION_COMPARISON_2026-10-03.md（新規）、STATUS.md。既存benchmarkの正規化・時刻集計、WAV切り出し、GPUサンプラー、atomic JSON保存を流用した計測専用コード。モデルのダウンロードと既存の完了結果の上書きを禁止する。
- 条件・実施: 指定4動画の全体をja/turbo/beam_size=5/word_timestamps/CUDA float16でA（逐次・previous既定true）/B（逐次・previous=false）/C8・C16（batched・VADあり）/D（Aの連続非無音空白3秒以上を前後2秒付きでfalse再読）で比較。RQの待機/実行中登録が0件のときだけGPUを使い、約1秒間隔で監視し、ユーザーのジョブまたは監視失敗があれば計測コンテナを停止する。元動画/モデルは読み取り専用・ネットワークなし、結果だけstorage/qa/transcription-comparison-20261003へ保存。20本の最終比較が完了した。
- Dの検証: 初回に再読文と元字幕の重なりが増えたため、現在の空白に入る語だけを追加し、別の元字幕と重なる同文の時刻補正は保留する方式へ修正。4動画でDを再実測し、時刻の重なりは全て0件。初回の結果はD-initial.jsonとして保持した。完全一致しない表記の時刻を無条件で直す仕組みではなく、幻の文を削除する処理でもない。
- 結果・推奨: 語単位の音あり空白3秒以上の合計は、卵焼きA312.2→B115.0→D41.2秒、晩酌A121.5→B81.4→D52.4秒。Bはお絵かき/夜勤事件で空白合計が増え、Cは速いが段落分割や語時刻の影響が大きい。まず雑談でBとtask-187の空白確認を組み合わせて実音声との受入確認をする候補とし、一律の本番切り替えは推奨しない。Dは確認を伴う補修の候補。B+Dは計測していない。
- 既知区間と限界: fresh Aでも指定の4欠落区間に文字があり、保存済み本番rawの欠落を再現できなかった。原因は未確定で、B/C/Dの改善と断定しない。語時刻にも長い誤割当があり、空白/定番文/文字数は正解率ではない。BGMのみの区間の定番文件数と全動画の正解字幕は未確認（音声の直接聴取機能が利用できない）。GPU最大値は他アプリを含むデバイス全体、Dの全体時間は独立したAと補修の和。保存済み本番rawへの補助D実験2本は別GPU処理の終了待ち。
- 保護・中断: 元MP4のサイズ/更新時刻4件、原本とQAのraw/silenceのSHA-256計8件が一致。最終全件テスト前後も稼働DBは446464 bytes・更新時刻2026-10-03 03:22:08.6944894 UTCで不変。途中でDocker Desktopが停止して再計測前のRQ確認ができず停止した。ユーザーの「起動して続ける」回答後、停止していた既存4コンテナを以前のイメージのまま起動して再開した。workerのimage digestは計測前と一致し、DBのサイズ/時刻は起動前後も不変。build・コンテナの再作成・コード反映・Codex中継の再起動はしていない。
- ローカル検証: Python 3.11.9でruff check . ../launcher ../scripts成功、python -m pytest全件1563 passed / 3 skipped（既存スキップ）・7 warnings。比較用24件で方式の条件、空白の3/5秒境界、語時刻、定番文・反復・時刻差、補修の切り出し・時刻補正・重なり防止、旧形式、完了時だけの保存を確認。frontendのtest（25ファイル）・lint・typecheck・通常build成功。Python 3.11/3.12・frontendのCIはPRで成功を確認してからmerge commitでマージする。比較の文書と計測コードだけのPRとし、Dockerへの反映は行わない。

## 2026-10-05 task-188: サムネ候補が見つかると保存に失敗する不具合を修正

- 症状: 宙科テンプレの通常サムネで「保存」（再生成）が毎回 `thumbnail_status=failed`、`thumbnail_error_code=TypeError` になる（export `exp_66d89b22b40d426ea676f18d64208369`）。候補抽出の状態も「候補を抽出できませんでした。」。
- 原因: task-178 の候補抽出で、アニメ顔検出（OpenCV）がNumPyの数値を返し、それを使った構図計算の `fits` が `numpy.bool` になる。保存する候補の `close_available` に `numpy.bool` が入り、書き出しメタデータのJSON保存で `TypeError: Object of type bool is not JSON serializable` になる。動画から候補が1件以上見つかる書き出しでだけ起き、これまでの候補0件の動画では表に出なかった。稼働中のworkerで再現と型を確認した。
- 修正: `backend/app/render/anime_subject.py`（検出結果を通常の float に変換）、`backend/app/render/video_subject_layout.py`（`fits` を bool に変換）、`backend/app/jobs/thumbnail_candidates.py`（保存する候補の値を float・int・bool に揃える）。回帰テスト `test_numpy_detector_values_are_saved_as_plain_json` を追加（修正前のコードで失敗し、修正後に成功することを確認）。
- 検証: Python 3.11.9 の全件 `python -m pytest -q` は 1540 passed / 3 skipped（既存のスキップ）。ロックファイルと同じ ruff 0.16.10 で `ruff check . ../launcher ../scripts` 成功（手元に入っていた ruff 0.15.4 では、既存の tests/test_subtitle_gaps.py に F811 の誤検出が出るが、0.16.10 と CI では出ない）。frontend は変更なし。
- 未確認事項: 稼働環境への反映後に、対象の書き出しで候補の抽出とサムネの保存ができること。Codexの利用状況により、Claude Code が実施した。


## 2026-10-05 task-189 文字起こしの音あり空白を1回補修

- 目的・方針: ユーザー決定の A＋D を本番のバックグラウンド処理に組み込む。PR #121 を CI 3.11・3.12・frontend 成功後、merge commit `952dc92` で取り込み、その main から作成。先頭から読む本番 ASR の前文脈の既定値は変えず、B/C への切り替えや定番の誤認識の削除は行わない。既存の品質回復経路は維持する。
- 組み込み: `runner.py` で最終的に採用した ASR 結果に対し、raw の保存・文字列後処理の直前に補修を1回行う。語時刻の空白から無音を差し引いた連続3秒以上の区間に前後2秒を足し、重なる読み直し区間を結合。読み直しだけ `condition_on_previous_text=False`・VAD なしとし、既存モデルを再利用する。品質回復の別モデルを読み込む前には旧モデルを解放し、補修後も選定・書き出しへモデルを持ち越さない。
- 保存・安全性: D v2 の区間演算・マージを `audio/transcript_repair_merge.py` に移し、比較ツールと共有。`audio/transcript_gap_repair.py` の本番用マージは既存本文を変更・削除せず、字幕が覆っていない対象空白に入る語だけを追加。空白直後の同じ正規化文は、他の既存字幕と重ならず、読み直した区間内の有効な時刻の場合だけ時刻を補正する。語時刻のない一部の行はその行全体を保護し、全行に語時刻がない旧形式はスキップする。無音検出に失敗した場合も補修はスキップ。補修途中の失敗時は部分的な結果を採用せず、元の ASR 結果で続ける。
- 由来・画面: `transcribe_faster_whisper.py` の語時刻、`repaired`、読み直した元動画の区間 `repairWindows` を保存。後処理、字幕確認の分割・結合・再書き出しでも由来を引き継ぐ。`subtitle_review.py`、`subtitle_structure.py`、frontend の字幕確認ページ・`lib/types.ts` に反映し、補った行と時刻を補正した行に「補修」を表示する。task-187 の印は現行字幕から再計算し、埋まった空白は消え、残った空白だけが表示される。
- 要約: `summaries.py` の `transcript_summary.gap_repair` に状態、追加・時刻補正・補修の件数、追加文字数、計画/実際の読み直し区間数、読み直し秒数、経過時間、区間ごとの補正・拒否の理由を記録する。失敗時も状態と例外の種類を記録し、実際に採用した追加件数は0とする。
- 処理時間の見積もり: task-186 の D 追加時間は4動画で約15〜163秒。2〜3時間の新規ジョブについて `jobs/timeouts.py` に既存の書き出し予算とは別に、元動画の長さ2回分（ASR と補修をそれぞれ実時間で行う余裕）を加える。結合済みの読み直し区間の合計は元動画の長さ以下。enqueue 時に未計測のアップロードは3時間を仮の予算として6時間を追加する。既定 fixed（通常2・Shorts3）では2時間の入力で約10時間33分、3時間/尺未計測で約12時間33分の RQ 枠。再選定・書き出しのみの枠は変更しない。これは予算の見積もりであり、CPU・全動画での完走保証ではない。
- 検証: Python 3.11.9 の `ruff check . ../launcher ../scripts` 成功。`python -m pytest -q` 全件は 1587 passed / 3 skipped（既存の FFmpeg 不在によるスキップ）。その後追加した残存空白の印の回帰テストを含む `test_transcript_gap_repair.py` 24件も成功。共有した比較ツールの既存24件も成功。frontend の `test`（25ファイル）・`lint`・`typecheck`・`build` 成功。実行前後の稼働DBは 446464 bytes、更新時刻 2026-10-04T15:24:04.6925702Z で不変。CI はPRで Python 3.11・3.12・frontend を確認してからマージする。
- 未確認事項: この版で実動画を本番実行した場合の補修品質・追加時間、ブラウザでの実際の印の確認。Dockerへの反映、実ジョブの再試行、稼働DB・既存字幕の変更はしていない。主フォルダの未コミットの task-188 反映記録は専用 worktree 外で保護し、このPRには混ぜていない。

## 2026-10-05 task-188 の稼働環境への反映（運用作業）

- 目的: main `2880316`（サムネ候補のJSON保存の不具合修正）を稼働環境へ反映する。Claude Codeが実施。
- 事前確認: RQのキュー0件・実行中の登録0件。Codex中継のrequests・processingは空。処理中の状態のジョブは、強制終了済みの `job_ea68be9806884d25aaa3dbd62a259f24` のみ（変更していない）。前回の反映からlauncherの変更なし。
- 実施: DBバックアップ `storage/backups/autoclipper-20261005-012045-before-task188-deploy.db`（integrity_check ok、jobs 17・export_items 50で元と一致）。`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker frontend`。Codex中継は再起動していない（ready、契約の指紋がmainと一致を確認）。
- 確認: backend healthy、`/health` 200、`/upload` 200、workerの av 18.1.0、稼働中のworkerに修正が入っていることを確認。workerの起動ログにエラーなし。
- 未確認事項: 対象の書き出し（exp_66d89b22b40d426ea676f18d64208369）での候補の抽出とサムネの保存（ユーザーが画面で確認する）。

## 2026-10-05 task-189 の稼働環境への反映（運用作業）

- 目的: main `89a2374`（文字起こしの読み飛ばしの補修、PR #121・#123）を稼働環境へ反映する。Claude Codeが実施。
- 事前確認: RQのキュー0件・実行中の登録0件。Codex中継のrequests・processingは空。処理中の状態のジョブは、強制終了済みの `job_ea68be9806884d25aaa3dbd62a259f24` のみ（変更していない）。前回の反映（`2880316`）からlauncherの変更なし。
- 実施: DBバックアップ `storage/backups/autoclipper-20261005-150533-before-task189-deploy.db`（integrity_check ok、jobs 17・export_items 50で元と一致）。`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker frontend`。Codex中継は再起動していない（ready、契約の指紋がmainと一致を確認）。
- 確認: backend healthy、`/health` 200、`/upload` 200、workerの av 18.1.0、補修の処理（app.audio.transcript_gap_repair）を読み込めることを確認。workerの起動ログにエラーなし。
- 未確認事項: 新しいジョブでの補修の品質・処理時間、字幕確認の画面での「補修」の印の表示（ユーザーが確認する）。既存ジョブの字幕は変わらない。

## 2026-10-06 task-191 ショート冒頭評価とキャラ別認知度

- 目的: 知名度低のキャラで、知らない視聴者にも題材が伝わるショート候補を優先する。既存・未指定のキャラは known とする。
- 変更ファイル: api/character_presets.py、schemas.py、scoring/clip_preferences.py・rule_score.py、candidates/merge_boundaries.py・codex_initial_selection.py、jobs/pipeline_common.py・runner.py・clip_plan_runner.py、clip_allocation.py。frontend は CharacterPresetManager・SettingsPanel、types.ts・characterPresets.ts と対応テスト。
- 冒頭3秒に重なる字幕segmentの文字（重なった時間に比例して切り出す）と発話秒数を使い、発話密度・具体語（数字、カタカナ、漢字2字以上の並び、既存のフック語）・弱い書き出しを0〜15点で評価する。語ごとの時刻は不要。漢字の並びは名詞の近似であり、形態素解析ではない。
- unknown のShortsだけルール採点へ加点し、日本語の弱い書き出しを追加で10点減点する。known は点数・順位不変。通常候補の順位も変更しない。opening_score は候補に保存する。
- Codexの選定プロンプト・返答スキーマは変更しない。unknown のShortsだけ confidence + 0.2 * opening_score / 15 で決定的に並べ替える。初期選定・再選定で共通処理を使い、境界補正後・多様性判定・合計本数の振り分けでも同じ補正を維持する。
- キャラ設定の共通欄に認知度を追加。保存項目・JobSettingsへ引き継ぎ、旧プリセットに切り替えた場合は known に戻す。
- 検証: Python 3.11の全件pytest 1599 passed / 3 skipped、ruff check . ../launcher ../scripts 成功。frontend test（25本）・lint・typecheck・build 成功。knownの旧点数、Codex順位、境界補正後と合計配分、プリセット保存・ジョブへの引き継ぎを回帰テストで確認。
- 稼働DBはテスト前後とも483328 bytes、更新時刻2026-10-06 01:52:20 UTCで不変。既存Dockerはbackend healthy・worker/frontend起動中を確認しただけで、変更の反映は行っていない。
- 未確認事項: 実際の動画・画面操作での受入、engaged率の改善（目標40%超）は未確認。最大15点とCodex補正0.2はデータで決めた値ではなく仮の重み。そぴあの5〜10本で運用検証する。knownへの日本語減点は別タスクで判断する。

## 2026-10-06 task-192 知名度低モードのタイトル・フック

- 目的: 出演者を知らない視聴者にも、題材が先に伝わるショートの投稿タイトルとフックを生成する。前提のtask-191はPR #125（CI 3.11・3.12・frontend成功）としてmainへmerge commitで取り込み済み。
- 変更ファイル: scoring/title_hook_suggestions.py・codex_title_hook_suggestions.py、jobs/title_hook_suggestions.py・runner.py、api/jobs.py、tests/test_unknown_audience_hooks.py・test_title_hook_suggestions.py・test_codex_title_hook_suggestions.py。
- prompt versionをtitle_hook_suggestions_v11へ更新。unknownかつshortだけ、字幕由来の題材語をhookText/publicationTitleの先頭へ置く条項を追記する。knownのプロンプト本文はv10とUTF-8 SHA256で完全一致を確認。通常動画の本文も変えない。
- audienceFamiliarityをジョブから自動生成・字幕確認での生成へ渡し、保存する入力モデル・payload・キャッシュのinput hashに含める。旧入力は未指定=knownとして読む。字幕と境界のrevision hashは維持し、既存投稿メタデータとの照合を壊さない。
- unknownのshortだけ、hookTextにclip字幕と共通する2文字以上の漢字・カタカナ・英数字の連続があることを決定的に検証する（NFKC正規化、指示語・フィラーの定数を除外）。検証に落ちた案は提示・推薦しない。Codexの推薦が不合格なら、生成順で先頭の合格案を推薦する。返答は従来どおり3案要求し、合格した1〜3案のみを保存・提示する。
- 全3案が不合格なら、既存の生成経路で1回だけ再試行する。タイトル重複による再試行と合計2回の生成を共有する。なお全案不合格ならfailedと日本語の理由を保存し、無理に採用しない。knownと通常動画では題材語検証を行わない。
- 最初の全件テストで、共通生成器を継承するサムネ表情選択のプロンプトが置き換わる影響を1件検出。出し分けをtitle_hook_suggestionsの仕事だけに限定し、継承先固有のプロンプトを保持して修正した。
- 最終検証: ruff check . ../launcher ../scripts、Python 3.11の全件pytest 1619 passed / 3 skipped、frontend test（25本）・lint・typecheck・build成功。題材語の有無・除外語、旧入力、キャッシュ更新、実際の中継へ送る本文、再試行の上限、失敗理由のAPIへの受け渡し、自動生成と推薦の変更を確認した。
- テスト前後で稼働DBは483328 bytes、更新時刻2026-10-06 01:52:20 UTCのまま。quality_gateとlauncher/codex_bridge.pyは変更不要。返答スキーマ・中継の固定値は同じで、ホスト側Codex中継の再起動は不要。Dockerへの反映は行っていない。
- 未確認事項: 実動画・画面操作での受入、そぴあの5〜10本によるengaged率40%超の効果検証は運用側で行う。task-191の最大15点・Codex補正0.2は仮の重みであり、効果を確認済みとはしない。

## 2026-10-06 task-191・192 稼働環境への反映（運用）

- 目的: main `d11936cccf8b80db7cd3d028d705c5d848522f06` の冒頭評価と低知名度向けタイトル・フック基準を、GPU構成の稼働環境へ反映する。アプリのコード変更は無し。
- 事前確認: main・未コミット変更無し、RQキューと実行中登録はいずれも0件、Codex中継の requests / processing は空。`job_ea68be9806884d25aaa3dbd62a259f24` はユーザー指定の孤立行として除外し、`detecting_scenes` の状態を変更していない。
- バックアップ: `storage/backups/autoclipper-20261006-055226-before-task191-192-deploy.db`。sqlite3 の backup() を使用し、integrity_check は ok。jobs 19件・export_items 48件が元DBと一致。
- 反映: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build backend worker frontend` が成功。redis は再作成していない。Codex中継の変更は無いため再起動していない。
- 検証: backend は healthy、worker・frontend は Up。backend の `/health`・`/api/health` と frontend の `/upload` は200。worker の av は18.1.0。backend・worker の変更対象5ファイルと frontend の CharacterPresetManager のハッシュがmainと一致。worker起動ログに ERROR / Traceback は無し。反映後もRQキューと実行中登録は0件。
- 設定: 画面に「視聴者の認知度」が表示され、宙科そぴあを「知名度低（題材優先）」で保存。再読み込み後も unknown。保存前後のAPI応答を比較し、変更はそぴあの audienceFamiliarity（known → unknown）1項目だけ。ジョブ件数は19件のまま。
- 未確認: 実動画の確認に使う元動画の指定待ちで、新しいjobはまだ実行していない。冒頭・フックの実動画での受入、3案不採用による停止頻度、engaged率の改善は未確認。15点・0.2は引き続き仮の重み。

## 2026-10-07 task-193 RQで失敗した仕事と孤立ジョブの状態同期

- 目的: RQの時間切れ・work-horseの強制終了・通常例外で、アプリのジョブが処理中のまま残る問題を防ぐ。
- 変更ファイル: `backend/app/jobs/worker.py`、新規 `worker_failures.py`・`worker_state.py`、`backend/app/api/jobs.py`、新規 `backend/tests/test_worker_failures.py`、`STATUS.md`。
- 仕組み: 固定済みのRQ 2.12.0の `Worker.handle_job_failure` を拡張する。通常例外・時間切れは子プロセスから、SIGKILLや異常終了は生存する親workerの `monitor_work_horse` から同じ処理に到達する。enqueueの on_failure だけでは、親が検知する強制終了の経路に到達しないため、この共通の処理を使用する。RQ自身の失敗・再試行処理を先に実行し、終端の FAILED / STOPPED のときだけアプリの状態を更新する。
- 対象: 元動画のジョブ実行・retry、字幕確定後の全体書き出し、候補の再選定。旧runner上の再選定関数パスも受け付ける。サムネ再生成・字幕の個別プレビュー・フックや境界の個別変更・タイトル案生成・素材収集はジョブ全体の失敗にしない。
- エラー: 時間切れは `worker_timeout`、それ以外の強制終了は `worker_terminated_unexpectedly`、通常例外は `worker_execution_failed`。RQ親側watchdogが時間超過後にSIGKILLした場合も時間切れと判定する。メッセージには停止時の current_step と status を含める。UPDATEは状態・更新時刻・処理段階が読み取り時と一致することを条件にし、completed / failed や、同時に更新されたジョブを上書きしない。
- 点検: workerの `run_maintenance_tasks` で、処理中かつ最終更新から既存APIと同じ期限を超え、対応するRQの仕事が無いジョブを失敗にする。期限は `workerHeartbeatTimeoutSeconds`、既定1800秒・最低60秒。境界値ちょうどでは失敗にしない。queued・uploaded・各確認待ち・完了・失敗、および既存の個別確認動画を準備する操作は対象外。キュー・実行中登録に加え、dequeue途中・scheduled / deferredの再試行待ちも保護し、UPDATE直前にも再点検する。Redisの状態や登録済み仕事を確認できない場合は点検を見送り、警告を出す。素材候補の期限切れ掃除も維持する。
- 検証: Python 3.11.9の `python -m pytest` は1676 passed・3 skipped。追加57件の回帰テストも最終差分で成功。実際にインストールされたRQの親側監視を使い、SIGKILLのwaitpid結果とwatchdogの時間切れを模擬して、アプリ側の失敗記録への到達を検証した。通常例外、保護対象、条件付きUPDATE、点検期限、再試行、Redisを確認できない場合も確認した。`ruff check . ../launcher ../scripts`、frontendのtest（25ファイル）・lint・typecheck・buildが成功。CIのPython 3.11 / 3.12とfrontendはPRで確認する。
- 稼働環境: DBのサイズ507904 bytes・更新時刻は全件テスト前後で一致。DBを読み取り専用で確認し、`job_ea68be9806884d25aaa3dbd62a259f24` はdetecting_scenesのまま。既存コンテナは正常起動中。Dockerへの反映、稼働ジョブの手動更新、実プロセスの強制終了による受入テストは行っていない。反映後の保守点検で対象ジョブが失敗に変わることは未確認。

## 2026-10-08 task-194 ショート親区間の比率補正

- 目的: 妥当な完成区間を持つ候補が、親区間の比率だけで却下される損失を防ぐ。10/06のtask-191・192反映記録10行も本PRに含める。
- 実装前の調査: `job_5a1b8902200e4f34b6ec222e30d926f0` の保存済み応答（requestId `7d24634e194d4c628c9c33fe4a38ea7d`）の proposal_003 は、start=2992.08 / end=3066.72、parentStart=2960.44 / parentEnd=3071.4。完成区間74.64秒、親区間110.96秒、比率1.486602357985。DBを読み取り専用で確認した動画長は8235秒。
- 後続用途: Candidateに親区間を保存し、境界補正後のショート多様化で親区間の重なり80%以上を high_parent_overlap として除外する。初期選定・再選定の両経路で使うため、補正によりその採否が変わり得る。moment_keyと完成区間は補正で変えない。字幕・フック・書き出しの区間計算は完成区間を使い、親区間を直接使わない。clip planのclipには親区間の専用項目は無い。
- 制約: 現行コードの話題window検証は完成区間start/endに適用し、親区間には適用しない。親区間は完成区間を含み、順序が正しく、元動画の範囲内である必要がある。当時のrequestファイルは残っておらず、実例の話題windowの実値は未確認。
- 調査の順序: アプリの実装前にdraft PR #128を作成し、上記の調査結果を本文へ記載した。
- 変更ファイル: `backend/app/candidates/codex_initial_selection.py`、新規 `backend/app/candidates/short_parent_range.py`、新規 `backend/tests/test_short_parent_range.py`、`STATUS.md`。比率の定数は親区間専用モジュールにまとめ、完成clipの尺ルールと区別した。
- 補正: 元の順序・完成区間の包含・元動画の範囲・話題の制約を読み取り専用で検証してから、提案のコピーの親区間を補正する。1.5未満は完成区間の中心へ1.5倍、3超は同じ中心へ3倍にし、動画端からはみ出す分を反対側に寄せる。動画が短く1.5倍を取れない場合は動画全体を最大範囲として採用する。完成区間・moment_key・根拠字幕IDは変更しない。不正な元の提案は補正で隠さず従来どおり却下する。
- 記録: 初期選定・再選定の要約に `parentRangeAdjustments` を保存する。proposalId、理由parent_ratio_adjusted、補正前後の親区間と比率、動画長の制限を受けたか（sourceLimited）を記録する。保存済みの補正記録が無い要約も読み込め、補正の無い新しい要約は従来の書式を保つ。後続の多様化は補正後の親区間を使用する。
- 検証: Python 3.11.9の `python -m pytest` は1699 passed・3 skipped（追加23件）。既存のcodex_initial_selection系44件も成功。比率1.2 / 1.4 / 1.5 / 3.0 / 3.1 / 4.0、動画端、短い動画、不正な包含・順序・動画外、検証と入力の非変更、話題window、両段階のログ保存、多様化の判定を確認した。実例と同じ座標の回帰テストでは親区間2973.42〜3085.38秒へ補正され、比率1.5で候補が残ることを確認した。ruff 0.16.10の `ruff check . ../launcher ../scripts`、frontendのtest（25ファイル）・lint・typecheck・buildが成功。CIの3.11・3.12・frontendはPRで確認する。
- 制限・未確認: プロンプト・Codex入出力モデルのAST9項目がmainと一致し、launcherの差分は無い。中継の再起動は不要。稼働DBのサイズ・更新時刻はテスト前後で一致し、Dockerの稼働環境へ反映していない。実ジョブの再選定は行っておらず、6本すべてが採用されるかは未確認。他の品質・重複判定による却下は引き続きあり得る。
## 2026-10-09 task-195 人物素材の自動・手動収集を削除

- 目的: 元動画全体の素材収集が単一workerを占有して手動操作を待たせるため、ユーザー判断で収集機能を廃止する。
- 変更ファイル: `jobs/character_asset_harvest.py`・`character_asset_harvest_state.py`・収集専用の`character_asset_frames.py`・`scoring/character_asset_classify.py`・候補APIと画面/通信/テストを削除。`runner.py`の完成時登録2か所、`queue.py`の入口、モデル、設定、router登録、保守/ストレージの収集保護・候補30日削除も除去した。
- 維持: 手動素材の登録・一覧・削除・画像配信、動画区間の`thumbnail_candidates.py`、`anime_subject.py`、予備素材を選ぶ`choose_character_asset`は維持。キャラ設定の素材件数確認・削除APIは`api/character_assets.py`へ移し、確認・削除対象を採用済み素材だけにした。旧候補はキャラ設定削除時にも残す。
- 互換: `legacy_settings.py`で`autoHarvestCharacterAssets`とsnake_caseの旧キーを読み捨て、`CharacterSettings`と`JobSettings`で読み込み/保存を受け付ける。GETは保存データを書き換えない。frontendでも旧キーを引き継がない。既存の収集/候補テーブルはdropせず、新規DBには作らない。
- 保存データ: `storage/character_asset_candidates/<preset_id>/<video_id>/<candidate_id>.png`は93ファイル・45,262,717バイト（約43.2MiB）。稼働DBは素材33行・候補93行・収集4行。読み取りだけで確認し、削除していない。
- 検証: Python 3.11.9で`cd backend; ruff check . ../launcher ../scripts`（ruff 0.16.10）成功、`python -m pytest`は1671 passed・2 skipped。新規回帰9件は旧設定GET/保存、新旧キー、既存テーブル/行と候補画像の保持、廃止API/キュー入口を確認。frontendのtest（24ファイル）・lint・typecheck・build成功。API一覧は明示廃止の6経路だけを除外して一致した。
- 稼働DB保護: 全件テスト前後で`storage/autoclipper.db`のサイズ520,192バイト・更新時刻、素材/候補/収集の件数、候補画像の件数/容量が不変。Dockerは読み取りの起動状態確認だけ（backend healthy、worker/frontend running）。実動画処理・Dockerへの反映は行っていない。CIの3.11/3.12/frontendはPRで確認する。
- 残るharvest参照: backendの旧キー除去関数・呼び出し、frontendの旧キー削除だけ。launcherは変更せず、使われなくなった`character_asset_classify`の受け付け宣言はそのまま。中継の再起動は不要。
- 反映時の注意: 削除した関数を指すharvest仕事がRedisのキュー（予約/待機を含む）に残っていないことを確認してから反映する。実行中のharvestも終了を待つ。残っているとimportに失敗する。既存候補画像の削除は後日のユーザー判断に委ねる。
## 2026-10-13 task-196 同一文字・単語の暴走も方式Dで読み直す

- 目的: wordが区間全体を被覆する文字起こしの暴走は空白として検出できないため、既存方式Dの後に独立した暴走補修を追加する。新規ジョブの文字起こし後・後処理前に既存の呼び出し経路から適用し、既存ジョブへの再適用は作らない。
- 変更ファイル: `audio/transcript_runaway_repair.py`（純関数の検出・置換と定数）、`audio/transcript_gap_repair.py`（モデルを使い回す追加パス）、`tests/test_transcript_runaway_repair.py`、本記録。
- 判定: NFKC/小文字化/空白・句読点除去の後、同じ文字または同じwordが連続し時間幅3.0秒以上なら対象。wordsがない場合だけ、同一文字10連続以上かつセグメント5秒以上を補助条件にする。普通の「わーーー」1.7秒は対象外。
- 読み直し: 暴走の前後2秒を動画内に収め、同じモデル・beam・言語でword_timestamps=True、vad_filter=False、condition_on_previous_text=False。従来の空白窓は変更/統合せず、元入力に暴走があるセグメントだけ追加で処理する。空白補修で新たに作った字幕をこの追加パスの対象にはしない。
- 置換: 読み直し全体と抽出後の結果に暴走がなく、正規化した文字の種類が元より多い場合だけ、暴走区間内の語から作ったセグメントで元セグメント全体を置き換える。区間前の正常な部分は別途保持しない。ほかの字幕と重なる場合・読み直し失敗・語の時刻がない等は元を残し、成功済みの空白補修も巻き戻さない。置換後は既存形式の`repaired`/`repair_windows`を付ける。字幕段階の長音畳み込みは変更なし。
- summary: `gap_repair`に`runaway_segment_count`、`runaway_replaced_count`、`runaway_skipped`（理由付きの配列）を追加。`windows`にもkind、元の時刻/テキスト冒頭80文字、暴走の時刻、文字種類数、置換/不採用理由を残す。`added_characters`は置換で得た文字数も加算する（暴走文字の削除による差し引きではない）。
- 実音声比較: `job_cb72fb4d6f8843c5ab4819a41699161a`の2900〜2940秒を読み取り、RQ待機/実行中/中間キュー0を0.2秒間隔で監視しながら、既存キャッシュのturbo/CUDA float16/beam5で補修。元の2912.34〜2933.24秒は全112word（`ぃ`109個と`く`/`っ`/`き`）。暴走2912.64〜2933.24秒を検出し、2910.64〜2935.24秒を読み直して10セグメント・90文字へ置換、文字の種類は4→28。処理4.445秒、モデル読み込み込み6.645秒。例:「ムズイテクッキーは!!」「待ってぇ!!!」「こんな感じだった気がする」。左端は区間内の語だけを取るため「ー!!!」が残った。音声の完全な復元・新規ジョブ全体の受入は未確認。
- 保存先/保護: 比較結果は`storage/qa/task196-runaway-repair-20261013/comparison.json`。元ジョブのraw/transcript/silence JSONのSHA256、稼働DBのサイズ/更新時刻は前後で不変。ジョブへの保存や再適用、Dockerのbuild/再起動/反映は行っていない。
- 検証: Python 3.11.9、ruff 0.16.10で`cd backend; ruff check . ../launcher ../scripts`成功、`python -m pytest`1690 passed・2 skipped。新規19件＋既存方式D24件の計43件成功。従来D本体は関数名を除くASTが同一、`merge_repair`とlauncherは差分なし。frontendのtest（24ファイル）・lint・typecheck・build成功。CIの3.11/3.12/frontendはPRで確認する。
- 未確認: 全動画で暴走が多数ある場合の処理時間、Docker反映後の新規ジョブと字幕画面の実受入。既存job_timeoutは変更していない。Codex中継の変更なし、再起動不要。
## 2026-10-13 task-197 ショートの本編上限とフック映像を分離

- 目的: 本編が75秒近い候補にフックを足すと字幕applyが422になり、未保存状態でフック編集も開けなくなる行き止まりを解消する。
- 仕様: 上限は本編のみ`shortMaxDuration`（既定75・設定範囲1〜180は維持）。フック映像は別枠0.5〜3秒、完成尺は最大で本編上限+3秒。`duration_rules.py`に`HOOK_SCENE_MIN_SECONDS`/`HOOK_SCENE_MAX_SECONDS`と`clip_body_duration`を追加し、完成尺の`completed_clip_duration`は維持した。
- backend変更: `api/clip_plan.py`、`candidates/select_candidates.py`、`jobs/clip_plan_runner.py`、`jobs/subtitle_review.py`の上限判定を本編へ変更。`api/jobs.py`の字幕フック最終検証は共有関数を通じて同じ規則になる。candidate/clip plan/review/request schemaとrenderのフック区間検証は共有定数を参照し、0.5〜3秒の範囲と本編内の条件は維持した。
- 最小尺の扱い: 品質ゲートの現物は本編だけを`shortMinDuration`と比較していた。今回指定された最小判定「本編+フック」にそろえるため、`jobs/quality_gate.py`のshort最小チェックだけ完成尺へ変更。上限は本編、通常clipの判定・探索用のshortMinDuration設定は変更なし。
- frontend変更: `lib/durationRules.ts`を同期し、ClipHookSceneEditorはフック単体0.5〜3秒で制限。ClipBoundaryEditor/ManualClipPlanEditor/ManualClipRangeEditor/候補ページは本編で上限検証・表示する。SettingsPanelに「本編の長さ（フック映像は別に最大3秒）」を表示。字幕apply失敗は保存失敗の表示に理由を添え、`lib/api.ts`で422の文字列・Pydanticエラー配列を読み、日本語のフック不正理由も表示する。
- 検証: ruff 0.16.10で`cd backend; ruff check . ../launcher ../scripts`成功、Python 3.11.9の`python -m pytest`は1723 passed・2 skipped。新規backend33件で本編72.4/75/75.1、フック0.49/0.5/3/3.1、選定・計画API・worker・字幕apply・jobs側のフック検証・品質ゲートを確認。frontendのtest（25ファイル）・lint・typecheck・build成功。SSRで本編75秒のフック追加ボタンが有効、各編集欄の同一判定、422の日本語理由を確認した。
- データ保護: `job_cb72fb4d6f8843c5ab4819a41699161a`の暫定`shortMaxDuration=78.0`はそのまま。全件検証前後で稼働DBのサイズ/更新時刻・同ジョブの設定hash・raw transcript/subtitle review/clip planのSHA256が不変。既存ジョブの保存・再適用は実施していない。
- 未確認/反映: 実画面・実動画での保存/書き出しの受入は未実施、Docker反映なし。既存コンテナは読み取りだけでbackend healthy/worker・frontend runningを確認。CIの3.11/3.12/frontendはPRで確認する。AI選定プロンプトとlauncherに差分なし、中継の再起動不要。

## 2026-10-14 task-198 完成動画ごとの制作記録

- 目的: Clip Intelligenceが手動投稿した動画と投稿タイトル一致で結び付け、成績比較に使える制作情報を長期保存する。Clip Intelligence側は変更していない。
- 変更ファイル: 新規`backend/app/production_records.py`、`backend/app/storage/paths.py`、`backend/app/jobs/runner.py`、`backend/app/maintenance.py`、新規`backend/tests/test_production_records.py`、`test_real_pipeline.py`・`test_maintenance.py`・`test_storage_lifecycle.py`、新規`docs/PRODUCTION_RECORD_CONTRACT_v1.md`、`.gitignore`、本記録。運用の制作記録JSONはGitへ入れない。
- 保存/寿命: `StoragePaths.production_record()`に集約した`storage/production_records/<export_id>.json`を`write_json_atomic`で保存する。初回revision=1、更新で+1。ジョブ削除・期限切れの掃除から独立して保持し、テストで固定した。動画とメタデータの公開・DBのcompleted更新成功後に記録し、記録の保存失敗は例外の種類とIDだけを警告する。動画をfailedへ戻さない。
- 再書き出し: 現行処理はExportItemを新IDで作り直すため、同じjob/candidateの前の記録からrevisionとcreatedAtを引き継ぎ、新IDの記録へpreviousRecordIdを保存する。旧記録は残す。公開API・既存の出力ファイル・ID生成は変更していない。
- 契約: schemaVersion=1。投稿タイトルは既存`export_download_name().stem`と同じ規則。画面文言、候補タイトル/intent/選択・推薦ID、本編/完成尺、設定にある元配信タイトル/URL、元動画内start/end、キャラ名、既存の選定情報とサムネの出どころを許可リストで出力する。フック区間は本編開始からの相対秒。絶対パス・字幕全文・連絡先/秘密設定はコピーせず、URLの認証情報・秘密クエリも除外する。親区間補正は候補IDとの対応が保存されていないため、ジョブ単位の履歴としてscope=jobを明示する。
- backfill: `python -m app.maintenance backfill-production-records`（指定なし/`--dry-run`は読み取りのみ）。`--execute`で作成、既存は`--force`なしでは保護する。force更新もrevisionを増やす。書き込みはストレージ変更ロックで直列化する。記録は書き出し確定時の状態で、完成後のサムネ編集などの反映はforce backfillで行える。
- 実DBのdry-run: SQLiteのmode=roで完成済みExportItemを検証し、対象16本・既存スキップ0・エラー0・書き込み0。production_recordsディレクトリも作っていない。検証前後で稼働DBの536,576バイトと更新時刻が不変。
- 検証: Python 3.11.9の`python -m pytest`は1737 passed・2 skipped。ruff 0.16.10の`cd backend; ruff check . ../launcher ../scripts`成功。制作記録の単体/CLI10件と、既存パイプラインでの自動作成・記録失敗でもcompleted・字幕再書き出しのrevision/履歴引き継ぎを確認。自動掃除・delete-jobs後の記録保持も確認。frontend変更は無いがtest（25ファイル）・lint・typecheck・build成功。CIの3.11/3.12/frontendはPRで確認する。
- 未確認/運用: 実動画の新規書き出しでの記録作成とClip Intelligenceでの照合は未実施。実DBでのbackfill実行とDockerのbuild/反映は行っていない。既存コンテナの読み取り確認だけでbackend healthy、worker/frontend running。launcher・Codex中継は変更なし、再起動不要。

## 2026-10-14 task-199 backfillのcreatedAtを書き出し時刻へ修正

- 目的/原因: backfillが通常保存用の生成関数へ日時を指定せず、現在時刻または既存記録のcreatedAtを使っていたため、過去の投稿と「投稿日時 >= createdAt」で結び付けられなかった。
- 変更ファイル: `backend/app/production_records.py`、`backend/tests/test_production_records.py`、`docs/PRODUCTION_RECORD_CONTRACT_v1.md`、本記録。
- 修正: backfillのdry-run・実行・force更新では、対象の`ExportItem.created_at`をUTCへ正規化してcreatedAtに指定する。SQLiteのタイムゾーン無し日時はUTCとして扱い、タイムゾーン付き日時は同じ瞬間のUTCへ変換する。JSONはISO 8601・末尾Z。updatedAtは実行時刻とcreatedAtの遅い方にし、未来の日時でもupdatedAt >= createdAtを保証する。
- 維持: 通常の書き出し完了時の日時処理、再書き出し時の日時引き継ぎ、revisionの増やし方、既存ファイル保護は変更しない。forceでは旧createdAtを引き継がず、ExportItem.created_atへ修正する。契約に「createdAt＝書き出し完了時刻。backfillも同じ」を追記した。
- 検証: ruff 0.16.10の`cd backend; ruff check . ../launcher ../scripts`成功。Python 3.11.9の`python -m pytest`は1744 passed・2 skipped。制作記録17件のうち追加7件で、新規/forceの書き出し時刻一致、末尾Z、UTC変換、updatedAtの順序、dry-run無変更、revision、通常経路の現状維持を確認。frontendは変更なしだがtest（25ファイル）・lint・typecheck・buildも成功。CIの3.11/3.12/frontendはPRで確認する。
- データ保護/未確認: 検証前後で稼働DBの536,576バイト・更新時刻、既存の制作記録16件のSHA256が不変。稼働環境でのforce backfill・Docker反映・Clip Intelligenceでの実照合は未実施。Dockerは既存コンテナの起動状態を読み取っただけでbackend healthy、worker/frontend running。launcher・Clip Intelligenceに変更なし。

## 2026-10-14 task-200 古い作業記録を月別アーカイブへ移動

- 目的: STATUS.mdの冒頭の既存節と直近の記録を保持し、2026-09-30以前の作業履歴を月別に参照できるようにする。
- 変更ファイル: `STATUS.md`、`docs/status_archive/STATUS_2026-06.md`・`STATUS_2026-07.md`・`STATUS_2026-08.md`・`STATUS_2026-09.md`、`AGENTS.md`。アプリコード・設定は変更していない。
- 移動: 6月40件・7月74件・8月59件・9月134件の計307件。日付のない7節と10月以降の38件は原文のまま残した。索引は月別リンクと、折りたたみの見出し一覧を元の順序で掲載した。
- 運用メモ: 有料Platform APIの廃止とCodex利用、キルゴUかなNBのローカル限定、使用済み区間の保持と元動画尺変更の停止、字幕確認から尺調整へ戻る際の保全を要約し、元の記録へリンクした。初期仕様を残す冒頭の既存節は編集していない。反映・DBバックアップ手順は10月の運用記録にもあり、そのまま残る。
- 検証: 変更前のバイト列を保存してスクリプトで照合。元の全見出し1301出現の数が一致し、日付付き345件はSTATUSまたは月別アーカイブに各1回だけ存在する。移動した本文734,659バイトは改行・空白を含め完全一致し、月内順序・全体の移動順序、冒頭と10月記録も不変。GitステージのLF表現でも724,187バイトが元のGit本文と一致した。git diff --checkはアーカイブ4件の元からある末尾空行を警告するが、原文の改行を保持するため削っていない。CIのbackend（3.11/3.12）とfrontendはPRで確認する。実装変更は無いためローカルのアプリ全件テスト・Docker反映は実施していない。

## 2026-10-14 task-201 字幕確認画面の補助関数と型をlibへ切り出す

- 目的: 字幕確認ページのコンポーネント外の補助関数・型を役割別の小さなファイルへ移し、見た目・動作・既存の比較規則を変更せずに読みやすくする。
- 変更ファイル: `frontend/app/jobs/[jobId]/subtitles/page.tsx`、新規`frontend/lib/subtitleReview/{display,preview,text,suggestions,posting,drafts,framing}.ts`、新規`frontend/tests/subtitleReviewHelpers.test.ts`、本記録。backend・launcher・設定には変更なし。
- 移動: 表示・時刻4関数、プレビュー/表示判定3関数、文言整形2関数、生成入力/ハッシュ2関数、投稿文4関数、下書き3関数+1型、画角比較2関数+1型の計20関数・2型。名前と宣言本文はexport追加以外の文字を変更せず、TypeScriptの宣言位置から抽出した文字列で照合。コンポーネント本体も文字単位で一致した。page.tsxは3695行→3428行。
- 統合は見送り: `youtubePosting.ts`のhashtagsFromText/PostingMetadataDraftと投稿文の役割、`subtitlePreview.ts`の文言正規化、`clipBoundaryTime.ts`の時刻処理を将来の整理候補としてPRに列挙する。特にハッシュタグの大小文字の比較・12件制限が異なるため、このPRでは共有化していない。
- 検証: frontendのlint・typecheck・test（追加1件を含む26ファイル）・build成功。下書きの既定値/公開タイトル/投稿情報/字幕書式、未保存変更、書式の等価性、ハッシュタグの区切り/重複/大小文字/件数、各種改行と2行制限を確認。タグ欄だけの値差をisClipContentDirtyが判定に含めない現状も維持し、テストに記録した。git diff --check成功。CIのbackend（3.11/3.12）とfrontendはPRで確認する。
- 停止条件/未確認: ユーザー指示によりPRとCI成功で停止し、マージしない。レビューとユーザーの画面確認は未実施。Dockerのbuild/反映、実ジョブでの画面操作・保存は行っていない。

## 2026-10-15 task-202 字幕確認画面の本体をコンポーネントとフックへ分割

- 目的: 字幕確認ページを役割別に分け、見た目・操作・API呼び出しの条件/引数/順序/タイミングを維持する。task-203/204の変更は含めない。
- 変更ファイル: `frontend/app/jobs/[jobId]/subtitles/page.tsx`、新規`frontend/components/subtitleReview/`の8ファイル、新規`frontend/lib/subtitleReview/hooks/`の12ファイル、`frontend/tests/subtitleReviewActions.test.ts`、本記録。backend・launcher・CSS・API実装・依存パッケージは変更していない。
- 構成: clip一覧、プレビュー、字幕一覧/編集、タイトル/フック/投稿文、フック映像、文字書式/画角、下部操作をpropsで接続する。state/refは専用フックへ、41内部関数は更新ガード・プレイヤー・字幕編集・内容下書き・タイトル案・確定操作の6フックへ移した。page.tsxは3428行→9行、画面組み立てのSubtitleReviewScreenは101行。状態管理ライブラリは追加していない。
- 動作の照合: 分割前のmain `9da16f9`から保存したASTと比較し、41関数の処理本文と捕捉する値、14effectの本文/依存配列、59初期化文、65派生値、state/memo/effectの登録順が一致した。新コンポーネントを展開したJSXも、元のDOM構造・表示条件・文言・イベント・ref・key・既存子コンポーネントのpropsと一致。比較用のsnapshot/スクリプトはGit管理外の`.codex_tmp`で実行した。
- effect: useEffect 13件・useLayoutEffect 1件の依存配列変更は0件。安定したsetter/refを引数から受け取ることによるESLintの推論上の警告には、元の依存配列の直前だけに注釈を付けた。React Compilerの規則・eslint設定は変更していない。API対応表と14依存配列をPR本文に記載する。
- 検証: frontendのlint・typecheck・test（追加1件を含む27ファイル）・build成功。追加テストはmocked HTTPで、queued previewでもapplyできること、タイトルとdirty字幕の送信/他clipの未保存字幕保全、未保存変更/未完成previewの操作制限、成功後の遷移、フック更新・一括保存・422の理由表示と更新ガード解除を確認した。backendのローカル検証は実行していない（変更なし）。CIのbackend 3.11/3.12・frontendはPRで確認する。
- 停止条件/未確認: PRとCI成功で停止し、マージしない。実ブラウザでの操作・保存/書き出しの受入は未確認。Dockerのbuild/反映、実jobのAPI取得・編集は行っていない。レビューとユーザーの画面確認の後にマージを判断する。

## 2026-10-15 task-203 字幕空白の確認操作と一覧表示を廃止

- 目的: 字幕空白についてはプレビューの注意マーカーだけを残し、一覧内の空白行・確認操作・件数表示を廃止する。
- 変更ファイル: `frontend/components/SubtitleGapMarkers.tsx`、`frontend/components/subtitleReview/{ReviewClipList,ReviewSubtitleSegments}.tsx`、`frontend/lib/{api,subtitleGaps}.ts`、`frontend/lib/subtitleReview/hooks/{context,useSubtitleEditing,useSubtitleReviewDocument,useSubtitleReviewState}.ts`、`frontend/tests/subtitleGaps.test.ts`、本記録。backend・launcherには変更なし。
- 表示/操作: SubtitleGapRowと確認ボタン、clip一覧/字幕編集欄の「字幕なし○か所」を削除。プレビューの橙色マーカー・区間のtooltip/読み上げラベルとクリックでのシーク/一時停止は維持する。マーカーの凡例からも件数だけを外し、acknowledgedのtrue/falseによる表示差はなくした。字幕行の時刻順と元のsegmentIndex、構成変更/一括修正、停止位置からの追加、clipのOK/確定操作は維持する。
- 削除したfrontend専用処理: acknowledgeSubtitleReviewGap、acknowledgeGap、確認中のstateと編集ガードへの条件、mergeSubtitleGapAcknowledgement、unacknowledgedSubtitleGaps、字幕と空白を混在させるsubtitleTimeline/SubtitleTimelineItemと対応するview-model項目。アプリ側の参照が残っていないことを検索で確認した。
- 互換性: backendの空白検出とPATCHの確認APIは残した。SubtitleReviewGapはマーカーとAPI応答で使うため残し、既存のacknowledged値は応答型として受け取るが表示条件には使わない。保存データを読み替えて書き戻す処理は追加していない。
- 検証: frontendのlint・typecheck・test（27ファイル）・build成功。SSRとクリックの回帰テストで確認済み/未確認のマーカー表示が一致すること、2区間の位置/幅、pause→seek、保存済みフラグの不変、gapsなし/空/尺0の互換、空白行/件数/確認ボタンの非表示、字幕行の時刻順/元配列の不変、字幕なし時の表示、clipの確認状態とOK操作の維持を確認。git diff --check成功。CIはPRで確認する。
- 未確認/反映: 実ブラウザでの受入確認、稼働環境への反映、既存jobの取得/編集は未実施。backendのローカル検証は実行していない（変更なし）。


## 2026-10-15 task-204 字幕確認を下書き編集と1回の確定へ変更

- 目的: 字幕・画角・タイトル・フック文言/映像・書式・投稿文を待たずに編集し、clipの確定1回でまとめて保存、正式プレビューを1回だけ依頼する。
- 変更ファイル: backendの`api/{jobs,_job_common}.py`、`jobs/{subtitle_review,subtitle_review_preview,queue,runner}.py`、`render/render_exact_review_preview.py`、`schemas.py`と関連テスト。frontendの`components/subtitleReview/`、既存の画角/フック/一括修正部品、`lib/subtitleReview/`の下書き・再生・各hook、`lib/{api,types}.ts`と関連テスト。本記録。launcher変更なし。
- 保存/生成: segments・structure・hook-scene・settings・旧framing保存は正式表示をstale/未確定へ戻すだけ。previewDeferredを保存し、後続GETからも正式生成を再開させない。apply/finalizeで正式生成を許可し、applyの任意framingで画角も同時保存する。手動確認の初回準備と旧hook workerは文字なしlive動画のみ。自動/shadow/guardedの初回品質ゲートに必要な正式プレビューと、最終書き出しの尺/品質/全clip確定/準備完了検証は従来どおり維持する。
- 簡易プレビュー: 既存live specは字幕文字・文字スタイル・タイトル・フック文言を含まないため、文字だけの変更では再生成しない。映像区間・フック映像区間・画角/配置/帯が変わるとliveを更新する。人物追従では字幕の時刻区切りも追従窓に関係する。未保存のフックはブラウザで既存live動画の再生順序を組み替え、映像と音声を確認できる。保存済みliveの古いフック長も別に保持して時刻を正しく対応させる。画角は既存canvas方式を使用する。
- 下書き/表示: 字幕文字・一括修正・フック映像・画角はローカルで保持し、applyにまとめる。構成変更はIDが変わるため即時保存を維持する。localStorageへclip別に保管し、移動/再読み込みで復元、確定または外部の文書変更で破棄する。プレビュー完了やポーリング時刻だけでは破棄しない。保存禁止/容量不足はtry/catchで保護する。「このショートを確定」/「この動画を確定」、未保存件数、正式作成中を表示し、他clipの編集を妨げない。
- キュー/失敗: liveのみの仕事と正式生成を別のRQ IDにし、同じspecのlive処理中に確定依頼が吸収されるのを防ぐ。liveの失敗も理由を表示し、明示的な再試行まで再登録しない。
- 生成回数の比較: 同一clipの「字幕文字保存→分割→帯設定→apply」で旧main b77125dは正式enqueue 4件（hashも4種）、変更後は1件。隔離DBのTestClientで旧ルーターと新規回帰テストを比較した。初回画面準備を除く要求件数で、実動画のFFmpeg処理回数/所要時間の測定ではない。
- 検証: ruff 0.16.10の`cd backend; python -m ruff check . ../launcher ../scripts`成功。Python 3.11.9の`python -m pytest -q`は1751 passed・2 skipped。frontendのlint/typecheck/test（28ファイル）/build成功。正式生成の保留・単一apply・finalizeの409ゲート、normal/shortのlive-onlyで正式MP4/ASSを作らないこと、旧hook worker、RQ ID、live失敗/再試行を確認。下書きの単一送信、保存/復元/破棄/保存不能、hook/bodyの時計対応、旧liveのフック長もテストした。
- ブラウザ検証: 別ポートの架空APIと合成MP4だけを使用。タイトル・字幕・3秒フックを下書きで編集→別clipへ移動→再読み込みで復元→apply1件に全項目が含まれる→未保存0・正式作成中→他clip編集可能を確認。稼働API/DB・Codexへは接続していない。テスト前後で稼働DBの536,576 bytes・更新時刻2026-10-14T14:12:33.1189291Zが不変。
- 未確認/反映: 実動画と稼働環境でのユーザー受入は未実施。Docker Desktop Linuxエンジン停止のため既存コンテナの起動確認はできていない。Dockerのbuild/反映、稼働jobの取得/編集は行っていない。Codex中継の変更・再起動は不要。PRとCI確認後、レビュー/ユーザー確認のため未マージで止める。


## 2026-10-15 task-205 Clip Intelligence統合① YouTube接続と自チャンネル同期

- 目的/範囲: Clip Intelligenceの本人OAuthと公式統計の取得をAutoClipperへ移す。参照元は読み取りのみ。制作記録のDB結合・Codex分析・派生集計/制作反映・分析画面・既存データ移行・旧アプリ停止は含めない。既存の切り抜きrunner/選定/字幕処理とlauncherは変更しない。
- 変更ファイル: 新規`backend/app/intelligence/`（models/credentials/oauth/secret_files/youtube_client/collection/ingest/sync/queue/policy/maintenance/schemas/common）、新規`api/intelligence.py`、既存のconfig/db/main/storage paths/worker、pyprojectと2つのrequirements lock、composeとGit/Docker除外。frontendの新規settingsページ・YouTubeConnectionSettings・lib/intelligenceとuploadの設定リンク。新規backend/frontendテスト、API一覧契約、`docs/INTELLIGENCE_YOUTUBE_SYNC.md`、本記録。
- DB: channels/channel_connections/youtube_videos/video_daily_stats/sync_runsの5テーブルをcreate_allで追加。既存テーブルの列は変更しない。トークンはDBに保存しない。日次/期間集計、チャンネル/動画、公開/内部の出所を混同しない。
- 認可: Desktopループバックの既定URLはhttp://localhost:8000/api/intelligence/oauth/callback（設定でループバックhost/portのみ変更可）。youtube.readonly/yt-analytics.readonlyの2スコープ、10分・1回限りのstate、HttpOnly/SameSite cookie、PKCEを使用。指定したチャンネルIDとmine=trueの取得結果が一致した場合だけ保存する。認可開始と同期POSTは外部Originを拒否する。
- 秘密情報: Googleクライアント設定はユーザーがstorage/secrets/google-client.jsonへコピーする。トークンはStoragePathsに集約したstorage/secrets/youtube_tokens/<channel_external_id>.jsonへ、一時ファイルを600で作り置換（親700、Linux）。state一時情報も同様。GitとDocker build contextからsecretsを除外。OAuthライブラリの資格情報debugログ、callbackアクセスログのqueryを抑止し、API/例外には許可リストの理由だけを返す。実際の資格情報の値は開いていない。
- 同期: HTTPではRQ登録だけ。同じチャンネルの実行中claimはuniqueで二重登録を409にする。最新200本＋追跡済みの旧動画を更新し、公開動画だけ登録する。公開のviews/likes/comments、内部の10指標を取得。チャンネル日次60日、最終返却日から28日/前28日、動画別日次60日/28日、公式creatorContentType、公開翌日から7暦日（新しい順50本）を保存する。集計日はAmerica/Los_Angeles。件数上限による打切りはpartialとして表示する。
- 欠損/失敗: NULLはUNAVAILABLE、空レポートはNO_ROWS。0にせず、負数likes・100%超の平均視聴割合も公式値のまま保存。invalid_grant/401は再接続が必要へ。利用枠/権限エラーはRQとsync_runsをfailedにする。通信中にDB書き込みロックを保持せず、取得後一括commit、失敗時は前回の成功分を保つ。実行のAPI期限は既定120秒・最大90要求、各I/O timeout最大10秒、RQ hard timeoutは150秒（設定上限+30秒）。強制終了/孤立した同期はworker失敗処理/保守で記録する。
- 保持条件: 2026-10-15のユーザー決定に基づきderived_allowed/extended_storageは既定true、確認日と追加ポリシーURLをconfigに保存。統計は取得から最大36暦月。タイトル・名前等は30日更新できなければ消す。extended_storage=falseなら統計も30日。workerのrun_maintenance_tasksで期限処理し、切り抜き出力の掃除からは独立させる。この段階で独自の派生指標は作らない。
- 画面: /settingsにYouTube連携を追加。接続/再接続/同期、接続状態、最終成功日時、今回の結果、最新返却日、NO_ROWSを表示する。接続成功と統計取得成功は別に扱う。
- 依存: uv 0.12.22で実行用/dev用universal lockを再生成し、同じコマンドで再生成してSHA256不変を確認。既存pin変更なし、新規13パッケージ（google-auth-oauthlib 1.5.0/google-auth 2.62.0と推移依存、tzdata等）。Python 3.11/3.12の既存NumPy分岐、av 18.1.0/faster-whisper 1.2.1は維持する。
- ローカル検証: Python 3.11.9の`python -m pytest -q`は1777 passed・2 skipped。ruff 0.16.10の`cd backend; python -m ruff check . ../launcher ../scripts`成功。frontendのlint/typecheck/test（29ファイル）/build成功。OAuth/state/本人不一致/権限不足/トークン非表示/atomic保存失敗/invalid_grant/欠損/期間/再同期/二重登録/キュー失敗/時間制限/強制終了/DBロック回避/保持期限/既存schema不変をモックと隔離DBで確認した。
- compose/ブラウザ: task205-validationの専用CPU構成、専用DBボリューム、18050/13050ポートでbuild/起動。最終APIは読み取り専用source bindでも起動確認した。backend healthy、worker/frontend/redis running、/healthと/settingsが200、5テーブル作成、Linuxの合成トークンファイル600、av 18.1.0/faster-whisper 1.2.1を確認。ブラウザでも連携設定画面を確認。外部Originの同期POSTは403。検証専用コンテナ・ボリューム・イメージは終了後に削除した。稼働コンテナの作り直しは行わず、稼働DBの536,576 bytes・更新時刻2026-10-14T23:52:24.2735236Zが検証前後で不変。
- 未確認: 実際のGoogle認可・実チャンネル同期は未実施（ユーザーが反映後に行う）。既存チャンネル/過去統計/手入力データは移行していない。CIの3.11/3.12/frontendはPRで確認し、成功後もレビュー待ちで未マージとする。稼働環境へは未反映、Codex中継の変更/再起動なし。
