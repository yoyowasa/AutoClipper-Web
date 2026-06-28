# AutoClipper Web Status

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

## 2026-06-28 Task 01 Repository scaffold

### 目的

AutoClipper の初期 monorepo scaffold を作る。

### 変更ファイル

- `README.md`
- `AGENTS.md`
- `STATUS.md`
- `.env.example`
- `.gitignore`
- `.dockerignore`
- `package.json`
- `package-lock.json`
- `docker-compose.yml`
- `backend/Dockerfile`
- `backend/.dockerignore`
- `backend/pyproject.toml`
- `backend/app/__init__.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/tests/test_health.py`
- `frontend/Dockerfile`
- `frontend/.dockerignore`
- `frontend/package.json`
- `frontend/next.config.ts`
- `frontend/next-env.d.ts`
- `frontend/tsconfig.json`
- `frontend/tailwind.config.ts`
- `frontend/postcss.config.mjs`
- `frontend/eslint.config.mjs`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/app/page.tsx`
- `storage/uploads/.gitkeep`
- `storage/temp/.gitkeep`
- `storage/outputs/.gitkeep`

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 2 passed, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- local backend 起動後 `http://127.0.0.1:8000/health`: `{"status":"ok"}`。
- local frontend 起動後 `http://127.0.0.1:3000`: 200、期待テキスト表示確認。
- `docker compose config`: 未実施。`docker` コマンド未検出。

### 未解決事項

- Docker Desktop / Docker CLI 導入後に `docker compose up --build` の本検証が必要。
- `npm audit --omit=dev` の Next.js 内包 PostCSS moderate 警告。

## 2026-06-28 Initial FastAPI data model and API routes

### 目的

SQLite を使い、`Video` / `Job` / `ExportItem` と初期 API routes を実装する。

### 変更ファイル

- `.env.example`
- `.gitignore`
- `backend/pyproject.toml`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/ids.py`
- `backend/app/api/__init__.py`
- `backend/app/api/videos.py`
- `backend/app/api/jobs.py`
- `backend/app/api/exports.py`
- `backend/app/storage/__init__.py`
- `backend/app/storage/paths.py`
- `backend/tests/test_api_routes.py`

### 実装内容

- `POST /api/videos/upload`: `storage/uploads` に保存し、`Video` record を作成。
- `POST /api/jobs`: 既存 `Video` に対して `queued` status の `Job` record を作成。
- `GET /api/jobs/{job_id}`: job status を返却。
- `GET /api/jobs/{job_id}/results`: `ExportItem` を normal / short に分けて返却。
- `GET /api/jobs/{job_id}/download.zip`: 生成済み ZIP がある場合のみ返却。
- `GET /api/exports/{export_id}/download`: 生成済み export MP4 がある場合のみ返却。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 8 passed, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `Get-Command docker`: 未検出。

### 未解決事項

- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- 実動画処理、worker、実 export 生成は未実装。

## 2026-06-28 RQ worker and dummy AutoClipper job

### 目的

RQ worker で dummy AutoClipper job を実行し、status 進行、fake export、ZIP 生成まで通す。

### 変更ファイル

- `README.md`
- `.env.example`
- `docker-compose.yml`
- `backend/pyproject.toml`
- `backend/app/config.py`
- `backend/app/api/jobs.py`
- `backend/app/storage/paths.py`
- `backend/app/jobs/__init__.py`
- `backend/app/jobs/status.py`
- `backend/app/jobs/runner.py`
- `backend/app/jobs/queue.py`
- `backend/app/jobs/worker.py`
- `backend/tests/test_api_routes.py`

### 実装内容

- `POST /api/jobs` 後に RQ へ dummy job を enqueue。
- worker entrypoint `python -m app.jobs.worker` を追加。
- dummy job で成功系 status を `queued` から `completed` まで更新。
- `storage/outputs/{job_id}` に placeholder MP4、metadata JSON、`download.zip` を生成。
- dummy `ExportItem` を normal 2件、short 3件作成。
- `docker-compose.yml` に `worker` service を追加。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 9 passed, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `Get-Command docker`: 未検出。

### 未解決事項

- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- placeholder MP4 は実動画ではない。実レンダリングは後続 Phase。

## 2026-06-28 Next.js frontend upload flow

### 目的

Next.js frontend で upload -> job progress -> results の導線を実装する。

### 変更ファイル

- `frontend/app/page.tsx`
- `frontend/app/upload/page.tsx`
- `frontend/app/jobs/[jobId]/page.tsx`
- `frontend/app/results/[jobId]/page.tsx`
- `frontend/components/UploadDropzone.tsx`
- `frontend/components/SettingsPanel.tsx`
- `frontend/components/JobProgress.tsx`
- `frontend/components/ProgressTimeline.tsx`
- `frontend/components/ResultVideoCard.tsx`
- `frontend/components/StatusBadge.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `frontend/lib/format.ts`
- `STATUS.md`

### 実装内容

- `/upload`: video upload、settings、job 作成、`/jobs/{jobId}` へ遷移。
- `/jobs/[jobId]`: 2秒間隔で job status polling、completed 時に results link 表示。
- `/results/[jobId]`: normal clips、shorts、MP4 download、ZIP download を表示。
- 手動編集、手動 trimming、approve/reject UI は未実装。

### 検証結果

- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 9 passed, 1 warning。

### 未解決事項

- ブラウザでの実操作 E2E は未実施。理由: Docker CLI 未検出で backend/worker/redis の compose 本検証不可。
- 実動画処理は未実装。結果は dummy worker の placeholder export 前提。

## 2026-06-28 FFmpeg and ffprobe wrappers

### 目的

FFmpeg / ffprobe の薄い wrapper を追加し、後続 worker から使える動画処理基盤を作る。

### 変更ファイル

- `backend/Dockerfile`
- `backend/app/video/__init__.py`
- `backend/app/video/probe.py`
- `backend/app/audio/__init__.py`
- `backend/app/audio/extract.py`
- `backend/app/render/__init__.py`
- `backend/app/render/filters.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `backend/tests/test_ffmpeg_wrappers.py`
- `STATUS.md`

### 実装内容

- `video/probe.py`: duration, width, height, fps, has_audio を ffprobe JSON から取得。
- `audio/extract.py`: mono 16k wav 抽出 command と実行関数を追加。
- `render/render_normal.py`: start/end clip、ASS subtitle burn、optional loudnorm に対応。
- `render/render_short.py`: 1080x1920 center crop、ASS subtitle burn、optional loudnorm に対応。
- `backend/Dockerfile`: backend / worker container 用に `ffmpeg` package を追加。
- HTTP handler には FFmpeg 実行を追加していない。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 16 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- API handler 内の FFmpeg 呼び出し検索: 該当なし。
- `Get-Command ffmpeg`: 未検出。
- `Get-Command ffprobe`: 未検出。
- `Get-Command docker`: 未検出。

### 未解決事項

- tiny fixture integration test は skip。理由: local PATH に `ffmpeg` / `ffprobe` が無い。
- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- wrappers は未接続。実 worker での本処理接続は後続 Phase。

## 2026-06-28 faster-whisper transcription wrapper

### 目的

wav から `transcript_segments.json` を出力する transcription wrapper と将来の OpenAI 差し替え interface を作る。

### 変更ファイル

- `backend/pyproject.toml`
- `backend/app/audio/transcribe_faster_whisper.py`
- `backend/tests/test_transcribe_faster_whisper.py`
- `STATUS.md`

### 実装内容

- `TranscriptSegment`: `start`, `end`, `text`, optional `confidence` の Pydantic model。
- `TranscriptionEngine`: `transcribe(wav_path)` protocol。
- `FasterWhisperTranscriptionEngine`: faster-whisper lazy import、segments 変換、word probability 由来 confidence 対応。
- `OpenAITranscriptionEngine`: placeholder。呼び出し時は `NotImplementedError`。
- `write_transcript_segments`: `transcript_segments.json` 形式の JSON list を書き出し。
- `transcribe_wav_to_json`: engine 実行から JSON 書き出しまでを実行。
- HTTP handler には transcription 実行を追加していない。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 24 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- API handler 内の transcription 呼び出し検索: 該当なし。
- `Get-Command docker`: 未検出。

### 未解決事項

- `faster-whisper` 実モデルでの実音声 transcription は未検証。テストは fake model / fake engine。
- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- worker への transcription 接続は後続 Phase。

## 2026-06-28 Scene and audio feature extraction

### 目的

scene segments、silence segments、audio features、visual quality の JSON 出力基盤を作る。

### 変更ファイル

- `backend/pyproject.toml`
- `backend/app/video/scene_detect.py`
- `backend/app/video/black_screen.py`
- `backend/app/audio/silence_detect.py`
- `backend/app/audio/volume_features.py`
- `backend/tests/test_feature_extraction.py`
- `STATUS.md`

### 実装内容

- `video/scene_detect.py`: PySceneDetect lazy wrapper、`scene_segments.json` writer、boundary から start/end pair 生成。
- `audio/silence_detect.py`: FFmpeg `silencedetect` command builder、log parser、`silence_segments.json` writer。
- `audio/volume_features.py`: wav peak 読み取り、`silence_ratio`、`speech_density`、`volume_peak`、`audio_features.json` writer。
- `video/black_screen.py`: FFmpeg `blackdetect` command builder、log parser、`visual_quality.json` writer。
- HTTP handler には feature extraction 実行を追加していない。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 40 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- API handler 内の feature extraction 呼び出し検索: 該当なし。
- `Get-Command docker`: 未検出。

### 未解決事項

- PySceneDetect / FFmpeg 実入力での integration は未検証。
- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- worker への feature extraction 接続は後続 Phase。

## 2026-06-28 Candidate generation

### 目的

transcript segments、scene segments、silence segments、settings から short / normal 候補を大量生成する。

### 変更ファイル

- `backend/app/candidates/__init__.py`
- `backend/app/candidates/merge_boundaries.py`
- `backend/app/candidates/generate_short_candidates.py`
- `backend/app/candidates/generate_normal_candidates.py`
- `backend/tests/test_candidate_generation.py`
- `STATUS.md`

### 実装内容

- `Candidate`: `id`, `type`, `start`, `end`, `duration`, `transcript_text`。
- `CandidateGenerationSettings`: default short `20-75` 秒、normal `90-600` 秒。
- `merge_boundaries`: transcript / scene / silence の境界を統合。
- `generate_short_candidates`: short 候補を生成。最終本数ではなく多数候補を返す。
- `generate_normal_candidates`: normal 候補を生成。最終本数ではなく多数候補を返す。
- start/end が発話中に入る場合、近い発話境界へ寄せる。寄せられない候補は除外。
- HTTP handler / worker にはまだ接続していない。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 47 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- API handler 内の candidate generation 呼び出し検索: 該当なし。
- `Get-Command docker`: 未検出。

### 未解決事項

- 実 transcript / scene / silence artifact を使った大規模候補数の実測は未実施。
- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- worker への candidate generation 接続は後続 Phase。

## 2026-06-28 Rule scoring and candidate deduplication

### 目的

候補へ rule_score を付与し、時間重複と近似 transcript による重複候補を削減する。

### 変更ファイル

- `backend/app/candidates/merge_boundaries.py`
- `backend/app/candidates/deduplicate.py`
- `backend/app/scoring/__init__.py`
- `backend/app/scoring/rule_score.py`
- `backend/tests/test_scoring_and_deduplicate.py`
- `STATUS.md`

### 実装内容

- `Candidate` に optional `rule_score` を追加。
- `rule_score.py`: hook keywords、silence ratio、speech density、duration fit、transcript length、incomplete start/end penalty、audio peak を scoring。
- `score_candidates(...)`: 全候補に `rule_score` を付与した候補リストを返す。
- `deduplicate.py`: 高い時間 overlap と近似 transcript text を削減。
- dedup は既定で同一 type 内のみ。必要時は `deduplicate_across_types=True`。
- API handler / worker にはまだ接続していない。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 57 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- API handler 内の scoring / dedup 呼び出し検索: 該当なし。
- `Get-Command docker`: 未検出。

### 未解決事項

- 実候補データでの score 分布調整は未実施。
- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- worker への scoring / dedup 接続は後続 Phase。

## 2026-06-28 OpenAI Structured Outputs candidate scoring

### 目的

OpenAI Structured Outputs で候補を採点し、retry、rejection、cache、batch scoring を実装する。

### 変更ファイル

- `backend/pyproject.toml`
- `backend/app/candidates/merge_boundaries.py`
- `backend/app/scoring/score_schema.py`
- `backend/app/scoring/openai_score.py`
- `backend/app/jobs/runner.py`
- `backend/tests/test_openai_score.py`
- `STATUS.md`

### 実装内容

- strict JSON schema `clip_candidate_score` を追加。
- `ClipCandidateScore`: `should_use`, `final_score`, component scores, `title`, `overlay_title`, `reason`, `risk_flags` を検証。
- `OpenAICandidateScorer`: OpenAI Responses API 呼び出し、transient error retry、Structured Outputs parse。
- repeated failure 時は候補を `should_use=False`、`reject_reason=openai_scoring_failed: ...` にする。
- cache は candidate hash + transcript/features 入力で保存。
- request payload は transcript と features のみ。video file/path は送らない。
- `score_candidate_batch(...)` で worker から候補 batch を採点可能。
- `jobs.runner.score_candidate_batch_for_worker(...)` を追加し、worker 層から batch scoring を呼べる受け口を作成。
- API handler にはまだ接続していない。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 68 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- API handler 内の OpenAI scoring 呼び出し検索: 該当なし。
- worker runner wrapper の mock scoring test: passed。
- OpenAI 実API呼び出し: 未実施。mock client tests のみ。
- `Get-Command docker`: 未検出。

### 未解決事項

- 実APIでの smoke test は未実施。key は実行環境側で供給される前提。
- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- 実ジョブ pipeline 内での candidate generation / scoring / render 連結は後続 Phase。

## 2026-06-28 Quality gate and final candidate selection

### 目的

候補に quality gate をかけ、normal clips と shorts を別々に最終選定し、`selected_clips.json` を保存する。

### 変更ファイル

- `backend/app/scoring/quality_gate.py`
- `backend/app/candidates/select_candidates.py`
- `backend/tests/test_quality_gate_and_selection.py`
- `STATUS.md`

### 実装内容

- `QualityGateSettings` / `QualityGateResult` を追加。
- max silence ratio、min speech density、incomplete sentence、low final_score、model rejected を個別候補単位で reject。
- `final_score` が無い場合は `ai_score`、次に `rule_score` を選定 score として使用。
- normal / short を分けて選定。
- 高 overlap 候補を reject し、次点候補から auto-refill。
- 個別候補が落ちても job 全体を失敗させない戻り値にした。
- `select_and_write_candidates(...)` で `selected_clips.json` を保存。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend\tests\test_quality_gate_and_selection.py`: 4 passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 72 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `Get-Command docker`: 未検出。

### 未解決事項

- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- 実ジョブ pipeline への `selected_clips.json` 保存接続は後続 Phase。

## 2026-06-28 ASS subtitle generation

### 目的

選定済み clip ごとに、candidate 範囲へ clip した transcript から ASS 字幕を生成する。

### 変更ファイル

- `backend/app/render/subtitles_ass.py`
- `backend/tests/test_subtitles_ass.py`
- `STATUS.md`

### 実装内容

- `format_ass_timestamp(...)`: ASS centisecond timestamp を生成。
- `split_subtitle_lines(...)`: 最大2行の字幕 text に整形。
- `clipped_transcript_segments(...)`: transcript segment を candidate 範囲へ切り、clip start 相対時刻へ変換。
- `SubtitleLayout.short()`: 1080x1920 shorts 用の大きい subtitle / title style。
- `SubtitleLayout.normal(...)`: normal clip の元解像度/aspect 用 style。
- lower subtitle safe area と shorts 用 optional top title overlay に対応。
- `write_ass_for_selected_clips(...)`: normal clips / shorts の各 selected clip に `.ass` を保存。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend\tests\test_subtitles_ass.py`: 5 passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 77 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `Get-Command docker`: 未検出。

### 未解決事項

- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- 実 job pipeline での ASS 生成呼び出しと render への subtitle path 受け渡しは後続 Phase。

## 2026-06-28 Selected normal candidates to FFmpeg rendering

### 目的

選定済み normal candidates をFFmpeg renderへ接続し、MP4保存と `ExportItem` 作成で results/download に表示できるようにする。

### 変更ファイル

- `backend/app/render/render_normal.py`
- `backend/tests/test_render_normal_selected.py`
- `STATUS.md`

### 実装内容

- `render_selected_normal_candidates(...)` を追加。
- normal候補のみを `storage/outputs/{job_id}/normal` 配下へ `normal_XX.mp4` として保存。
- `burn_subtitles=True` 時は `normal_XX.ass` を生成し、renderに渡す。
- `normalize_audio=True` を render に渡す。
- 成功候補ごとに `ExportItem(type="normal")` を作成。
- 候補単位の例外は `NormalRenderFailure` に記録し、他候補のrenderを継続。
- results endpoint / export download で成功normal clipを取得できることを確認。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend\tests\test_render_normal_selected.py`: 1 passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 78 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `Get-Command docker`: 未検出。

### 未解決事項

- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- 実 worker pipeline 内での selected candidates 読み込みから normal render 呼び出しまでの連結は後続 Phase。

## 2026-06-28 Automatic short rendering

### 目的

選定済み short candidates を自動crop strategy付きFFmpeg renderへ接続し、1080x1920 MP4保存と `ExportItem` 作成で results/download に表示できるようにする。

### 変更ファイル

- `backend/app/video/face_detect.py`
- `backend/app/render/crop_strategy.py`
- `backend/app/render/render_short.py`
- `backend/tests/test_short_rendering.py`
- `STATUS.md`

### 実装内容

- `face_detect.py`: OpenCV が使える場合にclip範囲から顔検出し、weighted face center を算出。
- `crop_strategy.py`: `face_tracking_crop`、`center_crop`、`blur_background` の1080x1920 filterを生成。
- layout `auto` では face tracking を試し、失敗時は center crop、さらに失敗時は blur backgroundへfallback。
- short ASS字幕をburnし、candidate `overlay_title` があれば上部title overlayとしてASSに含める。
- `render_selected_short_candidates(...)` を追加。
- short候補のみを `storage/outputs/{job_id}/shorts` 配下へ `short_XX.mp4` として保存。
- 成功候補ごとに `ExportItem(type="short")` を作成。
- 候補単位の例外は `ShortRenderFailure` に記録し、他候補のrenderを継続。
- results endpoint / export download で成功short clipを取得できることを確認。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend\tests\test_short_rendering.py`: 4 passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_ffmpeg_wrappers.py`: 7 passed, 1 skipped。
- `.\.venv\Scripts\python -m pytest .\backend`: 82 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `Get-Command docker`: 未検出。

### 未解決事項

- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- 実 worker pipeline 内での selected candidates 読み込みから short render 呼び出しまでの連結は後続 Phase。

## 2026-06-28 Real AutoClipper worker pipeline

### 目的

dummy worker enqueue を実処理pipelineへ置き換え、probeからZIP生成までを1つのjobとして実行する。

### 変更ファイル

- `backend/app/jobs/runner.py`
- `backend/app/jobs/queue.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `backend/tests/test_real_pipeline.py`
- `STATUS.md`

### 実装内容

- RQ enqueue先を `run_dummy_autoclipper_job` から `run_autoclipper_job` へ変更。
- pipeline stage: `probing` -> `extracting_audio` -> `transcribing` -> `detecting_scenes` -> `generating_candidates` -> `scoring_candidates` -> `selecting_clips` -> `rendering_normal_clips` -> `rendering_shorts` -> `packaging_zip` -> `completed`。
- 各stageで `Job.status` / `progress` / `current_step` を更新。
- `video_metadata.json`, `transcript_segments.json`, `scene_segments.json`, `silence_segments.json`, `audio_features.json`, `visual_quality.json`, candidates/scored/selected/render_failures JSON を保存。
- scene / silence / audio feature / black screen は失敗時に安全なfallbackで継続。
- scoringはrule scoreを常時実行。OpenAI scoringは `useOpenAIScoring` / `openaiScoring` / `enableOpenAIScoring` がtrueの時だけ実行。
- normal / short renderは候補単位で失敗を記録し、他候補を継続。
- 成功clipごとにMP4、ASS、clip metadata JSON、`ExportItem` を作成。
- 出力が1件以上あればZIP化してcompleted。出力0件ならjob failed。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend\tests\test_real_pipeline.py`: 2 passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 84 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `Get-Command docker`: 未検出。
- `Get-Command ffmpeg`: 未検出。
- `Get-Command ffprobe`: 未検出。

### 未解決事項

- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- 実サンプル動画でのFFmpeg/ffprobe E2E検証は未実施。理由: `ffmpeg` / `ffprobe` CLI 未検出。
- 現在のE2E pipeline testはprobe/transcribe/renderをfake依存に差し替えた検証。

## 2026-06-28 App hardening

### 目的

既知失敗を明確なerror code/messageで扱い、upload validation、temp cleanup、OpenAI fallback、failed UI表示を追加する。

### 変更ファイル

- `backend/app/config.py`
- `backend/app/api/videos.py`
- `backend/app/jobs/runner.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_real_pipeline.py`
- `frontend/lib/api.ts`
- `frontend/components/JobProgress.tsx`
- `.env.example`
- `docker-compose.yml`
- `STATUS.md`

### 実装内容

- upload extension/content-type validation を追加。
- `MAX_UPLOAD_SIZE_BYTES` をconfig化し、streaming保存中に超過検出。超過時はpartial fileを削除。
- upload API error detail を `{code,message}` 形式で返す。
- frontend API parser が dict detail の message を表示可能に変更。
- failed job UIで error code と message を表示。
- `PipelineExpectedError(code,message)` を追加。
- known worker failure: `probe_failed`, `missing_audio`, `audio_extraction_failed`, `transcription_failed`, `transcription_empty`, `candidate_generation_failed`, `no_candidates_found`, `no_usable_output`。
- known failure はjob failedへ記録してreturnし、未処理例外にしない。
- success/failureどちらでも `storage/temp/{job_id}` をcleanup。
- OpenAI scoring failure は `openai_fallback_rule_score` としてrule scoreへfallback。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend\tests\test_api_routes.py .\backend\tests\test_real_pipeline.py`: 14 passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 89 passed, 1 skipped, 1 warning。
- `npm run typecheck`: passed。
- `npm run lint`: passed。
- `Get-Command docker`: 未検出。
- `Get-Command ffmpeg`: 未検出。
- `Get-Command ffprobe`: 未検出。

### 未解決事項

- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。
- 実サンプル動画でのFFmpeg/ffprobe E2E検証は未実施。理由: `ffmpeg` / `ffprobe` CLI 未検出。

## 2026-06-28 CI and Codex operation rules

### 目的

CI設計とCodex運用ルールをrepoへ反映し、PR単位で backend / frontend の最小検証を自動実行できる状態にする。

### 変更ファイル

- `.github/workflows/ci.yml`
- `backend/pyproject.toml`
- `README.md`
- `AGENTS.md`
- `STATUS.md`

### 実装内容

- GitHub Actions CIを追加。backend job は `ruff check .` と `pytest` を実行。
- frontend job は root `package-lock.json` と npm workspace 構成に合わせ、`npm ci` 後に `npm --workspace frontend run lint/typecheck/build` を実行。
- backend dev dependency に `ruff` を追加。
- `pyproject.toml` に ruff config を追加。
- README にローカルCI確認コマンドを追加。
- AGENTS にCIルール、1 task = 1 PR、branch naming、禁止UI、storage pathハードコード禁止を追記。

### 検証結果

- `Get-Content .\.github\workflows\ci.yml`: workflow作成を確認。
- `.\.venv\Scripts\python -m pytest .\backend`: 89 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `..\.venv\Scripts\python -m ruff check .`: 未完了。Windows application control policy により `ruff.exe` 起動がブロック。

### 未解決事項

- ローカル ruff 実行は Windows application control policy で未検証。GitHub Actions の Ubuntu runner で実行予定。
- Docker Compose 本検証は未実施。理由: Docker CLI 未検出。

## 2026-06-28 GitHub initial repository setup

### 目的

既存の AutoClipper Web workspace を Git repository として初期化し、GitHub remote `https://github.com/yoyowasa/AutoClipper-Web.git` へ接続する。

### 変更ファイル

- `.gitignore`
- `STATUS.md`

### 実装内容

- 空の `.git` ディレクトリを `git init` で正規のGit repositoryへ初期化。
- `frontend/tsconfig.tsbuildinfo` を生成物として扱うため、`.gitignore` に `*.tsbuildinfo` を追加。
- 初回commitでは既存実装一式を対象にし、`.env`、`.venv`、`node_modules`、`.next`、runtime storage出力は除外する方針。
- branch を `main` に変更し、`origin` を `https://github.com/yoyowasa/AutoClipper-Web.git` に設定。
- `main` を `origin/main` へpush。

### 検証結果

- `git init`: 成功。
- `git check-ignore -v .env node_modules frontend/.next .venv`: ignore確認済み。
- `git commit -m "Initial commit"`: 成功。commit `07af24d`。
- `git push -u origin main`: 成功。

### 未解決事項

- なし。

## 2026-06-28 CI ruff F401 fix

### 目的

GitHub Actions backend job の `ruff check .` で検出された F401 unused import を修正する。

### 変更ファイル

- `backend/app/audio/volume_features.py`
- `backend/app/render/render_short.py`
- `backend/app/video/black_screen.py`
- `STATUS.md`

### 実装内容

- `typing.Any` の未使用importを削除。
- `build_center_crop_filter` は既存 import 互換を維持するため、内部alias + thin wrapper に変更。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend`: 89 passed, 1 skipped, 1 warning。
- `.\.venv\Scripts\python -m py_compile .\backend\app\audio\volume_features.py .\backend\app\render\render_short.py .\backend\app\video\black_screen.py`: passed。
- `git diff --check`: whitespace errorなし。
- GitHub Actions CI run `28318268336`: backend / frontend passed。
- backend `ruff check .`: GitHub Actions上でpassed。
- local `ruff check .`: Windows application control policy により実行不可。

### 未解決事項

- local ruff 実行は Windows application control policy で未検証。CI上ではpassed。

## 2026-06-28 Docker Desktop install and compose verification

### 目的

Windows環境へDocker Desktopを導入し、AutoClipper Web の docker compose 起動条件を実機で確認する。

### 変更ファイル

- `STATUS.md`

### 実施内容

- Docker Desktop 4.78.0 を導入。
- WSL / VirtualMachinePlatform を有効化。
- Docker Desktop を起動し、`docker-desktop` WSL distro の起動を確認。
- `docker compose up -d --build` を実行。

### 検証結果

- `docker --version`: Docker 29.5.3。
- `docker compose version`: Docker Compose v5.1.4。
- `docker info`: `server=29.5.3 os=linux`。
- `docker compose up -d --build`: success。
- `docker compose ps`: backend / frontend / redis / worker が `Up`。
- backend container health: `healthy`。
- `http://localhost:8000/health`: `{"status":"ok"}`。
- `http://localhost:3000`: HTTP 200、AutoClipper page content確認。

### 未解決事項

- 実サンプル動画を使ったworker E2Eは未実施。

## 2026-06-28 Task 17 Runtime verification and real video E2E hardening

### 目的

docker compose runtime、backend/worker の処理バイナリ、共有DB/storage、実動画smoke導線を検証可能にする。

### 変更ファイル

- `scripts/smoke_runtime.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `scripts/smoke_runtime.py` を追加。
- smoke script で frontend / backend / worker / redis の起動状態を検証。
- backend `/health` と frontend HTTP 200 を検証。
- backend / worker の `DATABASE_URL` と `/app/storage` 配下 paths が一致することを検証。
- backend で uploads / temp / outputs に marker を作成し、worker から読めることを検証。
- backend / worker 内の `ffmpeg` / `ffprobe` を検証。
- backend で1秒のMP4を生成し、worker から同じMP4を `ffprobe` できることを検証。
- README を現行v1実装に合わせて更新し、docker compose、health、worker、upload、outputs、troubleshooting、real-video E2Eの実行手順を追記。

### 検証結果

- `docker compose up -d --build`: success。
- `.\.venv\Scripts\python .\scripts\smoke_runtime.py`: SMOKE PASSED。
- backend / worker: `ffmpeg version 7.1.5-0+deb13u1`。
- backend / worker: `ffprobe version 7.1.5-0+deb13u1`。
- generated MP4 probe: backend `128,72`、worker duration `1.000000`。
- `.\.venv\Scripts\python -m py_compile .\scripts\smoke_runtime.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 89 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `git diff --check`: whitespace errorなし。

### 未解決事項

- 実サンプル動画を使った完了job E2Eは未実施。tone-only smoke video は upload/probe 用で、speech transcript によるclip生成保証用ではない。

## 2026-06-28 Task 18 Real sample video E2E validation

### 目的

小さい synthetic MP4 を生成し、docker compose runtime 上で upload / job / worker / render / download / ffprobe まで再現できるE2E検証導線を作る。

### 変更ファイル

- `backend/app/jobs/runner.py`
- `backend/tests/test_real_pipeline.py`
- `scripts/generate_sample_video.py`
- `scripts/e2e_sample_video.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `e2eFixtureTranscript` job setting を追加。明示指定時だけ synthetic video 用 transcript を使う。
- production default は通常 transcription のまま。quality gate は変更なし。
- `scripts/generate_sample_video.py` で runtime backend container の `ffmpeg` を使い、25秒の test pattern + sine audio MP4 を生成。
- `scripts/e2e_sample_video.py` で API upload、job作成、polling、output MP4/ZIP download、worker container `ffprobe` を実行。
- README に real sample video E2E 手順、出力場所、synthetic audio の制約を追記。

### 検証結果

- `.\.venv\Scripts\python -m py_compile .\scripts\smoke_runtime.py .\scripts\generate_sample_video.py .\scripts\e2e_sample_video.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_real_pipeline.py`: 6 passed, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 90 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `.\.venv\Scripts\python .\scripts\generate_sample_video.py`: `320,180,10/1`、`25.000000`。
- `.\.venv\Scripts\python .\scripts\e2e_sample_video.py`: E2E PASSED。worker `ffprobe` で downloaded MP4 `1080,1920`。
- `.\.venv\Scripts\python .\scripts\e2e_sample_video.py --start`: E2E PASSED。`docker compose up -d --build` 後、backend `/health`、frontend、upload、job completed、MP4/ZIP download、worker `ffprobe` `1080,1920` を確認。
- `docker compose ps` via Docker Desktop path: backend healthy、frontend / worker / redis Up。
- `git diff --check`: whitespace errorなし。

### 未解決事項

- 実話者音声を含むサンプル動画での full transcription E2E は未実施。

## 2026-06-28 Task 19 Real spoken-video E2E without fixture transcript

### 目的

ユーザー supplied の実話者MP4で、fixture transcript を使わず faster-whisper transcription を通すE2E検証導線を作る。

### 変更ファイル

- `scripts/e2e_real_video.py`
- `backend/tests/test_e2e_real_video_script.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `scripts/e2e_real_video.py` を追加。
- `--video`、`--backend-url`、`--timeout`、`--normal-count`、`--short-count`、`--mode`、`--profile`、`--burn-subtitles` を受け取る。
- job settings で `e2eFixtureTranscript=false` を明示。
- upload、job作成、polling、results取得、ZIP/MP4 download、worker `ffprobe` を実行。
- `transcript_segments.json` の存在、非空text、最小文字数、fixture marker不在を検証。
- clips生成時は `selected_clips.json` を検証。
- clips 0件や failed job の場合、no transcript / no candidates / quality gate rejection / render failure を artifact から分類して失敗する。
- README に real spoken-video E2E 手順、推奨入力、low-cost初回実行、出力、troubleshooting を追記。

### 検証結果

- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py .\scripts\e2e_sample_video.py .\scripts\generate_sample_video.py .\scripts\smoke_runtime.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_e2e_real_video_script.py`: 5 passed。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 95 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run build`: passed。
- `npm --workspace frontend run typecheck`: passed。最初の並列実行では `.next/types` 更新raceで失敗、build後の単独再実行で成功。
- `.\.venv\Scripts\python .\scripts\e2e_sample_video.py`: E2E PASSED。worker `ffprobe` で downloaded MP4 `1080,1920`。

### 未解決事項

- 実話者動画ファイルは未指定のため、`scripts/e2e_real_video.py --video ...` による実 faster-whisper runtime E2E は未実施。

## 2026-06-28 Task 20 Add early failure for silent or unusable audio

### 目的

silent / unusable audio または unusable transcript を candidate generation 前に止め、明確な error code と診断値を返す。

### 変更ファイル

- `backend/app/jobs/runner.py`
- `backend/app/api/jobs.py`
- `backend/tests/test_real_pipeline.py`
- `README.md`
- `STATUS.md`

### 実装内容

- audio extraction 後、transcription 前に silence detection と audio feature analysis を実行。
- `volume_peak`、`silence_ratio`、`speech_seconds`、`speech_density` から near-silent / unusable audio を判定。
- unusable audio は `audio_silent_or_unusable` で failed にする。
- transcript 後、candidate generation 前に transcript usability を判定。
- `segment_count == 0`、total text length不足、speech duration不足、confidence低すぎ、repeated low-information text を `transcript_unusable` にする。
- `GET /api/jobs/{job_id}` の `details` に artifact 由来の `duration`、`silence_ratio`、`speech_seconds`、`speech_density`、`volume_peak`、transcript diagnostics を返す。
- `e2eFixtureTranscript` の挙動は維持。quality gate / score threshold は変更なし。
- README troubleshooting に `audio_silent_or_unusable` / `transcript_unusable` を追記。

### 検証結果

- `.\.venv\Scripts\python -m pytest .\backend\tests\test_real_pipeline.py`: 8 passed, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 97 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run build`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `.\.venv\Scripts\python .\scripts\e2e_sample_video.py --start`: E2E PASSED。worker `ffprobe` で downloaded MP4 `1080,1920`。
- `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video .\storage\uploads\vid_2b24c19c2dbc44be893c812491b9ef62.mp4 --normal-count 0 --short-count 1 --timeout 1800`: REAL VIDEO E2E PASSED。transcript 11 segments / 324 chars、short `1080x1920`。
- generated silent MP4 `storage/temp/e2e_silent.mp4`: expected failure。`audio_silent_or_unusable`、diagnostics `duration=25.0`、`silence_ratio=1.0`、`speech_density=0.0`、`speech_seconds=0.0`、`volume_peak=0.0`。
- `GET /api/jobs/job_652fa07557174bd3add86e1ca4171b71`: failed response の `details` に `duration`、`silence_ratio`、`speech_seconds`、`speech_density`、`volume_peak` を確認。
- silent job `job_652fa07557174bd3add86e1ca4171b71`: `candidates.json` absent。candidate generation 前に停止。

### 未解決事項

- 閾値は現時点の保守的な初期値。多様な実動画で false positive / false negative が出る場合は実測値で調整する。

## 2026-06-28 Task 21 Add generation diagnostic summaries

### 目的

completed / failed job ごとに生成診断 summary JSON を `storage/outputs/{job_id}/` へ保存し、E2E scripts から短く確認できるようにする。

### 変更ファイル

- `backend/app/jobs/summaries.py`
- `backend/app/jobs/runner.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_e2e_real_video_script.py`
- `scripts/e2e_summary.py`
- `scripts/e2e_sample_video.py`
- `scripts/e2e_real_video.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `transcript_summary.json` を追加。segment count、text length、speech duration、average confidence、first segments、engine、fixture flag を保存。
- `audio_feature_summary.json` を追加。duration、silence ratio、speech density、volume peak、silent/speech seconds を保存。
- `candidate_summary.json` を追加。total / normal / short counts、transcript text coverage、duration / rule_score / final_score stats を保存。
- `rejection_summary.json` を追加。quality gate rejection と render failure の集計を保存。
- `selected_clips_summary.json` を追加。selected counts、IDs、durations、scores、output paths を保存。
- 成功時は ZIP metadata に summary files を含める。
- 失敗時は `finally` で summary files を保存する。
- `scripts/e2e_sample_video.py` と `scripts/e2e_real_video.py` で summary files を表示する。
- README に Generation Diagnostics を追記。

### 検証結果

- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_summary.py .\scripts\e2e_sample_video.py .\scripts\e2e_real_video.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_e2e_real_video_script.py`: 6 passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_real_pipeline.py`: 8 passed, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 98 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run build`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `.\.venv\Scripts\python .\scripts\e2e_sample_video.py --start`: E2E PASSED。summary 表示確認済み。job `job_31cea2c5626448dabe2833953fc425ae`。

### 未解決事項

- Task 21 では実話者動画 E2E は未再実行。summary 出力は unit / pipeline tests と synthetic docker E2E で確認済み。

## 2026-06-28 Task 22 Make normal clip duration settings configurable from UI/API

### 目的

短めの動画でも明示設定時に normal clip を生成できるよう、normal / short duration settings を API schema と UI から指定可能にする。

### 変更ファイル

- `backend/app/schemas.py`
- `backend/app/api/jobs.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_candidate_generation.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_e2e_real_video_script.py`
- `frontend/lib/types.ts`
- `frontend/components/SettingsPanel.tsx`
- `scripts/e2e_real_video.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `JobSettings` Pydantic schema を追加し、`normalMinDuration`、`normalMaxDuration`、`shortMinDuration`、`shortMaxDuration` を OpenAPI に露出。
- duration default は `normalMinDuration=90`、`normalMaxDuration=600`、`shortMinDuration=20`、`shortMaxDuration=75` のまま維持。
- `settings_json` 保存時に alias 名の JSON に正規化。
- 既存の追加設定は `extra=allow` で維持。
- frontend `ClipSettings` と `SettingsPanel` に advanced duration inputs を追加。
- `scripts/e2e_real_video.py` に `--normal-min-duration` / `--normal-max-duration` / `--short-min-duration` / `--short-max-duration` を追加。
- 60秒相当の spoken fake pipeline で `normalMinDuration=20` / `normalMaxDuration=60` の normal clip 生成を検証。

### 検証結果

- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_api_routes.py .\backend\tests\test_candidate_generation.py .\backend\tests\test_real_pipeline.py .\backend\tests\test_e2e_real_video_script.py`: 34 passed, 1 warning。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_api_routes.py`: 12 passed, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 103 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `.\.venv\Scripts\python .\scripts\e2e_sample_video.py --start`: E2E PASSED。job `job_9091a2fc976142958ec606e1f55ebc93`。

### 未解決事項

- 実話者60秒動画での runtime E2E は未実施。60秒 normal clip 生成は fake dependency pipeline test で確認済み。

## 2026-06-29 Task 23 Separate Hard Gate and Soft Score Selection

### 目的

客観的な hard gate と score 閾値による soft selection を分離し、default では `low_final_score` だけで全候補を hard reject しないようにする。

### 変更ファイル

- `backend/app/candidates/merge_boundaries.py`
- `backend/app/candidates/select_candidates.py`
- `backend/app/jobs/summaries.py`
- `backend/app/schemas.py`
- `backend/app/scoring/quality_gate.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_e2e_real_video_script.py`
- `backend/tests/test_quality_gate_and_selection.py`
- `backend/tests/test_real_pipeline.py`
- `frontend/components/SettingsPanel.tsx`
- `frontend/lib/types.ts`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `evaluate_hard_gate()` を追加し、default policy では `low_final_score` を hard rejection から除外。
- `selectionPolicy` を追加。default は `fill_requested`、strict は `strict_quality`。
- `fill_requested` では threshold 以上を優先し、不足分を hard gate 通過候補から `final_score` 順で backfill。
- backfill した selected clip に `below_quality_threshold=true`、`quality_warning=below_min_final_score`、`selection_reason=backfill_below_quality_threshold` を保存。
- `selected_clips.json`、`candidate_summary.json`、`selected_clips_summary.json` に hard gate / threshold / backfill diagnostics を追加。
- frontend advanced settings と `scripts/e2e_real_video.py --selection-policy` を追加。
- silent audio / transcript usability / existing quality gates は変更なし。

### 検証結果

- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py .\scripts\e2e_summary.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_quality_gate_and_selection.py`: 7 passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_api_routes.py .\backend\tests\test_real_pipeline.py .\backend\tests\test_e2e_real_video_script.py`: 27 passed, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 106 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `.\.venv\Scripts\python .\scripts\e2e_sample_video.py --start`: E2E PASSED。job `job_75ecebfd11664a2ba022ff6a3982f7ba`、short `1080x1920`。
- `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --timeout 1800`: REAL VIDEO E2E PASSED。job `job_b8a594d8310d4f70b44f6f4efee84c8a`、fixture transcript disabled、transcript 11 segments / 324 chars、normal MP4 `1632x912`。
- job `job_b8a594d8310d4f70b44f6f4efee84c8a`: `selected_clips.json` で `hard_gate_passed=true`、`below_quality_threshold=true`、`quality_warning=below_min_final_score`、`selection_reason=backfill_below_quality_threshold` を確認。
- strict policy expected failure: `--selection-policy strict_quality` job `job_1001ae473e864d8d86704d862bfda698`。hard gate passed 564、`low_final_score=278`、selected 0、script exit code 1。

### 未解決事項

- `fill_requested` は出力数を優先する policy。低 score backfill の品質改善は scoring / candidate generation の別 task。
- この PowerShell セッションでは Docker が PATH に無かったため、検証時は `C:\Program Files\Docker\Docker\resources\bin` を一時追加して実行した。

## 2026-06-29 Task 24 10-minute real video E2E validation

### 目的

10分級の実話者動画を docker compose runtime に流し、timing / candidate / output metrics を確認できる E2E validation path を追加する。

### 変更ファイル

- `backend/app/audio/extract.py`
- `backend/app/audio/silence_detect.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `backend/app/video/black_screen.py`
- `backend/app/video/probe.py`
- `backend/tests/test_e2e_real_video_script.py`
- `scripts/e2e_real_video.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `scripts/e2e_real_video.py` に runtime metrics 出力を追加。
  - upload time
  - transcription time
  - candidate generation time
  - scoring time
  - render time
  - total time
- `scripts/e2e_real_video.py` に pipeline metrics 出力を追加。
  - transcript segment count
  - total transcript text length
  - short / normal candidate count
  - hard gate passed count
  - selected normal / short count
  - backfilled count
- downloaded MP4 の ffprobe を JSON parsing に変更し、duration を検証。
- short output は `1080x1920` を検証。
- normal output は export metadata に近い有効 duration を検証。
- FFmpeg / ffprobe wrapper の `subprocess.run(..., text=True)` に `encoding="utf-8", errors="replace"` を追加。
  - 日本語ファイル名または FFmpeg stderr の非UTF-8 byte 混入で audio extraction が落ちる問題への最小修正。
- README に 10分動画 E2E command と metrics 説明を追加。

### 検証結果

- 初回10分動画 E2E: expected failure。job `job_767eded8360e41bfa8d8a315c9eb6784`、`audio_extraction_failed`、原因は FFmpeg stderr decode error。
- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_ffmpeg_wrappers.py .\backend\tests\test_e2e_real_video_script.py`: 16 passed, 1 skipped。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 109 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `docker compose up -d --build`: backend / worker / frontend image rebuild succeeded。
- 10分級実動画 E2E: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Downloads\【騒然】アンソロピックの裏に「本当の勝ち組」（ジェーンストリート_ゴールドマン・サックス_JPモルガン・チェース_ウォール街_マットエックス_AIデータセンター_解説後藤直義、森川潤） - NewsPicks _ニューズピックス (1080p, h264) (1).mp4' --normal-count 1 --short-count 1 --normal-min-duration 90 --normal-max-duration 600 --short-min-duration 20 --short-max-duration 75 --selection-policy fill_requested --mode low_cost --timeout 3600`: REAL VIDEO E2E PASSED。
- 10分級 job `job_c18978fad90a425890c0f4c5b20e4eeb`:
  - transcript 1008 segments / 9038 chars
  - video duration 1331.747083 seconds
  - candidates total 2400、normal 1200、short 1200
  - hard gate passed 2400
  - selected normal 1、short 1、backfill 0
  - normal MP4 `1920x1080`, duration `599.389750s`
  - short MP4 `1080x1920`, duration `44.960875s`
  - runtime metrics: upload `1.407s`, transcription `97.078s`, candidate generation `91.344s`, scoring `n/a`, render `32.406s`, total `293.984s`
- `.\.venv\Scripts\python .\scripts\e2e_sample_video.py`: E2E PASSED。job `job_0d5d03b61560483b81351353b98ac053`。
- short real-video E2E: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --timeout 1800`: REAL VIDEO E2E PASSED。job `job_ba1a10409cba4834b3e192492c3cb565`。

### 未解決事項

- phase timing は status polling からの近似値。短時間で通過する `scoring_candidates` などは `n/a` になる場合がある。
- この PowerShell セッションでは Docker が PATH に無かったため、検証時は `C:\Program Files\Docker\Docker\resources\bin` を一時追加して実行した。

## 2026-06-29 Task 25 OpenAI Structured Outputs scoring real API validation

### 目的

`high_quality` mode で OpenAI Structured Outputs scoring の production API path を検証し、候補数制限・失敗時 diagnostics・summary 出力を追加する。

### 変更ファイル

- `backend/app/jobs/runner.py`
- `backend/app/jobs/summaries.py`
- `backend/app/schemas.py`
- `backend/app/scoring/openai_score.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_e2e_real_video_script.py`
- `backend/tests/test_openai_score.py`
- `backend/tests/test_real_pipeline.py`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `scripts/e2e_real_video.py` に OpenAI scoring options を追加。
  - `--use-openai-scoring true/false`
  - `--openai-candidate-limit`
  - `--openai-model`
  - `--openai-fallback-to-rule-score`
  - `--no-openai-fallback-to-rule-score`
- E2E script で high_quality / OpenAI scoring 有効時、worker container 内の `OPENAI_API_KEY` presence を事前確認。値は出力しない。
- backend settings schema に `openaiCandidateLimit`、`openaiModel`、`openaiFallbackToRuleScore` を追加。
- worker scoring で `openaiCandidateLimit` を適用。default backend limit は `40`、E2E script default は `20`。
- OpenAI API へ送る payload は candidate transcript と audio / visual feature summary のみ。video file / MP4 は送らない。
- OpenAI scorer に stats を追加。
  - model
  - candidates sent
  - success / failed / fallback counts
  - average latency
  - estimated input / output text length
  - total API calls
  - error types
- `openai_scoring_summary.json` を追加。
- missing key は `openai_configuration_missing` で明確に失敗。
- API/schema failure は `openaiFallbackToRuleScore=true` なら rule score fallback、false なら `openai_scoring_failed`。
- malformed response / schema validation failure は `schema_validation_failed` として記録。
- README に OpenAI key 設定、high_quality E2E、candidate limit、troubleshooting を追加。

### 検証結果

- `OPENAI_API_KEY`: host `.env` と worker container で presence 確認済み。値は出力せず。
- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py .\scripts\e2e_summary.py`: passed。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_openai_score.py .\backend\tests\test_e2e_real_video_script.py .\backend\tests\test_api_routes.py .\backend\tests\test_real_pipeline.py`: 46 passed, 1 warning。
- `.\.venv\Scripts\python -m pytest .\backend`: 114 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `docker compose up -d --build`: backend / worker / frontend image rebuild succeeded。
- high_quality real OpenAI E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --mode high_quality --use-openai-scoring true --openai-candidate-limit 3 --openai-model gpt-4o-mini --timeout 1800`
  - result: REAL VIDEO E2E PASSED
  - job `job_c06425f7fbab45c781324e1b045ad6fb`
  - `openai_scoring_summary.json`: model `gpt-4o-mini`、sent `3`、success `3`、failed `0`、fallback `0`、calls `3`、avg latency `3.250862`
  - scored candidates: 3 candidates have numeric `ai_score` / `final_score`, `title`, `overlay_title`, `risk_flags=[]`
  - final output: normal MP4 `1632x912`, duration `58.333333s`
- existing synthetic E2E: `.\.venv\Scripts\python .\scripts\e2e_sample_video.py`: E2E PASSED。job `job_3021f13b3a6a461e82f835ae84169c7a`。
- existing low_cost real E2E: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --mode low_cost --timeout 1800`: REAL VIDEO E2E PASSED。job `job_73e7a12c17f84e7c9beb50d18f9bdd10`。

### 未解決事項

- 今回は API path validation。score quality tuning は未実施。
- OpenAI scoring 対象は cost safety のため上位候補に制限。今回の selected normal は candidate limit 外の rule-score backfill。
- phase timing は status polling 由来の近似値。短時間 phase は `n/a` になる場合がある。

## 2026-06-29 OpenAI scoring default model correction

### 目的

Task 25 の high_quality OpenAI scoring 検証で使った `gpt-4o-mini` が品質検証用として弱いため、既定モデルを `gpt-5.5` に修正する。

### 変更ファイル

- `backend/app/schemas.py`
- `backend/app/jobs/runner.py`
- `backend/app/scoring/openai_score.py`
- `scripts/e2e_real_video.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_e2e_real_video_script.py`
- `backend/tests/test_openai_score.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `JobSettings.openaiModel` default を `gpt-5.5` に変更。
- worker fallback model を `gpt-5.5` に変更。
- `OpenAICandidateScorer` default model を `gpt-5.5` に変更。
- `scripts/e2e_real_video.py --openai-model` default を `gpt-5.5` に変更。
- README の high_quality E2E 例と Job Settings 例を `gpt-5.5` に更新。
- 既定値を検証する backend tests を更新。

### 検証結果

- OpenAI `/v1/models` で `gpt-5.5` 利用可能を確認。API key 値は出力せず。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_openai_score.py .\backend\tests\test_e2e_real_video_script.py .\backend\tests\test_api_routes.py`: 35 passed, 1 warning。
- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 114 passed, 1 skipped, 1 warning。
- high_quality real OpenAI E2E default model check:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --mode high_quality --use-openai-scoring true --openai-candidate-limit 1 --timeout 1800`
  - result: REAL VIDEO E2E PASSED
  - job `job_6f5a8709212d4edb9ed10e48455f47e7`
  - `openai_scoring_summary.json`: model `gpt-5.5`、sent `1`、success `1`、failed `0`、fallback `0`、calls `1`、avg latency `9.661316`
  - final output: normal MP4 `1632x912`, duration `58.333333s`

### 未解決事項

- 今回は model default 修正。score quality tuning は未実施。

## 2026-06-29 Task 26 30-minute real video E2E validation

### 目的

30分級の実発話動画で pipeline stability を検証し、長尺 E2E 用の実行 profile、詳細 runtime metrics、pipeline metrics、artifact 検証を追加する。

### 変更ファイル

- `scripts/e2e_real_video.py`
- `backend/tests/test_e2e_real_video_script.py`
- `README.md`
- `STATUS.md`

### 実装内容

- `scripts/e2e_real_video.py` に `--validation-profile 30min` を追加。
  - `normalCount=2`
  - `shortCount=3`
  - `normalMinDuration=90`
  - `normalMaxDuration=600`
  - `shortMinDuration=20`
  - `shortMaxDuration=75`
  - `selectionPolicy=fill_requested`
  - `mode=low_cost`
  - `timeout=7200`
- 既存 default profile は従来値を維持。
- runtime metrics を拡張。
  - upload
  - transcription
  - scene detection
  - candidate generation
  - scoring
  - selection
  - normal render
  - short render
  - ZIP packaging
  - total
- pipeline metrics を拡張。
  - video duration
  - transcript segment count / text length
  - total / normal / short candidates
  - hard gate passed / rejected
  - selected normal / short
  - backfilled
  - render failures
  - ZIP size
- 必須 artifact 検証を追加。
  - `selected_clips.json`
  - `candidate_summary.json`
  - `selected_clips_summary.json`
- ZIP download の size 検証を追加。
- normal MP4 の dimension > 0 検証を追加。
- stdout line buffering を有効化し、長尺実行中の進捗が即時出るように修正。
- README に 30分 E2E 手順、推奨入力、期待出力、troubleshooting を追加。

### 検証結果

- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_e2e_real_video_script.py`: 12 passed。
- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py`: passed。
- `.\.venv\Scripts\python -m pytest .\backend`: 116 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- synthetic E2E: `.\.venv\Scripts\python .\scripts\e2e_sample_video.py`: E2E PASSED。job `job_8d049214cf784508a0f7718019fa3b94`。
- short real-video low_cost E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --mode low_cost --timeout 1800`
  - result: REAL VIDEO E2E PASSED
  - job `job_f7a9062240f14f53bbfbfe5a64e43aba`
- OpenAI path validation:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --mode high_quality --use-openai-scoring true --openai-candidate-limit 1 --timeout 1800`
  - result: REAL VIDEO E2E PASSED
  - job `job_ab5a6bac005444578797cb91347680e1`
  - `openai_scoring_summary.json`: model `gpt-5.5`、sent `1`、success `1`、failed `0`、fallback `0`
- 30-minute real-video low_cost E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video '<30min spoken mp4>' --validation-profile 30min`
  - result: REAL VIDEO E2E PASSED
  - job `job_611687fe254f49259a39c0aac4417bfb`
  - video duration: `1820.735583`
  - transcript: `1555` segments, `15457` chars
  - candidates: total `2400`, normal `1200`, short `1200`
  - hard gate: passed `2400`, rejected `0`
  - selected: normal `1`, short `3`, backfilled `0`
  - rejection summary: `high_overlap=1209`
  - render failures: `0`
  - ZIP size: `112042483` bytes
  - normal output: `1280x720`, duration `600.0154s`
  - short outputs: `1080x1920`, durations `34.533817s`, `33.600233s`, `30.68s`
  - runtime metrics:
    - upload `1.922s`
    - transcription `169.859s`
    - scene detection `99.281s`
    - candidate generation `127.735s`
    - scoring `n/a`
    - selection `n/a`
    - normal render `40.453s`
    - short render `20.375s`
    - ZIP packaging `4.109s`
    - total `472.609s`

### 未解決事項

- 30分 E2E では `normalCount=2` を要求したが、high overlap 除外により selected normal は `1`。short は `3` 生成済み。pipeline failure ではないが、通常切り抜き本数をより満たす調整は今後の品質調整対象。
- いくつかの短時間 phase は polling 間隔内で通過するため `n/a` になる場合がある。
