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

## 2026-06-29 Task 27 Improve selection count fulfillment and overlap diversity

### 目的

30分 E2E で `normalCount=2` に対して normal が1本しか選ばれなかった問題を修正する。hard gate は維持し、normal / short は default で独立 selection とし、overlap / diversity diagnostics を増やす。

### 変更ファイル

- `backend/app/candidates/merge_boundaries.py`
- `backend/app/candidates/select_candidates.py`
- `backend/app/jobs/summaries.py`
- `backend/app/schemas.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_candidate_generation.py`
- `backend/tests/test_e2e_real_video_script.py`
- `backend/tests/test_quality_gate_and_selection.py`
- `frontend/components/SettingsPanel.tsx`
- `frontend/lib/types.ts`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- `README.md`
- `STATUS.md`

### 実装内容

- selection overlap audit:
  - 既存実装は normal と short を別々に selection しており、default では cross-type overlap はブロックしていなかった。
  - 30分 job の旧 `normal_candidates.json` は `1200` 件あったが `start_max=5.1s`、`end_max=602.76s` で、candidate cap が冒頭に偏っていた。
- candidate generation の `max_candidates` 切り詰めを時系列分散に変更。
- `crossTypeOverlapDedupe` setting を追加。default `false`。
- `fill_requested` selection を Phase A/B/C に分割。
  - Phase A: above `minFinalScore`。
  - Phase B: below score threshold backfill。
  - Phase C: count 不足時のみ overlap threshold を段階緩和。
- overlap relaxed selected clip に以下を保存。
  - `selection_reason=backfill_overlap_relaxed`
  - `overlap_relaxed=true`
  - `overlap_ratio_used`
- hard gates は維持。
  - no transcript
  - invalid duration
  - too much silence
  - too little speech
  - incomplete sentence
  - model rejected
- timeline cluster diversity を追加。
  - type 別に time cluster を作る。
  - 各 cluster の上位候補を優先してから同 cluster の2巡目を選ぶ。
- diagnostics を拡張。
  - requested / selected count
  - normal / short hard-gate passed count
  - high overlap rejected count by type
  - cross-type overlap rejection count
  - time cluster count
  - selected clusters
  - unfilled requested counts
  - unfilled reason counts
  - overlap relaxed count
- `scripts/e2e_real_video.py` に selected/requested ratio、high overlap by type、unfilled、overlap relaxation を出力。
- README に selectionPolicy / overlap / cross-type dedupe の説明を追記。

### 検証結果

- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m pytest .\backend\tests\test_quality_gate_and_selection.py .\backend\tests\test_candidate_generation.py .\backend\tests\test_e2e_real_video_script.py .\backend\tests\test_api_routes.py`: 45 passed, 1 warning。
- `.\.venv\Scripts\python -m pytest .\backend`: 122 passed, 1 skipped, 1 warning。
- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py .\scripts\e2e_summary.py`: passed。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run build`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `docker compose up -d --build`: passed after adding Docker Desktop resources path to this PowerShell session.
- synthetic E2E: `.\.venv\Scripts\python .\scripts\e2e_sample_video.py`: E2E PASSED。job `job_2e3fc97230fe4225bb108b1abfb7c597`。
- short real-video low_cost E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --mode low_cost --timeout 1800`
  - result: REAL VIDEO E2E PASSED
  - job `job_359d215ed73c444b96cc1f1d92616814`
- 10-minute real-video low_cost E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video '<spoken mp4>' --normal-count 1 --short-count 1 --normal-min-duration 90 --normal-max-duration 600 --short-min-duration 20 --short-max-duration 75 --selection-policy fill_requested --mode low_cost --timeout 3600`
  - result: REAL VIDEO E2E PASSED
  - job `job_6102aa6b924d4458b78b93c8225d5b92`
  - selected: normal `1/1`, short `1/1`
  - render failures: `0`
- 30-minute real-video low_cost E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video '<30min spoken mp4>' --validation-profile 30min`
  - result: REAL VIDEO E2E PASSED
  - job `job_37089f0d82d84ce5a5e4076ed83f2d77`
  - video duration: `1820.735583`
  - transcript: `1245` segments, `15068` chars
  - candidates: total `2400`, normal `1200`, short `1200`
  - hard gate: passed `2400`, rejected `0`
  - selected: normal `2/2`, short `3/3`, backfilled `0`
  - high overlap rejected by type: normal `78`, short `114`
  - time clusters: normal `6`, short `9`
  - selected clusters: normal `[2, 4]`, short `[1, 2, 3]`
  - overlap relaxed: `0`
  - render failures: `0`
  - ZIP size: `59639101` bytes
  - normal outputs: `1280x720`, durations `103.236467s`, `98.14805s`
  - short outputs: `1080x1920`, durations `69.668917s`, `58.425033s`, `61.061s`
  - total runtime: `417.656s`
- OpenAI path validation:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video 'C:\Users\peace.YAGURUMAGIKUHM\Desktop\bandicam 2026-06-28 23-06-52-866.mp4' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --mode high_quality --use-openai-scoring true --openai-candidate-limit 1 --timeout 1800`
  - result: REAL VIDEO E2E PASSED
  - job `job_9e69814f87a64a34a106e8c1d8f08ff3`
  - `openai_scoring_summary.json`: model `gpt-5.5`、sent `1`、success `1`、failed `0`、fallback `0`

### 未解決事項

- selection quality tuning は未実施。今回の修正は count fulfillment / overlap diagnostics / timeline diversity に限定。
- frontend typecheck は `.next/types` 未生成状態では失敗する場合があるため、local では `npm --workspace frontend run build` 後に再実行して passed を確認した。CI は build job で typecheck も実行する。

## 2026-06-29 Task 28: 30-minute high_quality limited OpenAI scoring E2E

### 目的

- 30分実動画で `high_quality` + OpenAI Structured Outputs scoring を候補数制限付きで検証する。
- API経路、fallback、schema validation、latency、cost-safety 指標を確認する。
- quality tuning は実施しない。

### 変更ファイル

- `backend/app/scoring/openai_score.py`
- `backend/app/jobs/runner.py`
- `backend/app/jobs/summaries.py`
- `backend/tests/test_openai_score.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_e2e_real_video_script.py`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `openai_scoring_summary.json` を拡張。
  - `candidate_limit`
  - `candidates_eligible_for_openai_scoring`
  - `candidates_selected_for_openai`
  - `candidates_actually_sent`
  - `successful_structured_scores`
  - `failed_structured_scores`
  - `schema_validation_failures`
  - `avg_latency_seconds`
  - `max_latency_seconds`
  - `total_latency_seconds`
  - `estimated_text_payload_size`
  - `selected_ai_score_count`
  - `selected_fallback_score_count`
  - `selected_rule_score_only_due_to_limit_count`
  - final selected clip score source lists
- `scripts/e2e_real_video.py` に `30min_high_quality` validation profile を追加。
  - `mode=high_quality`
  - `useOpenAIScoring=true`
  - `openaiCandidateLimit=20`
  - `openaiFallbackToRuleScore=true`
  - `normalCount=2`
  - `shortCount=3`
  - `selectionPolicy=fill_requested`
  - `timeout=7200`
- E2E stdout に OpenAI model、candidate limit、eligible/sent counts、success/failure/fallback、schema failures、latency、text-size proxy、selected clip score source counts を追加。
- `OPENAI_API_KEY` 欠如時の script error に `openai_configuration_missing` を明記。
- OpenAI scoring batch fallback 時に `fallback_scores` が 0 のままになる経路を修正。
- README に 30分 high_quality E2E 手順と cost-safety 説明を追記。

### 検証結果

- `..\.venv\Scripts\python -m pytest tests\test_openai_score.py tests\test_e2e_real_video_script.py tests\test_real_pipeline.py` from `backend`: 37 passed, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `.\.venv\Scripts\python -m py_compile .\scripts\e2e_real_video.py .\scripts\e2e_summary.py`: passed。
- `..\.venv\Scripts\python -m pytest` from `backend`: 123 passed, 1 skipped, 1 warning。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run build`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `docker compose up -d --build`: passed。
- backend `/health`: `{"status":"ok"}`。
- worker container: `OPENAI_API_KEY` visible。値は記録しない。
- 30-minute high_quality E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video '<30min spoken mp4>' --validation-profile 30min_high_quality`
  - result: REAL VIDEO E2E PASSED
  - job: `job_9b255223fb794123af9495fff438eacf`
  - video duration: `1820.735583`
  - transcript: `1325` segments, `14797` chars
  - candidates: total `2400`, normal `1200`, short `1200`
  - hard gate: passed `2380`, rejected `20`
  - selected: normal `2/2`, short `3/3`
  - render failures: `0`
  - ZIP size: `77706529` bytes
  - OpenAI summary:
    - model: `gpt-5.5`
    - candidate limit: `20`
    - eligible: `2400`
    - selected for OpenAI: `20`
    - sent: `20`
    - success: `20`
    - failed: `0`
    - fallback: `0`
    - schema failures: `0`
    - API calls: `20`
    - avg latency: `8.639599`
    - max latency: `18.529867`
    - total latency: `172.791975`
    - estimated text payload size: `33485`
    - final selected clips using AI score: `0`
    - final selected clips using fallback score: `0`
    - final selected clips rule-only due to limit: `5`
  - normal outputs: `1280x720`, durations `137.303150s`, `152.101267s`
  - short outputs: `1080x1920`, durations `58.591183s`, `66.632550s`, `67.383300s`
  - total runtime: `685.796s`

### 未解決事項

- 最終選択された5本は今回の `openaiCandidateLimit=20` 外の rule-only 候補だった。API経路検証としては成功。品質チューニングや「選択候補を優先してOpenAI scoringする」設計は別タスク。

## 2026-06-29 Task 29: Ensure OpenAI scoring affects final selection

### 目的

- `high_quality` で最終選択された clip に OpenAI Structured Outputs score を反映する。
- 全候補を OpenAI に送らず、preselection pool と finalist on-demand scoring で API コストを抑える。
- score tuning、hard gate 変更、manual review UI は実施しない。

### 変更ファイル

- `backend/app/candidates/merge_boundaries.py`
- `backend/app/jobs/runner.py`
- `backend/app/jobs/summaries.py`
- `backend/app/schemas.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_e2e_real_video_script.py`
- `backend/tests/test_real_pipeline.py`
- `frontend/components/SettingsPanel.tsx`
- `frontend/lib/types.ts`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `JobSettings` に `ensureSelectedOpenAIScored` と `openaiFinalistScoringLimit` を追加。
  - `high_quality`: `ensureSelectedOpenAIScored=true`
  - `low_cost`: `ensureSelectedOpenAIScored=false`
  - finalist limit default: `normalCount + shortCount + 2`
- OpenAI scoring pool を hard-gate-passed candidates から type-aware / cluster-diverse に構築。
- 最終選択後、render 前に rule-only finalist へ on-demand OpenAI scoring を実行。
- 選択候補に以下を保存。
  - `used_ai_score`
  - `ai_score`
  - `rule_score`
  - `final_score`
  - `openai_scored`
  - `openai_fallback_used`
  - `openai_score_source`
  - `openai_not_scored_reason`
- `openai_scoring_summary.json` に preselection / finalist / selected score source counts を追加。
- E2E stdout に OpenAI finalist calls、selected AI/fallback/not_scored counts を追加。
- README に finalist on-demand scoring と cost-safety 設定を追記。

### 検証結果

- `..\.venv\Scripts\python -m pytest` from `backend`: 126 passed, 1 skipped, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `docker compose up -d --build`: passed。
- Synthetic E2E: REAL VIDEO E2E PASSED、job `job_2793964686b44851b92594a25c332c63`。
- Short real low_cost E2E: REAL VIDEO E2E PASSED、job `job_207054fc996049ebaa5ef01a64c86da5`、normal `1/1`。
- 30-minute low_cost E2E: REAL VIDEO E2E PASSED、job `job_bfe84635e7064edbb59079261d058a10`、normal `2/2`、short `3/3`。
- 30-minute high_quality E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video '<30min spoken mp4>' --validation-profile 30min_high_quality`
  - result: REAL VIDEO E2E PASSED
  - job: `job_dfd13dd8435a401f9ab9773fa217bd18`
  - OpenAI summary: candidate limit `20`、finalist limit `7`、preselection sent `20`、finalists sent `5`、success `25`、failed `0`、fallback `0`
  - selected: normal `2/2`、short `3/3`
  - selected using AI score: `5`
  - selected using fallback: `0`
  - selected not scored: `0`
- Forced finalist smoke after final docker rebuild:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video '<61s spoken mp4>' --normal-count 1 --short-count 0 --normal-min-duration 20 --normal-max-duration 60 --mode high_quality --use-openai-scoring true --openai-candidate-limit 0 --ensure-selected-openai-scored true --openai-finalist-scoring-limit 1 --timeout 1800`
  - job: `job_482223dfa6cc4c9bbf61eebad0800392`
  - OpenAI summary: preselection sent `0`、finalists sent `1`、success `1`、fallback `0`
  - selected using AI score: `1`
  - selected using fallback: `0`
  - selected not scored: `0`
  - selected `openai_score_source`: `finalist_on_demand`

### 未解決事項

- OpenAI の score calibration / quality tuning は未実施。
- `OPENAI_API_KEY` が無い環境では high_quality OpenAI 実API E2E は実行不可。CI は key 不要の mock/unit path のみ。

## 2026-06-29 Task 30: Add low_cost vs high_quality comparison report

### 目的

- 同じ動画の `low_cost` と `high_quality` job artifact を比較できる再現可能 workflow を追加する。
- score tuning、selection behavior 変更、hard gate 変更は実施しない。

### 変更ファイル

- `scripts/compare_runs.py`
- `scripts/e2e_compare_quality.py`
- `backend/tests/test_compare_runs_script.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `scripts/compare_runs.py` を追加。
  - 入力: `--low-cost-job-id`、`--high-quality-job-id`、`--output`、`--format json|markdown|both`
  - 読み取り対象: `storage/outputs/{job_id}/selected_clips.json`、`selected_clips_summary.json`、`candidate_summary.json`、`openai_scoring_summary.json`、`transcript_summary.json`
  - 出力: `comparison_report.json`、`comparison_report.md`
- 比較指標を追加。
  - selected normal / short count
  - requested / selected fulfillment
  - selected clip time range
  - low_cost / high_quality overlap
  - rule_score / ai_score / final_score 差分
  - title / overlay_title
  - selection_reason / below_quality_threshold / quality_warning
  - openai_score_source / fallback / backfill
  - render failure count
  - high_quality selected clips using AI / fallback / not scored
- `scripts/e2e_compare_quality.py` を追加。
  - 同じ `--video` で low_cost E2E を実行。
  - 続けて high_quality E2E を限定 OpenAI scoring で実行。
  - 完了後に comparison report を生成。
- README に比較 workflow と report 出力先を追記。
- fixture JSON だけで CI 実行できる tests を追加。`OPENAI_API_KEY` は不要。

### 検証結果

- `..\.venv\Scripts\python -m pytest tests\test_compare_runs_script.py tests\test_e2e_real_video_script.py` from `backend`: 17 passed。
- `..\.venv\Scripts\python -m pytest` from `backend`: 130 passed, 1 skipped, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `npm --workspace frontend run lint`: passed。
- `npm --workspace frontend run typecheck`: passed。
- `npm --workspace frontend run build`: passed。
- `.\.venv\Scripts\python -m py_compile .\scripts\compare_runs.py .\scripts\e2e_compare_quality.py`: passed。
- `docker compose up -d --build`: passed。
- `docker compose ps`: backend / frontend / redis / worker running。backend healthy。
- backend `/health`: `{"status":"ok"}`。
- frontend `http://localhost:3000`: HTTP `200`。
- Existing 30-minute artifacts comparison smoke:
  - command: `.\.venv\Scripts\python .\scripts\compare_runs.py --low-cost-job-id job_bfe84635e7064edbb59079261d058a10 --high-quality-job-id job_dfd13dd8435a401f9ab9773fa217bd18 --format both`
  - result: passed
  - same selected clips by time overlap: `2`
  - different high_quality selected clips: `3`
  - high_quality selected using AI score: `5`
  - fallback: `0`
  - not scored: `0`
  - output: `storage/outputs/comparisons/job_bfe84635e7064edbb59079261d058a10_vs_job_dfd13dd8435a401f9ab9773fa217bd18/comparison_report.json`
  - output: `storage/outputs/comparisons/job_bfe84635e7064edbb59079261d058a10_vs_job_dfd13dd8435a401f9ab9773fa217bd18/comparison_report.md`

### 未解決事項

- `e2e_compare_quality.py` の high_quality 実行には `OPENAI_API_KEY` が必要。
- 今回は比較可視化のみ。score calibration / selection tuning は未実施。

## 2026-06-29 Task 31: Bounded streaming candidate generation for long videos

### 目的

- 58分動画で `generating_candidates` 中に worker work-horse が `signal 9` 終了した問題を修正する。
- candidate generation を memory-bounded / chunked にし、1時間級動画で selection/rendering へ進める。
- hard gate、score threshold、OpenAI candidate limit、manual editing UI は変更しない。

### 変更ファイル

- `backend/app/candidates/merge_boundaries.py`
- `backend/app/candidates/generate_normal_candidates.py`
- `backend/app/candidates/generate_short_candidates.py`
- `backend/app/jobs/runner.py`
- `backend/app/jobs/summaries.py`
- `backend/app/api/jobs.py`
- `backend/app/schemas.py`
- `backend/tests/test_candidate_generation.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_e2e_real_video_script.py`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- `README.md`
- `STATUS.md`

### 変更内容

- candidate generation 内部を `LightweightCandidate` + bounded keeper に変更。
  - raw candidate では `transcript_text` を materialize しない。
  - kept candidate だけ `Candidate` 化し、`segment_start_index` / `segment_end_index` / `transcript_char_count` / `speech_seconds` / `silence_ratio` を保存。
- chunked generation を追加。
  - default chunk: `600s`
  - overlap: `75s`
  - time bucket: `300s`
- candidate caps を追加。
  - `maxRawCandidatesPerType`: `250000`
  - `maxKeptCandidatesPerType`: `1200`
  - `maxCandidatesPerTimeBucket`: `100`
  - `candidateTimeBucketSeconds`: `300`
  - `maxCandidateGenerationMemoryMb`: `12000`
  - `candidateChunkSeconds`: `600`
  - `candidateChunkOverlapSeconds`: `75`
- `candidate_generation_summary.json` を追加。
  - chunks processed
  - raw candidates considered
  - kept candidates by type
  - dropped due to cap / duplicate / no transcript / invalid duration
  - peak memory
  - configured caps
- candidate generation heartbeat を追加。
  - heartbeat 時に `updated_at` と `candidate_generation_summary.json` を更新。
- stale running job recovery を追加。
  - 実行中 job の heartbeat が止まった場合、status polling 時に `worker_terminated_unexpectedly` で failed 化。
- E2E script に candidate generation metrics / caps 表示と cap override CLI を追加。
- README に1時間 low_cost E2E、candidate generation caps、troubleshooting を追記。

### 検証結果

- `..\.venv\Scripts\python -m pytest tests\test_candidate_generation.py tests\test_api_routes.py tests\test_e2e_real_video_script.py` from `backend`: 40 passed, 1 warning。
- `..\.venv\Scripts\python -m pytest` from `backend`: 135 passed, 1 skipped, 1 warning。
- `..\.venv\Scripts\python -m ruff check .` from `backend`: All checks passed。
- `npm run lint` from `frontend`: passed。
- `npm run typecheck` from `frontend`: passed。
- `npm run build` from `frontend`: passed。
- `docker compose up -d --build`: passed。
- backend `/health`: `ok`。
- frontend `http://localhost:3000`: HTTP `200`。
- 58分 artifact candidate generation smoke:
  - input job artifacts: `job_f98f00dbafcb4a97a67c5b7a2d7db80a`
  - normal candidates: `600`
  - short candidates: `900`
  - chunks processed: `12`
  - raw candidates considered: `500000`
  - selection result: normal `5/5`、short `10/10`
- 58分 real low_cost E2E:
  - command: `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video '<58min spoken mp4>' --timeout 14400 --normal-count 3 --short-count 5 --mode low_cost --profile talk --burn-subtitles true --normal-min-duration 90 --normal-max-duration 600 --short-min-duration 20 --short-max-duration 75 --selection-policy fill_requested`
  - result: REAL VIDEO E2E PASSED
  - job: `job_aeea2831f0d7486dac106cd9462a94fe`
  - total time: `489.250s`
  - candidate generation time: `52.828s`
  - selected: normal `3/3`、short `5/5`
  - render failures: `0`
  - ZIP size: `219480888 bytes`
  - generated shorts: all verified `1080x1920`
  - `candidate_generation_summary.json`:
    - chunks processed: `12`
    - raw candidates considered: `477250`
    - kept: normal `600`、short `800`
    - peak memory: `457.145 MB`
    - memory guard: `false`
- Disk:
  - E2E start C free: `181.70 GB`
  - after E2E C free: `180.67 GB`
  - job output size: `0.424 GB`

### 未解決事項

- 58分 E2E は `normal=3` / `short=5` で実施。`normal=5` / `short=10` は artifact smoke では selection `5/5` / `10/10` まで確認済みだが、全render E2Eは未実施。
- candidate generation は memory-bounded になったが、raw candidates considered は still large。CPU時間最適化は別タスク。
- `worker_terminated_unexpectedly` は status polling 時の stale recovery。worker kill 瞬間に即時 failed へ更新する仕組みではない。

## 2026-06-30 Task 32: 58-minute full render E2E validation

### 目的

- 58分実動画で `normal=5` / `short=10` の full render E2E を検証する。
- candidate generation OOM 再発なし、selection 充足、render、ZIP、出力サイズ、ディスク使用量を確認する。
- selection logic、hard gate、score threshold、UI は変更しない。

### 変更ファイル

- `README.md`
- `STATUS.md`

### 変更内容

- README に58分 `low_cost` full-render reference run の実測結果を追記。
- STATUS に Task 32 の検証結果を追記。
- 実装コード変更なし。

### 検証結果

- command:
  - `.\.venv\Scripts\python .\scripts\e2e_real_video.py --video '<58min spoken mp4>' --backend-url http://localhost:8000 --timeout 21600 --normal-count 5 --short-count 10 --mode low_cost --profile talk --burn-subtitles true --normal-min-duration 90 --normal-max-duration 600 --short-min-duration 20 --short-max-duration 75 --selection-policy fill_requested`
- result: `REAL VIDEO E2E PASSED`
- job: `job_6e0b6c7539644c679e853eccfcb77039`
- total runtime: `627.141s`
- upload time: `1.750s`
- transcription time: `224.313s`
- scene detection time: `101.265s`
- candidate generation time: `52.704s`
- selection time: `2.015s`
- normal render time: `111.219s`
- short render time: `87.281s`
- zip packaging time: `22.266s`
- selected: normal `5/5`、short `10/10`
- render failures: `0`
- generated MP4 count: normal `5`、short `10`
- generated shorts: all downloaded MP4s verified `1080x1920`
- normal clips: all downloaded MP4s had valid dimensions and durations
- ZIP size: `385749028 bytes` (`367.88 MB`)
- job output size: `790240046 bytes` (`753.63 MB`)
- disk:
  - before E2E C free: `180.39 GB`
  - after E2E C free: `177.99 GB`
- `candidate_generation_summary.json`:
  - chunks processed: `12`
  - raw candidates considered: `487517`
  - kept: normal `600`、short `900`
  - dropped due to cap: `477404`
  - dropped due to duplicate: `8623`
  - dropped due to invalid duration: `3623`
  - peak memory: `466.258 MB`
  - memory guard: `false`
- `candidate_summary.json`:
  - total candidates: `1500`
  - hard gate passed: `1500`
  - hard gate rejected: `0`
  - selected below threshold backfill: `1`
  - unfilled requested counts: normal `0`、short `0`
- required artifacts present:
  - `selected_clips.json`
  - `candidate_generation_summary.json`
  - `selected_clips_summary.json`
  - `download.zip`

### 未解決事項

- 58分 full render workload は検証済み。品質評価、字幕精度、ショート構図改善は別タスク。
- raw candidates considered はまだ大きい。CPU時間最適化は未実施。

## 2026-06-30 Task 33: Output quality audit and review report

### 目的

- 完了済みjobの出力MP4、subtitle、selected clip artifactを読み、品質確認用のJSON/Markdownレポートを生成する。
- 生成物の問題候補を見つけやすくする。
- selection behavior、scoring weight、rendering、manual review UI、approve/reject workflow は変更しない。

### 変更ファイル

- `scripts/audit_outputs.py`
- `backend/tests/test_audit_outputs_script.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `scripts/audit_outputs.py` を追加。
  - 入力: `--job-id`、`--output`、`--format json|markdown|both`
  - 読み取り対象: `selected_clips.json`、`selected_clips_summary.json`、`candidate_summary.json`、`transcript_segments.json`、`openai_scoring_summary.json`、`normal/*.json`、`shorts/*.json`、`.ass` subtitle files
  - 出力: `output_audit_report.json`、`output_audit_report.md`
- per-clip audit項目を追加。
  - type、file path、duration、resolution、selected start/end、transcript text length、first/last transcript text、rule/AI/final score、selection reason、quality warning、OpenAI score source、subtitle path、title、overlay title
- heuristic warnings を追加。
  - `very_short_transcript_text`
  - `likely_abrupt_start`
  - `likely_abrupt_ending`
  - `subtitle_too_dense`
  - `no_subtitle_file`
  - `missing_title`
  - `below_quality_threshold`
  - `backfilled_clip`
  - `rule_only_clip_in_high_quality_mode`
  - `short_duration_outside_recommended_range`
  - `normal_duration_outside_recommended_range`
  - `short_resolution_not_1080x1920`
- 解像度は metadata にあればそれを使い、不足時は host `ffprobe`、さらに Docker worker `ffprobe` へフォールバック。
- README に output quality audit の使い方と58分jobの監査結果を追記。
- fixture artifact だけで動く unit tests を追加。CIで実動画やDockerは不要。

### 検証結果

- `..\.venv\Scripts\python -m pytest tests\test_audit_outputs_script.py` from `backend`: 4 passed。
- `..\.venv\Scripts\python -m ruff check ..\scripts\audit_outputs.py tests\test_audit_outputs_script.py` from `backend`: All checks passed。
- 58分 full-render job audit:
  - command: `.\.venv\Scripts\python .\scripts\audit_outputs.py --job-id job_6e0b6c7539644c679e853eccfcb77039 --format both`
  - result: passed
  - output: `storage/outputs/job_6e0b6c7539644c679e853eccfcb77039/audit/output_audit_report.json`
  - output: `storage/outputs/job_6e0b6c7539644c679e853eccfcb77039/audit/output_audit_report.md`
  - generated normal count: `5`
  - generated short count: `10`
  - average duration: `154.669667`
  - average final score: `68.9708`
  - shorts: all resolved as `1080x1920`
  - clips requiring human visual inspection: `15`
  - warnings by type:
    - normal: `likely_abrupt_start=1`、`subtitle_too_dense=4`、`missing_title=5`、`below_quality_threshold=1`、`backfilled_clip=1`
    - short: `subtitle_too_dense=5`、`missing_title=10`、`likely_abrupt_start=4`、`likely_abrupt_ending=1`

### 未解決事項

- 監査は heuristic。実際の良し悪しはMP4目視確認が必要。
- subtitle density / missing title / abrupt boundary の改善実装は未実施。
- ショート構図改善は保留中。

## 2026-06-30 Task 35: Improve subtitle readability and reduce subtitle density warnings

### 目的

- ASS subtitle generation を読みやすくする。
- 特に 1080x1920 shorts で、1-2行・短すぎない表示時間・長文segment分割を行う。
- transcription、candidate selection、scoring、manual subtitle editing UI は変更しない。

### 変更ファイル

- `backend/app/render/subtitles_ass.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `backend/app/jobs/runner.py`
- `backend/app/schemas.py`
- `frontend/lib/types.ts`
- `frontend/components/SettingsPanel.tsx`
- `scripts/audit_outputs.py`
- `backend/tests/test_subtitles_ass.py`
- `backend/tests/test_audit_outputs_script.py`
- `backend/tests/test_api_routes.py`
- `README.md`
- `STATUS.md`

### 変更内容

- subtitle layout settings を追加。
  - `maxCharsPerLineShort`
  - `maxCharsPerLineNormal`
  - `maxLines`
  - `minSubtitleDuration`
  - `maxSubtitleDuration`
  - `minGapBetweenSubtitles`
- shorts default:
  - `maxCharsPerLineShort=16`
  - `maxLines=2`
- normal default:
  - `maxCharsPerLineNormal=28`
  - `maxLines=2`
- ASS生成を改善。
  - 日本語句読点 `。、！？!?` と自然境界を優先して分割。
  - 長い transcript segment を複数 subtitle event に分割。
  - event timing を文字数比で配分。
  - 短すぎる隣接eventを結合。
  - min display duration と max display duration を考慮。
- render path に subtitle settings を伝播。
  - normal render
  - short render
  - worker pipeline settings
- audit を更新。
  - Title style は subtitle density 判定から除外。
  - normal / short 別の readability threshold を使用。
  - `density_reasons` と `worst_density_samples` を report に出力。

### 検証結果

- full checks:
  - `..\.venv\Scripts\python -m ruff check . ..\scripts\audit_outputs.py` from `backend`: All checks passed。
  - `..\.venv\Scripts\python -m pytest` from `backend`: 144 passed, 1 skipped, 1 warning。
  - `npm run lint` from `frontend`: passed。
  - `npm run typecheck` from `frontend`: passed。
  - `npm run build` from `frontend`: passed。
- targeted tests:
  - `..\.venv\Scripts\python -m pytest tests\test_subtitles_ass.py tests\test_audit_outputs_script.py`: 14 passed。
  - `..\.venv\Scripts\python -m pytest tests\test_subtitles_ass.py tests\test_audit_outputs_script.py tests\test_api_routes.py tests\test_render_normal_selected.py tests\test_short_rendering.py`: 33 passed, 1 warning。
  - `..\.venv\Scripts\python -m ruff check app\render\subtitles_ass.py app\render\render_normal.py app\render\render_short.py app\schemas.py app\jobs\runner.py ..\scripts\audit_outputs.py tests\test_subtitles_ass.py tests\test_audit_outputs_script.py tests\test_api_routes.py`: All checks passed。
- 58分 subtitle-only smoke:
  - source job: `job_6e0b6c7539644c679e853eccfcb77039`
  - smoke job: `job_6e0b6c7539644c679e853eccfcb77039_task35_subtitle_smoke`
  - MP4は再レンダーしていない。既存 selected clips と transcript から ASS だけ再生成。
  - `scripts/audit_outputs.py --job-id job_6e0b6c7539644c679e853eccfcb77039_task35_subtitle_smoke --format both`: passed。
  - subtitle_too_dense:
    - normal: `1`
    - short: `0`

### 未解決事項

- 58分 smoke はASS再生成のみ。MP4焼き込み済み字幕の完全確認には再レンダーが必要。
- subtitle誤変換そのものは transcription 側の問題であり未対応。
- missing title、abrupt boundary、short composition は別タスク。

## 2026-06-30 Task 35b: Validate subtitle burn-in after readability improvements

### 目的

- Task 35 の ASS readability 改善が、実際の MP4 焼き込みでも壊れていないか確認する。
- 既存58分完了jobから小さめの subset を再レンダーする。
- candidate selection、scoring、manual subtitle editing UI、approve/reject workflow は変更しない。

### 変更ファイル

- `backend/Dockerfile`
- `backend/app/render/subtitles_ass.py`
- `backend/tests/test_subtitles_ass.py`
- `backend/tests/test_smoke_subtitle_burn_in_script.py`
- `scripts/smoke_subtitle_burn_in.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `scripts/smoke_subtitle_burn_in.py` を追加。
  - 既存job artifacts から selected clips と transcript を読み込む。
  - `normal=1`、`short=2` など小さめの実レンダー smoke を実行できる。
  - host に FFmpeg がなくても `--docker-service worker` で worker container 内の FFmpeg / ffprobe を使える。
- backend/worker container に `fonts-noto-cjk` と `fontconfig` を追加。
- ASS subtitle font を `Arial` から `Noto Sans CJK JP` に変更。
  - 日本語字幕が `□` になる missing-glyph 問題を解消。
- README に subtitle burn-in smoke command を追記。

### 検証結果

- targeted tests:
  - `..\.venv\Scripts\python -m pytest tests\test_subtitles_ass.py tests\test_smoke_subtitle_burn_in_script.py`: 14 passed。
  - `..\.venv\Scripts\python -m ruff check app\render\subtitles_ass.py tests\test_subtitles_ass.py ..\scripts\smoke_subtitle_burn_in.py tests\test_smoke_subtitle_burn_in_script.py`: All checks passed。
- Docker runtime:
  - `docker compose up -d --build backend worker`: passed。
  - `Invoke-RestMethod http://localhost:8000/health`: `{"status":"ok"}`。
  - worker `fc-match 'Noto Sans CJK JP'`: `NotoSansCJK-Regular.ttc`。
- Burn-in smoke:
  - source job: `job_6e0b6c7539644c679e853eccfcb77039`
  - smoke job: `job_6e0b6c7539644c679e853eccfcb77039_task35b_burnin`
  - command: `.\.venv\Scripts\python .\scripts\smoke_subtitle_burn_in.py --docker-service worker --source-job-id job_6e0b6c7539644c679e853eccfcb77039 --output-job-id job_6e0b6c7539644c679e853eccfcb77039_task35b_burnin --normal-count 1 --short-count 2 --normal-duration-limit 120 --short-layout center_crop`
  - normal rendered: `1`
  - shorts rendered: `2`
  - render failures: `0`
  - short dimensions: `1080x1920`
  - normal dimensions: `1280x720`
  - ASS files: normal `1`、short `2`
  - MP4 files: normal `1`、short `2`
- Audit:
  - command: `.\.venv\Scripts\python .\scripts\audit_outputs.py --job-id job_6e0b6c7539644c679e853eccfcb77039_task35b_burnin --format both`
  - result: passed。
  - generated normal: `1`
  - generated short: `2`
  - subtitle_too_dense: normal `0`、short `0`
  - warnings: `likely_abrupt_start` のみ。
- Visual frame checks:
  - `storage/temp/task35b_short_01_frame.png`: Japanese subtitle rendered as glyphs, not boxes。
  - `storage/temp/task35b_normal_01_frame.png`: normal subtitle rendered correctly。

### 未解決事項

- transcription 誤変換そのものは未対応。
- short composition / face-aware layout は保留。
- overlay_title ありの short overlap は今回の low_cost subset では未確認。

## 2026-07-01 Task 35c: Validate overlay title burn-in for high_quality shorts

### 目的

- high_quality short の `overlay_title` と subtitles を同時に焼き込んだ場合の表示を検証する。
- title は上 safe area、subtitle は下 safe area に出し、重なりがないことを確認する。
- candidate selection、scoring weights、manual subtitle editing UI、approve/reject workflow は変更しない。

### 変更ファイル

- `scripts/smoke_subtitle_burn_in.py`
- `scripts/audit_outputs.py`
- `backend/tests/test_smoke_subtitle_burn_in_script.py`
- `backend/tests/test_audit_outputs_script.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `scripts/smoke_subtitle_burn_in.py` を high_quality overlay title smoke に拡張。
  - `--job-id` alias を追加。
  - `--video` から小さめの high_quality E2E を先に走らせる経路を追加。
  - `--mode high_quality`
  - `--openai-candidate-limit`
  - `--timeout`
  - `--require-overlay-title`
  - `--force-overlay-title`
  - `--extract-short-frames` / `--no-extract-short-frames`
  - `--run-audit` / `--no-run-audit`
- shortごとに代表フレームを `storage/outputs/{job_id}/audit_frames/` に保存。
- ASS の Title / Subtitle style と dialogue event を検査。
- Title と Subtitle の推定縦位置 gap を計算し、overlap を検出。
- `audit_outputs.py` に ASS title検査を追加。
  - `title_dialogue_count`
  - `font_supports_japanese`
  - `title_subtitle_vertical_gap`
  - `title_subtitle_vertical_overlap`
  - warning: `missing_ass_title_event`
  - warning: `title_subtitle_vertical_overlap`
  - warning: `subtitle_font_missing_japanese_support`

### 検証結果

- targeted tests:
  - `..\.venv\Scripts\python -m pytest tests\test_smoke_subtitle_burn_in_script.py tests\test_audit_outputs_script.py tests\test_subtitles_ass.py`: 23 passed。
  - `..\.venv\Scripts\python -m ruff check ..\scripts\smoke_subtitle_burn_in.py ..\scripts\audit_outputs.py tests\test_smoke_subtitle_burn_in_script.py tests\test_audit_outputs_script.py tests\test_subtitles_ass.py`: All checks passed。
- Docker runtime:
  - `docker compose ps`: backend healthy、frontend/redis/worker running。
  - worker `fc-match 'Noto Sans CJK JP'`: `NotoSansCJK-Regular.ttc`。
  - worker `DEFAULT_ASS_FONT`: `Noto Sans CJK JP`。
- high_quality overlay burn-in smoke:
  - source job: `job_dfd13dd8435a401f9ab9773fa217bd18`
  - smoke job: `job_dfd13dd8435a401f9ab9773fa217bd18_task35c_overlay_burnin`
  - command: `.\.venv\Scripts\python .\scripts\smoke_subtitle_burn_in.py --docker-service worker --job-id job_dfd13dd8435a401f9ab9773fa217bd18 --output-job-id job_dfd13dd8435a401f9ab9773fa217bd18_task35c_overlay_burnin --mode high_quality --normal-count 1 --short-count 2 --normal-duration-limit 120 --require-overlay-title --force-overlay-title "日本語タイトル確認 {number}" --short-layout center_crop`
  - normal rendered: `1`
  - shorts rendered: `2`
  - render failures: `0`
  - short dimensions: `1080x1920`
  - shorts with overlay title: `2`
  - ASS title dialogue count: `1` per short
  - ASS subtitle dialogue count: `19`, `22`
  - Title margin: `150`
  - Subtitle margin: `250`
  - title/subtitle vertical gap: `1172`
  - title/subtitle overlap: `false`
  - safe vertical positions: `true`
  - extracted frames:
    - `storage/outputs/job_dfd13dd8435a401f9ab9773fa217bd18_task35c_overlay_burnin/audit_frames/short_01.png`
    - `storage/outputs/job_dfd13dd8435a401f9ab9773fa217bd18_task35c_overlay_burnin/audit_frames/short_02.png`
- Audit:
  - `scripts/audit_outputs.py --job-id job_dfd13dd8435a401f9ab9773fa217bd18_task35c_overlay_burnin --format both`: passed。
  - generated normal: `1`
  - generated short: `2`
  - short warnings: `0`
  - normal warnings: `likely_abrupt_ending=1`、`subtitle_too_dense=1`
- Visual frame checks:
  - `short_01.png`: top title and lower subtitle render as Japanese glyphs, no overlap。
  - `short_02.png`: top title and lower subtitle render as Japanese glyphs, no overlap。

### 未解決事項

- normal clip の `subtitle_too_dense=1` は今回の overlay title 検証対象外。
- forced overlay title を使って glyph と layout を確認した。実際の OpenAI title 文言の品質調整は未実施。
- short composition / face-aware layout は保留。

## 2026-07-01 Task 34: Fix title fallback and propagation

### 目的

- low_cost / rule-only clip でも OpenAI API なしで非空 title を生成する。
- `selected_clips.json`、clip metadata、ExportItem、results API、audit report に title を伝播する。
- candidate selection、scoring weights、hard gates、manual editing UI、approve/reject workflow は変更しない。

### 変更ファイル

- `backend/app/candidates/merge_boundaries.py`
- `backend/app/candidates/title_fallback.py`
- `backend/app/jobs/runner.py`
- `backend/app/jobs/summaries.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `backend/app/scoring/openai_score.py`
- `scripts/audit_outputs.py`
- `backend/tests/test_title_fallback.py`
- `backend/tests/test_render_normal_selected.py`
- `backend/tests/test_short_rendering.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_audit_outputs_script.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `Candidate.title_source` を追加。
  - `openai`
  - `transcript_fallback`
  - `deterministic_fallback`
  - `existing`
- `backend/app/candidates/title_fallback.py` を追加。
  - OpenAI / 既存 title を保持。
  - candidate `transcript_text` から title を生成。
  - candidate text が空なら clip 範囲内 transcript segments から title を生成。
  - transcript が使えない場合は `Normal Clip 01` / `Short 01` 形式に fallback。
  - 日本語 filler prefix を除去。
- pipeline で selection 後、render 前に selected candidates へ title を付与。
- normal / short metadata JSON に `title_source` を出力。
- short metadata に fallback `overlay_title` を出力。
- fallback overlay title は metadata に残すが、low_cost fallback title を自動で burn-in しない。
- OpenAI structured score 由来 title は `title_source=openai` として保持。
- selected clips summary に title / overlay_title / title_source を追加。
- audit の `missing_title` を「本当に title が空」のみに変更。
- placeholder title は `generic_fallback_title` として弱い warning に分離。

### 検証結果

- targeted tests:
  - `..\.venv\Scripts\python -m pytest tests\test_title_fallback.py tests\test_render_normal_selected.py tests\test_short_rendering.py tests\test_audit_outputs_script.py tests\test_real_pipeline.py`: 34 passed。
  - `..\.venv\Scripts\python -m ruff check app\candidates\title_fallback.py app\candidates\merge_boundaries.py app\jobs\runner.py app\jobs\summaries.py app\render\render_normal.py app\render\render_short.py app\scoring\openai_score.py tests\test_title_fallback.py tests\test_render_normal_selected.py tests\test_short_rendering.py tests\test_audit_outputs_script.py tests\test_real_pipeline.py ..\scripts\audit_outputs.py`: All checks passed。
- full checks:
  - `..\.venv\Scripts\python -m ruff check . ..\scripts\audit_outputs.py ..\scripts\smoke_subtitle_burn_in.py`: All checks passed。
  - `..\.venv\Scripts\python -m pytest`: 162 passed, 1 skipped。
  - `npm run lint`: passed。
  - `npm run typecheck`: passed。
  - `npm run build`: passed。
- Existing 58-minute audit rerun:
  - `job_e6369a199f9945d7bdbef9f5bad5bb32`
  - `missing_title`: `0`
  - `generic_fallback_title`: `15`
  - `subtitle_too_dense`: `0`
  - `title_subtitle_overlap`: `0`
- Reference 58-minute audit rerun:
  - `job_6e0b6c7539644c679e853eccfcb77039`
  - `missing_title`: `0`
  - `generic_fallback_title`: `15`

### 未解決事項

- 既存 artifact は再renderしていないため、title 内容は generic fallback のまま。新規生成では transcript fallback title が metadata に入る。
- likely abrupt start/end は未対応。次タスクは boundary refinement。

## 2026-07-01 Task 36a: Move subtitle sidecar files away from rendered MP4 files

### 目的

- 焼き込み済みMP4と同じフォルダ・同じbasenameの `.ass` が動画プレイヤーに外部字幕として自動読込され、字幕が二重表示される問題を防ぐ。
- candidate selection、scoring、字幕テキスト分割、manual review UI、approve/reject workflow は変更しない。

### 変更ファイル

- `backend/app/storage/paths.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `backend/app/jobs/runner.py`
- `scripts/audit_outputs.py`
- `scripts/check_subtitle_sidecar_risk.py`
- `scripts/smoke_subtitle_burn_in.py`
- `backend/tests/test_render_normal_selected.py`
- `backend/tests/test_short_rendering.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_audit_outputs_script.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `.ass` 生成先をMP4横から分離。
  - `outputs/{job_id}/subtitles/normal/normal_XX.ass`
  - `outputs/{job_id}/subtitles/shorts/short_XX.ass`
- `normal/` と `shorts/` にはMP4とJSONだけを残す。
- ExportItem / clip metadata の `subtitle_path` を新しいsubtitleディレクトリへ更新。
- ZIP内レイアウトを分離。
  - `videos/normal/*.mp4`
  - `videos/shorts/*.mp4`
  - `subtitles/normal/*.ass`
  - `subtitles/shorts/*.ass`
  - `metadata/normal/*.json`
  - `metadata/shorts/*.json`
  - `metadata/*.json`
- auditに `external_subtitle_autoload_risk` warning を追加。
- `scripts/check_subtitle_sidecar_risk.py` を追加。
  - job IDからMP4横の同名 `.ass/.srt/.vtt` を検出する。
- subtitle burn-in smoke scriptも新レイアウトに更新。

### 検証結果

- targeted ruff:
  - `..\.venv\Scripts\python -m ruff check app\storage\paths.py app\render\render_normal.py app\render\render_short.py app\jobs\runner.py tests\test_render_normal_selected.py tests\test_short_rendering.py tests\test_real_pipeline.py tests\test_audit_outputs_script.py ..\scripts\audit_outputs.py ..\scripts\check_subtitle_sidecar_risk.py ..\scripts\smoke_subtitle_burn_in.py`: All checks passed。
- targeted tests:
  - `..\.venv\Scripts\python -m pytest tests\test_render_normal_selected.py tests\test_short_rendering.py tests\test_audit_outputs_script.py tests\test_real_pipeline.py tests\test_smoke_subtitle_burn_in_script.py`: 38 passed。
- full backend checks:
  - `..\.venv\Scripts\python -m ruff check . ..\scripts\audit_outputs.py ..\scripts\check_subtitle_sidecar_risk.py ..\scripts\smoke_subtitle_burn_in.py`: All checks passed。
  - `..\.venv\Scripts\python -m pytest`: 164 passed, 1 skipped。
- frontend checks:
  - `npm run lint`: pass。
  - `npm run typecheck`: pass。
  - `npm run build`: pass。
- real-video smoke:
  - input: `C:\Users\peace.YAGURUMAGIKUHM\Desktop\解説_後藤直義、森川潤）.mp4`
  - job: `job_6a67dd0097e64d47bce4ed5ddc58ef1b`
  - mode: `low_cost`
  - output: normal `1/1`, short `2/2`, job `completed`
  - ffprobe: normal `1280x720`, shorts `1080x1920`
  - layout: `normal/normal_01.ass=False`, `shorts/short_01.ass=False`, `subtitles/normal/normal_01.ass=True`, `subtitles/shorts/short_01.ass=True`
  - `scripts/check_subtitle_sidecar_risk.py --job-id job_6a67dd0097e64d47bce4ed5ddc58ef1b --json`: `risk_count=0`
  - `scripts/audit_outputs.py --job-id job_6a67dd0097e64d47bce4ed5ddc58ef1b --format both`: `external_subtitle_autoload_risk=0`

### 未解決事項

- 既存の生成済みjobは旧レイアウトの `.ass` が残るため、再生成しない限りプレイヤー自動読込リスクが残る。
- 今回のsmokeではshortに `missing_ass_title_event=2` が残る。二重字幕原因ではないため、overlay title burn-in側の別件として扱う。

## 2026-07-02 Task 36: Improve abrupt start and end boundaries

### 目的

- selected clip の start/end を render 前に保守的に補正し、会話途中で始まる/終わる出力を減らす。
- scoring weights、hard gates、OpenAI scoring、title fallback、subtitle layout、subtitle sidecar layout、manual review UI、approve/reject workflow は変更しない。

### 変更ファイル

- `backend/app/candidates/boundary_refinement.py`
- `backend/app/candidates/merge_boundaries.py`
- `backend/app/jobs/runner.py`
- `backend/app/jobs/summaries.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `backend/app/schemas.py`
- `backend/tests/test_boundary_refinement.py`
- `backend/tests/test_audit_outputs_script.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_render_normal_selected.py`
- `backend/tests/test_short_rendering.py`
- `frontend/lib/types.ts`
- `frontend/components/SettingsPanel.tsx`
- `scripts/audit_outputs.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `enableBoundaryRefinement` を追加。default `true`。
- boundary 設定を追加。
  - `boundaryLeadingPaddingSeconds`: `0.4`
  - `boundaryTrailingPaddingSeconds`: `0.6`
  - `maxBoundaryExpansionSeconds`: `3`
  - `allowBoundaryExpansionBeyondMaxDuration`: `false`
- `selecting_clips` 後、render 前に selected candidate のみ boundary refinement を実行。
- transcript segment start/end、弱い継続マーカー、scene boundary、隣接 silence interval を使って境界を補正。
- `normalMinDuration` / `normalMaxDuration`、`shortMinDuration` / `shortMaxDuration` を維持。
- selected clip / render metadata / summary / audit に以下を出力。
  - `original_start`
  - `original_end`
  - `refined_start`
  - `refined_end`
  - `boundary_refined`
  - `boundary_refinement_reason`
  - `boundary_expansion_seconds`
- `audit_outputs.py` は refined boundary を有効境界として扱い、original/refined range をレポートに出す。

### 検証結果

- targeted ruff:
  - `..\.venv\Scripts\python -m ruff check app\candidates\boundary_refinement.py app\candidates\merge_boundaries.py app\jobs\runner.py app\jobs\summaries.py app\schemas.py app\render\render_normal.py app\render\render_short.py tests\test_boundary_refinement.py tests\test_audit_outputs_script.py tests\test_real_pipeline.py tests\test_render_normal_selected.py tests\test_short_rendering.py ..\scripts\audit_outputs.py`: All checks passed。
- targeted tests:
  - `..\.venv\Scripts\python -m pytest tests\test_boundary_refinement.py tests\test_audit_outputs_script.py tests\test_real_pipeline.py tests\test_render_normal_selected.py tests\test_short_rendering.py`: 42 passed。
- backend CI checks:
  - `..\.venv\Scripts\python -m ruff check .`: All checks passed。
  - `..\.venv\Scripts\python -m pytest`: 175 passed, 1 skipped。
- frontend CI checks:
  - `npm run lint`: pass。
  - `npm run typecheck`: pass。
  - `npm run build`: pass。
- synthetic E2E:
  - `python .\scripts\e2e_sample_video.py --start --duration 25 --timeout-seconds 300`: E2E PASSED。
  - job: `job_ed6d1222e0994400ba75d621259d1eb0`
  - output: short `1/1`, `1080x1920`
  - `selected_clips.json` / `short_01.json` に boundary metadata が出力されることを確認。
  - audit warning: `missing_ass_title_event=1`。boundary 起因ではなく low_cost overlay title 非焼き込みの既存警告。
- docker compose rebuild:
  - `docker compose up --build -d`: backend / worker / frontend を PR #13 ブランチのコードで再build。
  - `docker compose ps`: backend / frontend / redis / worker 起動。
  - `GET http://localhost:8000/health`: `ok`。
- short real-video E2E:
  - input: `C:\Users\peace.YAGURUMAGIKUHM\Desktop\解説_後藤直義、森川潤）.mp4`
  - command: `python .\scripts\e2e_real_video.py --mode low_cost --normal-count 1 --short-count 2 --normal-min-duration 20 --normal-max-duration 120 --short-min-duration 20 --short-max-duration 75 --selection-policy fill_requested --timeout 1800`
  - job: `job_5b228a81145b4422a4f3d2265541f2bc`
  - result: `REAL VIDEO E2E PASSED`
  - output: normal `1/1`, short `2/2`, render failures `0`
  - shorts: all `1080x1920`
  - ZIP size: `37600578` bytes
  - runtime: total `197.578s`, transcription `115.390s`, candidate generation `26.406s`, normal render `2.047s`, short render `10.234s`
  - boundary metadata: `original_start/end`, `refined_start/end`, `boundary_refined`, `boundary_refinement_reason`, `boundary_expansion_seconds` 出力確認。
  - boundary refined: `2/3`
  - `scripts/audit_outputs.py --job-id job_5b228a81145b4422a4f3d2265541f2bc --format both`: reports written。
  - `scripts/check_subtitle_sidecar_risk.py --job-id job_5b228a81145b4422a4f3d2265541f2bc --json`: `risk_count=0`
  - audit warnings: `likely_abrupt_start=1`, `likely_abrupt_ending=1`, `missing_ass_title_event=2`
  - `missing_title=0`, `subtitle_too_dense=0`, `title_subtitle_overlap=0`, `external_subtitle_autoload_risk=0`
- 58-minute real-video E2E:
  - input: `C:\Users\peace.YAGURUMAGIKUHM\Desktop\【朝倉慶vs西田真澄】物価が牙をむく！？株高の代償…フジメディアHG大株主・ダルトンアクティビストが語るインフレの悲劇とは？【ReHacQ】 - ReHacQ−リハック−【公式】 (720p, h264).mp4`
  - command: `python .\scripts\e2e_real_video.py --mode low_cost --normal-count 5 --short-count 10 --selection-policy fill_requested --timeout 14400`
  - job: `job_e9a049ee5e3446c0b92943429fa8918a`
  - result: `REAL VIDEO E2E PASSED`
  - output: normal `5/5`, short `10/10`, render failures `0`
  - shorts: all `1080x1920`
  - normal durations: all within `90-600s`
  - short durations: all within `20-75s`
  - ZIP size: `388844740` bytes
  - runtime: total `594.859s`, transcription `236.750s`, scene detection `105.500s`, candidate generation `66.860s`, normal render `64.859s`, short render `71.266s`, zip packaging `22.250s`
  - candidate generation: chunks `12`, raw considered `500000`, kept `normal=600 / short=800`, peak memory `406.035MB`, memory guard `False`
  - selected: normal `5/5`, short `10/10`, backfill `1`, overlap relaxed `0`
  - boundary metadata: all `15/15` clips include original/refined boundary fields.
  - boundary refined: `8/15`
  - `scripts/audit_outputs.py --job-id job_e9a049ee5e3446c0b92943429fa8918a --format both`: reports written。
  - `scripts/check_subtitle_sidecar_risk.py --job-id job_e9a049ee5e3446c0b92943429fa8918a --json`: `risk_count=0`
  - audit warnings: `likely_abrupt_start=4`, `likely_abrupt_ending=1`, `subtitle_too_dense=2`, `missing_ass_title_event=10`, `below_quality_threshold=1`, `backfilled_clip=1`
  - `missing_title=0`, `title_subtitle_overlap=0`, `external_subtitle_autoload_risk=0`
- 58-minute before/after comparison:
  - before reference: `job_e6369a199f9945d7bdbef9f5bad5bb32`
  - before abrupt warnings: `likely_abrupt_start=1`, `likely_abrupt_ending=7`, total `8`
  - after abrupt warnings: `likely_abrupt_start=4`, `likely_abrupt_ending=1`, total `5`
  - 判断: end boundary は大きく改善。start warning は増えたが、合計 abrupt warning は減少。

### 未解決事項

- 58分auditで残った `likely_abrupt_start=4` / `likely_abrupt_ending=1` はゼロではない。境界補正は保守的に維持し、過剰拡張はしない。
- 58分auditで `subtitle_too_dense=2` が出たが、該当2clipはいずれも `boundary_refined=false`。Task36の境界補正起因ではないため、字幕密度側の別件として扱う。
- low_cost shorts の `missing_ass_title_event` は overlay title burn-in 非使用の既存警告。Task36の境界補正対象外。
- `scripts` 全体を ruff 対象に含めた追加確認では、今回未変更の `scripts/compare_runs.py` 既存長行で `E501` が出る。CI対象の `backend && ruff check .` は通過済み。

## 2026-07-02 Task 37: Clarify short overlay title policy and audit semantics

### 目的

- low_cost short で overlay title を metadata として持つが ASS に焼かないケースを正式な挙動として扱う。
- `missing_ass_title_event` は overlay title burn-in が期待される場合だけ warning にする。
- candidate selection、scoring、subtitle splitting、boundary refinement、manual review UI、approve/reject workflow は変更しない。

### 変更ファイル

- `backend/app/schemas.py`
- `backend/app/jobs/runner.py`
- `backend/app/render/render_short.py`
- `backend/tests/test_short_rendering.py`
- `backend/tests/test_audit_outputs_script.py`
- `backend/tests/test_smoke_subtitle_burn_in_script.py`
- `backend/tests/test_e2e_real_video_script.py`
- `frontend/lib/types.ts`
- `frontend/components/SettingsPanel.tsx`
- `scripts/audit_outputs.py`
- `scripts/e2e_real_video.py`
- `scripts/smoke_subtitle_burn_in.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `shortOverlayTitleMode` を追加。
  - `auto`
  - `always`
  - `high_quality_only`
  - `never`
- default は `auto`。
  - `high_quality`: overlay title burn-in を期待。
  - `low_cost`: overlay title は metadata に保持し、明示指定がなければ焼き込まない。
- short metadata に以下を追加。
  - `overlay_title_expected`
  - `overlay_title_rendered`
  - `overlay_title_mode`
- `audit_outputs.py` は `overlay_title_expected=true` の場合だけ `missing_ass_title_event` を warning にする。
- overlay title が存在するが意図的に焼かれていない場合は `overlay_title_not_rendered=true` として情報に残す。
- smoke / E2E script に `--short-overlay-title-mode` を追加。
- frontend settings に short overlay title mode の選択肢を追加。

### 検証結果

- targeted checks:
  - `..\.venv\Scripts\python -m ruff check app\render\render_short.py app\jobs\runner.py app\schemas.py tests\test_short_rendering.py tests\test_audit_outputs_script.py tests\test_smoke_subtitle_burn_in_script.py tests\test_e2e_real_video_script.py ..\scripts\audit_outputs.py ..\scripts\smoke_subtitle_burn_in.py ..\scripts\e2e_real_video.py`: All checks passed。
  - `..\.venv\Scripts\python -m pytest tests\test_short_rendering.py tests\test_audit_outputs_script.py tests\test_smoke_subtitle_burn_in_script.py tests\test_e2e_real_video_script.py`: 44 passed。
- backend CI checks:
  - `..\.venv\Scripts\python -m ruff check .`: All checks passed。
  - `..\.venv\Scripts\python -m pytest`: 182 passed, 1 skipped。
- frontend CI checks:
  - `npm run lint`: pass。
  - `npm run typecheck`: pass。
  - `npm run build`: pass。
- 既存58分 low_cost job audit再実行:
  - job: `job_e9a049ee5e3446c0b92943429fa8918a`
  - `..\.venv\Scripts\python ..\scripts\audit_outputs.py --job-id job_e9a049ee5e3446c0b92943429fa8918a --format both`
  - generated clips: normal `5`, short `10`
  - `missing_ass_title_event=0`
  - short `overlay_title_not_rendered=10`
  - short `overlay_title_expected=0`
  - short `overlay_title_rendered=0`
  - 判断: low_cost short で overlay title を metadata に持つが焼かないケースは warning ではなく情報として扱われる。

### 未解決事項

- 新規の実動画 render E2E は未実行。既存 58分 low_cost artifact の audit再実行で Task 37 の主目的は確認済み。
- high_quality overlay title smoke は実動画では未実行。unit/script tests で policy と ASS title event 条件を確認済み。

## 2026-07-02 Task 38: Display clip metadata and audit warnings in results UI

### 目的

- results UI を品質確認に使えるように、clip metadata と audit warning を表示する。
- 手動 trimming、approve/reject、subtitle editing、candidate selection、scoring、rendering は変更しない。

### 変更ファイル

- `backend/app/api/jobs.py`
- `backend/app/api/exports.py`
- `backend/app/schemas.py`
- `backend/tests/test_api_routes.py`
- `frontend/app/results/[jobId]/page.tsx`
- `frontend/components/ResultVideoCard.tsx`
- `frontend/lib/types.ts`
- `README.md`
- `STATUS.md`

### 変更内容

- `GET /api/jobs/{job_id}/results` に clip metadata を追加。
  - `candidateId`
  - `titleSource`
  - `finalScore`
  - `ruleScore`
  - `aiScore`
  - `selectionReason`
  - `belowQualityThreshold`
  - `qualityWarning`
  - `openaiScoreSource`
  - `boundaryRefined`
  - `overlayTitleExpected`
  - `overlayTitleRendered`
  - `start` / `end` / `originalStart` / `originalEnd` / `refinedStart` / `refinedEnd`
  - `resolution`
  - `auditWarnings`
  - `subtitlePath` / `subtitleUrl`
  - `metadataPath` / `metadataUrl`
- `audit/output_audit_report.json` が存在する場合、results response に `auditSummary` を追加。
- `GET /api/exports/{export_id}/metadata` を追加。
- `GET /api/exports/{export_id}/subtitle` を追加。
- results page に job-level audit summary を表示。
- result card に title、duration、score、warning badges、title source、score source、boundary refined、short overlay title status を表示。
- card details に range、original range、selection reason、quality warning、subtitle path、metadata/subtitle links を表示。

### 検証結果

- targeted backend tests:
  - `..\.venv\Scripts\python -m pytest tests\test_api_routes.py tests\test_render_normal_selected.py tests\test_short_rendering.py`: 24 passed。
- targeted backend ruff:
  - `..\.venv\Scripts\python -m ruff check app\api\jobs.py app\api\exports.py app\schemas.py tests\test_api_routes.py`: All checks passed。
- frontend checks:
  - `npm run typecheck`: pass。
  - `npm run lint`: pass。
- backend CI checks:
  - `..\.venv\Scripts\python -m ruff check .`: All checks passed。
  - `..\.venv\Scripts\python -m pytest`: 182 passed, 1 skipped。
- frontend build:
  - `npm run build`: pass。
- merge前 runtime smoke:
  - `docker compose up -d --build`: backend / worker / frontend / redis 起動。
  - `Invoke-RestMethod http://localhost:8000/health`: `{"status":"ok"}`。
  - `Invoke-WebRequest http://localhost:3000 -UseBasicParsing`: `200`。
- 既存58分 auditあり job results確認:
  - job: `job_e9a049ee5e3446c0b92943429fa8918a`
  - `GET /api/jobs/{job_id}/results`: `200`。
  - result: normal `5`, short `10`, `auditSummary` present。
  - audit warning counts: `likely_abrupt_start=4`, `likely_abrupt_ending=1`, `below_quality_threshold=1`, `backfilled_clip=1`, `subtitle_too_dense=2`。
  - first clip metadata: `titleSource=transcript_fallback`, `selectionReason=above_quality_threshold`, `metadataUrl` present, `subtitleUrl` present。
  - `GET /api/exports/{export_id}/metadata`: `200`、metadata title / boundary field を確認。
  - `GET /api/exports/{export_id}/subtitle`: `200`、ASS file downloaded、`[Script Info]` を確認。
  - `GET http://localhost:3000/results/{job_id}`: `200`。
- auditなし completed job確認:
  - job: `job_aeea2831f0d7486dac106cd9462a94fe`
  - `GET /api/jobs/{job_id}/results`: `200`。
  - result: normal `3`, short `5`, `auditSummary=null`。
  - `GET http://localhost:3000/results/{job_id}`: `200`。

### 未解決事項

- audit warning は `audit/output_audit_report.json` が存在する場合だけ results API に出る。HTTP handler 内で重い audit/ffprobe は実行しない。

## 2026-07-03 Task 39 v1 release smoke checklist

### 目的

- v1 release 前の確認項目、実行順、合格条件を固定化する。
- 実動画処理・selection・scoring・rendering の挙動は変更しない。

### 変更ファイル

- `docs/V1_RELEASE_CHECKLIST.md`
- `scripts/v1_smoke_check.py`
- `backend/tests/test_v1_smoke_check_script.py`
- `README.md`
- `STATUS.md`

### 変更内容

- v1 release smoke checklist を追加。
  - `docker compose up -d --build`
  - backend `/health`
  - frontend reachable
  - low_cost real-video E2E
  - optional high_quality OpenAI smoke
  - `audit_outputs.py`
  - `check_subtitle_sidecar_risk.py`
  - results UI
  - metadata endpoint
  - subtitle endpoint
  - ZIP download
- `scripts/v1_smoke_check.py` を追加。
  - backend health / frontend reachability を確認。
  - 任意 `--job-id` で results API、metadata、subtitle、MP4、ZIP、local sidecar risk を確認。
  - `OPENAI_API_KEY` は要求しない。
- README から v1 checklist と smoke helper に誘導。

### 検証結果

- script syntax/help:
  - `python -m py_compile scripts\v1_smoke_check.py`: pass。
  - `python .\scripts\v1_smoke_check.py --help`: pass。
- targeted backend tests:
  - `..\.venv\Scripts\python -m pytest tests\test_v1_smoke_check_script.py`: 5 passed。
- backend CI checks:
  - `..\.venv\Scripts\python -m ruff check .`: All checks passed。
  - `..\.venv\Scripts\python -m pytest`: 187 passed, 1 skipped。
- frontend CI checks:
  - `npm run lint`: pass。
  - `npm run typecheck`: pass。
  - `npm run build`: pass。
- docker runtime確認:
  - `docker compose ps`: Docker Desktop daemon 未起動で失敗。
  - error: `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`。
  - そのため、この変更ブランチでは runtime smoke / 実動画E2E は未実行。

### 未解決事項

- v1 smoke helper は実動画 E2E 自体は実行しない。実動画生成は既存 `scripts/e2e_real_video.py` を使う。

## 2026-07-04 Task 40 v1 release smoke execution

### 目的

- Task 39 で追加した v1 release smoke checklist / script を Docker runtime 上で実行する。
- v1 release tag 作成前の可否判断材料を残す。
- 機能追加、selection、scoring、rendering、UI 挙動変更は行わない。

### 対象

- tested main commit: `88d0a82`
- base tag: `v0.20-v1-release-smoke-checklist`
- branch: `codex/task-40-v1-release-smoke-execution`

### 実行内容

- Docker Desktop 起動確認:
  - 初回 `docker version`: daemon 未起動で失敗。
  - `Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"` 後、`docker info` が成功。
- compose rebuild/start:
  - `docker compose down --remove-orphans`: pass。
  - `docker compose up -d --build`: pass。
  - `docker compose ps`: backend / frontend / worker / redis が running。
  - backend health: `healthy`。
- endpoint:
  - `curl.exe -fsS http://localhost:8000/health`: `{"status":"ok"}`。
  - `curl.exe -fsSI -L http://localhost:3000`: `/` は `/upload` へ 307 redirect 後、200。
  - `curl.exe -fsSI http://localhost:3000/upload`: 200。
  - `curl.exe -fsSI http://localhost:3000/results/job_e9a049ee5e3446c0b92943429fa8918a`: 200。
- runtime script:
  - `python scripts\smoke_runtime.py --skip-video`: `SMOKE PASSED`。
  - services: backend / frontend / redis / worker running。
  - backend/worker DB: `sqlite:////app/storage/autoclipper.db` で一致。
  - backend/worker storage: `/app/storage/uploads`, `/app/storage/temp`, `/app/storage/outputs` で一致。
  - backend/worker ffmpeg: `7.1.5-0+deb13u1`。
  - backend/worker ffprobe: `7.1.5-0+deb13u1`。
- v1 smoke script:
  - `python scripts\v1_smoke_check.py`: pass。
  - `python scripts\v1_smoke_check.py --job-id job_e9a049ee5e3446c0b92943429fa8918a`: pass。
    - normal: 5
    - short: 10
    - `auditSummary`: present
    - metadata download: pass
    - subtitle download: pass
    - MP4 download: pass, first clip bytes `45881151`
    - ZIP download: pass, bytes `388844740`
    - `local_sidecar_risk`: 0
- sample upload/job lifecycle:
  - `python scripts\e2e_sample_video.py`: `E2E PASSED`。
  - generated sample: `storage/temp/e2e_sample.mp4`
  - job: `job_9b1c19028e324691bfe7fc5db2cecb53`
  - transcript: fixture transcript, `fixture=True`
  - selected: normal 0/0, short 1/1
  - render failures: 0
  - downloaded MP4 ffprobe: `1080,1920`
  - ZIP download: pass。
- audit / sidecar:
  - `python scripts\audit_outputs.py --job-id job_9b1c19028e324691bfe7fc5db2cecb53 --format both`: pass。
    - report: `storage/outputs/job_9b1c19028e324691bfe7fc5db2cecb53/audit/output_audit_report.json`
    - report: `storage/outputs/job_9b1c19028e324691bfe7fc5db2cecb53/audit/output_audit_report.md`
    - generated normal: 0
    - generated short: 1
    - inspection: 0
  - `python scripts\check_subtitle_sidecar_risk.py --job-id job_9b1c19028e324691bfe7fc5db2cecb53 --json`: pass。
    - `risk_count`: 0
- no-audit job:
  - job: `job_aeea2831f0d7486dac106cd9462a94fe`
  - `GET /api/jobs/{job_id}/results`: 200。
  - normal: 3
  - short: 5
  - `auditSummaryIsNull`: true。

### 判定

- v1 release smoke checklist の Docker runtime 確認は pass。
- Docker services、health、frontend、worker、redis、DB/storage共有、ffmpeg/ffprobe、upload/job lifecycle、results API、metadata/subtitle/MP4/ZIP download、audit、sidecar risk を確認済み。
- `v1.0.0` tag はこの STATUS 更新が main に入った後に切るのが整合的。

### 未解決事項

- high_quality OpenAI smoke は未実行。`OPENAI_API_KEY` は v1 smoke script 上では `false`。
- no-audit 確認に使った `job_aeea2831f0d7486dac106cd9462a94fe` は古い sidecar 分離前の出力なので、sidecar risk は評価対象外。no-audit API semantics の確認のみに使用。

## 2026-07-04 v1 implementation status confirmation

### 確認日

- 2026-07-04

### 確認対象

- main commit: `88d0a82`
- current status branch: `codex/task-40-v1-release-smoke-execution`
- Task 40 status commit: `e0e02ae`
- base tag: `v0.20-v1-release-smoke-checklist`

### 現時点の実装状態

- v1 core implementation は release candidate 水準まで到達。
- 実装済み:
  - Next.js upload / job progress / results UI
  - FastAPI upload / job / results / metadata / subtitle / MP4 / ZIP download API
  - RQ worker / Redis / SQLite / local storage
  - ffmpeg / ffprobe wrappers
  - faster-whisper transcription
  - feature extraction
  - candidate generation
  - rule scoring
  - OpenAI Structured Outputs scoring
  - hard gate / soft selection
  - normal / short rendering
  - ASS subtitle burn-in
  - ZIP packaging
  - diagnostics summaries
  - long-video bounded candidate generation
  - overlap diversity
  - OpenAI finalist scoring
  - title fallback
  - subtitle readability
  - Japanese subtitle burn-in
  - subtitle sidecar separation
  - boundary refinement
  - overlay title policy
  - output audit
  - results metadata / audit warning display
  - v1 release smoke checklist / script
- 確認済み:
  - Docker runtime smoke: pass
  - sample upload/job lifecycle: pass
  - generated short: `1080x1920`
  - metadata / subtitle / MP4 / ZIP download: pass
  - sidecar risk: 0
  - PR #17 CI: backend / frontend pass

### 残件

- PR #17 を main に merge。
- merge 後に main を pull。
- `v1.0.0` または `v1.0.0-rc.1` tag を作成。
- high_quality OpenAI smoke は今回未実行。
- short crop / composition quality improvement は保留。
- subtitle transcription accuracy tuning は未着手。

## 2026-07-04 high_quality OpenAI smoke execution

### 目的

- `OPENAI_API_KEY` ありの Docker runtime で high_quality OpenAI Structured Outputs 経路を確認する。
- `v1.0.0` tag 前の外部 API 経路確認として実行する。
- コード変更、selection tuning、scoring tuning、rendering tuning は行わない。

### 対象

- tested commit: `1ee05a4`
- base tag: `v1.0.0-rc.1`
- branch: `codex/task-41-high-quality-openai-smoke-status`
- input video: `C:\Users\peace.YAGURUMAGIKUHM\Desktop\解説_後藤直義、森川潤）.mp4`
- input size: 76.6 MB

### 実行コマンド

```powershell
python .\scripts\e2e_real_video.py `
  --video "C:\Users\peace.YAGURUMAGIKUHM\Desktop\解説_後藤直義、森川潤）.mp4" `
  --mode high_quality `
  --use-openai-scoring true `
  --openai-candidate-limit 10 `
  --normal-count 1 `
  --short-count 2 `
  --normal-min-duration 20 `
  --normal-max-duration 120 `
  --short-min-duration 20 `
  --short-max-duration 75 `
  --selection-policy fill_requested `
  --timeout 3600
```

### 結果

- result: `REAL VIDEO E2E PASSED`
- job: `job_c1ac598dad5d439a9e48a3cc0742aa97`
- fixture transcript: disabled
- transcription engine: `faster_whisper`
- transcript: 1231 segments, 9228 chars, speech 1139.5 sec, average confidence 0.707189
- video duration: 1331.747083 sec
- selected: normal 1/1, short 2/2
- render failures: 0
- ZIP size: 32714119 bytes
- normal output:
  - `1280x720`
  - duration: 79.912 sec
- short outputs:
  - short 1: `1080x1920`, duration 47.171 sec
  - short 2: `1080x1920`, duration 62.353 sec

### OpenAI Structured Outputs 確認

- model: `gpt-5.5`
- openai candidate limit: 10
- finalist limit: 5
- candidates sent: 11
- successful structured scores: 11
- failed scores: 0
- fallback scores: 0
- schema validation failures: 0
- API calls: 11
- average latency: 7.861855 sec
- max latency: 10.247546 sec
- selected clips using AI score: 3
- selected clips using fallback: 0
- selected clips not scored: 0
- selected clip OpenAI score source:
  - normal: `finalist_on_demand`
  - short 1: `preselection_pool`
  - short 2: `preselection_pool`

### 追加確認

- `python scripts\audit_outputs.py --job-id job_c1ac598dad5d439a9e48a3cc0742aa97 --format both`: pass。
  - generated normal: 1
  - generated short: 2
  - clips requiring inspection: 1
  - normal warnings: `likely_abrupt_ending`, `below_quality_threshold`, `normal_duration_outside_recommended_range`
  - short warnings: none
- `python scripts\check_subtitle_sidecar_risk.py --job-id job_c1ac598dad5d439a9e48a3cc0742aa97 --json`: pass。
  - `risk_count`: 0
- `python scripts\v1_smoke_check.py --job-id job_c1ac598dad5d439a9e48a3cc0742aa97`: pass。
  - results API: normal 1, short 2
  - metadata download: pass
  - subtitle download: pass
  - MP4 download: pass
  - ZIP download: pass
  - local sidecar risk: 0
- `curl.exe -fsSI http://localhost:3000/results/job_c1ac598dad5d439a9e48a3cc0742aa97`: 200。

### 判定

- high_quality OpenAI API 経路は pass。
- OpenAI Structured Outputs は全 API call で schema validation 成功。
- 最終 selected clips は全て AI score を使用。
- fallback / not_scored は 0。
- これで `v1.0.0` tag 前に残っていた high_quality OpenAI smoke 未実行は解消。

### 未解決事項

- normal clip に品質警告が 1 件残るが、smoke profile で `normalMinDuration=20`, `normalMaxDuration=120` を指定した検証用条件のため、API 経路保証の blocker とは扱わない。
- short crop / composition quality improvement は引き続き保留。
- subtitle transcription accuracy tuning は未着手。

## 2026-07-04 Task 41 short composition improvement

### 目的

- v1.0.0 後の v1.1 品質改善として、ショート動画の 9:16 クロップ判定を安全寄りに改善する。
- 顔・人物検出シグナルが弱い場合は既存 fallback を維持する。
- crop strategy の診断 metadata を残し、結果確認しやすくする。

### 変更ファイル

- `backend/app/render/crop_strategy.py`
- `backend/app/render/render_short.py`
- `backend/tests/test_short_rendering.py`

### 変更内容

- `CropPlan` を追加し、short render 前に crop strategy / signal source / confidence / fallback reason / crop x,y / detection count を決めるようにした。
- 複数顔の横幅が 9:16 crop に収まらない場合は `blur_background` を優先する。
- 顔シグナルが小さすぎる場合は `center_crop` fallback にする。
- 顔が字幕安全領域に近い場合は、可能な範囲で crop center を上側に寄せる。
- `short_XX.json` に以下を追加した。
  - `crop_strategy`
  - `crop_signal_source`
  - `crop_confidence`
  - `crop_fallback_reason`
  - `crop_x`
  - `crop_y`
  - `crop_detection_count`
  - `crop_attempted_strategies`

### 検証結果

- `cd backend && ..\.venv\Scripts\python -m ruff check app\render\crop_strategy.py app\render\render_short.py tests\test_short_rendering.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_short_rendering.py`: 12 passed。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 191 passed, 1 skipped。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run build`: pass。
- `docker compose up -d --build`: pass。
- `python scripts/smoke_runtime.py --skip-video`: pass。
  - backend/frontend/redis/worker running。
  - backend/worker DB and storage path match。
  - backend/worker ffmpeg and ffprobe available。
- `python scripts/e2e_sample_video.py`: pass。
  - job: `job_befbb678ce10432f92e27ea41928f762`
  - selected: normal 0/0, short 1/1。
  - short output: `1080x1920`。
  - render failures: 0。
- `python scripts/check_subtitle_sidecar_risk.py --job-id job_befbb678ce10432f92e27ea41928f762 --json`: pass。
  - `risk_count`: 0。

### 未解決事項

- 今回は安全な crop planning と診断 metadata の追加まで。
- 人物ごと・台詞ごとの構図最適化は未実装。
- 実写 58 分動画での構図主観評価は未実施。

## 2026-07-04 Task 42 subtitle mistranscription post-processing

### 目的

- faster-whisper の根本精度変更ではなく、字幕に出る明らかな誤変換を後処理で軽減する。
- 低リスクな正規化と辞書補正を、候補生成・字幕生成の前に適用する。
- 元 transcript を失わず、補正内容を summary で追跡できるようにする。

### 変更ファイル

- `backend/app/audio/transcript_postprocess.py`
- `backend/app/jobs/runner.py`
- `backend/app/schemas.py`
- `backend/tests/test_transcript_postprocess.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_e2e_real_video_script.py`
- `frontend/lib/types.ts`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- `README.md`
- `STATUS.md`

### 変更内容

- transcription 後に transcript post-processing を追加。
- `raw_transcript_segments.json` に元 transcript を保存。
- `transcript_segments.json` は補正後 transcript として保存。
- `transcript_postprocess_summary.json` を追加。
  - enabled
  - changed segment count
  - before/after chars
  - replacement counts
  - normalization settings
- 既定のローカル補正を追加。
  - Unicode NFKC
  - whitespace 正規化
  - 連続句読点の圧縮
  - `OpenAI`, `ChatGPT`, `YouTube`, `NewsPicks`, `ReHacQ` などの保守的な辞書補正
- API settings を追加。
  - `enableTranscriptPostProcessing`
  - `transcriptNormalizeUnicode`
  - `transcriptNormalizeWhitespace`
  - `transcriptNormalizePunctuation`
  - `useDefaultTranscriptDictionary`
  - `transcriptReplacements`
- `scripts/e2e_real_video.py` に `--transcript-replacements-json` と postprocess on/off を追加。

### 検証状況

- `ruff` targeted: pass。
- `pytest tests/test_transcript_postprocess.py tests/test_e2e_real_video_script.py`: 20 passed。
- `pytest tests/test_real_pipeline.py`: 13 passed。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 198 passed, 1 skipped。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run build`: pass。
- `docker compose up -d --build`: pass。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- `python scripts/e2e_sample_video.py`: pass。
  - job: `job_cb173e6521db47b6a5f1e783d740ac64`
  - `transcript_postprocess_summary.json`: enabled, changed_segments=0。
  - selected: normal 0/0, short 1/1。
  - short output: `1080x1920`。
- `python scripts/check_subtitle_sidecar_risk.py --job-id job_cb173e6521db47b6a5f1e783d740ac64 --json`: pass。
  - `risk_count`: 0。

### 未解決事項

- OpenAI による字幕校正は未実装。
- 実動画の誤変換辞書は、実際の出力を見て追加する必要がある。
- 58分実写での short composition 主観評価は、この Task 42 PR とは分けて実施する。

## 2026-07-05 Task 43 no-face short composition fallback improvement

### 目的

- no-face / weak-signal の横長動画で、破壊的な `center_crop` を既定安全策にしない。
- 顔や主被写体の信頼できるシグナルが無い場合は、全体フレームを残す `blur_background` を優先する。
- 明示 `shortLayout=center_crop` の既存挙動は維持する。

### 変更ファイル

- `backend/app/render/crop_strategy.py`
- `backend/tests/test_short_rendering.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `shortLayout=auto` / `face_tracking_crop` で横長入力かつ no-face / weak-face / missing-dimensions の場合、`blur_background` を `center_crop` より優先。
- portrait 入力や明示 `center_crop` では既存 fallback を維持。
- `crop_signal_source=full_frame_fallback` を追加し、no-face 時に full-frame preservation を選んだことを metadata で追えるようにした。
- `strategy_order()` を `plan_short_crop()` ベースに揃え、診断と実際の fallback 順を一致させた。

### 検証状況

- `cd backend && ..\.venv\Scripts\python -m ruff check app\render\crop_strategy.py tests\test_short_rendering.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_short_rendering.py`: 17 passed。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 203 passed, 1 skipped。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run build`: pass。
- `docker compose up -d --build`: pass。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- `python scripts/e2e_sample_video.py`: pass。
  - job: `job_1b664752629542278ac1b3e614f37801`
  - short output: `1080x1920`。
- `python scripts/check_subtitle_sidecar_risk.py --job-id job_1b664752629542278ac1b3e614f37801 --json`: pass。
  - `risk_count`: 0。
- 58分実写 low_cost E2E: pass。
  - input: `C:\Users\peace.YAGURUMAGIKUHM\Desktop\【朝倉慶vs西田真澄】物価が牙をむく！？株高の代償…フジメディアHG大株主・ダルトンアクティビストが語るインフレの悲劇とは？【ReHacQ】 - ReHacQ−リハック−【公式】 (720p, h264).mp4`
  - job: `job_cb078ecb5fdd4f609fcfe4acf5dac233`
  - selected: normal 0/0, short 10/10。
  - render failures: 0。
  - shorts: all `1080x1920`。
  - `crop_strategy`: `blur_background` 10/10。
  - `crop_signal_source`: `full_frame_fallback` 10/10。
  - `crop_fallback_reason`: `no_face_detections` 10/10。
  - audit inspection count: 0。
  - sidecar risk: 0。
  - total runtime: 533.890s。
  - short render time: 121.469s。
  - visual contact sheet: `storage/outputs/job_cb078ecb5fdd4f609fcfe4acf5dac233/audit/composition_frames/contact_sheet.jpg`

### 未解決事項

- no-face では顔切れを避けられる一方、blur background の見た目は center crop より情報密度が下がる。
- 人物ごと・台詞ごとの構図最適化は未実装。

## 2026-07-05 Task 44 subject-aware short composition

### 目的

- no-face 時に lightweight な motion / edge / saliency signal を見て、信頼できる場合だけ `subject_tracking_crop` を使う。
- signal が弱い、または中心寄りで曖昧な場合は `blur_background` に逃がし、破壊的な crop を避ける。
- 既存の `face_tracking_crop` と明示 `center_crop` の挙動は維持する。

### 変更ファイル

- `backend/app/video/subject_detect.py`
- `backend/app/render/crop_strategy.py`
- `backend/app/render/render_short.py`
- `backend/tests/test_short_rendering.py`
- `README.md`
- `STATUS.md`

### 変更内容

- `SubjectDetection` と `detect_subject_for_clip()` を追加。
- clip 内の複数 frame から edge / motion energy を集計し、`center_x`、`confidence`、`stability_score` を推定。
- `CropStrategy` に `subject_tracking_crop` を追加。
- `shortLayout=auto` で no-face / weak-face の場合、信頼できる subject signal があれば `subject_tracking_crop` を試す。
- `confidence < 0.66`、`stability_score < 0.55`、または中心寄りで `confidence < 0.82` の signal は曖昧扱いにして `blur_background` を優先。
- short metadata に以下を追加。
  - `crop_sampled_frames`
  - `crop_subject_x`
  - `crop_stability_score`

### 検証状況

- `cd backend && ..\.venv\Scripts\python -m ruff check app\video\subject_detect.py app\render\crop_strategy.py app\render\render_short.py tests\test_short_rendering.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_short_rendering.py`: 22 passed。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 208 passed, 1 skipped。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run build`: pass。
- `docker compose up -d --build`: pass。
- `python scripts\smoke_runtime.py --skip-video`: pass。
- `python scripts\e2e_sample_video.py`: pass。
  - job: `job_21759784e27e490586e7ea488b82855f`
  - short output: `1080x1920`。
- `python scripts\check_subtitle_sidecar_risk.py --job-id job_21759784e27e490586e7ea488b82855f --json`: pass。
  - `risk_count`: 0。
- 58分実写 low_cost short-only E2E: pass。
  - input: `C:\Users\peace.YAGURUMAGIKUHM\Desktop\【朝倉慶vs西田真澄】物価が牙をむく！？株高の代償…フジメディアHG大株主・ダルトンアクティビストが語るインフレの悲劇とは？【ReHacQ】 - ReHacQ−リハック−【公式】 (720p, h264).mp4`
  - job: `job_9895ced289e2457fb01932c200505bbc`
  - selected: normal 0/0, short 10/10。
  - render failures: 0。
  - shorts: all `1080x1920`。
  - `crop_strategy`: `blur_background` 10/10。
  - `crop_signal_source`: `full_frame_fallback` 10/10。
  - `crop_fallback_reason`: `ambiguous_subject_signal` 10/10。
  - audit inspection count: 3。
  - sidecar risk: 0。
  - total runtime: 501.485s。
  - short render time: 111.593s。
  - visual contact sheet: `storage/outputs/job_9895ced289e2457fb01932c200505bbc/audit/composition_frames/contact_sheet.jpg`

### 未解決事項

- 58分実写では subject signal が中心寄りで曖昧だったため、`subject_tracking_crop` は採用されなかった。
- blur background により顔切れは避けられるが、ショートとしての情報密度は低め。
- 高信頼の no-face subject crop を増やすには、人物検出またはより強い foreground signal が別途必要。

## 2026-07-05 Task 45 person-aware short composition

### 目的

- no-face / weak-face 時に人物検出を追加し、信頼できる人物 box がある場合だけ `person_tracking_crop` を使う。
- 低信頼、複数人物で曖昧、または不安定な検出では `blur_background` に逃がす。
- 既存の `face_tracking_crop`、`subject_tracking_crop`、sidecar分離、字幕、選定ロジックは変更しない。

### 変更ファイル

- `backend/app/video/person_detect.py`
- `backend/app/render/crop_strategy.py`
- `backend/app/render/render_short.py`
- `backend/pyproject.toml`
- `backend/tests/test_short_rendering.py`
- `README.md`
- `STATUS.md`

### 変更内容

- OpenCV HOG ベースの optional person detector を追加。
- Docker / CI でも HOG API を使えるよう `opencv-python>=4.10.0,<5.0.0` を明示。
- clip 内の複数 frame を sampling し、人物 box の confidence / 安定性 / 複数人物の曖昧さを評価。
- crop 優先順位を以下に整理。
  - reliable face signal -> `face_tracking_crop`
  - reliable person signal -> `person_tracking_crop`
  - reliable lightweight subject signal -> `subject_tracking_crop`
  - weak / ambiguous signal -> `blur_background`
  - explicit center only -> `center_crop`
- short metadata に以下を追加。
  - `person_detection_count`
  - `person_detection_confidence`
  - `person_box`

### 検証状況

- `cd backend && ..\.venv\Scripts\python -m ruff check app\video\person_detect.py app\render\crop_strategy.py app\render\render_short.py tests\test_short_rendering.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_short_rendering.py`: 31 passed, 1 warning。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 216 passed, 1 skipped, 1 warning。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run build`: pass。
- `docker compose up -d --build`: pass。
- Docker worker OpenCV check: `cv2 4.13.0`, `HOGDescriptor=True`, `HOGDescriptor_getDefaultPeopleDetector=True`。
- Docker worker direct person detector check: no exception, `person_signal=None` on the 58分 input first 10s。
- `python scripts\smoke_runtime.py --skip-video`: pass。
- `python scripts\e2e_sample_video.py`: pass。
  - job: `job_ef6b60c148954bc39083e2b8f62568b1`
  - short output: `1080x1920`。
- `python scripts\check_subtitle_sidecar_risk.py --job-id job_ef6b60c148954bc39083e2b8f62568b1 --json`: pass。
  - `risk_count`: 0。
- 58分実写 low_cost short-only E2E: pass。
  - input: `C:\Users\peace.YAGURUMAGIKUHM\Desktop\【朝倉慶vs西田真澄】物価が牙をむく！？株高の代償…フジメディアHG大株主・ダルトンアクティビストが語るインフレの悲劇とは？【ReHacQ】 - ReHacQ−リハック−【公式】 (720p, h264).mp4`
  - job: `job_7325a1bd35eb4d53a7aa9cb7244cfc78`
  - selected: normal 0/0, short 10/10。
  - render failures: 0。
  - shorts: all `1080x1920`。
  - `crop_strategy`: `blur_background` 10/10。
  - `crop_signal_source`: `face_detection` 10/10。
  - `crop_fallback_reason`: `face_group_too_wide_for_9x16_crop` 10/10。
  - `person_detection_count`: 0/10。
  - audit inspection count: 5。
  - sidecar risk: 0。
  - total runtime: 504.360s。
  - short render time: 121.562s。
  - visual contact sheet: `storage/outputs/job_7325a1bd35eb4d53a7aa9cb7244cfc78/audit/composition_frames/contact_sheet.jpg`

### 未解決事項

- 58分実写では顔検出が広すぎる対談構図を検出し、`face_group_too_wide_for_9x16_crop` として `blur_background` に逃がした。
- `person_tracking_crop` はこの素材では採用されなかった。
- 見た目は顔切れ回避としては安全だが、情報密度改善には別の人物検出手段が必要。

## 2026-07-05 Task 46 dialogue-aware short composition

### 目的

- 横に広い顔 / 人物グループで `blur_background` に逃がす前に、transcript timing から安定した単一話者領域があるか確認する。
- 信頼できる dialogue / speaker region がある場合だけ `speaker_tracking_crop` を使う。
- 複数話者が同程度、話者領域が不安定、または9:16に安全に収まらない場合は `blur_background` を維持する。

### 変更ファイル

- `backend/app/video/speaker_detect.py`
- `backend/app/render/crop_strategy.py`
- `backend/app/render/render_short.py`
- `backend/tests/test_short_rendering.py`
- `README.md`
- `STATUS.md`

### 変更内容

- transcript segment overlap から `DialogueWindow` を生成。
- dialogue window ごとに face / person signal を見て、安定した単一 region のみ `SpeakerDetection` として集計。
- `CropStrategy` に `speaker_tracking_crop` を追加。
- crop 優先順位を以下に整理。
  - reliable single-speaker face signal -> `face_tracking_crop`
  - reliable dialogue / speaker region -> `speaker_tracking_crop`
  - reliable person signal -> `person_tracking_crop`
  - reliable subject signal -> `subject_tracking_crop`
  - wide group / ambiguous signal -> `blur_background`
  - explicit center only -> `center_crop`
- short metadata に以下を追加。
  - `speaker_window_count`
  - `speaker_region_confidence`
  - `speaker_region_box`

### 検証状況

- `cd backend && ..\.venv\Scripts\python -m ruff check app\video\speaker_detect.py app\render\crop_strategy.py app\render\render_short.py tests\test_short_rendering.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_short_rendering.py`: 37 passed, 1 warning。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 223 passed, 1 skipped, 1 warning。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run build`: pass。
- `docker compose up -d --build`: pass。backend / frontend / redis / worker 起動。
- `.\.venv\Scripts\python scripts\smoke_runtime.py --skip-video`: pass。
- `.\.venv\Scripts\python scripts\e2e_sample_video.py`: pass。
  - job: `job_fa4d41e337b34268ac963316a9918d7e`
  - short: 1/1, 1080x1920
- `.\.venv\Scripts\python scripts\check_subtitle_sidecar_risk.py --job-id job_fa4d41e337b34268ac963316a9918d7e --json`: `risk_count=0`。
- 58分実写 E2E:
  - command: `.\.venv\Scripts\python scripts\e2e_real_video.py --video <58min ReHacQ sample> --mode low_cost --normal-count 0 --short-count 10 --selection-policy fill_requested --timeout 14400`
  - job: `job_c3490513a8d2425ba1a8c00f03111651`
  - result: pass
  - total_time: 593.109s
  - transcription_time: 214.282s
  - scene_detection_time: 97.390s
  - candidate_generation_time: 58.797s
  - short_render_time: 188.688s
  - selected: normal 0/0, short 10/10
  - render_failures: 0
  - shorts: all 1080x1920
  - zip_size_bytes: 106485177
  - sidecar risk: 0
  - audit: normal 0, short 10, inspection 3
  - audit warnings: `likely_abrupt_start=2`, `likely_abrupt_ending=1`, `subtitle_too_dense=1`
- 58分 crop strategy distribution:
  - `blur_background`: 10
  - `speaker_tracking_crop`: 0
  - `center_crop`: 0
  - fallback reasons: `face_group_too_wide_for_9x16_crop=7`, `ambiguous_speaker_signal=2`, `weak_speaker_signal=1`
  - speaker windows detected: 3/10 clips
  - visual contact sheet: `storage/outputs/job_c3490513a8d2425ba1a8c00f03111651/audit/composition_frames/contact_sheet.jpg`

### 未解決事項

- 58分実写では `speaker_tracking_crop` 採用は 0/10。3本で speaker signal を評価したが、`ambiguous_speaker_signal` または `weak_speaker_signal` と判定し `blur_background` に逃がした。
- transcript timing だけでは本当の active speaker を確定できないため、曖昧な対談構図では `blur_background` を維持する。
- visual density 改善は限定的。今回の成果は、話者領域が弱い/曖昧な場合に破壊的 crop を避ける safety gate の追加。

## 2026-07-07 Task 47-75 local sample editing triage

### 目的

- Task 47-75 のローカル案件サンプル編集ログを、本体 pipeline の実装履歴から分離する。
- 詳細な試行錯誤は未コミット stash に保持し、main へは要約と安全な ignore ルールだけを入れる。

### 対象

- `.gitignore`
- `storage/fonts/.gitkeep`
- `STATUS.md`

### 整理内容

- Task 47-75 は、クライアント素材を使ったローカル編集試行として扱う。
- 本体 runtime の正式仕様変更にはまだ含めない。
- 字幕 style 調整、breath-cut 派生スクリプト、insert-image 派生スクリプト、ローカル font 使用は個別に triage してから product 化を判断する。
- font binary は commit 対象外とし、`storage/fonts/.gitkeep` だけで配置先を保持する。

### 検証結果

- `git check-ignore -v storage/fonts/SourceHanSansJP-Heavy.otf`: `.gitignore:24:storage/fonts/*` により font binary が ignore 対象。
- `git check-ignore -v storage/fonts/.gitkeep`: `.gitignore:30:!storage/fonts/.gitkeep` により `.gitkeep` 例外を確認。
- `git status --short --untracked-files=all`: `storage/fonts/.gitkeep` のみ追跡候補として表示され、font binary は表示なし。
- runtime behavior 変更なし。Docker / E2E 再実行は不要。

### 未解決事項

- `backend/app/render/subtitles_ass.py` の outline 変更は未採用。別タスクで configurable subtitle style として扱う。
- `scripts/create_breath_cut_deliverable.py` は未採用。別タスクでローカルツール化または product 化を判断する。
- `scripts/create_insert_image_deliverable.py` は未採用。別タスクでローカルツール化または product 化を判断する。

## 2026-07-07 Task 48 configurable subtitle style

### 目的

- Task 47-75 の案件サンプルで必要になった字幕 outline / font size / margin / alignment 調整を hardcode せず、Job settings から上書きできるようにする。
- 既存 default は維持し、通常 pipeline の見た目を予告なく変えない。

### 対象

- `backend/app/render/subtitles_ass.py`
- `backend/app/schemas.py`
- `backend/tests/test_subtitles_ass.py`
- `backend/tests/test_api_routes.py`
- `STATUS.md`

### 変更内容

- `SubtitleRenderSettings` に字幕 style override を追加。
  - font name
  - subtitle/title font size
  - outline
  - shadow
  - margin
  - ASS alignment
- short / normal の個別 override と、共通 `subtitle*` override をサポート。
- `JobSettings` に advanced subtitle style fields を追加し、OpenAPI に露出。
- default short subtitle style は従来互換のまま維持。
  - font: `Noto Sans CJK JP`
  - font size: `76`
  - outline: `5`
  - shadow: `2`
  - alignment: `2`
  - lower margin: `250`

### 検証結果

- `cd backend && ..\.venv\Scripts\python -m ruff check app\render\subtitles_ass.py app\schemas.py tests\test_subtitles_ass.py tests\test_api_routes.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_subtitles_ass.py tests\test_api_routes.py`: 26 passed, 1 warning。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 226 passed, 1 skipped, 1 warning。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run build`: pass。

### 未解決事項

- UI にはまだ字幕 style 設定を出していない。API / scripts / E2E settings からの指定を先に対応。
- font binary は commit 対象外。実フォントは `storage/fonts/` などローカル配置前提。

## 2026-07-07 Task 49 subtitle style UI

### 目的

- Task 48 で追加した字幕 style override を upload 設定UIから指定できるようにする。
- 未指定時は既存 default のままにし、通常の生成結果を変えない。

### 対象

- `frontend/components/SettingsPanel.tsx`
- `frontend/lib/types.ts`
- `STATUS.md`

### 変更内容

- Upload の `SettingsPanel` に `Subtitle style` 折りたたみ設定を追加。
- UIから以下の共通 override を送信可能にした。
  - `subtitleFontName`
  - `subtitleFontSize`
  - `subtitleOutline`
  - `subtitleLowerMargin`
  - `subtitleAlignment`
- 空欄の項目は `undefined` にし、JSON送信時に省略されるため backend default が使われる。
- 案件用 script、font binary、生成物は含めていない。

### 検証結果

- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run build`: pass。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 226 passed, 1 skipped, 1 warning。
- `docker compose up -d --build`: pass。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- `python scripts/e2e_sample_video.py`: pass。job `job_de83253db0ea4c8d870032ddb8d39671`、short `1/1`、`1080x1920`。
- `Invoke-WebRequest http://localhost:3000/upload`: `Subtitle style` / `Font name` / `Lower margin` / `Position` の表示を確認。

### 未解決事項

- UI経由で任意値を変えた実動画レンダリング確認は未実施。default path の smoke / sample E2E は pass。
- short / normal 個別 style override は backend API では対応済みだが、UIでは共通 override のみ露出。

## 2026-07-07 Task 49b duration input validation fix

### 目的

- Task 49 merge後のUI override確認中に、duration入力のHTML validationでジョブ作成が止まる問題を修正する。
- `normalMinDuration=20` / `normalMaxDuration=30` など、backendで有効な秒数指定をUIから送れるようにする。

### 対象

- `frontend/components/SettingsPanel.tsx`
- `backend/app/render/subtitles_ass.py`
- `backend/tests/test_subtitles_ass.py`
- `STATUS.md`

### 修正内容

- Advanced durations の4項目を `step={5}` から `step={1}` に変更。
  - `normalMinDuration`
  - `normalMaxDuration`
  - `shortMinDuration`
  - `shortMaxDuration`
- `min={1}` は維持。
- `subtitleFontSize` などの共通 override が、`shortSubtitleFontSize: null` / `normalSubtitleFontSize: null` によって無効化される問題を修正。
- `_first_value()` は `None` をスキップし、共通 override へ fallback する。
- type別nullを含むPydantic dump相当の回帰テストを追加。

### 検証結果

- `cd frontend && npm run typecheck`: pass。
- `cd frontend && npm run lint`: pass。
- `cd frontend && npm run build`: pass。
- `cd backend && ..\.venv\Scripts\python -m ruff check app\render\subtitles_ass.py tests\test_subtitles_ass.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_subtitles_ass.py`: 13 passed。
- `docker compose up -d --build`: pass。
- UI form validation確認: `normalMinDuration=20` / `normalMaxDuration=60` / `shortMinDuration=20` / `shortMaxDuration=30` で `formValid=true`。
- UI override render確認: job `job_2d23ea3b1dcd4f22878788fde8f2a58b` completed。
  - request settings: `subtitleFontSize=54`, `subtitleOutline=1`, `subtitleLowerMargin=500`, `subtitleAlignment=8`。
  - short ASS: `Style: Subtitle,Noto Sans CJK JP,54,...,1,1,2,8,86,86,500,1`。
  - normal ASS: `Style: Subtitle,Noto Sans CJK JP,54,...,1,1,1,8,51,51,500,1`。
  - short output: `1080x1920`。
  - normal output: `640x360`。
  - `python scripts/check_subtitle_sidecar_risk.py --job-id job_2d23ea3b1dcd4f22878788fde8f2a58b --json`: `risk_count=0`。
  - ZIP / normal MP4 / short MP4 download: HTTP 200。
  - extracted frame: `storage/temp/ui_override_short_frame.jpg` で字幕位置の反映を確認。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- `python scripts/e2e_sample_video.py`: pass。job `job_656992418eb745bea065d9b80c026bef`、short `1/1`、`1080x1920`。
- `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 227 passed, 1 skipped, 1 warning。

### 未解決事項

- UI override renderはTTS生成の短い検証動画で確認。実写素材での主観確認は別途。

## 2026-07-07 Task 50 breath-cut deliverable script triage

### 目的

- ローカル案件編集用に退避していた breath-cut script を確認し、main に入れるか判断する。
- 本体 pipeline と案件固有作業を混ぜず、汎用補助 script として成立する範囲だけ整理する。

### 対象

- `scripts/create_breath_cut_deliverable.py`
- `backend/tests/test_breath_cut_deliverable_script.py`
- `docs/BREATH_CUT_SCRIPT.md`
- `STATUS.md`

### 判断

- `create_breath_cut_deliverable.py` は、案件名・固定素材名・固定絶対パスを含まないため、完了済み job に対する任意の納品補助 CLI として main に入れる。
- 本体の upload / worker / scoring / rendering / results pipeline には接続しない。
- `scripts/create_insert_image_deliverable.py` と subtitle style のローカル差分は Task50 に含めない。
- font binary、client media、生成物は commit 対象外。

### 変更内容

- breath-cut script を `scripts/` に追加。
- `--dry-run` を追加し、`breath_cut_plan.json` / ASS / filter script だけを生成して ffmpeg render を省略できるようにした。
- render時のみ `--source-container-path` を必須にした。
- `--docker-service` を追加し、ffmpeg 実行対象 service を明示できるようにした。
- ffmpeg command construction を関数化し、単体テスト可能にした。
- 使用方法と scope を `docs/BREATH_CUT_SCRIPT.md` に記録。

### 検証結果

- `cd backend && ..\.venv\Scripts\python -m ruff check ..\scripts\create_breath_cut_deliverable.py tests\test_breath_cut_deliverable_script.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_breath_cut_deliverable_script.py`: 5 passed。
- `python scripts\create_breath_cut_deliverable.py --job-id job_9b53fb3d98d54dc4a2c6e3b862e073b8 --dry-run`: pass。`breath_cut_plan.json` 生成確認。
- `cd backend && ..\.venv\Scripts\python -m ruff check . ..\scripts\create_breath_cut_deliverable.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 232 passed, 1 skipped, 1 warning。

### 未解決事項

- 実動画での breath-cut render は未実施。必要時に既存完了 job に対して `--dry-run` から確認する。
- insert-image deliverable script は Task51 で別途 triage する。

## 2026-07-07 Task 51 insert-image deliverable script triage

### 目的

- ローカル案件編集用に退避していた insert-image script を確認し、main に入れるか判断する。
- 本体 pipeline と案件固有作業を混ぜず、汎用補助 script として成立する範囲だけ整理する。

### 対象

- `scripts/create_insert_image_deliverable.py`
- `backend/tests/test_insert_image_deliverable_script.py`
- `docs/INSERT_IMAGE_SCRIPT.md`
- `STATUS.md`

### 判断

- `create_insert_image_deliverable.py` は、案件名・固定素材名・固定絶対パスを含まないため、完了済み job に対する任意の納品補助 CLI として main に入れる。
- `--duration 46.673` のような案件寄り default は廃止し、未指定時は source video を ffprobe して duration を取得する。
- 本体の upload / worker / scoring / rendering / results pipeline には接続しない。
- breath-cut helper とは連携可能だが、production pipeline には組み込まない。
- font binary、client media、生成物は commit 対象外。

### 変更内容

- insert-image script を `scripts/` に追加。
- `--dry-run` を追加し、assets copy / filter script / manifest だけを生成して ffmpeg render を省略できるようにした。
- render時のみ `--source-container-path` を必須にした。
- `--docker-service` を追加し、ffmpeg / ffprobe 実行対象 service を明示できるようにした。
- `--duration` 未指定時は source video の ffprobe duration を使うようにした。
- asset name の path traversal と unsupported image extension を拒否する validation を追加。
- ffmpeg / ffprobe command construction を関数化し、単体テスト可能にした。
- 使用方法と scope を `docs/INSERT_IMAGE_SCRIPT.md` に記録。

### 検証結果

- `cd backend && ..\.venv\Scripts\python -m ruff check ..\scripts\create_insert_image_deliverable.py tests\test_insert_image_deliverable_script.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_insert_image_deliverable_script.py`: 7 passed。
- `python scripts\create_insert_image_deliverable.py --job-id job_9b53fb3d98d54dc4a2c6e3b862e073b8 --base-filter storage\outputs\job_9b53fb3d98d54dc4a2c6e3b862e073b8\breath_cut\filter_complex.txt --subtitle storage\outputs\job_9b53fb3d98d54dc4a2c6e3b862e073b8\breath_cut\short_01_breath_cut.ass --output-subdir inserts_task51_dry_run --image <local image> insert_01.jpg 0.5 1.5 test --dry-run`: pass。`insert_manifest.json` 生成確認。
- `cd backend && ..\.venv\Scripts\python -m ruff check . ..\scripts\create_insert_image_deliverable.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 239 passed, 1 skipped, 1 warning。

### 未解決事項

- 実動画での insert-image render は未実施。必要時に既存完了 job に対して `--dry-run` から確認する。
- local font files と subtitle style の残stashは未処理。

## 2026-07-08 Task 52 deliverable helper actual render validation

### 目的

- Task50 / Task51 で追加した補助 script の実render経路を、ignored sample artifacts で確認する。
- 本体 pipeline は変更せず、補助 script の ffmpeg 実行・出力MP4・ffprobe確認まで行う。

### 対象

- `scripts/create_insert_image_deliverable.py`
- `backend/tests/test_insert_image_deliverable_script.py`
- `STATUS.md`

### 事前整理

- 開始時点で `STATUS.md` と `storage/transcripts/` に別作業の未コミット差分があった。
- Task52 PR に混ぜないため、`git stash push -u -m "pre-task52-existing-transcript-work"` で退避した。

### 実render結果

- 使用job: `job_9b53fb3d98d54dc4a2c6e3b862e073b8`
- source short: `/app/storage/outputs/job_9b53fb3d98d54dc4a2c6e3b862e073b8/shorts/short_01.mp4`
  - ffprobe: `1080x1920`, duration `25.000000`
- breath-cut actual render:
  - command: `python scripts\create_breath_cut_deliverable.py --job-id job_9b53fb3d98d54dc4a2c6e3b862e073b8 --source-container-path /app/storage/outputs/job_9b53fb3d98d54dc4a2c6e3b862e073b8/shorts/short_01.mp4 --output-name short_01_breath_cut_task52.mp4`
  - output: `storage/outputs/job_9b53fb3d98d54dc4a2c6e3b862e073b8/breath_cut/short_01_breath_cut_task52.mp4`
  - ffprobe: `1080x1920`, duration `25.000000`
- insert-image sample asset:
  - generated ignored file: `storage/temp/task52_insert.png`
- insert-image actual render:
  - command: `python scripts\create_insert_image_deliverable.py --job-id job_9b53fb3d98d54dc4a2c6e3b862e073b8 --source-container-path /app/storage/outputs/job_9b53fb3d98d54dc4a2c6e3b862e073b8/breath_cut/short_01_breath_cut_task52.mp4 --base-filter storage\outputs\job_9b53fb3d98d54dc4a2c6e3b862e073b8\breath_cut\filter_complex.txt --subtitle storage\outputs\job_9b53fb3d98d54dc4a2c6e3b862e073b8\breath_cut\short_01_breath_cut.ass --output-subdir inserts_task52_render --output-name short_01_insert_task52.mp4 --image storage\temp\task52_insert.png insert_task52.png 0.5 2.0 task52`
  - output: `storage/outputs/job_9b53fb3d98d54dc4a2c6e3b862e073b8/inserts_task52_render/short_01_insert_task52.mp4`
  - ffprobe video: `1080x1920`, duration `25.000000`
  - ffprobe audio: `aac`, `16000Hz`, `1ch`
  - manifest: `insert_manifest.json` generated
  - contact sheet: `insert_contact_sheet.jpg` generated

### 修正内容

- insert-image helper の contact sheet 生成で、insert画像が1枚のとき `xstack=inputs=1` になりFFmpegが失敗した。
- 1枚の場合は `xstack` を使わず、単純に `scale=360:640` で contact sheet を作るよう修正。
- 1枚insert用の回帰テストを追加。

### 検証結果

- `cd backend && ..\.venv\Scripts\python -m ruff check ..\scripts\create_insert_image_deliverable.py tests\test_insert_image_deliverable_script.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest tests\test_insert_image_deliverable_script.py`: 8 passed。
- `cd backend && ..\.venv\Scripts\python -m ruff check . ..\scripts\create_insert_image_deliverable.py`: pass。
- `cd backend && ..\.venv\Scripts\python -m pytest`: 240 passed, 1 skipped, 1 warning。

### 未解決事項

- 退避した `pre-task52-existing-transcript-work` stash は未復元。Task52に混ぜないため保持。
- 生成MP4、contact sheet、sample image は ignored storage 配下にあり commit 対象外。

## 2026-07-09 Task 53 transcript work triage

### 目的

- 退避していた transcript 関連のローカル作業を確認し、main に入れるものと local-only に残すものを分ける。
- 実案件の文字起こし成果物や一時依存展開を、本体 pipeline / helper script PR に混ぜない。

### 対象

- `.gitignore`
- `storage/transcripts/.gitkeep`
- `STATUS.md`

### 判断

- `storage/transcripts/*.md` / `*.json` は実案件由来の生成物のため main 非投入。
- `.codex_tmp/` は一時依存展開のため main 非投入。
- `scripts/make_plotwith_*.ps1` / `scripts/make_plotwith_*.py` は案件別編集scriptのため main 非投入。汎用化する場合は別Taskで個別triageする。
- `ID146_*/` は案件素材の展開フォルダのため main 非投入。
- `STATUS.md` に戻っていた個別案件の詳細ログは main 非投入。ここでは要約のみ記録する。

### 変更内容

- `.gitignore` に local-only 対象を追加。
  - `storage/transcripts/*`
  - `!storage/transcripts/.gitkeep`
  - `.codex_tmp/`
  - `scripts/make_plotwith_*.ps1`
  - `scripts/make_plotwith_*.py`
  - `ID146_*/`
- `storage/transcripts/.gitkeep` を追加し、ローカル transcript 保存先だけを維持。
- stash の transcript / Plotwith / `.codex_tmp` ファイルを apply し、ignored 扱いになることを確認。

### 検証結果

- `git stash apply stash@{0}` 後、transcript成果物、Plotwith scripts、案件素材フォルダ、`.codex_tmp/` が ignored 表示になることを確認。
- `STATUS.md` の案件詳細ログは `git restore -- STATUS.md` で除外し、Task53要約だけを追記。

### 未解決事項

- `stash@{0}: pre-pr32-merge-local-work-20260709` と `stash@{1}: pre-task52-existing-transcript-work` はバックアップとして未削除。
- Plotwith系scriptを汎用補助scriptにするかは未判断。必要なら別Task。

## 2026-07-10 Task 54 normal clip quality warning improvements

### 目的

- normal clip の audit warning を隠さず、原因確認に使える詳細へ改善する。
- 対象 warning:
  - `likely_abrupt_ending`
  - `below_quality_threshold`
  - `normal_duration_outside_recommended_range`

### 対象

- `backend/app/candidates/merge_boundaries.py`
- `scripts/audit_outputs.py`
- `backend/tests/test_audit_outputs_script.py`
- `backend/tests/test_candidate_generation.py`
- `STATUS.md`

### 変更内容

- `candidate_generation_summary.json` に type 別 `configured_duration_ranges` を追加。
  - `min_duration`
  - `max_duration`
  - `step_seconds`
  - `speech_boundary_tolerance`
- `audit_outputs.py` が `candidate_generation_summary.json` の duration policy を読むよう変更。
  - 新規ジョブでは、設定された normal/short duration range を優先。
  - 既存ジョブで設定情報がない場合は従来の推奨値を使用。
- 各 clip report に `duration_policy` と `warning_details` を追加。
  - abrupt warning: transcript segment 境界、original/refined boundary、boundary refinement 理由を記録。
  - below quality warning: score、`selection_reason`、`quality_warning`、backfill context を記録。
  - duration warning: 実duration、min/max、policy source を記録。
- Markdown audit report に `Warning Details` セクションを追加。

### 代表ジョブ確認

- 代表ジョブ: `job_e9a049ee5e3446c0b92943429fa8918a`
- before:
  - normal:
    - `likely_abrupt_start`: 1
    - `likely_abrupt_ending`: 1
    - `below_quality_threshold`: 1
    - `backfilled_clip`: 1
  - short:
    - `likely_abrupt_start`: 3
    - `subtitle_too_dense`: 2
- after:
  - warning count は同一。
  - normal の `likely_abrupt_ending` に boundary refinement / transcript end 詳細が出ることを確認。
  - normal の `below_quality_threshold` / `backfilled_clip` に `selection_reason=backfill_below_quality_threshold` と backfill context が出ることを確認。
- 生成確認:
  - `.codex_tmp/task54_after_job_e9a/output_audit_report.json`
  - `.codex_tmp/task54_after_job_e9a/output_audit_report.md`

### 新規 sample E2E 確認

- rebuild 後 job: `job_760dd150c4084868b12e9a262e1bdb8a`
- `scripts/e2e_sample_video.py`: pass。
- `scripts/check_subtitle_sidecar_risk.py --job-id job_760dd150c4084868b12e9a262e1bdb8a --json`: `risk_count=0`。
- `scripts/audit_outputs.py --job-id job_760dd150c4084868b12e9a262e1bdb8a`: pass。
- 新規 `candidate_generation_summary.json` で以下を確認。
  - normal: `90.0-600.0`
  - short: `20.0-25.0`

### 検証結果

- `cd backend && ruff check .`: pass。
- `cd backend && pytest`: 242 passed, 1 skipped。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- `python scripts/e2e_sample_video.py`: pass。
- `docker compose up -d --build`: pass。
- rebuild 後 `python scripts/smoke_runtime.py --skip-video`: pass。
- rebuild 後 `python scripts/e2e_sample_video.py`: pass。

### 未解決事項

- 既存代表ジョブの warning 件数自体は減っていない。今回の主改善は、必要な warning を説明可能にすること。
- 実写 normal clip の境界そのものをさらに自然にする場合は、別Taskで boundary/selection 改善を行う。

## 2026-07-10 Task 55 normal clip warning reduction

### 目的

- Task54 の `warning_details` を使い、消せる normal clip warning は境界補正で減らす。
- 消せない warning は隠さず、採用理由をより明確にする。
- 対象 warning:
  - `likely_abrupt_ending`
  - `below_quality_threshold`
  - `normal_duration_outside_recommended_range`

### 対象

- `backend/app/candidates/boundary_refinement.py`
- `scripts/audit_outputs.py`
- `backend/tests/test_boundary_refinement.py`
- `backend/tests/test_audit_outputs_script.py`
- `STATUS.md`

### 変更内容

- boundary refinement の最終段に、補正後の end が新たに重なった transcript segment の途中で止まっていないかを確認する処理を追加。
  - 条件を満たす場合は transcript segment end まで延長。
  - 追加理由: `end_to_final_transcript_segment_end`
  - `maxBoundaryExpansionSeconds` / duration constraints は維持。
- `audit_outputs.py` の `below_quality_threshold` detail に selection summary を追加。
  - requested count
  - selected count
  - hard gate passed count
  - selected above threshold count
  - selected below threshold backfill count
  - unfilled requested count
- warning は非表示化していない。

### 代表ジョブ確認

- 代表ジョブ: `job_e9a049ee5e3446c0b92943429fa8918a`
- before:
  - normal:
    - `likely_abrupt_start`: 1
    - `likely_abrupt_ending`: 1
    - `below_quality_threshold`: 1
    - `backfilled_clip`: 1
  - short:
    - `likely_abrupt_start`: 3
    - `subtitle_too_dense`: 2
- after existing artifact audit:
  - warning count は同一。
  - 理由: 既存jobの `selected_clips.json` / rendered metadata は再生成されないため。
- 再補正予測:
  - 対象 clip: `cand_normal_1200920_1548060_ca4dab94c0`
  - old end: `1550.248`
  - new end: `1550.9`
  - new reason: `incomplete_ending_expanded_end, end_to_scene_boundary, trailing_padding, end_to_final_transcript_segment_end`
  - `last_segment_end` まで届くため、この類型の `likely_abrupt_ending` は新規生成で減る見込み。
- `below_quality_threshold` detail 確認:
  - 対象 clip: `cand_normal_1823200_2181780_6a480db9c7`
  - `requested_count=5`
  - `selected_count=5`
  - `hard_gate_passed_count=600`
  - `selected_below_threshold_backfill_count=1`
  - `unfilled_requested_count=0`
  - 残る warning は、fill_requested の本数充足 backfill として説明可能。

### 新規 sample E2E 確認

- rebuild 後 job: `job_a747767391054272bad9ce146f41a40e`
- `scripts/e2e_sample_video.py`: pass。
- `scripts/check_subtitle_sidecar_risk.py --job-id job_a747767391054272bad9ce146f41a40e --json`: `risk_count=0`。

### 検証結果

- `pytest backend/tests/test_boundary_refinement.py backend/tests/test_audit_outputs_script.py`: 27 passed。
- `cd backend && ruff check .`: pass。
- `ruff check scripts/audit_outputs.py`: pass。
- `cd backend && pytest`: 243 passed, 1 skipped。
- `docker compose up -d --build`: pass。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- `python scripts/e2e_sample_video.py`: pass。
- `python scripts/check_subtitle_sidecar_risk.py --job-id job_a747767391054272bad9ce146f41a40e --json`: `risk_count=0`。

### 未解決事項

- 既存代表ジョブの warning count は、artifact 再生成なしでは変わらない。
- `below_quality_threshold` は品質警告として残す。今回の変更は採用理由の明確化。
- `normal_duration_outside_recommended_range` は代表ジョブで発生なし。Task54 の duration policy 表示を維持。

## 2026-07-10 Task 56 representative normal warning regeneration check

### 目的

- Task55 後の main で代表素材を新規生成し、`likely_abrupt_ending` 改善が実artifactの audit に反映されるか確認する。
- 検証/status task のため runtime code は変更しない。

### 対象

- `STATUS.md`
- 代表素材:
  - `C:\Users\peace.YAGURUMAGIKUHM\Desktop\【朝倉慶vs西田真澄】物価が牙をむく！？株高の代償…フジメディアHG大株主・ダルトンアクティビストが語るインフレの悲劇とは？【ReHacQ】 - ReHacQ−リハック−【公式】 (720p, h264).mp4`

### 実行条件

- tested main: `0562f04 Improve normal clip warning reduction (#35)`
- command:
  - `python scripts\e2e_real_video.py --video <representative> --mode low_cost --normal-count 5 --short-count 10 --selection-policy fill_requested --timeout 14400`
- fixture transcript: disabled。
- OpenAI scoring: not used。

### baseline

- baseline job: `job_e9a049ee5e3446c0b92943429fa8918a`
- baseline audit:
  - normal:
    - `likely_abrupt_start`: 1
    - `likely_abrupt_ending`: 1
    - `below_quality_threshold`: 1
    - `backfilled_clip`: 1
  - short:
    - `likely_abrupt_start`: 3
    - `subtitle_too_dense`: 2

### new job result

- new job: `job_43288ae94650426aad679465b6515fc3`
- status: completed。
- video duration: `3495.8924`
- transcript:
  - segments: `2122`
  - text length: `22554`
  - engine: `faster_whisper`
  - fixture: `False`
- selection:
  - normal: `5/5`
  - short: `10/10`
  - hard gate passed: `1400`
  - render failures: `0`
  - backfill: `2`
  - unfilled: `{'normal': 0, 'short': 0}`
- outputs:
  - normal MP4: 5本、すべて `1280x720`
  - short MP4: 10本、すべて `1080x1920`
  - ZIP size: `370561422` bytes
- runtime:
  - transcription: `223.313s`
  - scene detection: `107.921s`
  - candidate generation: `54.907s`
  - normal render: `67.078s`
  - short render: `199.765s`
  - zip packaging: `20.297s`
  - total: `697.625s`

### audit result

- audit output:
  - `.codex_tmp\task56_job_43288ae_audit\output_audit_report.json`
  - `.codex_tmp\task56_job_43288ae_audit\output_audit_report.md`
- audit summary:
  - normal: 5
  - short: 10
  - inspection: 5
- warning counts:
  - normal:
    - `subtitle_too_dense`: 1
    - `below_quality_threshold`: 2
    - `backfilled_clip`: 2
  - short:
    - `likely_abrupt_start`: 1
    - `subtitle_too_dense`: 1
- `likely_abrupt_ending`:
  - before: `1`
  - after: `0`
- `end_to_final_transcript_segment_end`:
  - count: `0`
  - 解釈: 今回の新規生成では該当reasonは発火しなかったが、normal `likely_abrupt_ending` は 0 になった。
- `below_quality_threshold` detail:
  - count: `2`
  - `selection_summary` present: yes
  - `requested_count=5`
  - `selected_count=5`
  - `hard_gate_passed_count=600`
  - `selected_below_threshold_backfill_count=2`
  - `unfilled_requested_count=0`

### sidecar risk

- command:
  - `python scripts\check_subtitle_sidecar_risk.py --job-id job_43288ae94650426aad679465b6515fc3 --json`
- result:
  - `risk_count=0`

### 判断

- pass。
- Task55 後の新規生成では、代表素材の normal `likely_abrupt_ending` が `1 -> 0` になった。
- low score / backfill warning は残るが、Task55 の selection context により採用理由は確認可能。

### 未解決事項

- `end_to_final_transcript_segment_end` の実発火は今回の代表再生成では確認されていない。
- `subtitle_too_dense` と short `likely_abrupt_start` は Task56 の対象外。必要なら別Task。

## 2026-07-10 Task 58 subtitle font selector

### 目的

- Upload UIの字幕font自由入力を、workerで利用確認済みの日本語font選択へ変更する。
- 存在しないfont名や日本語glyphを持たないfontを誤指定する経路をなくす。

### 対象

- `frontend/components/SettingsPanel.tsx`
- `README.md`
- `STATUS.md`

### 変更内容

- `Font name` text inputをdropdownへ変更。
- workerの`fc-list`で確認した次のfontだけを選択肢にした。
  - 標準ゴシック: `Noto Sans CJK JP`
  - 明朝: `Noto Serif CJK JP`
  - 等幅ゴシック: `Noto Sans Mono CJK JP`
- 未指定時は既存defaultの`Noto Sans CJK JP`を維持。
- 字幕style欄のlabelを日本語化。

### 誤変換の切り分け

- fontは文字の形を変えるだけで、faster-whisperの認識結果は修正しない。
- 現在の標準文字起こしは`faster-whisper base`で、一般的な誤変換の主原因候補。
- Unicode・空白・句読点正規化、既定辞書、custom replacementsは実装済みだが、custom replacementsはUI未露出。
- OpenAI字幕校正またはtranscription model選択は別Taskで扱う。

### 検証結果

- worker font確認:
  - `fc-match 'Noto Sans CJK JP'`: exact match。
  - `fc-match 'Noto Serif CJK JP'`: exact match。
  - `fc-match 'Noto Sans Mono CJK JP'`: exact match。
- frontend:
  - `npm run lint`: pass。
  - `npm run typecheck`: pass。
  - `npm run build`: pass。
- backend:
  - `cd backend && ..\.venv\Scripts\python -m ruff check .`: pass。
  - `cd backend && ..\.venv\Scripts\python -m pytest`: 243 passed, 1 skipped, 1 warning。
- browser UI:
  - `/upload`の`字幕スタイル`を展開し、3font option表示を確認。
  - `Noto Serif CJK JP`と`Noto Sans Mono CJK JP`の選択値更新を確認。
- actual render:
  - job: `job_350588cebec648c9b8f9febfb3637679`。
  - selected font: `Noto Serif CJK JP`。
  - status: completed。
  - ASS Subtitle style: `FontName=Noto Serif CJK JP`。
  - short MP4: `1080x1920`。
- runtime:
  - `python scripts\smoke_runtime.py --skip-video`: pass。

### 未解決事項

- 字幕本文の誤変換改善はTask58の対象外。
## 2026-07-10 Task 59 transcription accuracy benchmark

### 目的

- 字幕誤変換の原因を、後処理を混ぜず faster-whisper の model/language 単位で比較できるようにする。
- 既定の `base + auto` は維持する。

### 変更

- `JobSettings` に `whisperModelSize` (`base|small|medium|large-v3`) と `transcriptionLanguage` (`auto|ja`) を追加。
- worker が設定値から `FasterWhisperTranscriptionEngine` を生成するよう変更。
- `transcript_summary.json` に `transcription_model` / `transcription_language` を追加。
- `scripts/e2e_real_video.py` に model/language オプションを追加。
- `app.audio.benchmark_transcription` を追加。raw transcriptのみで CER、固有語、timestamp、wall/CPU、peak RAMを比較し、JSON/Markdownを出力する。
- benchmark profileは別processで実行し、モデルごとのpeak RAMを分離する。

### 検証

- `python -m ruff check .`: pass。
- backend pytest: `249 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker backend/worker rebuild: pass。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- `python scripts/e2e_sample_video.py`: pass (`job_5b98bdc1b46f4f6cb2e88daae19f2909`, short `1080x1920`)。
- worker内 `python -m app.audio.benchmark_transcription --help`: pass。
- OpenAPI default: `whisperModelSize=base`, `transcriptionLanguage=auto`。
- CIではfaster-whisper modelをダウンロードせず、設定伝播・比較計算・report生成をmock/fixtureで検証。
- 正解原稿付き日本語TTS `119.628625s` で5構成を同一Docker CPU/int8環境で比較。
- cached結果: `base:auto CER=0.2345 / 6.023s / 415.7MB`, `base:ja CER=0.2345 / 5.536s / 416.2MB`, `small:ja CER=0.1623 / 14.492s / 911.0MB`, `medium:ja CER=0.1463 / 35.213s / 2495.0MB`, `large-v3:ja CER=0.2846 / 62.187s / 4571.4MB`。
- `small:ja` 実話者短尺E2E: pass (`job_145e70221060442cbbf209983559464a`)。
- `small:ja` 58分E2E: pass (`job_426ce190bb02459cb3dec1829e662f98`, transcription `445.313s`, total `652.406s`, normal `1/1`, short `2/2`, render failure `0`, sidecar risk `0`)。
- 匿名集計: `docs/TRANSCRIPTION_BENCHMARK_2026-07-10.md`。

### 未解決事項

- production defaultは互換性と非日本語入力を考慮し `base + auto` を維持。
- `small + ja` を日本語高精度optionとして推奨。人間音声CERの正解原稿がないため、TTS結果だけではdefault変更しない。
- OpenAI字幕校正はTask60候補。本Taskには含めない。

## 2026-07-11 Task 60 OpenAI subtitle correction

### 目的

- deterministic後処理済み字幕をOpenAI Structured Outputsで任意校正する。
- segment数・順序・timestampを変えず、API失敗時は部分適用せず全文をdeterministic字幕へfallbackする。

### 変更

- `JobSettings` / Upload UIへ以下を追加。
  - `subtitleCorrectionMode`: `off|openai`、default `off`。
  - `subtitleCorrectionModel`: default `gpt-5.5`。
  - `subtitleCorrectionMinConfidence`: default `0.9`。
  - `subtitleCorrectionBatchSize`: default `40`。
  - `subtitleCorrectionContextSegments`: default `2`。
  - `subtitleCorrectionFallbackEnabled`: default `true`。
- 校正APIへ送る対象を字幕text・ASR confidence・前後text context・辞書語だけに限定。動画・音声・pathは送らない。
- strict JSON schemaでindex、原文、校正文、変更有無、理由、confidenceを検証。
- transient error retry、schema validation error、missing key、fallback disabledの明確なerror codeを追加。
- 数値token変更を`numeric_expression`以外の理由で適用しないsafety gateを追加。
- raw / deterministic / OpenAI校正後 / final transcriptを分離保存。
- `transcript_correction_summary.json`と`transcript_correction_diff.md`を追加し、ZIPへ格納。
- `scripts/e2e_real_video.py`へ校正設定・artifact・timestamp検証を追加。
- `scripts/e2e_summary.py`へ校正summary表示を追加。

### 変更ファイル

- `backend/app/audio/openai_transcript_correction.py`
- `backend/app/audio/transcript_correction_schema.py`
- `backend/app/jobs/runner.py`
- `backend/app/schemas.py`
- `frontend/components/SettingsPanel.tsx`
- `frontend/lib/types.ts`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- backend tests
- `README.md`
- `STATUS.md`

### 自動検証

- backend `ruff`: pass。
- backend pytest: `264 passed, 1 skipped`。OpenAI校正test単体: `12 passed`。
- frontend lint / typecheck / build: pass。
- `docker compose up -d --build`: pass。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- default校正OFF synthetic E2E: pass (`job_65c624c6c02241f084cc9dd491ac7056`)。
- 校正schema、timestamp維持、低confidence拒否、数値変更safety gate、retry、missing key、全体fallback、fallback無効時error、artifact、ZIP layoutをtest済み。

### 短尺実API E2E

- input: Task59の実話者 `123.706917s` local sample。mediaはcommitしない。
- job: `job_d67a4d38c98144e0988bcec183fe74fb`。
- transcription: `small + ja`、48 segments。
- OpenAI correction: `gpt-5.5`、batch `40`、confidence `0.9`。
- result: corrected `9`、unchanged `39`、low-confidence reject `4`、safety reject `1`、fallback `0`、schema failure `0`、API calls `2`。
- short: `1/1`、`1080x1920`、render failure `0`。
- segment数・timestamp・final transcript一致: pass。
- ZIP correction artifacts: pass。
- sidecar risk: `0`。

### 58分実API E2E

- input duration: `3495.8924s` local real video。mediaはcommitしない。
- job: `job_0caea4d85baf4e9cbca9a84adaf0be80`。
- transcription: `small + ja`、1695 segments。
- OpenAI correction: `gpt-5.5`、batch `100`、confidence `0.9`。
- correction result:
  - corrected: `273`。
  - unchanged: `1422`。
  - low-confidence reject: `117`。
  - safety reject: `5`。
  - fallback: `0`。
  - schema failure: `0`。
  - API calls: `17`。
  - correction time: `1582.563s`。
- output:
  - normal: `1/1`、`1280x720`。
  - short: `2/2`、すべて`1080x1920`。
  - render failure: `0`。
  - ZIP: `73,201,537` bytes。
  - total runtime: `2195.156s`。
- segment数・timestamp・final transcript一致: pass。
- ZIP correction artifacts: pass。
- sidecar risk: `0`。
- 273変更の最大文字数差: `6`。極端な長文化なし。

### 未解決事項

- OpenAI correctionは長尺で処理時間を支配する。58分素材では校正だけで約26.4分。default `off`を維持する。
- 校正品質は素材依存。raw / deterministic / corrected / diffを保持し、目視監査可能にする。
- 長尺校正中もheartbeatはbatchごとに更新されるが、job表示は`transcribing 30%`のまま。校正専用progress表示は未実装。

## 2026-07-11 Task 61 subtitle correction progress reporting

### 目的

- OpenAI字幕校正を`transcribing`から分離し、batch進捗・retry・fallbackをジョブAPIと画面に表示する。

### 変更内容

- 校正ON時だけjob statusを`correcting_subtitles`へ遷移。校正OFF時のstatus列は変更しない。
- `subtitle_correction_progress.json`へbatch完了数、総数、stage進捗、retry回数、fallback、完了状態を保存。
- job details APIへ字幕本文・API keyを含まない安全な進捗情報だけを追加。
- Job Progressへ字幕校正専用のbatch表示とprogress barを追加。
- E2E timingをtranscriptionとsubtitle correctionに分離。
- retry時もheartbeatを更新し、停止と誤認されないようにした。

### 変更ファイル

- `backend/app/audio/openai_transcript_correction.py`
- `backend/app/jobs/runner.py`
- `backend/app/jobs/status.py`
- `backend/app/api/jobs.py`
- `backend/app/schemas.py`
- `frontend/components/JobProgress.tsx`
- `frontend/components/ProgressTimeline.tsx`
- `frontend/components/StatusBadge.tsx`
- `frontend/lib/types.ts`
- `scripts/e2e_real_video.py`
- `scripts/e2e_summary.py`
- backend tests
- `README.md`
- `STATUS.md`

### 検証結果

- backend ruff: pass。
- backend pytest: `266 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- changed scripts ruff: pass。
- `docker compose up -d --build`: pass。
- `python scripts/smoke_runtime.py --skip-video`: pass。
- 校正OFF sample E2E: pass (`job_d862e4b22e0241dea53edacd4de1a3a6`)。
- 校正ON real-video E2E: pass (`job_fd2798d3150b4d49bffa5d0b70ee7d4a`)。
  - status: `transcribing 30%` -> `correcting_subtitles 31%` -> 後続工程 -> `completed 100%`。
  - batch表示: `0/2`、retry `0 -> 3`を確認。
  - OpenAI API: `429 insufficient_quota`。4 calls後にfallbackし、short `1/1`、`1080x1920`、ZIP生成まで完走。
  - progress artifact: `stageProgress=100`、`correctionRetryCount=3`、`fallbackUsed=true`、`finished=true`。
- success batchの単調増加、retry、API details、ZIP artifactは自動testで確認。
- sidecar risk: `0`。

### 未解決事項

- 現在のOpenAI quota不足により、今回のruntimeでは成功batchの`1/2 -> 2/2`表示を再確認できなかった。Task60の実API成功経路とTask61の自動testはpass済み。

## 2026-07-12 Task 62 local transcript suspicion filter

### 目的

- OpenAI字幕校正前に疑わしいsegmentをローカル抽出し、API送信量と正常字幕の不要な書き換えを減らす。

### 変更内容

- `subtitleCorrectionScope=all|suspicious`を追加。既定は互換維持の`all`。
- `subtitleCorrectionSuspicionThreshold`を追加。既定`0.40`。
- confidence、表記揺れ、固有語候補、反復、文字種、数字、リスト、長尺内の反復漢字複合語を組み合わせてscore/reasonを保存。
- target以外は変更禁止。contextはread-onlyでbatchごと最大4件。
- target 0件はAPI call 0件。
- filter失敗時は全件APIへ切り替えずdeterministic transcriptへfallback。
- actual input/output/cached token usageを校正summaryへ追加。
- job API/UIへ対象segment進捗を追加。
- suspicion segments/summary/targetsの3 artifactをZIPへ追加。

### 検証

- backend ruff: pass。
- backend pytest: `282 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker runtime smoke: pass。
- correction OFF sample E2E: pass (`job_47d61624572043b8aba6cfb7491d78fd`)。
- TTS: target `8/19`、全件採用修正recall `7/7`、総token `3006 -> 2401`。
- 124秒実話者: calls `2 -> 1`、総token `14124 -> 7729`、校正時間 `157.3s -> 61.0s`。
- 58分full E2E: pass (`job_31b475f0328f4a6fa0239316100b34a0`)。
  - target `977/1695`、calls `10/17`、校正時間 `706.5s/1582.6s`。
  - normal `1/1`、short `2/2`、render failure `0`、sidecar risk `0`。
- 長尺recall改善後のoffline評価: target `1287/1695`、baseline採用修正coverage `250/273 = 91.6%`、想定calls `13/17`。
- 詳細: `docs/TRANSCRIPT_SUSPICION_FILTER_2026-07-12.md`。

### 未解決事項

- 最終長尺filterの実API replayは`7/13`成功後、`429 insufficient_quota`で停止。最終signalによる13 batch完走は未確認。
- 実際のinput token削減率は素材依存。短尺では固定prompt/schema比率が大きく、40%削減を保証しない。

## 2026-07-16 Task 62 final 58-minute API replay retry

### 目的

- PR #42 headで最終13 batch構成を実API再検証し、品質benchmarkとAPI失敗時の耐障害性を確認する。

### 実行条件

- tested commit: `c40e13b8a81f69bcca7fd5126e46845581eb2346`。
- job: `job_3ec9083055224a9fbd1c8a4b8f904d5b`。
- input SHA-256: `25DF7F71CAC8DBBDDC731D2C41A55F31A852E7981CC42DB5E2F9F29816D61890`。
- transcription: `small + ja`。
- correction model: `gpt-5.5`。
- scope: `suspicious`、threshold: `0.40`、batch size: `100`、context segments: `2`。
- requested outputs: normal `1`、short `2`。

### 検証結果

- suspicion filter: target `1287/1695`、想定batch `13`。
- OpenAI API: successful batch `0/13`、failed batch `1`、calls `4`、retry `3`、schema failure `0`。
- API error: `429 insufficient_quota`。actual token usageはinput/outputともに`0`。
- fallback: `true`。deterministic transcriptへ戻り、jobは`completed`まで完走。
- segment count: raw/deterministic/correctedすべて`1695`。
- array order/start/end timestamp mismatch: `0`。fallback後のdeterministic/corrected text差分: `0`。
- normal: `1/1`、`1280x720`、`348.982s`。
- short: `2/2`、両方`1080x1920`、`51.188s` / `61.194s`。
- render failure: `0`、sidecar risk: `0`、ZIP: `73,695,519 bytes`。
- runtime: total `674.328s`、transcription `439.047s`、correction/fallback `20.895s`。

### 結論

- 耐障害性実地検証: pass。quota不足でも全件API送信へ切り替えず、出力生成まで完走した。
- 品質benchmark: fail。`13/13`かつfallback `0`を満たさず、all-modeとのactual token比較は未実施。
- PR #42はDraftを維持する。quota確保後に同一条件で再実行する。

## 2026-07-16 Task 62 excluded-change classification

### 目的

- all-mode採用変更のうち最終suspicion filterが対象外にした23件を、APIを使わず分類する。

### 検証方法

- baseline all-mode job: `job_0caea4d85baf4e9cbca9a84adaf0be80`。
- filter job: `job_3ec9083055224a9fbd1c8a4b8f904d5b`。
- deterministic/OpenAI corrected transcriptの差分273件とtarget index 1287件を集合比較し、対象外23件を抽出。
- 元動画の該当区間を前後2秒付きで切り出し、ローカル`medium+ja`と`large-v3+ja`で再文字起こし。OpenAI APIは未使用。

### 分類結果

- 有益な修正の見逃し: `19`。
- 不要な表記変更: `1`（index 110）。
- 有害な誤修正: `1`（index 1256）。
- 判断不能: `2`（index 64、164）。
- 対象外変更の有益候補率: `19/23 = 82.6%`。
- 詳細: `docs/TRANSCRIPT_SUSPICION_MISSED_CHANGES_2026-07-16.md`。

### 判断

- filter調整は必要。現状のままReady化しない。
- global thresholdは下げず、異常語形、domain glossary、近接segment間の表記揺れを狙ったsignalを追加する。
- grammarだけを根拠にAPI対象へ入れない。index 110/1256で過修正が確認された。
- index 64/164は人手聴取が必要。

## 2026-07-16 Task 62 P2 targeted rescue signals

### 目的

- global threshold `0.40`を維持し、強い限定signalだけで有益な見逃しをOpenAI対象へ復帰させる。

### 変更内容

- `suspicion_score >= threshold OR rescue_signal`の選定を追加。
- rescue理由: `known_asr_malformed_expression`、`glossary_phonetic_match`、`nearby_spelling_inconsistency`。
- nearby表記揺れは既知aliasまたは設定glossaryに紐づく場合だけ対象化。
- segment artifactへ`selected`、`selection_source`、`rescue_reasons`を追加。
- summaryへscore/rescue選定数とrescue理由別件数を追加。
- API設定`transcriptCorrectionGlossary`を追加。既定は空配列で、UIには未露出。
- 固定23件fixtureとrescue回帰testを追加。

### Offline検証

- 固定23件: 有益な見逃し`17/19`を救済。
- 不要変更`0/1`、有害修正`0/1`、判断不能`0/2`を対象外維持。
- 全1695 segments: target `1287 -> 1304`、対象率`75.929% -> 76.932%`。
- expected calls（batch 100）: `13 -> 14`、all-modeは`17`。
- baseline採用変更coverage: `250/273 = 91.6%` -> `267/273 = 97.8%`。
- target+context文字数proxy: `14,407 -> 14,597`。all-mode `17,726`比で約`17.7%`削減を維持。
- rescue selected: `17`。理由件数はmalformed `11`、glossary `6`、nearby inconsistency `1`（重複あり）。
- 詳細: `docs/TRANSCRIPT_SUSPICION_RESCUE_EVALUATION_2026-07-16.md`。

### 現在判定

- P2 offline acceptance: pass。
- global threshold `0.40`、scope既定`all`、correction既定`off`は維持。
- backend: `ruff check .` pass、`pytest`は`287 passed, 1 skipped`。
- frontend: lint / typecheck / build pass。
- Docker rebuild / runtime smoke: pass。backend / frontend / worker / redis起動、共有DB/storage、FFmpeg / ffprobeを確認。
- correction OFF sample E2E: pass。job `job_139866cabc1e4603a407546764a616d8`、short `1/1`、`1080x1920`、render failure `0`、API call `0`、sidecar risk `0`。
- PR #42はDraft維持。rescue追加後はexpected callが`14`のため、quota確保後の実API `14/14`、fallback `0`再検証が残る。

## 2026-07-17 Task 62 P2 OpenAI API connectivity probe

### 目的

- 58分real API replayの前に、P2最終構成と既存keyで1 batch疎通を確認する。

### 実行条件

- tested commit: `aa67fd43e136b276925983c8a32065c34a2e3d01`。
- input SHA-256: `25DF7F71CAC8DBBDDC731D2C41A55F31A852E7981CC42DB5E2F9F29816D61890`。
- transcript: 既存58分jobの`small + ja` deterministic transcript、`1695` segments。
- correction model: `gpt-5.5`。
- scope: `suspicious`、threshold: `0.40`、context segments: `2`。
- P2 rescue対象index `157`を1件だけ送信。retryは`0`に固定。

### 結果

- OpenAI API call: `1`。
- result: `429 insufficient_quota`。
- successful batch: `0/1`、schema failure: `0`、actual token usage: `0`。
- 58分`14/14` replayは未開始。quota未復旧状態で追加callを行わないため停止。

### 判定

- API疎通: fail。key欠落やnetwork failureではなく、API billing/quota不足。
- PR #42はDraft維持。
- quota復旧後、同じ1 batch probeを再実行し、成功時のみ58分`14/14`へ進む。

## 2026-07-17 Task 62 P2 final real-API validation

### 目的

- quota復旧後、P2最終構成で58分real API replayを完走し、all-modeとの実token差を確定する。

### 実行条件

- tested code commit: `aa67fd43e136b276925983c8a32065c34a2e3d01`。
- input SHA-256: `25DF7F71CAC8DBBDDC731D2C41A55F31A852E7981CC42DB5E2F9F29816D61890`。
- transcription: `small + ja`。
- correction: `gpt-5.5`、batch `100`、context `2`、min confidence `0.9`。
- P2: scope `suspicious`、threshold `0.40`。
- P2 job: `job_ea301023a3cd431f8a5700ea4f4e4ca1`。

### 疎通確認

- rescue対象index `157`を1件送信。
- API call `1`、successful batch `1/1`、schema failure `0`。
- input/output tokens: `408/68`、processing `4.275s`。

### P2 E2E結果

- targets: `1304/1695`、context `55`、unique sent `1357`。
- API calls / successful batches: `14/14`。
- retry `0`、failed batch `0`、schema failure `0`、fallback `false`。
- input/output/total tokens: `52,247 / 100,698 / 152,945`。
- correction time: `1087.679s`。
- corrected `268`、low-confidence reject `94`、safety reject `4`。
- deterministic/corrected/final segment counts: `1695/1695/1695`。
- order/start/end timestamp mismatch: `0`。final transcriptはcorrected transcriptと一致。
- normal: `1/1`、`1280x720`、`348.982s`。
- short: `2/2`、両方`1080x1920`、`49.883s` / `61.194s`。
- render failure: `0`、sidecar risk: `0`、ZIP: `73,335,336 bytes`。
- total E2E runtime: `1745.609s`。

### All-mode実token baseline

- 同じdeterministic transcript `1695` segmentsと同じ校正設定を使用。
- API calls / successful batches: `17/17`。
- retry `0`、failed batch `0`、schema failure `0`。
- input/output/total tokens: `67,053 / 134,638 / 201,691`。
- correction time: `1469.749s`。
- baselineはtoken比較専用。transcription、candidate generation、renderはP2 E2Eで別途検証済みのため省略。

### 実測削減

- API calls: `17 -> 14`、`17.647%`削減。
- input tokens: `67,053 -> 52,247`、`22.081%`削減。
- output tokens: `134,638 -> 100,698`、`25.208%`削減。
- total tokens: `201,691 -> 152,945`、`48,746 tokens / 24.169%`削減。
- correction time: `1469.749s -> 1087.679s`、`382.071s / 25.996%`削減。

### 判定

- Task62 final real-API acceptance: pass。
- `14/14`、fallback `0`、schema failure `0`、segment/timestamp維持、render、ZIP、sidecar risk `0`を確認。
- PR #42をReady化し、CI通過後にmerge可能。

## 2026-07-18 Task 63 Windows launcher MVP refresh

### 目的

- 未mergeのTask57 Windows launcherを現行mainへ更新し、Docker版AutoClipperをコマンド入力なしで起動・確認・停止できる状態にする。
- frontend/backend/worker/pipelineは変更せず、既存Docker Compose runtimeを操作する薄いWindows GUIとして仕上げる。

### 対象

- `Start AutoClipper.cmd`
- `.github/workflows/ci.yml`
- `launcher/`
- `backend/tests/test_windows_launcher.py`
- `docs/WINDOWS_LAUNCHER.md`
- `README.md`

### 変更内容

- Python/Tkinter launcherへStart、Rebuild and Start、Open App、Stop、Refresh、logs、uploads/outputs folder操作を追加。
- Docker CLI/daemon/Compose、compose file、port、disk、service health、OpenAI key設定有無をpreflightで確認。
- Stopは`docker compose stop`のみを使い、SQLite、Redis volume、uploads、outputsを削除しない。
- project pathに空白がある場合も、明示cwdとargument listでDocker commandを実行。
- launcher log欄へ`Yu Gothic UI`を指定し、日本語文字化けを回避。
- 起動途中のAutoClipper serviceが使用するportを外部process競合と誤判定しないよう修正。
- `OPENAI_API_KEY`を`.env`とprocess environmentの両方から検出し、command outputとlauncher logで値をredact。
- `Start AutoClipper.cmd`でPython 3.11以上を明示確認。

### 検証結果

- tested main: `77d7426`。
- launcher/backend ruff: pass。
- launcher unit tests: `19 passed`。
- backend pytest: `306 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Tkinter GUI startup smoke: pass。
- launcher controllerによる`Stop -> Start`: pass。
- backend `/health`: HTTP `200`、`status=ok`。
- frontend `/upload`: HTTP `200`。
- runtime smoke: pass。backend/frontend/worker/redis、共有DB/storage、FFmpeg/ffprobeを確認。
- DB size: `524288 -> 524288 bytes`、output job count: `121 -> 121`。停止・再起動後も保持。
- sample E2E: pass。job `job_f70c3bd81894446b9dd748f7512af567`、short `1/1`、`1080x1920`、render failure `0`。
- sidecar risk: `0`。

### 未解決事項

- launcher MVPはWindows、Docker Desktop、Python 3.11以上が必要。
- installer、Python同梱、auto update、Docker Desktop自動導入は未実装。
- clean Windows環境での配布確認はpackaging taskとして別途実施する。

## 2026-07-18 Task 64 subtitle correction model / reasoning benchmark

### 目的

- 字幕校正のmodelとreasoning設定を固定transcriptで比較し、実token、推定費用、処理時間、品質差を確認する。
- production defaultは比較完了まで変更せず、音声・動画をOpenAIへ送らない。

### 実装

- `subtitleCorrectionReasoningEffort`をAPI、worker、Upload UI、real-video E2Eへ追加。
- `default`はResponses APIの`reasoning`を省略し、現行挙動を維持。明示値は`reasoning.effort`へ渡す。
- correction summaryへ`reasoning_tokens`と`visible_output_tokens`を追加。
- `scripts/benchmark_subtitle_correction_models.py`を追加。1 segment probe、固定target benchmark、手動review再集計に対応。
- benchmark reportへusage-based費用、変更index差、token/費用/時間のbaseline比を追加。

### 1 segment probe

- `gpt-5.5:default`: pass。
- `gpt-5.5:none`: pass。
- `gpt-5.4-mini:none`: pass。
- `gpt-5-mini:none`: reject、`minimal`: pass。比較値は`minimal`を採用。
- `gpt-5.6-luna:none`: pass。
- 全成功条件でStructured Outputs schemaとusage取得を確認。

### Controlled TTS

| profile | CER | proper nouns | output/reasoning/visible | cost USD | seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.5:default` | 0.0809 | 7/8 | 1614/1034/580 | 0.0524 | 21.058 |
| `gpt-5.5:none` | 0.0809 | 7/8 | 577/0/577 | 0.0213 | 5.753 |
| `gpt-5.4-mini:none` | 0.1006 | 7/8 | 577/0/577 | 0.0032 | 3.444 |
| `gpt-5-mini:minimal` | 0.1164 | 6/8 | 596/0/596 | 0.0014 | 5.703 |
| `gpt-5.6-luna:none` | 0.0907 | 7/8 | 577/0/577 | 0.0043 | 3.336 |

### 124秒実話者

- 固定`36/48` targets、`small + ja`、scope `suspicious`、context `2`、batch `100`。
- text/contextによる手動分類。音声正解原稿による確定評価ではない。

| profile | useful | missed | harmful | style | cost USD | seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.5:default` | 13 | 2 | 0 | 0 | 0.2140 | 88.225 |
| `gpt-5.5:none` | 15 | 0 | 0 | 1 | 0.0750 | 20.232 |
| `gpt-5.4-mini:none` | 8 | 6 | 0 | 1 | 0.0112 | 9.245 |
| `gpt-5-mini:minimal` | 4 | 7 | 0 | 2 | 0.0049 | 20.399 |
| `gpt-5.6-luna:none` | 11 | 2 | 2 | 6 | 0.0151 | 9.186 |

### 58分上位2条件

- input: Task62 P2の固定`1695` segments / `1304` targets。
- 共通設定: `small + ja`、scope `suspicious`、context `2`、batch `100`、min confidence `0.9`。
- 両条件ともAPI `14/14`、retry `0`、schema failure `0`、fallback `0`、segment/order/timestamp mismatch `0`。

| profile | changes | input | output | reasoning | visible | cost USD | seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.5:default` | 283 | 52247 | 105104 | 47467 | 57637 | 3.4144 | 1257.230 |
| `gpt-5.5:none` | 129 | 52247 | 61524 | 0 | 61524 | 2.1070 | 543.496 |

- `none`削減: output tokens `41.464%`、total tokens `27.696%`、推定費用`38.291%`、処理時間`56.770%`。
- 変更index: 共通`117`、defaultのみ`166`、noneのみ`12`。
- 長尺では変更件数差が大きいため、`none`を品質同等またはdefault候補とは未判定。

### Render / runtime検証

- 最新workerで`gpt-5.5:none`短尺実話者E2E: `job_3a220894ed9d4d129da1828961cbe85b`。
- correction: API `1/1`、input/output `1942/2159`、reasoning `0`、visible `2159`、fallback `false`、schema failure `0`、`22.765s`。
- normal `1/1`、short `2/2`、short `1080x1920`、render failure `0`、ZIP download pass、sidecar risk `0`。
- Docker rebuild / runtime smoke: pass。
- 58分default renderはTask62 job `job_ea301023a3cd431f8a5700ea4f4e4ca1`で確認済み。
- 58分`none`の重複pipeline E2Eは約`$2.11`の校正再課金を避けるため未実施。固定transcript API比較と短尺renderで設定経路を確認。

### 判定

- production defaultを維持:
  - `subtitleCorrectionMode=off`
  - `subtitleCorrectionModel=gpt-5.5`
  - `subtitleCorrectionReasoningEffort=default`
- `gpt-5.5:none`は有力な省コストoptionだが、長尺のdefault-only変更`166`件の正誤確認前に既定化しない。
- `gpt-5.4-mini`、`gpt-5-mini`は124秒評価で見逃し増加。`gpt-5.6-luna`は有害/表記変更増加のため採用しない。

## 2026-07-18 Task 65 default vs none long-form quality audit preparation

### 目的

- Task64の58分`gpt-5.5:default` / `gpt-5.5:none`差分を、追加API費用なしで音声確認できる形にする。
- reasoning差の品質評価とTask66 changes-only schema変更を分離する。

### 変更内容

- `scripts/audit_reasoning_quality.py`を追加。
- 既存change artifactを次の4群へ分類:
  - `default_only`
  - `none_only`
  - `shared_same_text`
  - `shared_different_text`
- 各indexへ元字幕、両model出力、前後segment、音声区間、review欄を記録。
- Docker workerのFFmpegで前後文脈付きmono 16kHz WAVを抽出可能。
- UTF-8 BOM CSVへ手動labelを記入し、JSON manifestと結合して品質指標を再集計可能。
- 未入力labelを成功・失敗へ推測せず、partial reviewとして扱う。

### 58分review package

- source job: `job_ea301023a3cd431f8a5700ea4f4e4ca1`。
- API call: `0`。
- unique changed indices: `295`。
- 分類:
  - default-only: `166`
  - none-only: `12`
  - shared + corrected text同一: `114`
  - shared + corrected text相違: `3`
- review JSON items / CSV rows / WAV: `295 / 295 / 295`。
- WAV size: `63,404,804 bytes`。
- 全WAV ffprobe: pass。空/header-only file: `0`。
- local output:
  - `storage/temp/transcription_benchmark/task65/long_58m_quality_audit/reasoning_quality_review.json`
  - `storage/temp/transcription_benchmark/task65/long_58m_quality_audit/reasoning_quality_review.csv`
  - `storage/temp/transcription_benchmark/task65/long_58m_quality_audit/audio/`

### 現在判定

- review label: `29/295`。標準設定の製品判断が確定したため全件確認を停止。
- 確認内訳:
  - default-only: `17`
  - none-only: `9`
  - shared + corrected text相違: `3`
  - shared + corrected text同一: `0`
- 人間判定:
  - `default`有益修正: `17`
  - `none`が上記17件を見逃し。
  - `none`有害修正: `5 segments`。
  - 重大な反復パターン: `キオクシア -> NVIDIA`が`4 segments`。
- 最も`none`に有利な仮定でも、useful recall上限は`117 / (117 + 17) = 87.3%`。暫定合格条件`95%`へ到達不可。
- 29件は差分優先sampleであり、`5/29`を全295件の有害修正率として使用しない。全母集団率の算出は保留。
- production recommendationは`gpt-5.5:default`を維持。
- `gpt-5.5:none`は実験的な省コスト・高速option。重要字幕の手動確認を前提とする。
- Task66 changes-only compact schemaはTask65音声監査後の別branch / PRで実施する。

## 2026-07-19 Task 67 GPU transcription benchmark

### 目的

- RTX 5070 Tiを使うfaster-whisper GPU workerを追加する。
- `small / medium / large-v3 / turbo + ja + CUDA FP16`を比較し、精度とOpenAI校正需要から採用profileを決める。
- Task66 changes-only schemaとはbranch / PRを分離する。

### 実装

- worker専用`backend/Dockerfile.gpu`と`docker-compose.gpu.yml`を追加。
- CUDA 12.8.1 + cuDNN runtime、CTranslate2 4.8.1、faster-whisper 1.2.1を使用。
- Whisper model cacheを`whisper_model_cache` volumeへ永続化。
- JobSettings / Upload UI / real-video E2Eへ以下を追加:
  - `transcriptionDevice`: `auto / cpu / cuda`
  - `transcriptionComputeType`: `auto / int8 / float16 / int8_float16`
  - `whisperModelSize`: `turbo`追加
- `cuda`明示時はGPU未検出を`transcription_cuda_unavailable`で失敗させ、CPUへ黙ってfallbackしない。
- `auto`時だけCPU fallbackを許可し、理由をmetadataへ保存。
- `transcript_summary.json`へrequested/actual device、compute type、GPU名、load/transcription秒、peak VRAM、fallbackを追加。
- benchmarkへdeterministic CER、suspicion target、API calls、対象音声、context込みtext/token proxyを追加。

### GPU preflight

```text
GPU: NVIDIA GeForce RTX 5070 Ti
VRAM: 16303 MiB
driver: 595.97
compute capability: 12.0
actual runtime: cuda / float16
fallback: false
pip check: pass
```

### CPU compatibility

- job: `job_a961a746c2d149f693c5d7d4af4665c9`
- compatibility defaultの`base / auto / cpu / auto`で短尺実話者E2Eを実行。
- actual runtimeは`cpu / int8`、short `1/1` (`1080x1920`)。
- render failure `0`、sidecar risk `0`、total runtime `31.188s`。

### 比較結果

- controlled TTS 119.629秒:
  - `small`: CER `0.1583`, transcribe `3.908s`, VRAM `3300MB`
  - `medium`: CER `0.1463`, transcribe `5.968s`, VRAM `4676MB`
  - `large-v3`: CER `0.2846`, transcribe `7.417s`, VRAM `6724MB`
  - `turbo`: CER `0.1804`, transcribe `2.715s`, VRAM `4642MB`
- 124秒実話者:
  - 固有名詞: `large-v3 3/4`, `turbo 3/4`
  - correction text proxy: `small 714`, `large-v3 328`, `turbo 294`
- 58分実話者:
  - `large-v3`: `265.400s`, VRAM `7716MB`, 重要語`2/5`
  - `turbo`: `100.963s`, VRAM `4772MB`, 重要語`4/5`
  - Task65人間確認済み難所の厳格一致: `large-v3 13/29`, `turbo 16/29`

### OpenAI需要

- 本番同条件`threshold=0.4 / context=2 / batch=100 / glossary=[]`。
- 現行`small + CPU`: target `1304/1695`, calls `14`, token proxy `14343`。
- `turbo + CUDA`: target `850/1396`, calls `9`, token proxy `11876`。
- 削減見込み:
  - target `34.8%`
  - calls `35.7%`
  - target speech `16.9%`
  - context込みtoken proxy `17.2%`
- 実OpenAI tokenは未測定。Task66 compact schemaと分離して評価する。

### 58分統合E2E

- job: `job_e7f350f808164c679cdd27f27bc3f63e`
- `turbo / ja / cuda / float16`, OpenAI correction `off`。
- total `303.391s`, transcription stage `89.063s`, engine `86.102s`。
- normal `1/1` (`1280x720`)、short `2/2` (全て`1080x1920`)。
- render failure `0`、ZIP `76050538 bytes`、audit inspection `0`、sidecar risk `0`。

### 判定・未解決

- RTX 5070 Ti推奨profileは`turbo / ja / cuda / float16`。
- compatibility defaultの`base / auto / cpu / auto`は変更しない。
- `turbo`でも既知難所`13/29`が未解決。OpenAI校正を完全に不要とは判定しない。
- GPU workerはCompose overrideで起動する。Windows launcherのGPU override自動選択は未実装。
- 次はTask66 changes-only schemaで、品質を維持したままOpenAI output token削減を検証する。

## 2026-07-20 Task 66 compact subtitle response schema rejection

### 目的

- `gpt-5.5:default`の品質を維持したまま、未変更segmentのAPI出力と費用を削減できるか検証する。

### 検証結果

- 固定124秒artifact: `48 segments / 36 suspicious targets / context=2 / batch=100`。
- full baselineはTask64の既存結果を再利用し、changes-only側だけ1 batchを実行。
- `full`:
  - estimated cost `$0.21398`
  - visible output tokens `2144`
  - accepted changes `13`
- `changes-only`:
  - estimated cost `$0.15216`
  - visible output tokens `606`
  - accepted changes `10`
  - retry `0`、fallback `0`、schema failure `0`
  - segment count / order / timestamp維持
- 費用削減 `28.891%`、visible output token削減 `71.7%`。
- changed indexはshared `9`、full only `4`、compact only `1`。
- fullで有益と確認済みの13修正に対するchanges-only coverageは最大`9/13 = 69.2%`。

### 判定

- Task66は検証完了。不採用。
- 費用削減に対して有益修正coverageの低下が大きく、品質受入条件を満たさない。
- 58分の有料API replayは短尺品質gate不合格のため意図的に実施しない。
- production response schemaと既定値は`full`を維持する。
- changes-only runtime codeはmainへmergeしない。
- Draft PR #45はrejected experimentとしてclose済み。

## 2026-07-20 Task 68 local subtitle correction model benchmark

### 目的

- ローカルLLMが危険な字幕修正を確定せず、OpenAI送信textを20%以上削減できるか独立benchmarkで判定する。
- pipeline・UI・production providerへ接続せず、OpenAI APIを使わない。

### 変更

- Ollama native API向けbenchmark CLIを追加。
- `think=false / JSON schema / temperature=0 / seed=42 / num_ctx=8192`を固定可能にした。
- timestampをモデルへ送信せず、検証済みindexで元segmentへ再結合する。
- 数字、単位、英字、カタカナ、漢字、固有名詞候補、大きい編集をAPI escalationへ残すdeterministic gateを追加。
- Task64固定124秒artifactとTask65人手確認済み29件の評価を追加。

### 実測環境

- Ollama `0.32.1`
- GPU `NVIDIA GeForce RTX 5070 Ti 16GB`
- driver `595.97`
- batch `10`

### 結果

- `qwen3.5:9b / Q4_K_M / digest 6488c96fa5fa`:
  - 124秒: targets `36`, model changes `6`, local accept `0`, text削減 `0%`, `13.656s`, peak VRAM `8659MiB`
  - 難所29件: model changes `8`, local accept `0`, unsafe accept `0`, text削減 `0%`, `10.390s`
- `qwen3:14b / Q4_K_M / digest bdbd181c33f2`:
  - 124秒: targets `36`, model changes `0`, local accept `0`, text削減 `0%`, `28.500s`, peak VRAM `12209MiB`
  - 難所29件: model changes `2`, local accept `1`, unsafe accept `1`, text削減 `6.575%`, `21.438s`

### 判定・未解決

- Task68は検証完了。不採用。
- 両モデルともAPI text削減20%未達。`qwen3:14b`は有害なlocal accept `1`で安全性条件も不合格。
- fail-fast条件成立後の反復・58分評価は意図的に実施しない。
- OpenAI API call `0`。pipeline・UI・production defaultは変更しない。
- benchmark reportはignored local outputに保存し、モデル本体と生成artifactはcommitしない。

## 2026-07-21 Task 69 launcher GPU recommended profile

### 目的

- Windows launcherの主操作から、検証済みGPU profileまたはCPU互換profileを選んで起動する。
- GPU明示時の暗黙CPU fallbackを禁止し、自動選択時だけfallback理由を表示する。

### 変更

- launcherへ`recommended / gpu / cpu` runtime profileを追加。
- host NVIDIA GPU、Docker NVIDIA runtime、`docker-compose.gpu.yml`をpreflightで確認。
- GPU profile起動後にworker内`app.audio.gpu_preflight`を実行し、`cuda / float16 / fallback=false`を検証。
- 推奨GPU起動の実体確認に失敗した場合のみCPU workerを再作成し、理由を表示。
- GPU必須起動は失敗時にworkerを停止し、CPUへ切り替えない。
- launcher画面へruntime profile、transcription設定、GPU名、worker構成、fallbackを表示。
- Upload URLへ`runtimeProfile`を付け、GPUでは`turbo / ja / cuda / float16`、CPUでは`base / auto / cpu / auto`を初期選択。
- Compose workerへ`AUTOCLIPPER_RUNTIME_PROFILE=cpu|gpu`を追加。backend schemaの互換defaultは変更しない。

### 検証

- launcher tests: `24 passed`。
- launcher/tests ruff: pass。
- backend ruff: pass。
- backend pytest: `341 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Compose config merge: pass。
- Docker runtime smoke `--skip-video`: pass。
- 実GPU起動:
  - GPU: `NVIDIA GeForce RTX 5070 Ti`
  - worker: `gpu`
  - transcription: `turbo / ja / cuda / float16`
  - actual device / compute type: `cuda / float16`
  - fallback: `false`
  - backend / frontend / worker / redis: running
  - backend health / Upload: HTTP `200`
- 実CPU切替: worker `cpu`、全service ready。
- `GPU -> CPU -> GPU -> Stop -> GPU Start`: pass。
- SQLite size: `569344 -> 569344 bytes`、output job directory count: `127 -> 127`。
- Upload UI実描画:
  - GPU query: `Runtime: GPU recommended`、`turbo / cuda / float16 / ja`
  - CPU query: `Runtime: CPU compatible`、`base / cpu / auto / auto`
- OpenAI API call、実動画生成は本Taskで実行しない。

### 未解決

- 別Windows環境での初回clone/ZIP展開、image/model初回download、PC再起動後、GPUなし環境、日本語パスは未検証。
- 上記はTask70 clean Windows distribution acceptanceで確認する。
- `v1.2.0 stable`はTask70 pass後に判断する。

## 2026-07-23 Task 70 Windows distribution acceptance

### 目的

- `v1.2.0-rc.2` tag ZIPを実配布候補としてWindows環境で受入確認する。
- クリーンCPU配布経路と実NVIDIA GPU経路の結果を分離して記録し、`v1.2.0`判定を確定する。

### 配布物

- tag: `v1.2.0-rc.2`
- commit: `d385b8c7d1925fd14b3de42280fc21d39832b179`
- local release ZIP SHA-256: `99D1194559A3E58A8DEA8FB3EBC6DB169F6851A3F829A9CDFA25FAC1647E3631`
- runtime codeはtagから変更なし。

### クリーンCPU Windows受入

- 判定: PASS。
- 開発checkoutとは別パスへtag ZIPを展開し、launcher GUI起動を確認。
- Python `3.11.9`、compile pass、launcher tests `24 passed`。
- port conflict `0`、確認時disk free `241.85GB`。
- Docker image、SQLite DB、Whisper cache、outputsがない状態から初回起動。
- backend / frontend / worker / redis: running。
- `/health`、`/upload`: pass。
- sample動画job、normal、short、ZIP download: pass。
- launcher Stop後にWindowsを再起動し、再Start: pass。
- SQLite DB、outputs、Whisper model cache保持: pass。
- NVIDIA GPU未検出のためCPU互換profileを使用。
- Docker DesktopはWindows再起動後に手動起動が必要。launcherによる未起動検出・案内は仕様どおり。

### NVIDIA GPU受入

- クリーンWindowsとの組合せ試験は未実施。
- 開発Windows 11 / NVIDIA GeForce RTX 5070 Tiで実GPU runtimeを確認済み。
- recommended profile: `turbo / ja / cuda / float16`。
- actual runtime: `cuda / float16`、fallback `false`。
- GPU/CPU切替、4 services、health、Stop/Start、DB・outputs保持: pass。

### 判定・既知制限

- Task70は合格。クリーンCPU配布経路と実NVIDIA runtime経路の独立PASSを`v1.2.0`受入根拠とする。
- クリーンWindows + NVIDIA GPUの初回download/build組合せは未検証として明記し、release blockerにはしない。
- OpenAI字幕校正は既定OFF。Task70ではAPIを使用しない。
- Docker Desktop、WSL2、Python 3.11+は前提条件。
- installer、Python同梱、Docker Desktop導入支援、自動更新は`v1.2.0`対象外。
- docs-only PR merge後、runtime差分がないことを確認して`v1.2.0` tagを作成する。

## 2026-07-23 Task 71 large-video upload limit

### 目的

- 長尺動画が固定の512 MiB上限で拒否される問題を解消する。

### 変更

- upload上限の互換設定`MAX_UPLOAD_SIZE_BYTES`を維持したまま、既定値を512 MiBから8 GiBへ変更。
- Compose、`.env.example`、backend既定値を8 GiBへ統一。
- 容量超過エラーをbyte数だけでなく`GiB` / `MiB`で読める表示へ変更。
- READMEへ8 GiBの既定値と`.env`によるoverride方法を記録。

### 検証

- backend ruff: pass。
- upload API tests: `16 passed`。
- backend pytest: `341 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- backend / worker Docker rebuild・再作成: pass。
- container設定: `MAX_UPLOAD_SIZE_BYTES=8 GiB`一致確認。
- backend `/health`: pass。

### 未解決

- 実際の512 MiB超ファイルのブラウザアップロードは未確認。対象動画で再試行して確認する。

## 2026-07-23 Task 72 upload feedback and subtitle preview

### 目的

- 動画アップロード中・完了後の状態を明確に表示する。
- 字幕スタイルの変更結果をレンダリング前に確認できるようにする。

### 変更

- upload API呼び出しを進捗取得可能なXMLHttpRequestへ変更。
- Upload画面へ実percent、progress bar、アップロード完了、ジョブ準備中の状態表示を追加。
- Job画面へアップロード完了通知を追加。
- 選択動画のファイルサイズ表示を追加。
- 字幕スタイルを常時表示し、ショート9:16 / 通常16:9のライブプレビューを追加。
- フォント、文字サイズ、縁取り、下余白、表示位置をプレビューへ即時反映。
- 字幕スタイルの既定値リセットを追加。

### 検証

- frontend lint / typecheck / build: pass。
- backend ruff: pass。
- backend pytest: `341 passed, 1 skipped`。
- Docker frontend rebuild: pass。
- Playwright + 実Chrome確認:
  - upload中表示: pass。
  - upload完了表示: pass。
  - Job画面の完了通知: pass。
  - 字幕設定変更の即時反映: pass。
  - desktop `1440x1000`: pass。
  - mobile `390x844`: 横スクロールなし。

### 未解決

- 実際の長尺ファイルでのupload percent推移は未確認。対象動画の次回uploadで確認する。

## 2026-07-23 Task 73 subtitle review workflow

### 目的

- 自動clip選定後、字幕焼き込み前に処理を一時停止する。
- 通常切り抜きとショートをGUIで順に再生し、音声と異なる字幕を修正してから書き出す。
- 複数clipでも工程と確認状況が分かる状態にする。

### 変更

- `requireSubtitleReview`を追加。backend/APIの互換defaultは`false`、Upload UIのdefaultは`true`。
- 字幕焼き込みONかつ手動確認ONの場合、選定後に`awaiting_subtitle_review`で停止する。
- source動画のRange対応preview、字幕review取得・更新、clip確認、最終確定APIを追加。
- 選定された通常・ショートを一覧表示する字幕確認画面を追加。
- clip区間の音声再生、segment単位の字幕修正、未保存表示、clipごとの確認状態を追加。
- 同じsource transcript segmentを使う複数clipへ修正を共通反映する。
- 共通segmentの再編集時は、影響するclipを未確認へ戻す。
- 全clip確認後のみrenderを再開し、normal / short / ZIPを生成する。
- 修正後transcriptを`reviewed_transcript_segments.json`、操作状態を`subtitle_review.json`へ保存する。
- 完了後の字幕確認画面は確認履歴として読み取り専用表示にする。
- 選定clipが0本の場合は確認待ちへ入らず`no_usable_output`で終了する。
- Uploadの動画選択欄を、未選択・選択完了・アップロード中・アップロード完了で全面的に切り替える。
- 選択後はファイル名・容量・選択解除・別動画選択を明示し、送信進捗を同じ欄へ表示する。
- 画面上部の実行ボタンも、未選択・アップロード中・ジョブ準備中に合わせて文言を切り替える。

### 検証

- backend ruff: pass。
- backend pytest: `346 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker全service rebuild: pass。
- `smoke_runtime.py --skip-video`: pass。backend / frontend / worker / redis running。
- 既存自動sample E2E: pass。
  - job: `job_e6d7c84ceb1143b788ded050b4359f8f`
  - 手動確認を要求しない既存API経路で`completed`
  - short: `1080x1920`
- 手動字幕確認runtime E2E: pass。
  - job: `job_9e91eab9ebf8490cabb28ca0b249ca7b`
  - `awaiting_subtitle_review` / `78%`で停止
  - normal `1` / short `1`
  - 共有字幕を修正し、2本へ反映
  - 各clip確認後にrender再開、normal / short / ZIP生成
  - metadata / subtitle download: HTTP `200`
  - source video Range request: HTTP `206`
  - short: `1080x1920`
  - sidecar risk: `0`
- ブラウザ確認:
  - desktopで字幕修正・保存・clip確認・最終確定: pass。
  - mobile `390x844`: 横はみ出しなし。
  - 完了画面の編集・保存・再render操作は無効。
  - browser error: `0`。
- Upload選択状態のブラウザ確認:
  - desktopで未選択の白い破線表示から、選択完了の緑色表示へ全面切替: pass。
  - 長い日本語ファイル名を表示したmobile `390x844`: 横はみ出しなし。
  - 選択解除で未選択表示へ復帰: pass。
  - browser error: `0`。
- OpenAI APIは本Taskで使用しない。

### 未解決・制限

- MVPでは字幕textのみ編集可能。timestamp、clip境界、clip採否は編集しない。
- 確認対象は自動選定されたclipと、その区間に重なる字幕segmentのみ。
- 同一source segmentの修正は、それを使う通常・ショート全clipへ共通反映する。
- 手動確認工程は`burnSubtitles=true`かつ`requireSubtitleReview=true`の場合だけ実行する。
- branch `codex/task-73-subtitle-review-workflow`で実装・ローカル検証済み。main mergeは未実施。

## 2026-07-23 Task 74 Source Han Sans JP Heavy font

### 目的

- 前案件で使用した`Source Han Sans JP Heavy`を字幕font選択へ追加する。
- 開発PCだけでなく配布ZIPとDocker workerでも同じfontを利用可能にする。

### 変更

- `SourceHanSansJP-Heavy.otf` Version 2.005と公式SIL Open Font License 1.1を配布物へ同梱。
- Upload UIへ`極太ゴシック（Source Han Sans JP Heavy）`を追加。
- ブラウザの字幕style previewへ同梱Web fontを適用。
- backend / workerへ同梱font fileをread-only mountし、そのdirectoryをFFmpeg/libassの`fontsdir`へ渡す。
- `ASS_FONTS_DIR`未指定時は従来のASS filterを維持する。

### 検証

- font asset:
  - family: `Source Han Sans JP Heavy`
  - version: `2.005`
  - SHA-256: `F875DE9C62ACE2082B90AB1DA940F3E8CEFFA933F500E49D205CB74E6E5D03BB`
  - SIL Open Font License 1.1を同梱。
- backend ruff: pass。
- backend pytest: `347 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker CPU backend / GPU worker / frontend rebuild: pass。
- worker:
  - `ASS_FONTS_DIR=/app/fonts`
  - font family / fullnameを`fc-scan`で確認。
  - mounted fontは`SourceHanSansJP-Heavy.otf`のみ。
- actual burn-in:
  - libass `fontselect`が`SourceHanSansJP-Heavy`を選択。
  - Japanese subtitle burn-in: pass。
  - output: H.264 / `1080x1920` / `2.000s`。
  - font fallback / license file load warning: `0`。
- browser:
  - font option表示・選択値更新: pass。
  - preview computed font: `Source Han Sans JP Heavy`。
  - bundled font HTTP: `200`。
  - browser error: `0`。
- `smoke_runtime.py --skip-video`: pass。backend / frontend / worker / redis running。

### 未解決・制限

- branch `codex/task-74-source-han-heavy-font`で実装・ローカル検証済み。main mergeは未実施。
- Task74 branchはPR #53のheadを親にしている。PR #53 merge後にmainへretarget / rebaseする。

## 2026-07-23 Task 75 output selection and per-type subtitle styles

### 目的

- Upload画面で通常切り抜きのみ、ショートのみ、両方を選べるようにする。
- 通常切り抜きとショートの字幕styleを別々に設定・previewできるようにする。
- 文字色、縁取り色、font、文字サイズ、縁取り幅、位置、画面端からの余白をGUIから設定する。
- font選択肢から案件固有の表現を除去する。

### 変更

- 生成対象へ`両方`、`通常のみ`、`ショートのみ`のsegmented controlを追加。
- 未生成側のcountを`0`にし、関連しないshort設定とduration設定を無効化。
- APIは`normalClipCount=0`または`shortCount=0`を許可し、両方`0`はrejectする。
- 通常とショートに独立したsubtitle font / size / outline / text color / outline color / alignment / margin設定を追加。
- 字幕style editorを通常`16:9`とショート`9:16`のtabへ分離し、選択中styleのpreviewを即時更新。
- 色はnative color pickerと白・黄・水色・pink・緑・黒のpresetを追加。
- ASS colorへ`#RRGGBB`からlibassのBGR表記へ変換して反映。
- 共通subtitle style fieldは既存API互換のfallbackとして維持。
- `Source Han Sans JP Heavy`の表示名を`極太ゴシック`へ変更し、案件固有文言を削除。

### 検証

- backend ruff: pass。
- backend pytest: `352 passed, 1 skipped`。
- targeted subtitle/API tests: `33 passed`。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / worker / frontend rebuild: pass。
- `smoke_runtime.py --skip-video`: pass。backend / frontend / worker / redis running。
- ショートのみ実render E2E: pass。
  - job: `job_a2b365e78c9f414a987451511d3d0624`
  - selected: normal `0/0` / short `1/1`
  - short: `1080x1920`
  - ZIP: generated
  - sidecar risk: `0`
- 通常のみ実render E2E: pass。
  - job: `job_27b31a915e774188a4dc166a1c68c3c2`
  - selected: normal `1/1` / short `0/0`
  - normal: video `320x180` + audio stream
  - ZIP: generated
  - sidecar risk: `0`
- API tests:
  - 通常のみ: accepted。
  - ショートのみ: accepted。
  - 両方`0`: validation error。
  - 通常/ショート別styleの保存: pass。
- ASS tests:
  - 通常/ショート別fontと色の反映: pass。
  - `#RRGGBB`からASS BGR colorへの変換: pass。
- 通常/ショート別style実render E2E: pass。
  - job: `job_b87b226b2628447d9e4ff1027bfbbdd9`
  - normal ASS: `Noto Serif CJK JP` / `52` / 水色 / alignment `5`
  - short ASS: `Source Han Sans JP Heavy` / `88` / 黄色 / alignment `8`
  - overlay titleの色は従来の白文字・黒縁を維持。
  - normal `1/1` / short `1/1`
  - sidecar risk: `0`
- browser:
  - `両方` / `通常のみ` / `ショートのみ`の切替: pass。
  - 非対象countの非表示とshort専用controlの無効化: pass。
  - 通常/ショート間でfont・色・位置を独立保持: pass。
  - desktop: pass。
  - mobile `390x844`: 重なり・横はみ出しなし。
  - browser error: `0`。

### 未解決・制限

- 本Taskの実render確認は25秒fixtureで実施。長尺実動画の再renderは実施していない。
- 共通subtitle style fieldは互換用途で残るが、Upload UIは通常/ショート別fieldを送信する。
- branch `codex/task-75-output-and-subtitle-style-controls`で実装・ローカル検証済み。main mergeは未実施。

## 2026-07-23 Task 76 clip-based subtitle review workspace

### 目的

- 字幕確認時にフル尺動画のtimelineを操作させず、選択した通常・ショートclipだけを確認できるようにする。
- 動画の再生・一時停止を常に操作できる位置へ固定し、字幕一覧だけを独立してscroll可能にする。
- 通常1、通常2、ショート1などを切り替え、clip単位で字幕確認・修正・確認済み操作を行う。

### 変更

- 字幕確認画面をclip一覧、選択clip player、選択clip字幕の3pane workspaceへ変更。
- 元動画のRange配信を再利用しながら、playerのtimelineとseek範囲を選択clipの`0:00`からclip終了までに制限。
- 元動画の対象外範囲へUIから移動できないようにし、clip切替時は選択clip先頭へ戻す。
- 字幕paneを独立scrollにし、再生中segmentのhighlightと自動追従を追加。
- 字幕時刻をclip相対時刻で表示し、元動画時刻は補助情報へ移動。
- playerへ再生・一時停止、5秒移動、音量、再生速度、全画面操作を追加。
- clipごとの確認済み操作を字幕pane下部へ固定。

### 検証

- frontend lint / typecheck / build: pass。
- Docker GPU composeでfrontend / backend rebuild: pass。
- existing review job `job_2190d60e0acb4a74a87e9e916152e38a`:
  - 通常1: `6:37.5` / `143`字幕。
  - 通常2: `1:30.0` / `51`字幕。
  - clip切替時にplayer duration、字幕見出し、字幕件数が連動: pass。
  - 通常2のplayer seek範囲: `0` - `90`秒。
- desktop Chrome `1905x855`:
  - 再生buttonがviewport内に残る: pass。
  - 字幕pane独立scroll: `455px` viewport / `26174px` content。
  - 横overflow: なし。
- mobile Chrome `390x844`:
  - responsive stack: pass。
  - 横overflow: なし。
- browser console error: なし。

### 未解決・制限

- 確認playerは新しい動画fileを生成せず、元動画をclip境界内へ制限して再生する。preview生成待ちと追加storageは発生しない。
- shortの確認playerは時間範囲確認用で、最終9:16 cropと字幕焼き込みは確認完了後の書き出しで行う。
- browser自動検証のbackground tabではvideo decode完了を観測できなかった。元動画配信APIとRange response、player state、clip境界UIは確認済み。実音声再生はforeground Chromeで最終確認する。
- branch `codex/task-76-clip-subtitle-review-workspace`で実装・ローカル検証済み。main mergeは未実施。

## 2026-07-23 Task 77 guided clip selection

### 目的

- 通常切り抜きとショートで、狙う場面・雰囲気・具体的な話題を別々に指定できるようにする。
- 冒頭挨拶、終了挨拶、告知だけの区間を避け、意味のある場面がない場合は本数を減らせるようにする。
- OpenAI APIを既定で使わず、抽象的な文脈判定が必要な場合だけ明示的に有効化する。

### 変更

- Upload画面へ通常・ショート別の選定presetと自由入力方針を追加。
- preset: `auto` / `highlights` / `funny` / `important` / `emotional` / `informative`。
- `冒頭・終了挨拶を除外`、`告知・視聴案内を除外`、`品質優先`、`AIで内容を判定`を追加。
- UIの新規jobは`strict_quality`を既定とし、良い候補が不足する場合に無関係なclipで本数を埋めない。
- ローカルrule scoreへ日本語hook、自由入力語句、preset語句、intro/outro・告知penaltyを追加。
- OpenAI scoring promptへ通常/ショート別方針を渡し、cache keyにも方針を含めた。
- 通常clip候補の基準長を設定範囲の中間から、最小長寄りの約150秒へ変更。
- raw candidate上限を各chunk先頭から順番に消費する偏りを修正し、開始時刻全体へ均等配分。
- 15秒の開始bucketごとに候補上限を設け、近接開始時刻の候補だけで上限を埋めないようにした。
- 同点候補は長い文字起こしより短いclipを優先。
- title fallbackは汎用挨拶segmentを避け、clip内の意味のあるsegmentを優先。

### 検証

- backend ruff: pass。
- backend pytest: `358 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend / worker rebuild: pass。
- `smoke_runtime.py --skip-video`: pass。backend / frontend / worker / redis running。
- `e2e_sample_video.py`: pass。
  - job: `job_27456e3e2f7c4f488172b5ef68bf7b07`
  - normal `0/0` / short `1/1`
  - short: `1080x1920`
  - render failures: `0`
  - sidecar risk: `0`
- browser:
  - 通常・ショート別preset / 自由入力欄: 表示pass。
  - ショートのみ選択時、通常側の方針欄を無効化: pass。
  - AI文脈判定のON/OFF表示と最大8候補の料金注意: pass。
- 既存32分素材 `job_2190d60e0acb4a74a87e9e916152e38a` をAPIなしで再選定:
  - distinct 15秒 start buckets: `26 -> 121`。
  - kept candidates: `130 -> 605`。
  - 指示: `配信を休んだ理由と復帰後の予定。ホロライブ運動会を欠席した経緯を優先。`
  - 1位選択: `263.16 - 412.58`、`149.42s`、rule score `95`。
  - 内容: 運動会を欠席した理由、倒れた経緯、回復状況。
  - OpenAI API call: `0`。

### 未解決・制限

- ローカル判定の自由入力は文字起こし語句とpreset特徴の照合。抽象的な意味・雰囲気の判定には明示的なOpenAI scoringが必要。
- 長尺実データは既存artifactによる候補生成・score・selection replayまで。Task77コードでの長尺再renderは未実施。
- branch `codex/task-77-guided-clip-selection`で実装・ローカル検証済み。親branchはTask76。main mergeは未実施。

## 2026-07-24 Task 78 subtitle review preview proxies

### 目的

- 長尺・大容量の元動画を字幕確認playerが直接読み込み続け、`字幕確認の動画準備中`から進まないように見える問題を解消する。
- 通常・ショートごとに、選択区間だけの軽量な確認用動画を準備して安定して再生できるようにする。
- 確認用動画の準備状況と読み込み遅延を画面上で明示する。

### 原因

- 字幕確認用job自体は完了していたが、確認playerが約65分・`1,470,830,350 bytes`の元動画を直接参照していた。
- 選択clipが元動画の後半にある場合、browserが多数のRange requestを行ってもmedia metadataを確定できず、`readyState=0`のまま停止したように見えていた。

### 変更

- 選択clipごとにH.264/AAC、960x540、30fps、faststartの軽量な確認用MP4を生成する処理を追加。
- `preparing_subtitle_review` statusと`字幕確認用動画を準備中 (n/total)` progressを追加。
- 字幕確認artifactへclip別`previewVideoUrl`を追加し、Range対応のpreview配信endpointを追加。
- 字幕確認画面はpreviewを優先し、既存artifactでは元動画へfallbackする。
- previewの時刻をclip相対時刻として扱い、字幕segmentの絶対時刻との変換を維持。
- clip切替時に`video.load()`を明示実行。
- 15秒以上読み込みが続く場合は、停止ではない旨と再読み込みbuttonを表示。
- preview生成失敗時はjobを曖昧な待機状態にせず、`subtitle_review_preview_failed`として明示する。

### 検証

- backend ruff: pass。
- backend pytest: `361 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend / worker rebuild: pass。
- `smoke_runtime.py --skip-video`: pass。backend / frontend / worker / redis running。
- `e2e_sample_video.py`: pass。
  - job: `job_ac4068ec075c4b48a791d33949c3191c`
  - normal `0/0` / short `1/1`
  - short: `1080x1920`
  - render failures: `0`
  - sidecar risk: `0`
- 問題が発生したjob `job_bc148159ccf54b0bbcd52a0e1552c98c`:
  - job処理時間: `9m44.874s`。statusは`awaiting_subtitle_review`。
  - short確認用動画: `3/3`生成。
  - duration: `40.233s` / `42.333s` / `42.500s`。
  - size: `6.223MiB` / `6.686MiB` / `6.827MiB`。
  - codec/resolution: H.264 + AAC / `960x540`。
  - preview endpointのRange response: `206`、3本ともpass。
  - browserで3本の切替、再生、一時停止、字幕表示連動: pass。
  - browser console error: `0`。

### 未解決・制限

- 問題jobは既存artifactへ確認用動画をbackfillして復旧した。Task78コードによる同じ65分素材の新規job再実行は行っていない。
- short確認用動画は時間範囲と字幕内容の確認用16:9 proxy。最終9:16 cropと字幕焼き込みは確認完了後の書き出しで行う。
- branch `codex/task-78-subtitle-review-preview-proxies`で実装・ローカル検証済み。親branchはTask77。main mergeは未実施。
