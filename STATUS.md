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

## 2026-07-24 Task 79 manual clip time ranges

### 目的

- 通常切り抜きとショートを、開始・終了の分秒を直接指定して生成できるようにする。
- 時間指定した種類では、おすすめ、AI採点、境界の自動調整を使用せず、指定範囲を固定する。
- 通常は自動・ショートは時間指定など、種類ごとの混在運用を可能にする。

### 変更

- Upload画面へ通常・ショート別の時間指定欄を追加し、指定本数と同じ数の入力行を表示。
- 1行でも入力するとその種類を時間指定モードに切り替え、全行の開始・終了を必須化。
- 分・秒入力、指定時間の長さ表示、一括クリア、本数変更時の行数追従を追加。
- 時間指定中の種類では選定preset、自由入力方針、推奨長さ設定を無効化。
- すべての生成対象が時間指定の場合は`useOpenAIScoring=false`へ自動補正。
- backendで本数、入力完了、開始・終了順、重複、元動画尺超過を検証。
- 時間指定を固定candidateとして生成し、rule/OpenAI scoringとboundary refinementから除外。
- 混在時は時間未指定の種類だけ既存の自動候補生成・選定を実行。
- 時間指定candidateへ`selection_reason=manual_time_range`と
  `boundary_refinement_reason=manual_time_range_locked`を記録。
- 既存のclip別字幕確認、確認用preview、字幕焼き込み、MP4/ZIP出力を再利用。

### 検証

- backend ruff: pass。
- backend pytest: `372 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend / worker rebuild: pass。
- `smoke_runtime.py --skip-video`: pass。
- 既存自動選定sample E2E: pass。
  - job: `job_db10f63b82ae42bba03701c9bf799202`
  - normal `0/0` / short `1/1`
  - short: `1080x1920`
  - render failures: `0`
  - sidecar risk: `0`
- 時間指定sample E2E: pass。
  - job: `job_3ae5eb340d4a40ef80931b5c57c3d1aa`
  - short指定: `0.00-6.00` / `7.00-14.00` / `15.00-24.00`
  - 字幕確認preview: `3/3`
  - 生成: short `3/3`、すべて`1080x1920`
  - 指定時刻と最終start/end: 完全一致
  - OpenAI scoring: 自動無効、summary生成なし
  - boundary refinement: `0/3`
  - render failures: `0`
  - sidecar risk: `0`
- browser:
  - 通常2行・ショート3行の初期表示: pass。
  - ショート3本入力で時間指定モードへ切替: pass。
  - 混在時にショート側だけ自動おすすめを無効化: pass。
  - ショートのみ時間指定時に全選定設定とAIを無効化: pass。
  - 本数`3 -> 4 -> 3`で入力行追従、既存値保持: pass。
  - desktop横overflow: なし。
  - console error: `0`。

### 未解決・制限

- 元動画の長さはupload前には確定しないため、指定終了時刻の尺超過はjob開始後のprobeで停止する。
- 時間指定は分秒の直接入力。動画timeline上の範囲選択は未実装。
- 指定範囲は固定するため、発話途中などを指定してもboundary refinementでは変更しない。
- branch `codex/task-79-manual-clip-time-ranges`で実装・ローカル検証済み。親branchはTask78。main mergeは未実施。

## 2026-07-24 Task 80 clip plan review stage

### 目的

- 字幕確認・最終レンダリングへ進む前に、通常切り抜きとショートの生成予定範囲を確認できるようにする。
- 予定が合わない場合、狙う場面の設定を変更し、保存済み解析結果から短時間で再選定できるようにする。
- `解析・選定 -> 予定確認 -> 字幕確認 -> 書き出し`の作業工程を画面上で明示する。

### 変更

- `clip_plan.json`とclip plan APIを追加し、予定clipの種類、開始・終了、長さ、タイトル、選定時の文字起こし抜粋、軽量preview URLを保持。
- `preparing_clip_review` / `awaiting_clip_review` / `reselecting_clips` statusを追加。
- Upload画面ではclip plan reviewを既定ONとし、字幕確認前に処理を一時停止。
- `/jobs/{jobId}/clips`へ予定確認画面を追加。
  - 左: 通常・ショートの生成予定一覧。
  - 中央: 選択範囲だけの軽量動画、元動画上の開始・終了、文字起こし抜粋。
  - 右: 通常・ショート別のpreset、具体的な方針、除外条件、品質優先、OpenAI scoring設定。
- 再選定では保存済みtranscript、候補、音声特徴、無音区間、scene/visual情報を再利用。
- OpenAI scoringがOFFの場合、再選定によるAPI料金は発生しないことを画面へ明記。
- 予定承認後に初めてclip別字幕確認artifactを作成し、字幕確認完了後に最終レンダリングを開始。
- 再選定失敗時は直前のplan、settings、selected/scored artifactへ復元。

### 検証

- backend ruff (`backend/app`): pass。
- backend pytest: `372 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend / worker rebuild: pass。
- `smoke_runtime.py --skip-video`: pass。
- clip plan実API E2E: pass。
  - job: `job_940f247a87444979a5ff7d4abf7547ce`
  - plan revision: `1 -> 2`
  - 再選定前後のtranscript hash: 完全一致
  - OpenAI scoring: OFF、API call `0`
  - 予定承認後に字幕確認を作成し、最終renderまで完走
  - normal `0/0` / short `1/1`
  - short: `1080x1920`
  - render failures: `0`
  - audit inspection: `0`
  - sidecar risk: `0`
- browser実操作: pass。
  - job: `job_6f8ab866e39f4f4b9f303655edb8fcb0`
  - 第1案を表示し、選択範囲だけの25秒previewを再生可能。
  - ショートpresetを`重要発言`へ変更し、自由入力を追加して第2案へ再選定。
  - 再選定中の二重操作防止と、完了後の操作復帰を確認。
  - `この切り抜き予定で字幕確認へ`から、選択clipだけの字幕確認画面へ遷移。
  - 字幕確認後の最終renderまで完走。
- `git diff --check`: pass。

### 未解決・制限

- 自動おすすめの初回選定には内容解析用transcriptが必要。ユーザー向け字幕確認artifactの作成と字幕焼き込みは予定承認後まで行わない。
- 再選定でOpenAI scoringをONにした場合だけAPI料金が発生する。
- 予定確認画面では選定方針を変更できる。開始・終了時刻の直接指定はUpload画面のTask79機能を使用する。
- `ruff check backend scripts`は今回未変更の既存2件で失敗:
  - `scripts/make_plotwith_solar_finished_variants.py:197` F841。
  - `scripts/smoke_runtime.py:173` F541。
- branch `codex/task-80-clip-plan-review`で実装・ローカル検証済み。親branchはTask79。main mergeは未実施。

## 2026-07-25 Task 81 subtitle style presets

### 目的

- 字幕スタイルを毎回設定し直さず、通常・ショート両方の設定を3枠まで保存して再利用できるようにする。

### 変更

- Upload画面の字幕スタイル内に、固定3枠の保存欄を追加。
- 各枠で名前変更、現在設定の保存・上書き、呼び出し、削除に対応。
- 1枠に通常・ショート両方のフォント、文字サイズ、縁取り、余白、位置、文字色、縁取り色を保存。
- 保存先をSQLiteの`app_preferences`へ変更。Docker・ランチャー停止後も保持。
- 字幕設定3枠のGET / PUT APIを追加し、slot数、文字サイズ、色などをbackendでも検証。
- 旧`localStorage`に保存値がありSQLite側が空の場合、初回表示時に自動移行。
- `localStorage`は移行元とローカルbackupに限定。動画本数、選定方針、AI設定、API keyなど字幕以外の設定は保存しない。
- 保存データをversion管理し、不正な保存値は設定へ適用しない。

### 検証

- backend ruff: pass。
- backend pytest: `374 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend rebuild: pass。
- browser実操作: pass。
  - 設定名を変更して保存。
  - フォント、文字色、表示位置を変更後、保存設定の呼び出しで復元。
  - ページ再読込後も保存名と設定を復元。
  - mobile幅`375px`で3枠が縦並びになり、横overflowなし。
- 永続化修正の実操作: pass。
  - 旧ブラウザ保存の`ホロライブ ショート`をSQLiteへ自動移行。
  - 2枠目を画面から保存後、backend / frontendを再起動。
  - 再起動後のAPIとUpload画面で2枠目を復元。
  - テスト枠削除後、元の保存枠だけを保持。
  - browser console error: `0`。

### 未解決・制限

- 保存設定は現在のAutoClipperインストール内で共有。別PC・別インストールとは同期しない。
- `storage/autoclipper.db`を削除・初期化すると保存枠も削除される。
- branch `codex/task-81-subtitle-style-presets`で実装・ローカル検証済み。親branchはTask80。main mergeは未実施。

## 2026-07-25 Task 82 clip plan boundary adjustment

### 目的

- 切り抜き予定画面で、選ばれた場面を保持したまま開始・終了時刻を調整できるようにする。
- 前後が不足する場合、再選定・再文字起こし・字幕生成を行わず、対象clipだけを短時間で確認し直せるようにする。

### 変更

- 予定確認画面へclip単位の範囲調整欄を追加。
  - 開始・終了を分秒で直接入力。
  - 前に／後に`+5秒`、`+15秒`、`+30秒`、`+1分`。
  - 自動選定時の範囲へ復元。
- 自動選定時の開始・終了と、手動調整状態を`clip_plan.json`へ保持。
- 境界更新APIとworker taskを追加。
  - HTTP request内ではFFmpegを実行しない。
  - 対象clip 1本の軽量previewだけを再生成。
  - `selected_clips.json`を更新し、字幕確認・最終renderへ調整後の範囲を引き渡す。
- 元動画の先頭・末尾、開始／終了の逆転、1秒未満をbackendで拒否。
- queue失敗・preview更新失敗時は直前のplan、selected clip、previewへ復元。
- 予定確認画面の再選定欄を狭いdesktop幅では縦1列にし、横overflowを解消。

### 検証

- backend ruff: pass。
- backend pytest: `372 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend / worker rebuild: pass。
- 境界更新統合テスト: pass。
  - 動画末尾超過を拒否。
  - queue失敗時に`awaiting_clip_review`へ復元。
  - preview再生成時のstart / durationを確認。
  - 調整後の境界が`selected_clips.json`と字幕確認clipへ一致。
- browser実操作: pass。
  - job: `job_6c50dc566fe4433b94fa74ae2599e5de`
  - `34:12.71 - 34:53.91`へ前後5秒を追加し、`34:07.71 - 34:58.91`へ更新。
  - 対象previewだけを更新し、手動調整表示を確認。
  - 自動選定範囲へ戻し、ミリ秒精度で完全復元。
  - 復元後preview duration: `41.200000`秒。
  - desktop幅`1265px`、mobile幅`375px`とも横overflowなし。
  - console error: `0`。

### 未解決・制限

- 範囲更新は1clipずつ行う。複数clipの一括延長は未実装。
- preview再生成時間はclip長とPC性能に依存する。
- 明示的な手動範囲は自動推奨の最大長を超えても許可する。最終auditではduration warningが残る場合がある。
- branch `codex/task-82-clip-plan-boundary-adjustment`で実装・ローカル検証済み。親branchはTask81。main mergeは未実施。

## 2026-07-26 Task 82 範囲調整欄の表示位置修正

### 目的

- 開始・終了の調整欄が動画の下に隠れ、予定確認画面を開いただけでは操作箇所を認識できない問題を解消する。

### 変更

- clip範囲調整欄をpreview動画の下から、選択clip見出しの直下へ移動。
- 状態表示の`選定範囲`を`自動選定のまま`へ変更し、操作ボタンとの誤認を防止。
- 手動変更後は`範囲を手動調整済み`と表示。
- 説明文へ、分秒の直接変更と前後追加ボタンを明記。

### 検証

- backend ruff: pass。
- backend pytest: `399 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker frontend rebuild: pass。
- browser表示確認: pass。
  - `1777x879`、scroll位置`0`で分秒入力、前後追加、復元、preview更新ボタンを表示。
  - mobile `390x844`で横overflowなし。
  - console error: `0`。

### 未解決・制限

- Task 82全体はDraft PR #62でreview・merge待ち。

## 2026-07-26 Task 82 入力範囲の文字起こし同期

### 目的

- 開始・終了を調整しても、動画下の文字起こしが選定時の短い抜粋に見える問題を解消する。
- preview保存前でも、入力中の範囲に含まれる文字起こしを確認できるようにする。

### 変更

- 保存済み`transcript_segments.json`から、指定範囲と重なるsegmentを返すread-only APIを追加。
- 分秒入力と前後追加ボタンの変更を250ms debounceでAPIへ反映。
- 360文字固定の「選定時の文字起こし抜粋」を廃止。
- 入力中の範囲、区間数、各segmentの元動画時刻、全文をスクロール表示。
- 再文字起こし、preview再生成、OpenAI API、DB更新は行わない。

### 検証

- backend ruff: pass。
- backend pytest: `374 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker backend / frontend rebuild: pass。
- API統合テスト: pass。
  - 指定範囲と重なるsegmentだけを返す。
  - 開始・終了の逆転を`422`で拒否。
- browser実操作: pass。
  - job: `job_627620b5cdfb44cbaa693cf8a4a78dab`
  - 保存済み範囲`14:52.4 - 18:09.0`で`181区間`を表示。
  - `前に+5秒`後、入力範囲`14:47.4 - 18:09.0`と`186区間`へ保存前に自動更新。
  - 追加された先頭segment`14:46.9 - 14:48.0`を表示。
  - 未保存の確認操作はページ再読込で破棄。

### 未解決・制限

- 表示内容は既存の文字起こし結果。誤字修正は次の字幕確認工程で行う。
- Task 82全体はDraft PR #62でreview・merge待ち。

## 2026-07-26 Task 82 予定確認画面の文字起こし配置

### 目的

- 開始・終了の調整欄と、変更範囲の文字起こしを同時に確認できる配置へ変更する。

### 変更

- 文字起こし欄を動画下からdesktop右列へ移動。
- 右列をviewport内に固定し、文字起こし一覧だけを独立スクロール可能に変更。
- 右列にあった再選定、狙う場面設定、字幕確認への遷移を動画下へ移動。
- 動画下の再選定欄は通常・ショート設定を2列表示できる幅へ変更。
- 狭い画面では、clip一覧、境界調整・動画、文字起こし、再選定の順に縦並びになる。

### 検証

- frontend lint / typecheck / build: pass。
- Docker backend / frontend rebuild: pass。
- browser実操作: pass。
  - viewport: `1280x720`
  - 開始・終了欄と右の文字起こし`181区間`を同一viewportへ表示。
  - `前に+5秒`後、右欄が`14:47.4 - 18:09.0`、`186区間`へ自動更新。
  - 右欄の表示高`406px`、内容高`12771px`、`overflow-y: auto`を確認。
  - 横overflow: `0`。
  - 動画下の再選定欄までスクロール後も、右の文字起こしを固定表示。
  - 未保存の確認操作はページ再読込で破棄。

### 未解決・制限

- 文字起こし欄は閲覧用。本文修正は次の字幕確認工程で行う。
- Task 82全体はDraft PR #62でreview・merge待ち。

## 2026-07-26 Task 83 clip別タイトル・冒頭フック編集

### 目的

- 字幕確認工程で、生成予定clipごとの表示タイトルを手動設定できるようにする。
- ショートでは、冒頭数秒だけ表示するフックをタイトルと分けて設定できるようにする。

### 変更

- 通常・ショート共通で、clip別の表示タイトル編集欄を追加。
- ショートへ冒頭フックと表示秒数`1〜8秒`を追加。
- 動画上に簡易プレビューを表示し、冒頭フック終了後にタイトルへ切り替える。
- 保存APIを追加し、タイトル・フック変更時は対象clipを未確認へ戻す。
- 最終render前にreview内容を`selected_clips.json`へ反映。
- ショートASSでは、フックとタイトルを時間で分離して重複表示を防止。
- `low_cost + auto`でも手入力タイトルは明示指定として焼き込む。
  - `shortOverlayTitleMode=never`は引き続き優先する。
- short metadataへ`hook_text`、`hook_duration_seconds`、`hook_rendered`を追加。
- review summaryへタイトル編集clipとフック設定clipのIDを追加。

### 検証

- backend ruff: pass。
- backend pytest: `380 passed, 1 skipped`。
- Task 83関連backend tests: `78 passed`。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend / worker rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- backend `/health`: `200 / ok`。
- frontend字幕確認route: `200`。
- browser表示確認: pass。
  - 通常clipでは表示タイトルだけを表示。
  - ショートでは表示タイトル、冒頭フック、表示秒数、動画上の簡易プレビューを表示。
  - 字幕一覧とタイトル・フック欄を右列で同時操作可能。

### 未解決・制限

- 冒頭フックはショート専用。通常clipには設定しない。
- 動画上の表示は内容と切替時間を確認する簡易プレビュー。実際の字体、色、縁取り、位置はrender時の字幕スタイル設定を使用する。
- タイトル・フックの文案自動生成は未実装。ユーザーがclip内容を確認して入力する。
- Task 83 branchはTask 82 branchを親にしている。Task 82 merge後にmainへ統合する。

## 2026-07-26 Task 84 完成jobの再編集・再レンダリング

### 目的

- 完成済みjobを再アップロードせずに開き直し、タイトル・フック・字幕を微調整して再レンダリングできるようにする。

### 変更

- Results画面へ`タイトル・フック・字幕を再編集`を追加。
- 完成済みsubtitle reviewを編集状態へ戻すAPIを追加。
  - 保存済みの元動画、選定範囲、文字起こし、既存修正を再利用。
  - 全clipを未確認へ戻し、再確認後に再レンダリング。
  - ASR、候補選定、OpenAI処理は再実行しない。
- review artifactへ`renderRevision`と`reopenedAt`を追加。
- 再レンダリングは短い一時パスへ出力し、全clip成功後に既存成果物へ反映。
- 再レンダリング時のExportItem重複を防止。
- 新ZIPを一時ファイルへ作成し、完成後に既存ZIPと置換。
- 再レンダリング失敗時は旧MP4・ZIP・download情報を保持し、字幕確認工程へ戻す。
- 成功時は旧auditを無効化し、変更前の警告を新成果物へ表示しない。

### 検証

- backend ruff: pass。
- backend pytest: `381 passed, 1 skipped`。
- 再編集統合テスト: pass。
  - 完成→再編集→タイトル/フック変更→再完成。
  - normal / shortのExportItem件数が重複しない。
  - 変更タイトルがresultsへ反映。
  - 再レンダリング失敗時に旧成果物を保持し、`awaiting_subtitle_review`へ復帰。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend / worker rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- backend `/health`: `200 / ok`。
- Results画面表示確認: pass。
  - desktop `1440x1000`で再編集説明と操作ボタンを表示。
  - mobile `390x844`で横overflow `0`。
- Docker実MP4再編集E2E: pass。
  - job: `job_701530dfaf214022a84faeb3333877a8`
  - 30秒sample、手動範囲`0:00 - 0:22`、short 1本、OpenAI無効。
  - 初回render完了後に再編集し、タイトル・フックを変更して再render完走。
  - 再アップロード・再文字起こしなし、short ExportItem重複なし、変更タイトル反映。

### 未解決・制限

- 再編集対象はタイトル、ショートの冒頭フック、字幕本文。切り抜き範囲の再選定は今回の対象外。
- 元動画またはreview artifactを削除した古いjobは再編集不可。
- 再レンダリング成功後は既存auditを無効化する。必要な場合は新成果物へauditを再実行する。
- Task 84 branchはTask 83 branchを親にしている。Task 83 merge後にmainへ統合する。

## 2026-07-27 Task 85 完成MP4の再アップロード再編集

### 目的

- Upload画面からAutoClipperの完成MP4を再投入し、対応する元jobのタイトル・フック・字幕編集へ戻れるようにする。
- 焼き込み済みMP4へ重ね書きせず、元動画と保存済み編集データを使って再レンダリングする。

### 変更

- Upload画面へ`新しい動画を作成 / 完成動画を再編集`の切替を追加。
- 完成MP4のSHA-256と保存済みExportItemを照合するAPIを追加。
  - 再投入MP4は識別にだけ使用し、`storage/uploads`へ複製しない。
  - ファイル名を変更したMP4も内容が同一なら照合可能。
- 一致した元jobを`awaiting_subtitle_review`へ戻し、該当clipを選択して字幕確認画面を開く。
- 二重送信時は同じ編集状態を返し、`renderRevision`を重複加算しない。
- 元job、元動画、選定結果、文字起こしが不足する場合は再編集を停止して理由を表示。
- 完成MP4と一致しないファイル、MP4以外、上限超過を明示的に拒否。

### 検証

- backend ruff: pass。
- backend pytest: `383 passed, 1 skipped`。
- 再アップロードAPI tests: pass。
  - renamed MP4から元jobを照合。
  - 再投入ファイルを保存しない。
  - job status、review state、確認状態、revisionを確認。
  - 二重送信、未知MP4、MP4以外を確認。
- frontend lint / typecheck / build: pass。
- Docker GPU composeでbackend / frontend rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- browser実操作: pass。
  - Upload画面で`完成動画を再編集`へ切替。
  - 完成MP4を選択し、元jobと照合。
  - 該当ショートを選択した字幕確認画面へ直接遷移。
  - タイトル、冒頭フック、表示秒数、字幕を復元。
  - 確認済み→再レンダリング→completed。
  - console error: `0`。
  - mobile `390x844`: 横overflow `0`。
- Docker実MP4再アップロード再編集E2E: pass。
  - job: `job_701530dfaf214022a84faeb3333877a8`
  - short `1/1`、再レンダリング完走。
  - sidecar risk: `0`。
  - Results: short重複なし、再編集可能状態を維持。

### 未解決・制限

- 同じAutoClipper環境に元jobと元動画が残る場合だけ再編集可能。
- MP4を再圧縮・加工するとSHA-256が変わるため照合不可。
- 完成MP4単体から焼き込み済み文字を除去する機能ではない。
- 別PCへの持ち出しやjob削除後の復元には、将来の編集用プロジェクトZIPが必要。
- 保存済みexportが非常に多い環境では初回照合に時間がかかる可能性がある。
- Task 85 branchはTask 84 branchを親にしている。Task 84 merge後にmainへ統合する。

## 2026-07-28 Task 86 clip別タイトル・フック・字幕スタイル

### 目的

- タイトル、冒頭フック、字幕の書体・サイズ・色・縁取り・位置を、clipごとに個別設定できるようにする。
- ショートと通常切り抜きで別の字幕スタイルを保存し、再アップロード再編集でも復元する。

### 変更

- 字幕確認画面へclip別の文字スタイル編集を追加。
  - ショート: タイトル / フック / 字幕を個別設定。
  - 通常切り抜き: 字幕を個別設定。
  - 書体プリセット: 標準ゴシック / 太字ゴシック / 極太ゴシック / 明朝 / 等幅ゴシック。
  - 文字サイズ、文字色、縁取り色、縁の太さ、横位置、縦位置を設定。
- 9:16 / 16:9の配置プレビューへ選択中のスタイルを反映。
- subtitle review、candidate、render metadataへclip別スタイルを保存。
- ASSのTitle / Hook / Subtitleを別styleとして生成し、個別の位置を`\an5\pos(x,y)`で焼き込み。
- スタイル未指定時は既存のjob設定と描画位置を維持。
- auditの日本語対応フォント判定へ新プリセット4書体を追加。

### 検証

- backend ruff: pass。
- backend pytest: `387 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker GPU compose rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- browser実操作: pass。
  - 5書体とTitle / Hook / Subtitleの個別タブを確認。
  - UI保存後のAPI永続化と、再読込後の設定復元を確認。
  - mobile `390x844`: 横overflow `0`、console error `0`。
- Docker実レンダリング: pass。
  - job: `job_701530dfaf214022a84faeb3333877a8`
  - Title: 極太ゴシック、黄色、`46% / 14%`。
  - Hook: 明朝、ピンク、`52% / 26%`。
  - Subtitle: 等幅ゴシック、水色、`50% / 82%`。
  - ASSの3style、色、サイズ、位置tagを確認。
  - short: `1080x1920`、render failure `0`、sidecar risk `0`。
  - auditの新書体誤警告を修正し、残警告は素材由来の`likely_abrupt_ending`のみ。

### 未解決・制限

- 通常切り抜きはタイトルを映像へ焼き込まないため、個別設定対象は字幕のみ。
- 書体は同梱済み・Dockerへmount済みのフォントだけを選択可能。任意フォントファイルの追加UIは対象外。
- `ruff check backend scripts`は未変更の`scripts/smoke_runtime.py:173`にある既知のF541で失敗する。今回変更したbackendとaudit対象のruffはpass。
- Task 86 branchはTask 85 branchを親にしている。Task 85 merge後にmainへ統合する。

## 2026-07-28 Task 86 推奨字幕フォント分類

### 目的

- 通常字幕向けの太字ゴシックと、ツッコミ・オチ向けの短い強調書体を設定画面で分ける。
- ブラウザプレビューとFFmpeg/libassの焼き込みで同じフォントを使う。

### 変更

- 通常字幕向けへ以下を追加。
  - Noto Sans JP Black
  - 源ノ角ゴシック Heavy
  - M PLUS 1 ExtraBold
  - M PLUS Rounded 1c ExtraBold
- 特殊字幕向けへ以下を追加。
  - 851チカラヅヨク
  - Dela Gothic One
  - コーポレート・ロゴ Bold
- Upload画面とclip別文字スタイルの書体選択を以下の3グループへ分類。
  - 通常字幕向け
  - 特殊字幕向け（短い強調）
  - 補助書体
- 7書体を`frontend/public/fonts`へ同梱し、出典・ライセンス・SHA-256を記録。
- ブラウザ用`@font-face`、ASSプリセット、auditの日本語フォント判定を追加。
- backend / workerへフォントファイルだけをread-onlyで個別mount。

### 検証

- backend ruff: pass。
- backend pytest: `388 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- Upload画面とclip別文字スタイル画面:
  - 3グループと7書体を確認。
  - 全書体のプレビュー`font-family`反映を確認。
  - console error: `0`。
- ブラウザ配信:
  - 7フォントすべてHTTP `200`。
- FFmpeg/libass burn-in smoke:
  - 7書体すべて指定したフォントファイルへ解決。
  - 代替フォント、missing glyph、render error: `0`。

### 未解決・制限

- ラノベPOP V2は公式BOOTHの無料ダウンロードにpixiv/BOOTHログインが必要。
- 未取得の第三者配布ファイルは使用せず、公式ZIP取得・ライセンス確認・焼き込み検証後に追加する。
- 今回は合成ASSによる実焼き込み確認まで。長尺実動画E2Eは再実行していない。

## 2026-07-28 Task 86 文字位置プリセット

### 目的

- 1080x1920の文字位置を数値だけでなく、用途と画面上の場所から選べるようにする。
- ショートと通常切り抜きで別の位置を保持し、必要な場合だけ1%単位で微調整する。

### 変更

- Upload画面とclip別文字スタイル画面へ以下を追加。
  - 縦位置7段階。
  - 横位置5段階。
  - タイトル / フック / 会話字幕 / 強調キーワード / ツッコミ用の用途プリセット。
  - 実出力のX/Yピクセル表示とガイド線。
  - 1%単位の調整を折りたたみの「位置を微調整」へ分離。
- ショートの初期位置を以下へ設定。
  - タイトル: Y=240。
  - フック: Y=360。
  - 会話字幕: Y=1320。
  - ツッコミ: Y=1100。
- 通常切り抜きは16:9用の7段階位置を独立保持。
- JobSettingsと字幕設定プリセットへshort / normal別のX/Y位置を保存。
- ASS生成時は指定座標を`\an5\pos(x,y)`へ変換。
- 旧jobにX/Y設定がない場合は、従来のalignment / margin設定を維持・換算する。

### 検証

- backend ruff: pass。
- backend pytest: `390 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- ASS生成テスト:
  - short会話字幕: `432,1320`。
  - shortタイトル: `540,240`。
  - shortフック: `540,360`。
  - clip別設定がjob全体設定を上書きすることを確認。
- Docker compose: backend / frontend / worker / redis起動、backend healthy。
- `scripts/smoke_runtime.py --skip-video`: pass。
- browser実操作:
  - Upload画面で縦7段階・横5段階・用途プリセットを確認。
  - short / normal切替後も位置設定が独立。
  - 字幕確認画面でもclip別位置設定を確認。
  - mobile `390x844`: 横overflowなし。
  - console error: `0`。

### 未解決・制限

- 新しい位置プリセットを指定した実動画の再レンダリングは未実施。ASS座標生成と既存runtime経路までは確認済み。
- 任意座標の直接数値入力は追加せず、プリセットと1%スライダーで調整する。

## 2026-07-28 Task 87 ショート冒頭への見せ場複製

### 目的

- ショート内の見せ場を0.5〜3秒だけ切り出し、同じショートの先頭へ複製する。
- 字幕生成前の切り抜き予定画面で設定し、軽量プレビューと最終MP4を同じ構成にする。

### 変更

- 切り抜き予定画面のショートへ「冒頭へ見せ場を複製」を追加。
  - 再生中の位置から1秒 / 2秒 / 3秒を設定。
  - 元動画上の開始・終了を分秒で直接入力。
  - 保存済み設定の解除。
  - 完成予定時間と`shortMaxDuration`超過を事前確認。
- hook scene範囲をcandidate、clip plan、subtitle reviewへ保存。
- 選択したショートの軽量プレビューだけを再生成するAPIとworker処理を追加。
- 軽量プレビューと最終ショートを以下の順序でFFmpeg連結。
  - `[指定した見せ場] -> [元のショート本編]`
  - 見せ場の元位置は本編側にも残す。
- 見せ場区間の字幕を冒頭用に複製し、本編字幕を見せ場秒数ぶん後ろへ移動。
- 字幕確認画面の再生位置、字幕クリック、完成時間を連結後の時間軸へ対応。
- 完成MP4の再アップロード後も、対象ショートのフック映像を追加・変更・解除可能。
  - 再編集画面へ同じ0.5〜3秒の範囲エディタを追加。
  - 対象ショートの軽量プレビューだけをworkerで再生成。
  - 保存済みタイトル、フック文字、文字スタイル、字幕、他clipは保持。
  - フック映像変更後は対象clipだけ未確認へ戻す。
- 最終metadataへhook scene範囲、複製有無、本編時間、完成時間を記録。

### 検証

- backend ruff: pass。
- 再アップロード・hook scene関連の対象tests: `52 passed`。
- backend pytest: `395 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker compose rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- Docker内FFmpeg実レンダリング: pass。
  - 5秒の合成素材へ2秒の見せ場を追加。
  - 完成時間: `7.000000`秒。
  - video: `1080x1920`。
  - audio stream: あり。
  - ASS字幕焼き込みと、冒頭字幕複製・本編字幕移動を確認。
- browser実表示: pass。
  - 既存のawaiting clip review jobでショート専用UIを確認。
  - 入力欄、1秒 / 2秒 / 3秒、完成予定時間、保存ボタンを確認。
  - 完成MP4を再アップロードし、対象ショートの再編集画面へ直接遷移。
  - 再編集画面から1秒のフック映像を追加後、2秒へ変更。
  - `設定済み`、複製場面`0:00.0 - 0:02.0`、完成予定`0:24.0`を確認。
  - job: `job_701530dfaf214022a84faeb3333877a8`。
  - review artifact: `hookSceneStart=0`、`hookSceneEnd=2`、既存タイトル保持、対象clip未確認化。
  - 更新後の軽量preview: `24.000000`秒。

### 未解決・制限

- 対象はショートのみ。通常切り抜きには追加しない。
- 見せ場は同じショート範囲内から0.5〜3秒を選ぶ。
- 元の見せ場を本編から削除するジャンプ編集、別動画挿入、トランジションは対象外。
- 実案件動画での最終的な見た目・テンポ評価は未実施。

## 2026-07-28 Task 88 字幕スタイル設定の横長レイアウト化

### 目的

- Upload画面の字幕スタイル設定が縦に長く、プレビューと設定を同時に確認しにくい状態を改善する。

### 変更

- デスクトップとタブレット幅では、字幕プレビューを左、基本設定・色・位置を右へ配置。
- 左側プレビューを設定スクロール中も確認できるsticky表示へ変更。
- プレビュー下の表示情報を4項目のコンパクト表示へ整理。
- 保存した字幕設定3枠を折りたたみへ変更。
  - 閉じた状態でも保存済み件数を表示。
  - 開くと従来どおり呼び出し・上書き・削除が可能。
- 字幕スタイル見出しとshort / normal切替を同じ行へ配置。
- モバイル幅では従来どおり縦配置へ戻す。

### 検証

- frontend build / typecheck / lint: pass。
- Docker compose rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- browser実表示:
  - `1280x720`: 字幕設定section高 約`633px`。
  - `800x800`: 字幕設定section高 約`721px`、プレビューと主要設定を同時表示。
  - `390x844`: 横overflow `0`、縦配置へ切替。
  - console error / warning: `0`。

### 未解決・制限

- モバイルでは操作幅を確保するため縦配置を維持する。

## 2026-07-28 Task 89 破損動画の事前検出とエラー表示改善

### 目的

- 破損または不完全なMP4で、FFmpegコマンドだけが表示される`audio_extraction_failed`を改善する。
- 復元不能な入力を重い文字起こし処理へ進めず、再ダウンロードが必要だと明確に表示する。

### 原因

- 対象ファイル: `vid_c408efea441b4fb69d90f5086fb08c11.mp4`。
- ffprobe実測:
  - 映像stream: `1301.466667`秒（`21:41`）。
  - 音声stream / container: `3832.075442`秒（`1:03:52`）。
- AACは約`13:22`以降に破損packetがあり、FFmpegが誤ったchannel構成を検出して停止した。
- 破損packetを除外しても映像・音声を約`21:40`までしか救済できず、元の約64分は復元不能。

### 変更

- ffprobe結果へ映像stream、音声stream、containerそれぞれの長さを保存。
- 映像・音声の差が`30秒`超かつ短い側の`10%`超なら、音声抽出前に
  `media_stream_duration_mismatch`で停止。
- エラーへ映像・音声の実時間と再ダウンロード手順を日本語で表示。
- FFmpeg音声decode失敗時も、生のコマンドやローカルパスではなく、
  破損・再変換・再アップロードの案内を表示。
- 音声抽出に失敗した部分WAVを削除。
- Job画面で対象error codeを日本語見出しへ変換。

### 検証

- backend ruff: pass。
- backend pytest: `397 passed, 1 skipped`。
- frontend build / typecheck / lint: pass。
- Docker compose rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- 対象ファイルをDocker内で再判定: pass。
  - `media_stream_duration_mismatch`。
  - 表示: `映像 21:41 / 音声 1:03:52`。
- 同じuploadから再試行Jobを作成: pass。
  - job: `job_3c5236e840674418be57f4b152ef000c`。
  - 音声抽出へ進まず、再ダウンロード案内付きで停止。

### 未解決・制限

- 欠落した映像・破損したAACはAutoClipper内では復元しない。
- 対象動画を最後まで処理するには、元アーカイブを正常なMP4として再ダウンロードし直す必要がある。

## 2026-07-28 Task 90 文字起こし品質検出とGPU自動再試行

### 目的

- 正常な動画でWhisperが同じ日本語を反復生成した場合、候補生成へ進む前に検出する。
- GPU推奨profileの`turbo + ja`だけを対象に、APIを使わず`small + ja`で1回再試行する。

### 原因

- job `job_b22bc8ea75d84308a28a286172b964e2`はCPUの`base + auto`で実行され、
  平均confidence `0.240124`の多言語誤認識となった。
- GPU profileへ戻したjob `job_390164f55f9d4f169545c98522b69b40`では、
  `turbo + ja`が21 segment中の大半を`ご視聴ありがとうございました`として反復生成した。
- 現行gateは英語の低情報語反復と平均confidenceだけを確認し、
  日本語の同一segment反復を検出していなかった。
- 同じ音声の120秒sampleは`small + ja + cuda + float16`で正常な日本語会話を生成した。

### 変更

- 正規化した同一segmentが`5件以上`かつ全体の`60%以上`を占める場合、
  `repeated_segment_text`として利用不能判定する。
- `turbo + ja`がCUDA上で品質gateに失敗した場合だけ、
  `small + ja`で1回再文字起こしする。
- 失敗したprimary transcriptを`primary_raw_transcript_segments.json`へ保持する。
- summaryへprimary / quality fallbackそれぞれのruntime・品質診断、実使用model、
  `quality_fallback_used`と理由を記録する。
- CPU、注入transcriber、`small`以外の任意modelでは自動再試行しない。
- Job画面へ文字起こし品質エラーの日本語見出しを追加する。

### 検証

- 対象pipeline tests: `18 passed`。
- backend ruff: pass。
- backend pytest: `399 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker GPU Compose rebuild: image build / 4サービス起動pass。
  - 最初の短いtimeoutで一時的にcontainer名競合が出たが、
    Compose再作成は完了し4サービスhealthy。
- `scripts/smoke_runtime.py --skip-video`: pass。
- GPU preflight: pass。
  - GPU: `NVIDIA GeForce RTX 5070 Ti`。
  - `actual_device=cuda`、`actual_compute_type=float16`、fallback `false`。
- 61分実動画の再実行: pass。
  - job: `job_d62794128f7e4075a8cd74324cd8752e`。
  - primary `turbo + ja`を`repeated_segment_text`でreject。
  - fallback `small + ja + cuda + float16`を採用。
  - segment: `2968`、平均confidence: `0.736416`。
  - total transcription: `249.431`秒。
  - fallback後の品質reason: `0`。
  - 選定: normal `0`、short `2`。`awaiting_clip_review`まで完走。
  - OpenAI字幕校正・AI採点: OFF。API料金なし。

### 未解決・制限

- 自動再試行はGPU上の`turbo + ja`に限定する。
- `small + ja`でも品質gateを満たさない動画は`transcript_unusable`で停止する。
- `turbo`が正常な動画では従来どおり再試行せず、その結果を使用する。

## 2026-07-29 Task 91 再編集画面の文字スタイル操作改善

### 目的

- 完成MP4から開いた再編集画面でも、タイトル・フック・字幕の文字サイズなどを
  clipごとに再設定できるようにする。

### 原因

- 文字サイズ、書体、縁取りの入力自体は実装済みだった。
- 再編集画面の右ペインが固定高かつスクロール不可で、入力欄が大きな配置プレビューの
  下へ隠れていた。

### 変更

- 右ペイン全体を縦スクロール可能にした。
- タイトル・フック・字幕の切替直後に、書体・文字サイズ・縁の太さを表示するよう
  配置を変更した。
- 既定値を表示中でも変更可能であることを`既定値から編集`と明示した。
- 個別設定中は、上部から`既定値に戻す`を実行できるようにした。

### 検証

- frontend lint / typecheck / build: pass。
- Docker frontend rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- 完成済みjobの再編集画面をEdge headlessで確認: pass。
  - job: `job_83df9af6a79f4741a23b926af57f3262`。
  - タイトル`88 -> 96`で個別設定へ切替。
  - フック`88`、字幕`76`を個別タブで表示。
  - 変更後に保存ボタンが有効化。
  - ユーザー画像と同じ`1600x708`でも、タイトル文字サイズ入力を初期表示内で確認。
  - 右ペインは`overflow-y:auto`で全設定・字幕一覧まで移動可能。
- 実jobの値は保存せず、再読込で元へ戻した。

### 未解決・制限

- 実レンダリング結果は変更していない。文字スタイルの保存・ASS反映経路は既存実装を
  使用する。

## 2026-07-29 Task 92 小型文字スタイルプレビューの縮尺修正

### 目的

- 再編集画面右側の配置プレビューでも、タイトル・フック・字幕の文字サイズ変更を
  小さい値まで正確に反映する。

### 原因

- 小型プレビューが`cqh`を使用していたが、高さのcontainer queryを定義していなかった。
- `Math.max(3)`と`clamp(11px, ...)`の二重下限により、文字サイズを下げても一定サイズ未満に
  縮小されなかった。

### 変更

- 小型プレビューを`container-type: inline-size`の横幅基準へ変更。
- ショート`1080px`、通常`1920px`の出力横幅に対する比率から、文字サイズと縁取り幅を
  計算するよう変更。
- 不正確な`cqh`基準と`11px`固定下限を削除。

### 検証

- frontend lint / typecheck / build: pass。
- Docker frontend rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- 完成済みjobの再編集画面をEdge headlessで確認: pass。
  - job: `job_83df9af6a79f4741a23b926af57f3262`。
  - 小型プレビュー幅: `230px`。
  - タイトル文字サイズ`20 / 88 / 220`:
    `4.22px / 18.58px / 46.44px`へ連続変化。
  - タイトル・フック・字幕は、すべて文字サイズ`20`で`4.22px`まで縮小。
- 実jobの値は保存せず、再読込で元へ戻した。

### 未解決・制限

- 今回は右側の小型配置プレビューだけを修正した。
- メイン動画プレビューと実レンダリングの文字サイズ計算は変更していない。

## 2026-07-29 Task 93 字幕確認ヘッダーの省スペース化

### 目的

- `clip別 字幕確認`画面上部の工程表示を見出し横へ移し、編集領域までの縦方向の
  占有を減らす。

### 変更

- `1. 自動処理`、`2. clip別 字幕確認`、`3. 字幕焼き込み・書き出し`を、
  見出しと`処理状況へ戻る`ボタンと同じヘッダー内へ移動。
- デスクトップでは3工程を見出し横へ1列表示。
- 横幅が足りない画面では、工程表示だけを見出し下へ折り返す。
- 工程名、状態判定、再編集通知の内容は変更していない。

### 検証

- frontend lint / typecheck / build: pass。
- Docker frontend rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- 完成済みjobの再編集画面をEdge headlessで確認: pass。
  - job: `job_83df9af6a79f4741a23b926af57f3262`。
  - `1600x900`: 3工程を見出し横へ表示、ページ横overflowなし。
  - `390x844`: 工程表示を見出し下へ折り返し、ページ横overflowなし。

### 未解決・制限

- 紫・緑の再編集通知は重要情報のため、今回は移動していない。
- 右ペイン内の文字スタイル配置再設計は別タスクとする。

## 2026-07-29 Task 95 字幕確認画面の全幅領域削減

### 目的

- 字幕確認画面を、動画・配置プレビュー・字幕・各設定を同時に見られる
  1画面完結の作業環境へ再構成する。
- ヘッダーと全幅通知の占有を減らし、デスクトップではページ全体を
  スクロールせずに主要操作へ到達できるようにする。

### 変更

- 再編集時の紫・緑の全幅通知を削除。
- 再編集状態を左列見出しの`再編集`、`MP4照合済み`バッジへ圧縮。
- 最下部の全幅レンダリング確定欄を削除。
- 確認数、修正数、`字幕を確定してレンダリング`を左列下部へ移動。
- 中央動画上の選択clip情報欄を削除。
- 本編時間と元動画範囲を左の選択clipカードへ移動。
- `先頭から再生`を動画コントロール内の`先頭`ボタンへ移動。
- ページ外枠の`1600px`上限を削除し、デスクトップでは画面横幅を全て使用。
- 大型の工程表示と説明文を削除し、ヘッダーを
  `clip別 字幕確認 / 確認数・修正数 / 状態 / 処理状況へ戻る`の1行、
  高さ`45px`へ圧縮。
- `1536px`以上では上段を
  `clip一覧 / メイン動画 / 文字配置プレビュー / 字幕確認`の4列へ変更。
- 上段4枠の高さを揃え、字幕一覧は枠内だけをスクロールする。
- 字幕の確認ボタンは字幕列下部へ固定し、動画と同時に見える状態を維持。
- 文字配置プレビューを独立部品化し、下段の`タイトル / フック / 字幕`
  選択と連動。
- 下段を
  `タイトル・フック / 書体・サイズ / 位置 / 色`の4設定パネルへ分割。
- 下段は画面の残り高さだけを使用し、内容が多いパネルだけ内部スクロール。
- フック映像設定は`フック映像設定`内へ折りたたみ、通常設定の視認性を優先。
- フック映像設定の入力・現在位置を、メイン動画と字幕に合わせて
  `clip先頭=0:00`基準へ統一。
- フック映像設定には元動画時刻も併記し、保存時だけ従来の元動画絶対時刻へ変換。
- 元のショートが設定上限をすでに超えている場合は、完成予定尺を警告表示したうえで
  0.5〜3秒のフック映像を追加可能にした。
- 元のショートが上限内の場合は、フック追加による新たな上限超過を従来どおり拒否する。
- 字幕の時刻ボタンを`から再生`から`へ移動`へ変更し、クリック時は
  字幕開始位置へ移動して一時停止する。
- メイン動画の微調整用に`-1秒 / +1秒`を追加し、
  既存の5秒操作も`-5秒 / +5秒`へ省スペース化。
- `1536px`未満では従来どおり縦積みし、モバイルの横overflowを発生させない。
- 保存、確認、レンダリングの公開API contractは変更していない。

### 検証

- backend `ruff check .`: pass。
- backend `pytest`: `400 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker Compose rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- 完成済みjobの再編集画面を実ブラウザで確認: pass。
  - job: `job_83df9af6a79f4741a23b926af57f3262`。
  - `1600x900`: ヘッダー`45px`、上段4枠`558px`で下端一致。
  - `1600x900`: 左`210px`、動画列`757px`、プレビュー`240px`、
    字幕列`352px`。
  - `1920x900`: 左`250px`、動画列`903px`、プレビュー`288px`、
    字幕列`422px`。
  - `1600x900`: 下段4設定パネル`269px`、ページ
    `scrollHeight=clientHeight=900px`。
  - 字幕一覧: 表示高`385px`、内容高`6660px`、枠内スクロール。
  - `タイトル・フック`と`位置`は内容超過時のみ内部スクロール。
  - `ショート 1 -> ショート 2`切替で動画長と字幕見出しが連動。
  - 文字設定の対象を`字幕`へ切り替えると、配置プレビューも同期。
  - ショート2のメイン再生`1:34.7`に対し、フック映像設定も
    `clip内 1:34.7 / 元動画 9:08.6`を表示。
  - `ここから2秒`で
    `clip内 1:34.7-1:36.7 / 元動画 9:08.6-9:10.6`へ連動。
  - フック映像の設定値は画面上ではclip内時刻、保存値は従来の元動画時刻。
  - 上限`1:15.0`に対して元のclipが`1:39.7`あるショート2で、
    `clip内 1:22.02-1:25.02 / 元動画 8:55.9-8:58.9 / 完成予定 1:42.7`
    を表示し、警告付きで`この場面を冒頭へ追加`が有効になることを確認。
  - 画面確認では保存操作を行わず、既存job artifactは未変更。
  - 再生中に字幕`0:15.2へ移動`を押すと、動画は`15.22秒`で一時停止。
  - `+1秒`で`16.22秒`、`-1秒`で`15.22秒`へ移動し、一時停止を維持。
  - console error: なし。
  - `390x844`: ページ横overflowなし。

### 未解決・制限

- エラー通知と、字幕確定後・書き出し中の状態通知は必要なため全幅表示を維持する。
- `1536px`未満では各枠を縦積みするため、ページ縦スクロールを使用する。
- フック映像の詳細設定を開いた場合は、タイトル・フックパネル内をスクロールする。

## 2026-08-02 Task 96 YouTube人気区間sidecar連携

### 目的

- Downloaderが出力する`<動画名>.heatmap.json`を任意入力として受け取り、
  同一動画との照合後に自動候補の補助スコアへ使用する。
- sidecarがない、またはworker実行時の再検証に失敗した場合も、既存編集処理を継続する。

### 変更

- 新規アップロード画面と`POST /api/videos/upload`へ任意の`heatmap`ファイルを追加。
- JSONは`5 MiB`以下、UTF-8、`schema_version == 1`、厳密な型、UTC取得日時、
  区間順序、有限値、`value`の`0..1`、`heatmap_available`との整合を検証。
- 元動画のファイル名、サイズ、SHA-256、動画時間を照合。
  動画時間の許容差は`max(2秒, 実時間の0.1%)`。
- 検証済みsidecarを`<保存動画パス>.heatmap.json`へ正規化して保存。
  契約外フィールドは保存しない。
- worker開始後にもsidecarと動画を再照合し、結果を
  `heatmap_validation_summary.json`へ保存。
- clip-plan再選定時も再照合・再注釈し、sidecarが失効した場合は古い補助値を消去。
- 状態を`not_provided / unavailable / invalid_fallback / applied`で記録し、
  APIと処理状況画面へ表示。
- 人気区間との重複時間で候補ごとの値を算出し、ルールスコアへ最大`+10`の
  補助要素として加算。`value`は視聴回数ではなく動画内相対値。
- OpenAI scoringにも同じ意味を明記し、人気区間だけを採用理由にしない制約を追加。
- OpenAI score cache keyへsystem promptを含め、prompt変更前の結果を再利用しない。
- JSON選択inputを都度リセットし、外した同一ファイルを再選択可能にした。
- 既存hard gate、手動範囲、再編集APIは変更していない。
- 主な変更先:
  `backend/app/video/heatmap.py`、`backend/app/scoring/heatmap.py`、
  `backend/app/api/videos.py`、`backend/app/jobs/runner.py`、
  `frontend/app/upload/page.tsx`、`frontend/components/JobProgress.tsx`、
  `README.md`。

### 検証

- Downloader契約・実装のread-only確認: unit test `27 passed`。
- backend `ruff check .`: pass。
- backend `pytest`: `423 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- Docker Compose rebuild: pass。
- `scripts/smoke_runtime.py --skip-video`: pass。
- 実ブラウザ確認: 新規アップロード時だけJSON選択欄と説明を表示、
  再編集時は非表示、console errorなし。
- `git diff --check`: pass。

### 未解決・制限

- 許可済み実動画によるDownloaderのyt-dlp→FFmpeg→sidecar生成から
  AutoClipper処理までの実E2Eは未確認。
- 長尺実動画での追加SHA-256計算時間と実運用性能は未確認。
- 人気区間だけを起点に新しい候補を生成する処理は未実装。
  今回は既存候補集合の補助スコアに限定。
- 実動画での生成品質とユーザー受入は未確認。

## 2026-08-03 Task 97 GPU workerのCUDAライブラリ欠落修正

### 目的

- GPU profileのworkerで`libcublas.so.12`が見つからず、文字起こしが
  `transcription_failed`になる起動不整合を解消する。
- 誤ったworker imageをjob投入前に検出し、同じ不整合の再発を防ぐ。

### 観測事実・原因

- 失敗jobは`turbo / ja / cuda / float16`で実行されていた。
- workerにはRTX 5070 Tiが割り当てられ、CUDA device countは`1`だった。
- 稼働workerの実体はCPU用Debian/Python imageで、GPU用Ubuntu/CUDA imageではなかった。
- CPU/GPU Composeが同じ`autoclipperweb-worker`tagを共有し、launcherのprofile切替が
  `--force-recreate`のみだったため、CPU imageをGPU設定付きで再利用していた。
- 従来のGPU preflightはCUDA deviceの可視性だけを確認し、
  `libcublas.so.12`と`libcudnn.so.9`の実ロードを確認していなかった。
- 動画probe、音声抽出、音声特徴量計算は成功しており、動画・音声破損は原因ではない。

### 変更

- CPU/GPU worker imageを`${COMPOSE_PROJECT_NAME}`単位の別tagへ分離。
  profile間だけでなく別clone・別Compose project間の再利用も防止。
- CPU/GPU profile切替時は対象workerを`--build --force-recreate`するようlauncherを修正。
- 既にGPU profileで起動中でもGPU preflightを再実行し、不整合ならworkerを再build。
- preflight payloadをversion `1`として検証し、旧imageの結果は合格扱いしない。
- profile切替・GPU修復では稼働workerをbuild前に停止し、build中のjob取得を防止。
- GPU worker自身もRQ接続前に別processでpreflightを実行し、不正なCUDA runtimeでは
  jobを取得しない。RQ親processはCUDA未初期化のまま保ち、fork後の初期化失敗を防ぐ。
- GPU preflightで`libcublas.so.12`と`libcudnn.so.9`を`ctypes.CDLL`で実ロード。
  欠落時は`transcription_cuda_libraries_unavailable`で起動前に失敗させる。
- READMEへimage分離、profile切替build、native CUDA library検査を追記。
- 変更ファイル:
  `docker-compose.yml`、`docker-compose.gpu.yml`、
  `backend/app/audio/gpu_preflight.py`、`backend/app/config.py`、
  `backend/app/jobs/worker.py`、`launcher/controller.py`、
  `backend/tests/test_gpu_preflight.py`、`backend/tests/test_worker_startup.py`、
  `backend/tests/test_windows_launcher.py`、`README.md`。

### 検証

- 関連test: `47 passed`。
- backend `ruff check app tests`: pass。
- backend全体: `432 passed, 1 skipped`。
- frontend lint / typecheck / build: pass。
- CPU/GPU Composeの解決image:
  `autoclipperweb-worker-cpu / autoclipperweb-worker-gpu`。
- 別project `alternate-review`での解決image:
  `alternate-review-worker-cpu / alternate-review-worker-gpu`。
- GPU worker fresh build: pass。
- GPU preflight schema `1`: `cuda/float16`、CUDA device `1`、RTX 5070 Ti、
  `libcublas.so.12 / libcudnn.so.9`実ロード成功、fallbackなし。
- launcherの起動済みGPU再検証: `already_running=true / profile=gpu / fallback=false`。
- launcher実機profile切替: GPU→CPUでCPU image・CUDA device `0`、
  CPU→GPUでGPU image・CUDA device `1`へ復帰。最終状態は
  `autoclipperweb-worker-gpu / cuda / float16 / fallback=false`。
- 最終確認時のRQ queueは`0`、backendはhealthy、workerはGPU imageで稼働中。
- 失敗動画から抽出した10秒音声を実RQ jobとしてenqueueし、RQのfork子processで
  同じ`turbo / ja / cuda / float16`文字起こしが`finished`。
  `1 segment`、model load `2.644秒`、transcription `6.215秒`、
  peak VRAM `5434 MiB`、fallbackなし。
- worker logでpreflight schema `1`の出力後にRQ親が起動し、その後に上記jobを
  取得・完了した順序を確認。検証jobは削除、一時WAVも削除、queueは`0`へ復帰。
- `scripts/smoke_runtime.py --skip-video`: pass。

### 未解決・制限

- 元の失敗jobは履歴保持のため`failed`のまま。再enqueueは行っていない。
- 元動画全長`1816秒`の再処理と、通常切り抜き・ショート・ZIPまでの完全E2Eは未確認。

## 2026-08-03 Task 98 切り抜き予定画面の動画優先配置

### 目的

- 「切り抜き予定の確認」で、ページをスクロールする前に動画を再生できる配置へ変更する。
- 字幕・文字起こし領域のレイアウトと動作は維持する。

### 観測事実・原因

- 変更前の中央列は`選択clip見出し → 開始・終了調整 → 冒頭見せ場調整 → 動画`の順だった。
- `1280x720 / scrollY=0`では動画上端が`925px`で、2つの時間調整UIの下に隠れていた。

### 変更

- 中央列を`選択clip見出し → 動画 → 開始・終了調整 → 冒頭見せ場調整`へ並べ替え。
- 動画へ選択clip名を含む`aria-label`を追加。
- 右側の文字起こしaside、state、API、動画更新key、`onTimeUpdate`は変更なし。
- 変更ファイル: `frontend/app/jobs/[jobId]/clips/page.tsx`。

### 検証

- frontend lint / typecheck / build: pass。
- frontend image build・container再作成: pass。host/containerの対象ファイルSHA-256一致。
- `1280x720 / scrollY=0`: video `top=288 / bottom=601`、全体表示、controls可視。
- `1366x768 / scrollY=0`: video `top=288 / bottom=650`、全体表示、controls可視。
- `1025x768 / scrollY=0`: video `top=334 / bottom=505`、全体表示、controls可視。
- 右文字起こしaside: `sticky / width=390 / 23区間 / overflow-y=auto`を維持。
- browser console error / warning: `0 / 0`。
- 独立レビュー: P0 / P1 / P2 / P3なし。

### 未解決・制限

- Chrome profileが`80%` zoomのため`1024x768` exactは未確認。最接近`1025x768`は確認済み。
- `lg`未満では左clip一覧が動画より先に縦積みされるため、狭幅での無スクロール開始は保証外。
- ユーザー受入は未確認。

## 2026-08-03 Task 99 切り抜き予定画面の全幅化

### 目的

- `80%` zoomの横長viewportで左右に余っていた領域を、切り抜き予定の中央作業列へ渡す。
- 字幕列の幅と、スクロール前に動画再生を開始できる状態を維持する。

### 観測事実・原因

- 変更前はheader、工程表示、error、3列gridが`max-w-[1600px]`で制限されていた。
- `2400x1128` viewportではgridが`1600px`、左右余白が各`390.625px`、
  列幅が`280 / 930 / 390px`、動画幅が`896.76px`だった。

### 変更

- header、工程表示、error、3列gridから`max-w-[1600px]`を除去し、`w-full`へ変更。
- 左clip一覧`280px`、右文字起こし`390px`、動画上限`1100px`は維持。
  追加された横幅は中央作業列だけへ渡す。
- 変更ファイル: `frontend/app/jobs/[jobId]/clips/page.tsx`。

### 検証

- frontend lint / typecheck / build: pass。
- frontend image build・container再作成: pass。
- `2400x1128 / scrollY=0`: body/grid `2381.25px`、外余白`0 / 0px`、
  列幅`280 / 1711.25 / 390px`。
- 動画: `1100x618.75px`、`top=287.62 / bottom=906.37px`、
  viewport下余裕`221.63px`、controls可視、readyState `4`。
- 右文字起こし列: `390px / sticky`を維持。scrollX `0`、console error `0`。
- `1920x1080 / 2560x1440`: 全幅表示を確認。`1920x1080`は動画controlsまで初期表示。
- `390x844 / 1025x768`: document幅とclient幅が一致し、横overflowなし。
- 独立レビュー: P0 / P1 / P2 / P3なし。

### 未解決・制限

- 動画上限`1100px`は、横幅連動で動画が縦にも伸びて初期viewportから外れるのを防ぐため維持。
- `lg`未満の縦積み順は変更なし。
- ユーザー受入は未確認。

## 2026-08-03 Task 100 切り抜き予定画面の一画面4列配置

### 目的

- 横長viewportを`clip一覧 | 動画 | 時間調整 | 文字起こし`として使い、
  開始・終了調整と冒頭見せ場複製をスクロール前に操作できる配置へ変更する。
- 文字起こしUIの幅・sticky・内部scrollは維持する。

### 観測事実・原因

- Task 99後も動画は`p-4`と`max-w-[1100px]`で制限され、`2400x1128`では
  動画左右に各約`293px`の黒い余白が残っていた。
- 2つの時間調整UIが動画下に縦積みされ、冒頭見せ場複製は初期viewport外だった。

### 変更

- `1900px`以上では中央作業列を`minmax(0, 1fr) / 480px`へ分割。
- 動画の右、文字起こしの左へ、開始・終了調整と冒頭見せ場複製を縦配置。
- 動画外側の`p-4`、`mx-auto`、`max-w-[1100px]`を除去し、専用列幅へ一致させた。
- `1900px`未満は`動画 → 開始・終了調整 → 冒頭見せ場複製`の縦並びを維持。
- editor本体、state、API、文字起こしasideは変更なし。
- 変更ファイル: `frontend/app/jobs/[jobId]/clips/page.tsx`。

### 検証

- frontend lint / typecheck / build: pass。
- frontend image build・container再作成: pass。host/containerの対象ファイルSHA-256一致。
- HTTP `200`、browser console error / warning: `0 / 0`。
- `2400x1128 / scrollY=0`: 外側列`280 / 1714.67 / 390px`、
  中央内側列`1234 / 480px`。動画`1234x694.13px`で専用列の左右と一致。
- 同viewportで開始・終了panel `top=270 / bottom=671.33px`、
  冒頭見せ場panel `top=671.33 / bottom=1078px`。両panelを初期画面内で確認。
- `1920x1080 / scrollY=0`: 中央内側列`754 / 480px`、
  冒頭見せ場panel下端`1078px`で初期画面内。
- 文字起こし列: `390px / sticky / overflow-y=auto`を維持。
- `1366x768 / 1025x768 / 390x844`: 内側4列化なし、従来の縦並び、横overflowなし。
- 独立レビュー: P0 / P1 / P2 / P3なし。

### 未解決・制限

- `1900px`未満は縦並びのため、時間調整までの無スクロール表示は保証外。
- `1920x1080`での下端余裕は`2px`。フォントや文言変更時は再計測が必要。
- 保存APIを伴う実操作、通常clipで冒頭見せ場panelが非表示になる状態は未確認。
- ユーザー受入は未確認。

## 2026-08-04 Task 101 デスクトップ一括起動

### 目的

- デスクトップの`AutoClipper.lnk`を1回起動するだけで、停止中のDocker Desktopから
  AutoClipper推奨構成とUpload画面まで自動起動する。

### 観測事実・原因

- shortcutは`C:\BOT\AutoClipper Web\Start AutoClipper.cmd`を正しく参照していた。
- Docker Desktopはインストール済みだったが、daemon停止時のLauncherは
  `preflight()`でエラー表示して終了し、Docker Desktopを起動する処理がなかった。
- 初回の冷間E2Eで外部commandの`stdout / stderr=None`がredact処理へ渡り、
  `'NoneType' object has no attribute 'replace'`を検出した。

### 変更

- `LauncherController.start()`の先頭でDocker daemonを確認し、停止中なら
  `docker desktop start --detach --timeout 30`を実行する。
- Desktop CLIを使えない場合は、既知のインストール先にある
  `Docker Desktop.exe`をshellなしで起動する。
- daemon準備を最大`180秒`待ち、未準備ならComposeを実行せず専用エラーを返す。
- GUI初期表示後に`recommended` profileを自動起動し、
  `Docker Desktop → 4 services → health確認 → /upload`を1操作へ統合した。
- Refreshの`preflight()`は読み取り専用を維持した。
- redact入力を`None / bytes / str`で正規化し、冷間起動時のcommand出力差を吸収した。
- 起動処理全体へhard deadlineを適用し、各Docker commandへ残り時間だけを渡す。
- Desktop CLIのstartが非0でも起動途中のdaemonをpollし、即失敗や重複起動を避ける。
- per-user版Docker DesktopのCLI探索と、popup表示前の秘密値redactを追加した。
- Docker未導入、Desktop未検出、起動失敗、timeout、起動済み、CLI fallbackをtest追加。
- shortcutと`Start AutoClipper.cmd`は変更なし。
- 変更ファイル: `launcher/controller.py`、`launcher/app.py`、
  `backend/tests/test_windows_launcher.py`、`README.md`、
  `docs/WINDOWS_LAUNCHER.md`、`STATUS.md`。

### 検証

- launcher関連test: `40 passed`。
- backend全体: `443 passed, 1 skipped`。
- backend/launcher ruff、launcher compileall: pass。
- frontend lint / typecheck / build: pass。
- CPU/GPU Compose `config --quiet`: pass。
- Docker Desktop process `0`かつdaemon不通、Compose停止状態から実shortcutを起動。
- 最終コードの実launcher log: `00:20:41`起動開始、`00:21:04`Docker Desktopと
  4 services起動、`00:21:05`GPU recommended完了。所要約`24.3秒`。
- 起動後: backend/frontend/worker/redis稼働、backend healthy、
  `/health=200`、`/upload=200`、RQ queue `0`。
- worker: `gpu / cuda / float16`、RTX 5070 Ti、CUDA device `1`、fallbackなし。
- `git diff --check`: whitespace errorなし。
- 独立レビュー再確認: P0 / P1 / P2なし。

### 未解決・制限

- Docker Desktop自体のインストールは自動化しない。事前インストールが必要。
- 利用規約確認、WSL更新、Windows再起動要求が出た場合は`180秒`でtimeoutし、
  Docker Desktop画面でのユーザー操作が必要。
- clean Windows初回導入状態のE2Eとユーザー受入は未確認。

## 2026-08-04 Task 102 TOP画面の高密度ワークスペース化

### 目的

- 字幕再編集画面のデザイン言語を基準に、TOP `/upload`を横幅いっぱい使う高密度UIへ変更する。
- 参照画面の機能は複製せず、既存の動画入力・生成設定・開始操作を初期画面で把握できる構成にする。

### 観測事実・原因

- 従来TOPは`max-w-5xl`の縦積みで、`1920x957`でもフォーム幅が`1024px`に限定されていた。
- 入力、設定、開始操作が縦に離れ、設定全体を確認してから処理開始へ戻る必要があった。
- 参照画面は外周約`16px`、薄い罫線、角丸・影なし、左右固定列と中央可変列で情報密度を確保していた。

### 変更

- `/upload`を外周`16px`の全幅ワークスペースへ変更した。
- desktopを`入力動画 340px / 生成設定 可変 / 処理開始 300px`の3列にした。
- desktopはページ全体をviewport内に収め、中央設定だけを内部スクロールにした。
- mobileは1列と通常の縦スクロールへ切り替え、上部に開始操作を残した。
- 新規/再編集、動画選択、heatmap sidecar、設定、要約、開始操作を既存state/APIのまま再配置した。
- `UploadDropzone`へTOP専用compact表示、`SettingsPanel`へworkspace密度を追加した。
- 入力内容・出力本数・確認工程・処理フローを表示する`UploadWorkspaceSummary`を追加した。
- 右側の確認工程・処理フローを字幕焼き込み設定と再編集modeへ連動させた。
- TOP配下だけに`Yu Gothic UI`優先、角丸・影なし、focus outlineを適用した。
- `html lang`を`ja`へ変更した。
- 変更ファイル: `frontend/app/upload/page.tsx`、`frontend/components/UploadWorkspaceSummary.tsx`、
  `frontend/components/UploadDropzone.tsx`、`frontend/components/SettingsPanel.tsx`、
  `frontend/components/ManualClipRangeEditor.tsx`、`frontend/app/globals.css`、
  `frontend/app/layout.tsx`、`design-qa.md`、`STATUS.md`。

### 検証

- frontend lint / typecheck / build: pass。
- backend ruff: pass。backend全体: `443 passed, 1 skipped`。
- CPU/GPU Compose `config --quiet`: pass。
- 稼働中Compose: backend healthy、frontend/worker/redis稼働。`/health=200`、`/upload=200`。
- `1920x957`: document `1920x957`、横overflowなし。3列`340 / 1231 / 300px`。
- `1366x768`: 横overflowなし。3列`340 / 692.67 / 300px`、入力と開始操作を初期画面内に確認。
- `1280x767`: document・中央設定とも横overflowなし。手動範囲は1列へ切替。
- `390x844`: 横overflowなし、1列化、panel内部スクロールなし。
- 新規/再編集tab、出力モード変更、動画選択/解除、要約連動、開始ボタンの有効/無効: pass。
- 字幕焼き込みOFF、予定確認OFF、字幕確認OFF、再編集modeの右側フロー連動: pass。
- browser console error / warning: `0 / 0`。
- 参照画像と同じ`1920x957`で全体・上部拡大を1枚にした比較QA: pass。
- 独立レビュー再確認: P0 / P1 / P2なし。P3は`<xl`で同じsubmitを上部と最下部に置く意図した導線のみ。

### 未解決・制限

- 実動画を送信するjob作成E2Eは未実行。
- TOP以外の画面は今回のデザイン統一対象外。
- ユーザー受入は未確認。

## 2026-08-04 Task 103 TOP画面の情報整理

### 目的

- 注釈7点を基準に、TOP `/upload`の重複情報、空き領域、崩れたショート設定を整理する。
- 左の動画・人気区間JSON入力と字幕スタイル本体は維持する。

### 観測事実・原因

- 右側`UploadWorkspaceSummary`は左入力と中央設定を再掲し、固有機能は開始ボタンだけだった。
- 手動時間指定、4工程カード、2つの確認panelが常時展開され、初期画面の縦幅を消費していた。
- `Short layout`と`Short overlay title`が別行・別幅で配置され、広い空白と位置ずれを作っていた。

### 変更

- desktopを`入力動画 340px / 生成設定 可変`の2列にし、重複していた右側要約を削除した。
- 開始操作を`UploadActionBar`へ分離し、生成設定の下端へ固定した。
- 手動時間指定を初期状態で閉じ、使用中だけ`時間指定中`と表示するdetailsへ変更した。
- 通常・ショートの切り抜き方針をTOP中央幅いっぱいの2列にした。
- `ショート画面 / ショート冒頭タイトル / 字幕を焼き込む`を1区画へ集約した。
- 4工程カードを削除し、実際の2つの確認設定だけを閉じたdetailsへ移した。
- 閉じた確認設定のsummaryへ`予定確認 + 字幕確認 / なし`の現在値を表示した。
- 手動時間の検証失敗時はdetailsを自動展開し、最初の不足欄へfocusするようにした。
- mobileでは下部`UploadActionBar`を非表示にし、上部の開始ボタン1個だけを表示した。
- 処理モード・動画タイプを日本語化し、本数2項目をdesktop幅いっぱいへ配置した。
- 新規 / 再編集の切替を不完全なtab ARIAから`aria-pressed`のbutton groupへ変更した。
- 左の入力動画・人気区間JSONと`SubtitleStyleEditor`本体は変更していない。
- 変更ファイル: `frontend/app/upload/page.tsx`、`frontend/components/UploadActionBar.tsx`、
  `frontend/components/SettingsPanel.tsx`、`frontend/components/ManualClipRangeEditor.tsx`、
  `frontend/components/ClipSelectionEditor.tsx`、削除`frontend/components/UploadWorkspaceSummary.tsx`、
  `design-qa.md`、`STATUS.md`。

### 検証

- frontend lint / typecheck / build: pass。
- backend ruff: pass。backend全体: `443 passed, 1 skipped`。
- CPU/GPU Compose `config --quiet`: pass。
- 稼働中Compose: backend healthy、frontend/worker/redis稼働。`/health=200`、`/upload=200`。
- `1920x957 / 1821x1272 / 1280x767 / 390x844`: document横overflowなし。
- desktop: 開始操作をviewport内に常時表示。mobile: 上部開始操作を表示。
- 手動時間・確認設定の開閉、ショート画面・冒頭タイトルの変更と復帰: pass。
- 手動時間を途中入力して閉じた状態で開始: エラー表示、details再展開、不足欄focusを確認。
- desktop / mobileの実表示submit: 各`1`。
- 新規作成 / 完成動画再編集の見出し・JSON表示・CTA連動: pass。
- 通常のみ / ショートのみ: 残る本数欄を全幅表示し、ショート設定・見出しを出力対象へ連動: pass。
- browser console error / warning: `0 / 0`。
- 参照デザイン / 実装、注釈前 / 実装を各1枚の比較画像で確認: pass。
- 独立再レビュー: P0 / P1 / P2 / P3なし。

### 未解決・制限

- 実動画を選択してjobを作成するE2Eは未実行。
- TOP以外の画面は今回の変更対象外。
- ユーザー受入は未確認。

## 2026-08-04 Task 104 切り抜き予定画面の重複整理と文字起こし誤認識補正

### 目的

- 切り抜き予定画面の重複情報を減らし、動画確認を上から始められる状態にする。
- 左のclip一覧で時刻が元動画基準だと明示する。
- `その農منにしとったっちゃん`の表示と、その誤認識がタイトルへ流入する経路を補正する。

### 観測事実・原因

- 選択clipの種別・タイトル・元動画範囲が左一覧と動画直上の2か所に重複していた。
- 該当jobの`raw_transcript_segments.json`に`農من`が保存済みで、UI描画や文字コード変換による崩れではなかった。
- `من`はArabic文字`U+0645 / U+0646`。日本語文字起こしへ隣接して混入したWhisperの多言語誤認識だった。
- 該当jobはOpenAI文字起こし補正が無効で、未補正segmentが候補タイトルへ昇格していた。

### 変更

- 動画直上の重複メタ情報を削除し、進捗表示の直下から動画を表示するようにした。
- 左一覧の全clip時刻へ`元動画`を付けた。
- 既知誤認識`農من -> 能面`を既定の文字起こし後処理へ追加した。
- 日本語へ隣接するArabic等の想定外scriptを検出し、未補正文字列をタイトル採用しないguardを追加した。
- clip plan生成時と既存plan読込時に既知誤認識だけを冪等補正し、既存jobも再解析なしで表示補正するようにした。
- 文字起こし区間APIと字幕確認への引継ぎでも既知誤認識を補正したsegmentを使うようにした。
- 既存成果物ではユーザー辞書を再適用せず、`NewsPicks -> NewsPicks公式公式`のような多重置換を防いだ。
- 変更ファイル: `frontend/app/jobs/[jobId]/clips/page.tsx`、
  `backend/app/audio/transcript_postprocess.py`、`backend/app/audio/transcript_suspicion.py`、
  `backend/app/candidates/title_fallback.py`、`backend/app/jobs/clip_plan.py`、
  `backend/app/api/jobs.py`、`backend/tests/test_clip_plan.py`、
  `backend/tests/test_title_fallback.py`、`backend/tests/test_transcript_postprocess.py`、
  `backend/tests/test_transcript_suspicion.py`、`design-qa.md`、`STATUS.md`。

### 検証

- 関連test: `37 passed`。
- backend全体: `453 passed, 1 skipped`。既知のStarlette deprecation warning `1`のみ。
- backend/launcher ruff: pass。
- frontend lint / typecheck / build: pass。
- CPU/GPU Compose `config --quiet`: pass。
- frontend imageを再build後、backend / workerを最終コードで再buildし、Compose再起動: pass。
- 稼働中Compose: backend healthy、frontend/worker/redis稼働、`/health=ok`、対象画面`200`。
- 対象job API: clip `5`件、タイトル`その能面にしとったっちゃん`、
  タイトル・対象文字起こし区間ともArabic文字なし。
- `1821x1272`: document横overflowなし。重複メタ情報なし、左5件すべて`元動画`表示、
  Short 1選択時も動画・時間調整・見せ場複製・文字起こしが連動。
- Browser console: error `0`、warning `0`。開発用info / HMR logのみ。
- 実装画像: `.codex_tmp/task104-clip-review-after-1821x1272.png`。
- 独立レビューで既存成果物へのユーザー辞書再適用をP1検出し、冪等な既知補正へ限定して修正。再レビューP0 / P1なし。

### 未解決・制限

- 保存済みraw transcript artifact自体は書き換えない。読込・API応答・次工程への引継ぎ時に補正する。
- 許可済み実動画を再文字起こしするE2Eは未実行。
- clip再選定、予定確定、字幕保存は変更を避けるため実行していない。
- ユーザー受入は未確認。

## 2026-08-04 Task 105 切り抜き調整パネルの縦幅圧縮

### 目的

- `1821x1272`の初期表示で、動画、開始・終了調整、冒頭への見せ場複製の入力・追加ボタンまでスクロールなしで操作できるようにする。
- 配置、字幕列、動画、左clip一覧は維持する。

### 観測事実・原因

- 変更前は開始・終了調整`289.3px`、見せ場複製`325.3px`、見せ場複製の下端`1418.6px`だった。
- viewport下端まで約`147px`不足し、見せ場複製の入力欄と追加ボタンが初期表示外だった。
- 両panel内の縦余白、見出しと説明の縦積み、要約の3行表示が高さを消費していた。

### 変更

- 開始・終了調整の見出しと説明を横並び可能にし、panel余白、入力間隔、要約部を圧縮した。
- 見せ場複製へ`compact`表示を追加し、切り抜き予定画面だけで使用した。
- 字幕画面で共有する見せ場複製は`compact=false`を既定とし、従来表示を維持した。
- 文字サイズ、色、文言、動画、左clip一覧、右文字起こし、保存処理は変更していない。
- 変更ファイル: `frontend/components/ClipBoundaryEditor.tsx`、
  `frontend/components/ClipHookSceneEditor.tsx`、`frontend/app/jobs/[jobId]/clips/page.tsx`、
  `design-qa.md`、`STATUS.md`。

### 検証

- frontend lint / typecheck / build: pass。
- frontend image再build・container再作成: pass。
- 稼働中Compose: backend healthy、frontend/worker/redis稼働。`/health=200`、対象画面`200`。
- `1821x1272`: 開始・終了調整`217.3px`、見せ場複製`234.7px`、合計`162.7px`削減。
- 見せ場複製の下端`1256.0px`、追加ボタン下端`1227.3px`、viewport下端まで`16.0px`。両方とも初期表示内。
- `1821x1272 / 1280x720`: document横overflow`0`。両panelと追加ボタンの存在を確認。
- `前に+5秒 -> 自動選定の範囲へ戻す`、`ここから3秒 -> ここから2秒`のstate連動: pass。保存APIは未実行。
- Browser console: error`0`、warning`0`。開発用info / HMR logのみ。
- Before / After比較: `.codex_tmp/task105-before-after-final-1821x1272.png`、panel拡大比較: `.codex_tmp/task105-panels-before-after-final.png`。

### 未解決・制限

- 上限超過警告や入力エラーが表示される非初期状態は、その文量分だけ縦スクロールが発生し得る。
- 保存・再生成は既存job成果物を変えないため実行していない。
- ユーザー受入は未確認。

## 2026-08-05 Task 106 JSON区間モード

### 目的

- 人気区間JSONを選択した際、ユーザーがJSON基準の候補生成と従来の補助評価を明示的に切り替えられるようにする。
- `ON`: JSON人気区間を候補生成の起点にする。`OFF`: 従来候補へ人気度を最大`+10`点の補助として使う。

### 観測事実・原因

- 変更前はsidecarをアップロードしても常に従来候補を生成し、重複時間の人気度を補助加点するだけだった。
- JSONから候補区間を直接生成する設定、API field、候補生成strategy、UI切替がなかった。
- 無効・未添付sidecarは常に従来評価へfallbackするため、JSON基準を要求したか判別できなかった。

### 変更

- `heatmapIntervalMode`をfrontend/backendのjob設定へ追加し、既定値を`false`にした。
- TOPの人気区間JSON欄へ`OFF / ON`を追加した。JSON未選択時はON不可、JSON解除・動画変更・再編集切替時はOFFへ戻す。
- ON時は正規化値が正の人気区間を`value desc / start asc`でseed化し、通常・ショートの設定済みmin/max/stepへ拡張して候補を生成する。
- 同一ピークの細粒度区間がseed上限を独占しないよう、出力種別の最短時間単位で時系列分散してからseed上限を適用する。
- 動画端shift、字幕境界補正、完全重複排除、start/time bucket上限、global候補上限を適用した。
- 候補へ`generation_source`、seed開始・終了・値、動画全体時間基準の`heatmap_direct_score`を保存した。
- ON時の候補順位は`heatmap_direct_score`を第一キーとし、その後に既存rule/OpenAI scoreを使う。hard gate、品質閾値、重複排除は維持した。
- 手動時間指定がある種類は手動区間を優先し、未指定の種類だけJSON候補を生成する。
- ONかつ自動出力ありでJSON未添付、`heatmap_available=false`、値が全て0、worker再検証失敗の場合は従来処理へ黙ってfallbackせず明示失敗する。
- workerで実動画時間内に残る正値区間を再判定し、動画外区間しかない場合と自動出力種別の候補が0件の場合も明示失敗する。
- clip再選定でもmodeとseed由来候補を保持し、sidecarを再検証する。
- job進捗へ`JSON区間モードで候補生成`と表示する。
- ON適用失敗時のjob進捗を`従来評価`ではなく`JSON区間モードを適用できず停止`と表示する。
- 変更ファイル: `backend/app/schemas.py`、`backend/app/api/jobs.py`、
  `backend/app/candidates/generate_heatmap_candidates.py`、
  `backend/app/candidates/merge_boundaries.py`、`backend/app/candidates/select_candidates.py`、
  `backend/app/scoring/heatmap.py`、`backend/app/jobs/runner.py`、
  `backend/tests/test_heatmap_interval_candidates.py`、`backend/tests/test_api_routes.py`、
  `backend/tests/test_real_pipeline.py`、`frontend/lib/types.ts`、
  `frontend/components/SettingsPanel.tsx`、`frontend/components/JobProgress.tsx`、
  `frontend/app/upload/page.tsx`、`README.md`、`STATUS.md`。

### 検証

- backend全体: `462 passed, 1 skipped`。既知のStarlette deprecation warning `1`のみ。
- backend ruff: pass。frontend lint / typecheck / build: pass。
- ON通常・ショート: 高いJSON区間を含む候補を選択し、`strategy=heatmap_intervals`、seed情報、direct scoreを保存: pass。
- OFF: 既存E2Eで`heatmap_score=7.5`の補助評価を維持: pass。
- ON＋JSONなし / `heatmap_available=false`: job作成を`422`で拒否: pass。
- job作成後のsidecar改ざん: workerが`heatmap_interval_mode_unavailable`で失敗し、従来候補へfallbackしない: pass。
- ON＋手動時間指定: start/end完全一致、`manual_time_range_locked`、再選定後もmode保持: pass。
- GPU Composeを全image再build・再作成: pass。backend healthy、frontend/worker/redis稼働、CUDA preflight `ok=true`。
- Browser: JSON未選択でON disabled、JSON選択でON可能、ON文言切替、JSON解除でOFF復帰: pass。
- Browser console: error`0`、warning`0`。
- 独立再レビュー: P0/P1/P2なし。密集ピーク再現は通常2本選択・未達0、動画外正値区間はON適用不可を確認。

### 未解決・制限

- Downloaderが生成した許可済み実動画・実sidecarによる`upload -> worker -> FFmpeg -> JSON区間選定`の実E2Eは未実行。
- JSON区間でも既存hard gateを通過しない候補は採用しない。`strict_quality`では要求本数未達になり得る。
- ユーザー受入は未確認。

## 2026-08-06 Task 107 文字起こし言語の日本語固定

### 目的

- 新規処理や設定引き継ぎ漏れがあっても、Whisperの自動言語判定で英語字幕が生成されないようにする。
- 現在の日本語専用運用をUI、API、worker、launcherで一貫して強制する。

### 観測事実・原因

- 通常uploadの既定値、backend schema、worker fallback、CPU launcherが`transcriptionLanguage=auto`だった。
- GPU profileだけ`ja`で、profileなしの`/upload`から新しいjobを作ると`auto`へ戻った。
- 正式な完成MP4再編集は既存jobを開き、再文字起こししない。今回の英語字幕jobは新しいjobとして`base / auto / cpu`で処理されていた。

### 変更

- frontendの既定値と型を`ja`のみにし、音声言語UIを`日本語（固定）`表示へ変更した。
- API schemaを`ja`のみ、既定値`ja`にした。旧client/jobの`auto`は`ja`へ正規化し、`en`など非日本語指定は`422`で拒否する。
- workerは保存済み設定が欠損、`auto`、不正値でも必ず`ja`をWhisperへ渡すようにした。
- CPU/GPU launcherと実動画E2E scriptの既定言語を`ja`へ統一した。
- READMEの既定値・対応言語を日本語固定へ更新し、API、pipeline、launcher、scriptの再発testを追加した。
- 変更ファイル: `frontend/components/SettingsPanel.tsx`、`frontend/lib/types.ts`、
  `backend/app/schemas.py`、`backend/app/jobs/runner.py`、
  `launcher/controller.py`、`scripts/e2e_real_video.py`、`README.md`、
  `backend/tests/test_api_routes.py`、`backend/tests/test_real_pipeline.py`、
  `backend/tests/test_e2e_real_video_script.py`、`backend/tests/test_windows_launcher.py`、`STATUS.md`。

### 検証

- 関連test: `11 passed`。既知のStarlette deprecation warning `1`のみ。
- 対象backend/launcher/script ruff: pass。
- frontend typecheck / lint / build: pass。
- GPU Composeでbackend / frontend / workerを再build・再作成: pass。
- 稼働確認: backend healthy、`/health=ok`、`/upload?runtimeProfile=gpu=200`、worker GPU preflight `ok=true`。
- 稼働container内でAPI既定値、旧`auto`正規化、worker fallbackがすべて`ja`: pass。

### 未解決・制限

- 修正前に生成済みの英語transcript artifactは自動変換しない。正しい日本語jobを使うか、修正後に新規処理が必要。
- 許可済み実動画を修正後に新規文字起こしするE2Eは未実行。
- ユーザー受入は未確認。

## 2026-08-10 Task 108 ショート上下帯のON/OFF

### 目的

- ショート動画だけに上部タイトル帯と下部ロゴ帯を配置し、各帯を独立してON/OFFできるようにする。
- 下部帯は提供された完成画像を再描画せず、そのまま使用する。

### 観測事実・原因

- 変更前はショートのタイトル文字をASSで焼き込む設定だけで、帯画像をFFmpegへ入力・合成する経路がなかった。
- 上下帯の設定field、UI、job保存、worker受け渡し、export metadataがなかった。

### 変更

- `shortTopBannerEnabled` / `shortBottomBannerEnabled`をfrontend/backendのjob設定へ追加し、既定値を`false`にした。新規jobの`shortOverlayTitleMode`も`never`へ統一した。
- TOP設定のショート欄へ`上: 柄 + タイトル`と`下: ロゴ`の独立checkboxを追加した。
- 字幕確認・完成動画再編集画面のショート欄にも`帯プレビュー`として同じ2項目を追加した。元jobの値を初期表示し、変更時は即時保存する。
- ショート選択時は、右側の9:16文字配置プレビューへ選択中の上下帯を即時反映する。両帯は最終renderと同じPNGを3:1のまま上端・下端へ表示し、通常clipのプレビューは変更しない。
- `GET /api/jobs/{jobId}/subtitle-review/banner-assets/{position}`を追加し、`top` / `bottom`の固定assetをブラウザへ配信する。メイン動画は元の横長表示を維持し、最終shortの`auto` / `blur_background` cropを擬似再現しない。
- review responseへ`shortOverlayTitleMode`を追加し、旧jobの`auto` / `always` / `high_quality_only`を維持する。`never + 上帯OFF`の時だけ配置プレビューのタイトルを非表示にする。
- 旧jobで`shortOverlayTitleMode`自体が欠損する場合は、実rendererと同じ`auto`へ補完する。上帯変更時はfrontendも`always` / `never`を即時反映し、保存失敗時は元値へ戻す。
- 再編集用`PATCH /api/jobs/{jobId}/subtitle-review/settings`を追加し、2つのboolだけを厳格検証して`job.settings_json`、review artifact、summaryへ同期する。帯保存中はclip確認・最終レンダリングを開始できない。
- 旧review artifactに上下fieldがないjobは、GET時に`job.settings_json`を正としてhydrateし、artifactとsummaryも更新する。
- 字幕・タイトル・フック・clip確認・帯の保存処理は画面内で直列化し、最終レンダリング開始中も編集を禁止して同じreview artifactへの競合更新を防止した。
- 上帯の値を変更した時だけ`shortOverlayTitleMode`を`always` / `never`へ同期し、下帯だけの変更では旧jobの値を維持する。
- 上ON時は和柄画像を上端へ配置し、選定済みショートタイトルをその上へ表示する。会話字幕OFFでも上部タイトル用ASSだけ生成する。
- 下ON時は提供画像を再描画せず、画像全体を1080幅へ等倍縮尺して下端へ配置する。workspace内コピーと提供画像のSHA-256一致を確認した。
- 上下帯はショート全時間へ表示し、フック複製ありでもconcat後へ合成する。通常切り抜きは変更しない。
- 出力metadataへ`top_banner_rendered` / `bottom_banner_rendered`を追加した。
- 変更ファイル: `backend/app/schemas.py`、`backend/app/jobs/runner.py`、
  `backend/app/render/render_short.py`、`backend/app/render/assets/short_top_banner.png`、
  `backend/app/render/assets/short_bottom_banner.png`、`backend/tests/test_api_routes.py`、
  `backend/tests/test_short_rendering.py`、`frontend/lib/types.ts`、
  `frontend/components/SettingsPanel.tsx`、`frontend/components/ClipTextStyleEditor.tsx`、
  `frontend/app/jobs/[jobId]/subtitles/page.tsx`、
  `frontend/lib/api.ts`、`frontend/lib/types.ts`、`backend/app/api/jobs.py`、
  `backend/app/jobs/subtitle_review.py`、`backend/tests/test_subtitle_review.py`、
  `backend/tests/test_real_pipeline.py`、
  `README.md`、`STATUS.md`。

### 検証

- backend全体: `481 passed, 1 skipped`。既知のStarlette deprecation warning `1`のみ。
- backend ruff: pass。frontend lint / typecheck / build: pass。
- API既定OFF・明示ON保存、通常/フックの合成順、asset受け渡し、metadata、字幕OFF時の上部タイトルASS: pass。字幕OFF＋フック文ありでもHook eventを生成しない。
- 再編集APIのstrict bool・余分field拒否、上下独立保存、旧`auto`維持、上帯変更時のtitle mode同期、再レンダリングへのasset受け渡し: pass。
- 旧artifact欠損時のDB設定hydrateと永続化、保存中の他編集ロック: pass。
- banner asset配信のPNG byte一致・不正position拒否・欠損404、9:16配置プレビュー用title mode同期: pass。
- GPU Composeでbackend / frontend / workerを再build・再作成: pass。backend healthy、frontend`/upload=200`、worker GPU preflight`ok=true`。
- 稼働コンテナのOpenAPIで再編集設定PATCH、request schema、review responseの上下fieldを確認: pass。
- Docker worker内の実FFmpegで上下帯＋日本語タイトルを2秒動画へ合成: pass。
- 実出力: `1080x1920`、`yuv420p`、SAR `1:1`、duration `2.000000`。
- Compose全image再build・再作成: pass。backend healthy、frontend/worker/redis稼働、`/health=ok`、`/upload=200`。
- `/upload` HTMLに上下checkboxの表示文言を確認した。
- backend/worker container内の新規jobタイトル既定値がともに`never`: pass。
- プレビュー拡張後のGPU Compose最終rebuild・再作成: pass。backend healthy、frontend/worker/redis稼働、`/health=ok`、`/upload=200`、字幕確認URL`200`。
- 稼働環境の既存jobでreview API`200`、旧mode欠損から`auto`へのhydrate、上下PNG配信`200`を確認。配信byte数は上`587420`、下`1877811`でrender assetと一致。
- worker GPU preflight: `actual_device=cuda`、GPU`NVIDIA GeForce RTX 5070 Ti`、RQ listeningを確認。
- 独立再レビュー: P0/P1/P2なし。

### 未解決・制限

- 許可済み実動画を使ったjob全体の`upload -> worker -> ショート書き出し`は未実行。
- in-app browserのlocalhost URL制限で、再編集画面の実クリック保存と目視確認は未実行。HTTP/API・自動test・production buildまでは確認済み。
- 9:16文字配置プレビューは帯と文字位置の確認用。最終shortの被写体追従・中央crop・ぼかし背景は最終renderで決定する。
- ユーザー受入は未確認。

## 2026-08-10 Task 109 上部柄帯OFF時のタイトル保持

### 目的

- 再編集画面で上部の柄帯をOFFにしても、タイトル文字は単独で表示・書き出しできるようにする。

### 観測事実・原因

- 旧実装は上部の柄背景とタイトル表示を同じcheckboxで無効化していたため、柄帯を外すとタイトルも消えていた。
- プレビュー側の判定と最終rendererのタイトル表示条件が別実装で、`low_cost`や旧jobのmodeによって表示が一致しない経路があった。

### 変更

- checkbox名を`上: 柄帯`へ変更し、上部checkboxは柄背景だけを制御する仕様へ分離した。
- 上部柄帯をONからOFFへ変更した時は`shortOverlayTitleMode=always`を保存し、柄だけを消してタイトルを残す。
- 上部柄帯がOFFのまま下部ロゴだけを変更した場合は、明示済みの`never`を含む既存タイトルmodeを変更しない。
- `overlayTitleExpected`をclip単位でreview responseへ追加し、プレビュー、review artifact、summary、最終rendererを共通の`title_policy.py`で判定するようにした。
- 上部柄帯OFF・タイトル表示・会話字幕OFFでも、Title eventだけを含むASSを生成する。Hook/Subtitle eventと帯画像は追加しない。
- 新規jobのタイトルmode既定値をrenderer互換の`auto`へ戻した。
- 変更ファイル: `backend/app/render/title_policy.py`、`backend/app/render/render_short.py`、
  `backend/app/api/jobs.py`、`backend/app/jobs/subtitle_review.py`、`backend/app/jobs/runner.py`、
  `backend/app/schemas.py`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、
  `frontend/components/SettingsPanel.tsx`、`frontend/lib/types.ts`、関連test、`README.md`、`STATUS.md`。

### 検証

- backend全体: `493 passed, 1 skipped`。既知のStarlette deprecation warning `1`のみ。
- 最終関連test: `94 passed`。backend ruff: pass。
- frontend typecheck / lint / production build: pass。
- 独立再レビュー: P0/P1/P2なし。
- GPU Composeを再build・再作成: pass。backend healthy、`/health=ok`、`/upload=200`。
- worker GPU preflight: `actual_device=cuda`、`actual_compute_type=float16`、GPU`NVIDIA GeForce RTX 5070 Ti`、fallbackなし。
- 稼働中jobのreview API: `shortOverlayTitleMode=auto`、上部柄帯OFF、下部ロゴOFF、shortの`overlayTitleExpected=true`。
- in-app browserでショートを選択して確認: `上: 柄帯`は未チェック、上部柄画像なし、9:16配置プレビューのタイトル表示あり。job設定は変更していない。

### 未解決・制限

- 既に`上部柄帯OFF + shortOverlayTitleMode=never`で保存済みの旧jobは、明示的なタイトル非表示との区別ができないため自動移行しない。
- 許可済み実動画を使ったjob全体の`upload -> worker -> ショート書き出し`は未実行。
- ユーザー受入は未確認。

## 2026-08-11 Task 110 再選定時のJSON区間モード切替

### 目的

- 切り抜き予定の確認画面で、初回にJSON区間モードをONにしたjobでも、再選定時だけ従来評価へ切り替えられるようにする。
- OFF時は初回のJSON区間候補を再利用せず、保存済み解析結果から従来候補を作り直す。

### 観測事実・原因

- 変更前の再選定requestには`heatmapIntervalMode`がなく、初回job設定のONが常に引き継がれていた。
- 再選定workerは初回に保存した`candidates.json`を再採点するだけだった。初回ONでは候補母集団自体がJSON区間由来で、同じ条件の選定は決定的なため同じ場面になっていた。

### 変更

- 再選定画面へ`候補基準`の`従来評価 / JSON区間`切替を追加し、現在のplan設定を初期表示する。
- 再選定APIへoptional strict boolの`heatmapIntervalMode`を追加した。旧clientがfieldを省略した場合は保存済みmodeを維持する。
- mode変更時だけ保存済みの文字起こし・無音・シーン解析から候補母集団を再生成する。ONはJSON区間seed、OFFは従来generatorへ戻し、有効なJSON値は最大`+10`点の補助評価として使う。
- 同じmodeでの再選定は保存済み候補を再利用し、再生成コストを増やさない。手動時間指定はmodeより優先する。
- mode変更失敗時はjob設定、clip plan、候補4artifactを旧状態へ戻す。旧previewはfinal planとDB statusの確定後だけ削除し、cleanup失敗はjob失敗にしない。
- READMEへ再選定時の切替、候補再生成、決定的選定の制限を追記した。
- 変更ファイル: `frontend/app/jobs/[jobId]/clips/page.tsx`、`frontend/lib/types.ts`、
  `backend/app/schemas.py`、`backend/app/api/jobs.py`、`backend/app/jobs/runner.py`、
  `backend/tests/test_api_routes.py`、`backend/tests/test_real_pipeline.py`、`README.md`、`STATUS.md`。

### 検証

- backend全体: `496 passed, 1 skipped`。backend ruff: pass。
- frontend typecheck / lint / production build: pass。
- 自動testで初回ONから再選定OFFへ切り替え、候補sourceが`heatmap_interval`から従来generatorへ変わり、`heatmapSelectionBehavior=supporting_score`になることを確認: pass。
- APIの省略互換、strict bool、modeと4候補artifactのworker失敗rollback、旧preview内容の保全: pass。
- GPU Composeを最終差分で全image再build・再作成: pass。`/health=ok`、切り抜き予定URL`200`、worker GPU preflight `actual_device=cuda`、`float16`、fallbackなし。
- in-app browserでJSON区間ONの既存jobを確認し、`従来評価`選択で説明と`aria-pressed`が即時切替、`JSON区間`へ戻せることを確認。再選定POSTは送信せず、job設定がONのまま変わらないことを確認した。
- 独立再レビュー: P0/P1/P2なし。

### 未解決・制限

- OFFは候補母集団を従来generatorへ戻す機能。同じ場面の評価が高い場合まで、必ず別場面になることは保証しない。
- 許可済み実動画で実際に再選定POSTを送り、workerでpreviewを再生成する実E2Eは未実行。自動E2E、Docker起動、実画面の切替表示までは確認済み。
- ユーザー受入は未確認。

## 2026-08-17 Task 111 長尺文字起こし自動復旧と1クリック再処理

### 目的

- 長尺動画の文字起こしが崩れて候補0件になった場合も、再アップロードや設定のやり直しなしで復旧できるようにする。
- 新規jobは操作なしで自動復旧し、既に失敗した対象jobはボタン1回で再処理できるようにする。

### 観測事実・原因

- 対象jobの人気区間JSONは正常適用され、100区間中99区間が正値だった。
- JSON区間からショート候補68件を生成したが、全件が`strict_quality`の最低点60を下回り、最高点54.119、選定0件、render失敗0件だった。
- 155分12秒の動画に対して文字起こしは61segment、437文字、平均confidence 0.324、音声coverage 2.84%だった。同じ低情報文が反復し、候補320件中247件が文字起こし不足で除外された。
- 同じ動画の90秒区間は同じ`turbo / cuda / float16`で連続した日本語会話を認識できた。入力音声・GPU・モデル単体ではなく、長尺音声の一括認識結果と旧品質判定が原因だった。

### 変更

- CUDAで30分以上の動画は、通常の一括文字起こし後にcoverage、文字密度、confidence、反復を検査する。異常時だけ同モデルの90秒chunk・5秒overlapへ自動切替し、なお異常なら`small + ja`のchunk認識へ自動切替する。
- chunkごとにheartbeatを更新し、一時WAVは処理後すぐ削除する。全chunkのtimestampを元動画時刻へ戻し、境界の重複・両落ちを避けて統合する。品質閾値は緩和しない。
- primary、同モデルchunk、`small + ja`の各試行状態を`transcription_recovery_summary.json`へ保存する。最終試行が例外でも失敗型とruntime診断を残す。
- 選定0件を`no_usable_selection`、render全滅を`no_usable_output`へ分離した。旧jobは空の`selected_clips.json`、render失敗0件、字幕確認artifactなしを満たす場合だけ選定失敗として扱う。
- `POST /api/jobs/{jobId}/retry`を追加した。元動画・人気区間JSON・設定を再利用し、新しいjob/output領域で再処理する。再アップロードと設定入力は不要。
- 再処理は1回まで。queue投入前後の二重送信、DB commit直後の停止、RQ jobのactive/terminal競合を回収し、同じjobを重複実行しない。
- 失敗画面へ`同じ動画・設定で再処理`を追加した。候補0件だけに表示し、処理中の緑bannerは失敗時に表示しない。再処理後も失敗した場合とrender失敗では表示しない。
- 候補0件の旧100%表示を選定工程72%へ補正し、到達済み工程を緑、停止した`clip選定`を赤で表示する。
- RQ依存下限を実装で使うAPIに合わせて`>=2.10.0`へ更新した。
- 変更ファイル: `backend/app/audio/transcribe_faster_whisper.py`、`backend/app/jobs/runner.py`、
  `backend/app/jobs/queue.py`、`backend/app/api/jobs.py`、`backend/app/schemas.py`、
  `backend/pyproject.toml`、`frontend/app/jobs/[jobId]/page.tsx`、
  `frontend/components/JobProgress.tsx`、`frontend/components/ProgressTimeline.tsx`、
  `frontend/lib/api.ts`、関連test、`README.md`、`STATUS.md`。

### 検証

- backend全体: `526 passed, 1 skipped`。既知のStarlette `TestClient` deprecation warning 1件のみ。
- backend ruff、frontend typecheck / lint / production build、pip依存整合、`git diff --check`: pass。
- chunk境界のtimestamp揺れによる二重採用・両落ち、長い区間を挟む重複、3重重複、正常な長尺反復の誤検出を自動testで確認: pass。
- 選定失敗とrender失敗の分離、旧job判定、retry 1回上限、二重送信・enqueue失敗・terminal競合を自動testで確認: pass。
- 対象jobの稼働API応答が`no_usable_selection`へ正規化され、再処理対象になることを確認: pass。
- GPU Composeで全imageをbuild・再作成し、backend healthy、worker GPU preflight`ok=true`、`actual_device=cuda`、`float16`、GPU`NVIDIA GeForce RTX 5070 Ti`、RQ`2.11.0`を確認: pass。
- in-app browserで対象jobを確認し、進捗`72%`、到達済み工程`OK`、`clip選定`の赤表示、失敗内容直下の再処理button表示・有効化、失敗時の緑banner非表示を確認: pass。再処理POSTは送信していない。

### 未解決・制限

- 対象の155分動画で再処理ボタンは押していない。実CUDAの一括認識からchunk復旧、候補選定、書き出しまでの実E2Eは未確認。
- 3段階の文字起こしを含む155分動画がRQ timeout 3600秒以内に完了するかは未確認。
- chunk境界で文字列が大きく言い換わる認識差は、安全側で両segmentを残す場合がある。
- ユーザー受入は未確認。

## 2026-08-17 Task 112 完成表示一致プレビューと通常・ショート編集分離

### 目的

- 冒頭フック中に通常字幕を重ねない。
- 字幕確認画面を通常編集とショート編集に分け、ショート選択時は実際の9:16映像を再生する。
- タイトル、フック、字幕、crop、上下帯を完成動画と同じ見た目で確認できるようにする。

### 観測事実・原因

- 旧中央プレイヤーは通常・ショートとも固定16:9の元動画切出しで、右側の9:16表示はブラウザCSSによる静止モックだった。再生映像、文字折返し、最終FFmpeg出力が別実装だった。
- CSSモックはブラウザ幅で自動改行し、完成ASSは20文字・最大2行へ整形していたため、タイトルがプレビュー5行、完成動画2行になる差があった。
- ASS生成はフック文字と通常字幕を独立生成しており、冒頭複製の有無にかかわらずフック表示中へ通常字幕が入る経路があった。

### 変更

- 字幕確認画面を`通常編集`と`ショート編集`のタブへ分離し、種類ごとの選択状態を保持する。通常は16:9、ショートは9:16の動画プレイヤーを表示する。
- ブラウザCSSの文字モックを出力確認から外し、完成書出しと同じASS、normal/short renderer、crop、フック複製、上下帯assetでMP4プレビューを生成する。
- source、clip範囲、修正字幕、文字style、render設定、帯画像byteを含むSHA-256でプレビュー版を管理する。変更clipだけ非同期再生成し、現在版と直前版だけを保持する。
- `queued / rendering / ready / failed`をAPIへ追加した。生成失敗時は画面から再試行でき、現在版がreadyになるまでclip確認・最終レンダリングを開始しない。
- RQ preview job IDをRQ 2.11の許可文字`[A-Za-z0-9_-]`だけで構成する。実Redisで失敗したpreviewも同じspecの再試行で復旧する。
- hook文字の表示終了と冒頭複製終了の遅い方まで通常字幕を抑止する。画面の再生中字幕表示と字幕行seekも同じ境界を使う。
- review APIのread-modify-writeをjob単位lockで直列化し、hook workerはsnapshot/CASで後着更新を保護する。frontendもGET世代管理とhook更新中poll停止で古い応答を破棄する。
- 旧completed reviewは保存内容や確認済み状態を変更せず、既存raw previewが残る場合だけ履歴表示へ一時利用する。
- 変更ファイル: `backend/app/render/subtitles_ass.py`、`backend/app/render/render_exact_review_preview.py`、
  `backend/app/jobs/subtitle_review_preview.py`、`backend/app/jobs/subtitle_review.py`、
  `backend/app/jobs/queue.py`、`backend/app/jobs/runner.py`、`backend/app/api/jobs.py`、
  `frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/lib/api.ts`、`frontend/lib/types.ts`、
  関連test、`README.md`、`STATUS.md`。

### 検証

- backend全体: `556 passed, 1 skipped`。既知のStarlette deprecation warning 1件のみ。
- backend ruff、compileall、pip依存整合、frontend typecheck / lint / production build、`git diff --check`: pass。
- GPU Composeでbackend / frontend / workerをbuild・再作成: pass。backend healthy、`/health=ok`、字幕確認URL`200`、worker GPU preflight`cuda / float16 / NVIDIA GeForce RTX 5070 Ti`。
- 実Redis/RQでpreview enqueueの許可文字エラーを再現し、job ID修正後にfailedからretryして2本とも`ready`まで完了: pass。
- 実job `job_95119645acb356865e436016d9896e0b`のshort preview: 2本とも`1080x1920`、SAR`1:1`、`yuv420p`。durationは`209.450000` / `23.166667`。
- 1本目の実ASS: Hook`0:00-0:03`、Title`0:03-3:29.44`、最初のSubtitle`0:04`。フック終了前のSubtitle`0件`、Hook / Title / Subtitleはいずれも最大2行。
- 抽出frameを目視し、フック中はHook文字だけ、フック後は2行タイトルと会話字幕になることを確認: pass。
- in-app browserで`通常編集（0本） / ショート編集（2本）`、short 1/2切替、実video`1080x1920`、spec hash付きURLを確認。再生でcurrentTimeが`0 -> 2.41秒`へ進み、フック中`1.42秒`の字幕現在位置表示は`0件`、最初の字幕行移動は`4.00秒`。
- 独立最終レビュー: P0/P1/P2なし。

### 未解決・制限

- 実jobはshortのみのため、通常clipの実ブラウザ再生は未確認。通常16:9の共通renderer経路とAPIは自動testで確認済み。
- 3分26秒のshort preview生成は実環境で約2分34秒。正確な完成表示を優先した動作で、生成中は旧版を確定対象にしない。
- ユーザー受入は未確認。

## 2026-08-17 Task 113 Chrome低高さ表示のプレイヤー操作列修正

### 目的

- Chromeの1870x937表示でも、字幕確認画面の`再生`、`先頭`、前後移動、音量、速度、全画面を初期表示から操作できるようにする。
- ショート9:16と通常16:9の両方で、下段の文字設定が動画操作列へ重ならないようにする。

### 観測事実・原因

- `2xl`表示の上段は`62vh`、画面高937pxでは約581pxだった。
- 変更前のショートは動画だけで360x640px、操作列を含むplayer shellは約821pxだった。通常も1024x576pxの動画と操作列で上段高を超えていた。
- root gridが固定高かつ`overflow-hidden`のため、後続の文字設定行が操作列の上へ描画されていた。`再生`と`先頭`の中心点には書体選択欄が載り、クリック不能だった。

### 変更

- player shellを中央カラム幅へ広げ、操作列が狭い縦動画幅で多段折返ししないようにした。
- ショート9:16は`2xl`時に上段高から利用可能な動画高を算出し、幅を`clamp(210px, ..., 360px)`で追従させる。
- 通常16:9も同じ上段高へ追従し、幅を`clamp(640px, ..., 1024px)`へ制限する。縦長画面では`max-width: 100%`を併用し、中央カラムより横へはみ出さない。
- Backend、preview生成、字幕描画、API契約は変更していない。
- 変更ファイル: `frontend/app/jobs/[jobId]/subtitles/page.tsx`、`STATUS.md`。

### 検証

- Chrome 1870x937、short job `job_95119645acb356865e436016d9896e0b`: 動画`261.52x464.91`、操作ボタン下端`677.91px`、下段設定開始`704.94px`、重なりなし。`再生`でcurrentTime増加、`先頭`で0秒付近へ復帰: pass。
- Chrome 1870x937、normal job `job_46dcde5c8b1a40f1af54029fab4d0ea3`: 動画`826.55x464.92`、操作ボタン下端`677.92px`、下段設定開始`704.94px`、重なりなし。`再生`と`先頭`の通常click: pass。
- Chrome 1536x864でshort / normalとも操作ボタンが下段設定より上にあり、中心点hit test: pass。
- Chrome 1536x1080 / 1600x1200でnormal動画が中央カラム内へ収まり、左右の映像欠けなし: pass。
- frontend typecheck / lint / production build、`git diff --check`: pass。

### 未解決・制限

- 1536px未満では従来どおり縦スクロール型レイアウトになる。
- ユーザー受入は未確認。

## 2026-08-17 Task 114 字幕スタイルの即時プレビュー復旧

### 目的

- 字幕確認画面で、保存前の文字色、縁取り色、文字サイズ、書体、X/Y位置、表示文言を操作直後に確認できるようにする。
- 完成書出しと同じMP4確認と、編集中の即時確認を混同しないようにする。

### 観測事実・原因

- 文字設定の入力値はfrontend draftへ更新され、保存buttonも有効化されていた。
- Task 112でCSS表示を完成確認から外した際、即時プレビュー自体も非表示になり、中央には保存済みexact MP4だけが残っていた。
- 保存後のstyle保存、spec hash更新、RQ再生成、ready後の動画URL更新経路は維持されていた。

### 変更

- 中央MP4を`保存済み・完成表示`と明示し、完成書出しと同じASS/rendererによる確認として維持する。
- 文字色欄の右へ`編集中プレビュー（即時反映）`を復活し、現在のdraftへ直接追従させる。`2xl`では色操作と横並び、狭幅では縦積みにする。
- review APIへ、clipごとの実効title/hook/subtitle style、既定style、preview寸法、改行上限、表示時間設定を追加する。個別styleが未設定でもjobの書体・サイズ・色・配置を即時表示へ使う。
- 最初に色だけを変更しても、実効書体・サイズ・縁・配置を維持する。任意`fontName`と`bold`を失わず保存し、位置変更時だけ`positionMode=explicit`、それ以外はjob layoutを継承する。
- タイトル/フックと字幕をbackend ASSと同じ改行規則で分割する。字幕はevent分割、隣接結合、最小表示時間補正、フック時間shiftまで同じ処理にし、現在時刻のeventだけ表示する。
- 1080x1920 / 1920x1080またはclip固有preview寸法を基準に、文字サイズ、縁取り、影、ASS alignment、X/Y位置を縮尺表示する。ショートの上下帯とdraftを含むタイトル出力状態も反映する。
- 個別設定解除時は保存済みoverrideではなくjob/layout既定値へ即時復帰し、その後の編集も既定値から開始する。
- 表示用layout座標は画面外値も保持し、書込override座標の既存制約は維持する。通常字幕の有効範囲に合わせ、個別styleの文字サイズ下限を12pxへ整合する。
- 保存buttonを`保存して完成表示を更新`へ変更した。
- 変更ファイル: `backend/app/candidates/merge_boundaries.py`、`backend/app/render/subtitles_ass.py`、
  `backend/app/jobs/subtitle_review.py`、`backend/app/api/jobs.py`、`backend/app/jobs/runner.py`、
  `frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/components/ClipTextStyleEditor.tsx`、
  `frontend/lib/clipTextStyle.ts`、`frontend/lib/subtitlePreview.ts`、`frontend/lib/types.ts`、関連test、`STATUS.md`。

### 検証

- backend全体: `564 passed, 1 skipped`。関連3ファイル: `116 passed`。backend ruff: pass。
- frontend typecheck / lint / production build、`git diff --check`: pass。
- `x=187.5 / y=-150`のlayout座標、12px通常字幕のcontent PATCHとASS維持、個別設定解除後の既定値seedを自動testで確認: pass。
- 33文字字幕はfrontend/backendともevent長`[32, 1]`、改行`[16, 16]`で一致。split、merge、表示時間補正、hook shiftのfixture比較: pass。
- style変更でexact preview spec hashが変わり、保存後に完成表示が再生成されることを確認: pass。
- GPU Composeでbackend / worker / frontendをbuild・再作成: pass。`/health=ok`、worker GPU preflightは`cuda / float16 / NVIDIA GeForce RTX 5070 Ti`。
- 実job `job_95119645acb356865e436016d9896e0b`で、フック文字サイズ`88 -> 100`、文字色`白 -> 黄`、Y位置`650 -> 960`が保存前に即時反映されることを目視確認: pass。
- 同画面で個別設定解除後に`Noto Sans CJK JP Bold / 88px / 黒縁3 / Y360`へ即時復帰し、次の色変更でも旧overrideが復活しないことを確認: pass。
- 検証後、ユーザー画面の未保存フック設定（851チカラヅヨク、白文字・白縁、88px、縁5、中央、Y650）を保存せず復元した。
- 独立最終レビュー: P0/P1/P2なし。

### 未解決・制限

- 即時側はブラウザ描画、中央MP4はlibass/FFmpeg描画。改行、基準解像度、書体、サイズ、縁、影、位置を同じ値へ揃えたが、glyph rasterizationの微差は中央の`保存済み・完成表示`を正とする。
- 保存後にexact MP4が再生成されるまでの所要時間はclip長に依存する。
- ユーザー受入は未確認。

## 2026-08-18 Task 115 メインプレイヤーへの即時文字編集統合

### 目的

- 小さい別枠の即時プレビューを廃止し、メインプレイヤー内で文字色、サイズ、位置、文言の未保存変更を即時確認できるようにする。
- 即時表示と保存済み完成表示で同じ9:16 / 16:9の表示枠を使い、見切れ方と画面サイズの比較を直接行えるようにする。

### 観測事実・原因

- 変更前のメインプレイヤーは文字焼込済みexact MP4、即時側は小さいCSSプレビューだったため、表示枠と縮尺が異なっていた。
- exact MP4へCSS文字を重ねると保存済み文字と二重表示になる。入力ごとに全編MP4を再生成すると、長いclipでは即時編集にならない。
- 即時側の枠が小さく、出力フレーム外を隠す境界もメインと異なったため、添付比較では即時側だけ大きく見切れていた。

### 変更

- exact完成MP4とは別に、同じnormal/short renderer、crop、フック複製、上下帯を使い、文字だけ焼かないlive base MP4を生成する。
- メインプレイヤーの既定表示を`編集中・即時反映`とし、live base上へ未保存draftのタイトル、フック、字幕を描画する。
- 同じメインプレイヤーの`保存済み表示`でexact完成MP4へ切り替え、`編集表示へ戻る`で即時表示へ戻す。
- title / hookは最大20文字・最大2行、字幕はclip固有の改行・event分割・表示時間・フック抑止規則を使う。文字サイズ、縁、影、ASS alignment、X/Yを出力解像度基準で縮尺する。
- 9:16 / 16:9の実フレームへ`overflow-hidden`を適用し、即時文字も完成表示と同じ映像境界で見切れるようにする。
- live baseは文字・style変更ではhashを変えず、crop、layout、フック映像、帯など映像構成の変更時だけ再生成する。
- 字幕確認APIへlive preview URL / spec hashと固定hash版MP4配信routeを追加する。既存exact previewは確認・最終レンダリングの正として維持する。
- 変更ファイル: `backend/app/render/render_exact_review_preview.py`、`backend/app/jobs/subtitle_review.py`、
  `backend/app/jobs/subtitle_review_preview.py`、`backend/app/jobs/runner.py`、`backend/app/api/jobs.py`、
  `frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/components/ClipTextStyleEditor.tsx`、
  `frontend/lib/types.ts`、関連test、`README.md`、`STATUS.md`。

### 検証

- backend対象test: `19 passed`。backend全体: `565 passed, 1 skipped`。backend ruff: pass。
- frontend typecheck / lint / production build、`git diff --check`: pass。
- GPU Composeでbackend / worker / frontendをbuild・再作成: pass。`/health=ok`、worker GPU preflightは`cuda / float16 / NVIDIA GeForce RTX 5070 Ti`。
- 実job `job_95119645acb356865e436016d9896e0b`のshort 2本でlive base生成完了、`LIVE_READY=2/2`。
- Chrome実画面でメインの動画sourceがlive endpointになり、別枠即時プレビューが0件であることを確認: pass。
- title文字サイズ`52 -> 80`でメイン表示が`17.33px -> 26.67px`へ即時変化し、live動画URLが変わらないことを確認: pass。
- titleはメインの9:16枠内で2行、字幕も2行で表示し、枠外を隠すことを確認: pass。
- `保存済み表示`でexact endpoint、`編集表示へ戻る`でlive endpointへ切り替わることを確認: pass。
- メイン再生でcurrentTimeが`0 -> 1.107秒`へ進むことを確認: pass。
- 検証後、ユーザーの未保存title設定（Dela Gothic One、52px、縁1、X50%、Y9%）を保存せず復元した。

### 未解決・制限

- 即時表示はブラウザ描画、保存済み完成表示はFFmpeg/libass描画のため、glyph rasterizationには微差が残る。最終出力の正は`保存済み・完成表示`。
- 旧jobを初めて開く際はlive baseを1回生成するため待機が発生する。
- ユーザー受入は未確認。

## 2026-08-18 Task 116 即時確認後の一括OK保存

### 目的

- 文字調整の途中で保存・完成プレビュー生成を挟まず、メインの即時表示を見ながら連続編集できるようにする。
- 選択clipの確認が終わった時だけ`OK`を押し、タイトル、フック、文字設定、修正字幕を1回で保存する。

### 観測事実・原因

- 変更前はclip内容の保存と各字幕の保存が別操作で、それぞれexact完成プレビューを再生成した。
- clip確認にはexact完成プレビューの生成完了が必要だったため、`保存 -> 動画生成待ち -> 確認`の2段階になっていた。
- メインのlive表示で未保存draftを確認できても、操作導線が従来の個別保存・待機を要求していた。

### 変更

- `POST /api/jobs/{jobId}/subtitle-review/clips/{clipId}/apply`を追加した。
- 選択clipのtitle、hook、3種の文字style、修正された字幕segmentをdocument lock内で一括更新し、render contract再計算、preview refresh、clip確認を1 transactionで行う。
- 複数segment変更でもaffected clipを集約し、clipごとのexact previewを最後に1回だけqueueする。対象clip外のsegment IDと重複IDは拒否する。
- 画面から`保存して完成表示を更新`と各行の`この字幕を保存`を削除した。編集中はfrontend draftだけを変更し、メインlive表示へ即時反映する。
- 右下を`この内容でOK（保存して次へ）`へ変更した。OK後は次の未確認clipへ進み、exact完成プレビューはバックグラウンド更新する。
- clipはOK時点で確認済みにし、最終レンダリングだけは従来どおり全exact previewのreadyを待つ。
- saved exact表示中に文字・字幕を変更した場合は自動でlive編集表示へ戻す。
- 変更ファイル: `backend/app/schemas.py`、`backend/app/api/jobs.py`、
  `backend/tests/test_api_routes.py`、`frontend/lib/api.ts`、
  `frontend/app/jobs/[jobId]/subtitles/page.tsx`、`README.md`、`STATUS.md`。

### 検証

- 新APIの一括内容・字幕保存、即時確認済み化、preview queue 1回、artifact永続化、対象外segment拒否: pass。
- backend API test: `72 passed`。backend全体: `567 passed, 1 skipped`。既知のStarlette deprecation warning 1件のみ。
- backend ruff、frontend typecheck / lint / production build、`git diff --check`: pass。
- Docker backend / worker / frontendをbuild・再作成し、backend healthy、`/health=ok`: pass。
- 実画面で個別字幕保存button`0件`、個別完成表示更新button`0件`、一括OK button`1件`: pass。
- 実画面で文字サイズを変更しても`subtitle_review.json`の更新時刻・サイズとpreview artifact数が変わらないことを確認: pass。
- 実画面の一括OKはユーザーdraftを保存するため押していない。検証後、未保存title文字サイズを`52`、再生位置を`0`へ戻した。

### 未解決・制限

- フック映像の変更は映像構成自体が変わるため、従来どおり専用preview更新が必要。
- 上下帯はjob全体の映像構成設定のため、従来どおり設定変更時に保存・live base更新する。
- ユーザー受入は未確認。

## 2026-08-22 Task 117 即時文字プレビューのlibass寸法補正

### 目的

- メインの即時プレビューとFFmpeg/libass完成動画で、タイトル、冒頭フック、通常字幕の文字サイズ・改行間隔・位置を揃える。
- 保存や動画再生成を挟まず、3種の文字設定を同じ基準で即時確認できる状態を維持する。

### 観測事実・原因

- 同じフォントファイルとASS `Fontsize`を使っても、CSSはem square、libassはフォントのWindows ascent/descentを基準に文字を拡大するため、Dela Gothic Oneと源ノ角ゴシックは即時側が約1.45倍に見えていた。
- 851チカラヅヨクはemとWindows ascent/descentが同寸法のため、Dela等と同じ一律係数を掛けると逆に小さくなる。
- X/Y位置、ASS alignment、改行条件は既に一致しており、主因はフォントごとの文字寸法と行ピッチだった。

### 変更

- `frontend/lib/clipTextStyle.ts`へ、`unitsPerEm / (usWinAscent + usWinDescent)`からCSS文字サイズ係数と行高を返す共通ASSプレビューメトリクスを追加した。
- `frontend/components/ClipTextStyleEditor.tsx`のメイン即時overlayと小型style preview、`frontend/components/SubtitleStylePreview.tsx`のアップロード設定previewが同じ補正を使用するよう変更した。
- 共通overlayを使うタイトル、フック、字幕の全targetへ同じ変換を適用した。
- 縁取り幅と影はPlayResピクセル基準のため補正せず、従来の出力幅連動を維持した。
- 変更ファイル: `frontend/lib/clipTextStyle.ts`、`frontend/components/ClipTextStyleEditor.tsx`、`frontend/components/SubtitleStylePreview.tsx`、`STATUS.md`。

### 検証

- frontend typecheck / lint / production build: pass。
- Docker frontendをbuild・再作成し、実画面へ反映: pass。
- 同一テキストの完成ASS / 補正後CSSの画素bbox比較:
  - Delaタイトル: `724x62 / 719x62`。
  - 源ノ角ゴシック字幕: `628x102 / 625x101`。
  - 851フック: `978x181 / 978x179`。
- 実job `job_f2edbd8dc3e842b8ac9119b51ad2427e`の360x640メイン枠で、DelaタイトルのCSS幅`241.06px`=`723.19/1080px`、タイトル中心`X180/Y80`、字幕中心`X180/Y320`を確認した。完成側の基準位置`X540/Y240`、`X540/Y960`と一致。
- `/upload`の旧字幕style previewでも固定clampを使わず、ASS補正後の`font-size 10.14px / line-height 14.68px / stroke 0.97px`が適用されることを確認した。
- 独立監査と再照合で、3書体とも幅・高さ誤差`1.1%以下`、位置誤差`1px以下`。一律係数ではなくフォント別補正が必要との結論で一致した。

### 未解決・制限

- workerのシステムフォントを使う`Noto Sans CJK JP`、`Noto Serif CJK JP`、`Noto Sans Mono CJK JP`は同一ファイルをfrontendへ同梱していないため、ブラウザ環境によってfallback差が残る。今回使用中のDela、851、源ノ角は同一ファイルで確認済み。
- その他の同梱font presetはメトリクス値を反映したが、全presetの実画像一対一回帰は未確認。
- ユーザー受入は未確認。

## 2026-08-23 Task 118 通常切り抜きのタイトル・冒頭フック編集

### 目的

- 通常切り抜きでも、結果タイトル、冒頭フック文字、フック文字スタイル、冒頭へ複製する見せ場を編集し、プレビューと最終MP4へ反映する。

### 観測事実・原因

- 通常タイトルは字幕確認画面で編集可能だったが、結果画面・JSON用であり、通常動画内へは焼き込まない仕様だった。
- 冒頭フック文字と複製映像は、UI、保存model、API、worker、ASS、normal rendererの全層でshort限定だった。
- 起動中のbackend / worker / frontendはソースのbind mountがない旧imageで、ソース変更だけでは画面へ反映されなかった。

### 変更

- Candidate、clip plan、subtitle reviewでnormalの`hookText`、`hookStyle`、`hookSceneStart/End`を許可した。0.5〜3秒・clip内の検証は維持し、`shortMaxDuration`はshortだけに適用する。
- clip plan / subtitle review workerがclip typeに応じて`normalClips`または`shorts`を更新するよう変更した。
- normal rendererへフック映像・音声と本編のconcatを追加し、ASS字幕をフック映像尺だけ後方へ移動する。フック文字表示中は通常字幕を抑制する。
- normal exact/live previewへフック映像時刻を渡し、renderer versionをv2へ更新した。
- clip選定画面と字幕確認画面でnormalにもフック映像editorを表示した。字幕確認ではタイトル、フック文字、表示秒数、フック文字styleを編集できる。
- normalタイトル欄を`タイトル（結果画面・JSON用）`とし、通常動画内へ焼き込まないことを明記した。
- normal用フックの初期styleを1920x1080基準の76px・Y8%へ揃え、内蔵style previewの対象もeditorと一致させた。
- normal export metadataへ完成尺、本編尺、フック文字・時刻・尺・render有無を追加した。
- 変更ファイル: `backend/app/candidates/merge_boundaries.py`、`backend/app/jobs/clip_plan.py`、`backend/app/jobs/subtitle_review.py`、`backend/app/jobs/runner.py`、`backend/app/api/jobs.py`、`backend/app/render/subtitles_ass.py`、`backend/app/render/render_normal.py`、`backend/app/render/render_exact_review_preview.py`、`frontend/app/jobs/[jobId]/clips/page.tsx`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/components/ClipHookSceneEditor.tsx`、`frontend/components/ClipTextStyleEditor.tsx`、`frontend/lib/clipTextStyle.ts`、関連test、`STATUS.md`。

### 検証

- backend対象test: `82 passed, 1 skipped`。backend全体: `572 passed, 1 skipped`。既知のStarlette deprecation warning 1件のみ。
- backend ruff、frontend typecheck / lint / production build: pass。
- 実`normal_02.mp4`を入力にnormal rendererを実行し、1秒フック＋5秒本編が`6.000秒`、映像H.264・音声AACで生成されることを`ffprobe`で確認: pass。確認用artifactは削除した。
- GPU Composeでbackend / worker / frontendをbuild・再作成し、backend healthy、`/health=ok`: pass。
- 実job `job_91fb0c58f74443348b0653fe33fb051b`の通常編集画面で、タイトル欄、冒頭フック欄、表示秒数、フックstyle対象、通常用76px styleを確認: pass。
- 冒頭フック文字を未保存draftへ入力し、メイン即時表示へ反映されることを確認した。検証後はreloadし、保存せず破棄した。

### 未解決・制限

- 通常タイトルは結果画面・JSON用。通常動画内へは焼き込まない。
- 実jobでフック映像を保存して最終出力へ昇格する操作は、ユーザーの編集中jobを変更するため未実施。domain、API/worker、実FFmpegを分離して検証済み。
- ユーザー受入は未確認。

## 2026-08-24 Task 119 通常切り抜きの動画内タイトル編集

### 目的

- 通常切り抜きのタイトル本文と文字設定を編集し、メインプレビュー、完成プレビュー、最終MP4へ同じ内容で反映する。
- Task 118で残っていた「結果画面・JSON用のみ」の制限を解消する。

### 観測事実・原因

- 通常タイトル本文の入力欄は存在したが、`titleStyle`の保存、タイトルstyle対象、ライブ表示、ASS生成、normal rendererの動画内描画がshort限定だった。
- そのためタイトル文字列だけ編集でき、通常動画上のタイトルの書体・サイズ・色・位置は編集できなかった。

### 変更

- 通常編集にも`タイトル / フック / 字幕`の3つの文字style対象を表示し、初期対象をタイトルへ変更した。
- 通常タイトルの既定styleを1920x1080基準の76px・Y8%とし、個別の書体・サイズ・色・縁・X/Y位置を保存する。
- 通常タイトルをメインの即時表示、exact完成プレビュー、最終normal MP4のASSへ反映する。
- normal exact previewは古い`overlay_title`ではなく、字幕確認で編集した`title`を使用する。shortの`overlay_title`方針は維持する。
- タイトルはフック文字または複製フック映像の終了後から表示し、冒頭要素との重なりを防止する。
- review contractとnormal export metadataへタイトル表示予定・描画済み・styleを記録し、結果画面でも状態を表示する。
- 変更ファイル: `backend/app/jobs/subtitle_review.py`、`backend/app/render/subtitles_ass.py`、`backend/app/render/render_exact_review_preview.py`、`backend/app/render/render_normal.py`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/components/ClipTextStyleEditor.tsx`、`frontend/components/ResultVideoCard.tsx`、`frontend/lib/clipTextStyle.ts`、関連test、`STATUS.md`。

### 検証

- backend対象test: `135 passed`。backend全体: `573 passed, 1 skipped`。既知のStarlette deprecation warning 1件のみ。
- backend ruff、frontend typecheck / lint / production build: pass。
- GPU Composeでbackend / worker / frontendをbuild・再作成し、backend healthy、`/health=ok`: pass。
- 実job `job_91fb0c58f74443348b0653fe33fb051b`の通常編集画面で、`表示タイトル`、`タイトル / フック / 字幕`、通常タイトル76pxを確認: pass。
- 通常タイトルを未保存draftへ変更し、一覧・編集状態へ即時反映されることを確認した。reload後に元へ戻り、ユーザーjobは未変更。
- 実`normal_02.mp4`から5秒を再書き出しし、日本語タイトルが1920x1080 MP4上部へ焼き込まれることをASS、`ffprobe`、抽出フレームで確認: pass。確認用artifactは削除した。

### 未解決・制限

- 実jobのOK保存はユーザーの編集中データを変更するため未実施。保存contract、API、renderer、実FFmpegを分離して検証済み。
- ユーザー受入は未確認。

## 2026-08-24 Task 120 通常切り抜き用YouTubeサムネ2枚

### 目的

- `normal_01.mp4`と`normal_02.mp4`の内容に合うYouTubeサムネを各1枚作成する。

### 変更

- 実動画から表情候補を抽出し、`normal_01`は「まだ本編／始まってない」、`normal_02`は「痛風／オールバック」を主見出しにした。
- 儒烏風亭らでんの髪色・衣装・表情を参照し、和風の濃緑・黒・金を基調に人物右、文字左で構成した。
- 追加ファイル: `youtube/thumbnails/normal_01_youtube_thumbnail.jpg`、`youtube/thumbnails/normal_02_youtube_thumbnail.jpg`。

### 検証

- 2枚とも`1280x720`、JPEG。容量は`269327 bytes`、`297993 bytes`。
- 指定文字の誤字なし、人物の顔を文字が覆わないこと、スマホ向けの文字サイズと安全余白を目視確認: pass。

### 未解決・制限

- ユーザー受入は未確認。

## 2026-08-24 Task 121 normal_01の縦型ショート切り出し

### 目的

- 通常切り抜き`normal_01.mp4`から、休肝日スパチャと「本編始まってないね」のオチを縦型ショートへ再編集する。

### 変更

- 元クリップ内`99.55〜122.90秒`を採用し、23.35秒へ圧縮した。
- 9:16人物寄せcrop、冒頭フック「肝臓からの圧が強い。」、発言同期の大字幕、旧横字幕を隠す下部字幕帯を追加した。
- 音声速度`1.0`、音量正規化なし。元音声の間とテンポを維持した。
- 追加ファイル: `youtube/shorts/normal_01_main_not_started_short.mp4`、`normal_01_main_not_started_short.ass`、`normal_01_main_not_started_short_storyboard.json`、`normal_01_main_not_started_short_preview_frames/*.png`。

### 検証

- MP4: H.264/AAC、`1080x1920`、`30fps`、`23.366667秒`、音声`48kHz stereo`、`9753709 bytes`。
- 字幕bbox: 全11場面pass。最大幅`920px`、安全幅`940px`以内。
- 冒頭、2行字幕、最長字幕、オチの4 PNGを抽出し、文字見切れ、顔被り、旧字幕重複なしを目視確認: pass。
- blackdetect: 該当なし。

### 未解決・制限

- ユーザー受入は未確認。

## 2026-08-25 Task 122 元動画から手動作成

### 目的

- アップロードした元動画を自動選定せず、そのまま確認しながら通常切り抜きとショートを手作業で作成する。
- 自動作成・完成動画の再編集とは独立した入口にし、字幕も自動・なし・手入力から選べるようにする。

### 観測事実・原因

- 変更前は新規作成jobが必ず文字起こし、候補生成、自動選定を通り、元動画だけを編集画面へ渡す経路がなかった。
- 既存の任意時間指定は自動処理への補助条件であり、元動画からclipを追加・削除する手動編集契約ではなかった。
- 元動画をそのままvideo要素へ渡すと、MKVやH.265 MP4などブラウザ非対応形式を再生できない。

### 変更

- `/upload`へ`手動作成`を追加した。動画選択後は自動候補生成を行わず、手動編集用jobを作成する。
- 初回workerは動画情報を確認し、元形式に関係なくH.264/yuv420p/AACの編集用MP4を生成する。無音源は`-an`で生成する。
- 切り抜き予定画面へ手動editorを追加した。元動画の再生位置から開始・終了を取得し、分・秒入力、±1秒/±5秒、範囲再生で調整できる。
- 通常・ショートの追加、更新、削除、タイトル、冒頭フック文字、0.5〜3秒の見せ場複製を同じ画面で編集できる。通常12本、ショート24本を上限とする。
- 確定後は同じjobを再queueし、手動のclip ID・範囲・タイトル・フックを保持したまま既存の字幕確認・書き出しへ接続する。
- 手動字幕は`自動字幕 / 字幕なし / 手入力`を追加した。手入力はclipごとに独立した1件の字幕欄を字幕確認画面へ作る。字幕なしでもタイトル、フック、上下帯の確認は維持する。
- 音声なし動画は自動文字起こしを要求しない。音声なしでフック映像を複製する操作は、現行concat仕様に合わせて422で明示的に拒否する。
- 自動作成と完成動画の再編集は従来経路を維持した。
- 主な変更ファイル: `backend/app/schemas.py`、`backend/app/api/jobs.py`、`backend/app/jobs/manual_workflow.py`、`backend/app/jobs/runner.py`、`backend/app/jobs/clip_plan.py`、`backend/app/jobs/subtitle_review.py`、`backend/app/render/render_manual_source_proxy.py`、`backend/app/render/render_review_preview.py`、`frontend/app/upload/page.tsx`、`frontend/app/jobs/[jobId]/clips/page.tsx`、`frontend/components/ManualClipPlanEditor.tsx`、`frontend/lib/api.ts`、`frontend/lib/types.ts`、関連test、`README.md`、`STATUS.md`。

### 検証

- backend全体: `582 passed, 1 skipped`。backend ruff、compile/import: pass。
- frontend typecheck、lint、production build: pass。
- `git diff --check`: pass。改行コード変換のwarningのみ。
- in-app browserのローカル開発画面で`新しい動画を作成 / 手動作成 / 完成動画を再編集`の3入口、手動時の自動設定非表示、`自動字幕 / 字幕なし / 手入力`の切替と説明変更を確認: pass。
- GPU Composeでbackend / worker / frontendをbuild・再作成: pass。4 service running、`/health=ok`、workerは`cuda / float16 / NVIDIA GeForce RTX 5070 Ti`、fallbackなし。
- Docker内の実FFmpegでMKV入力から編集用MP4を生成し、H.264、`960x540`、yuv420p、30fps、AAC、2.000秒を`ffprobe`で確認: pass。さらに`1000x777`の無音MKVを`694x540`の偶数寸法H.264へ変換できることを確認した。確認用artifactは一時領域から削除済み。
- 再作成後の`http://localhost:3000/upload`で手動作成画面を目視確認し、3入口と3字幕modeのpressed状態・説明切替を再確認: pass。
- 独立レビューで指摘されたブラウザ非対応元動画と字幕mode不足を、常時H.264編集用MP4生成と3字幕modeで補完した。最終再レビュー: P0/P1なし、focused test `9 passed`。

### 未解決・制限

- 手入力字幕はclip全体に対応する1件から開始する。複数区間へ分割する場合は字幕確認画面で既存の字幕編集単位を拡張する必要がある。
- 音声なし動画のフック映像複製は未対応。通常・ショート本編とタイトル・字幕なし書き出しは対象内。
- 許可済み実動画による`upload -> worker -> 手動clip作成 -> 字幕確認 -> 最終MP4/ZIP`の全実E2Eは未確認。
- ユーザー受入は未確認。

## 2026-08-25 Task 123 派生ショート専用実装の撤回

### 目的

- 直前に追加した「完成済み通常clipから専用の手動ショート子jobを作る」実装だけを撤回し、Task 122の元動画手動作成を維持する。

### 変更

- 結果画面の手動ショート化ボタン、専用API、子job生成、元clip基準の時刻offset、字幕seed、ショート限定制約を削除した。
- 手動作成editorは、元動画から通常clipとショートの両方を追加できるTask 122の状態へ戻した。
- 派生ショート専用のtestとREADME記述を削除した。

### 検証

- backend全体: `582 passed, 1 skipped`。backend ruff、compile/import: pass。
- frontend typecheck、lint、production build: pass。
- 派生ショート専用識別子の実装コード残存: 0件。`git diff --check`: pass。改行コード変換のwarningのみ。
- GPU Composeでbackend / worker / frontendをbuild・再作成: pass。4 service running、`/health=ok`、frontend HTTP 200。
- worker GPU preflight: `cuda / float16 / NVIDIA GeForce RTX 5070 Ti`、fallbackなし。

### 未解決・制限

- 完成動画の手動再編集で、焼き込み済み字幕を除去できない問題は未解決。代替仕様は未実装。
- Task 122の許可済み実動画による全実E2Eとユーザー受入は未確認。

## 2026-08-25 Task 124 字幕確認中のAIタイトル・フック選定

### 目的

- 仮完成動画を外部へ渡していたタイトル・冒頭フック選定を、字幕確認から最終レンダリングまでの間へ組み込む。
- 既存の`OPENAI_API_KEY`を再利用し、通常・ショートの公開用タイトル、動画内タイトル、フック文字、見せ場区間を3案から選べるようにする。

### 観測事実・原因

- 変更前は字幕確認画面にAI候補生成がなく、タイトル・フックを選定するには一度動画を完成させる必要があった。
- 旧subtitle reviewでは`title`が公開タイトルを兼ね、shortの`overlay_title`と意味が分かれていたため、単純なfield追加では既存動画内タイトルを上書きする互換性問題があった。
- RQ artifactだけが`queued/generating`で残ると、Redis再起動やworker停止後にUIが永久待機する経路があった。

### 変更

- 字幕確認画面の`タイトル・フック`欄へ`AI タイトル・フック案`を追加した。明示ボタンを押した時だけ3案を生成し、案のフック区間をメイン動画で再生できる。
- AI案は公開用タイトル、動画内タイトル、冒頭フック文字、1.5〜3.0秒のclip相対見せ場区間、選定理由を返す。`フックなし`も選択できる。
- 案を選んだ時点ではブラウザの下書きだけを更新し、既存の右下`OK`で字幕・タイトル・フックをまとめて保存する。AI失敗時も手入力を継続できる。
- 現在の未保存字幕全文と、選択clipからFFmpegで抽出した代表JPEG 4枚をOpenAI Responses APIへ送る。動画本体、動画URL、保存path、Cookie、認証情報、元動画絶対時刻は送信しない。`store=false`を指定する。
- `publicationTitle`と動画内`title/overlay_title`を分離し、通常・ショートのlive preview、exact preview、完成MP4、結果metadataへ同じ意味で反映する。旧artifactでは既存shortの`overlay_title`を保持する。
- 生成はRQで非同期実行する。入力hashとraw字幕hashでcache・再読込を照合し、字幕変更後の古い案は適用禁止にした。
- `queued/generating` artifactはGET pollingとPOSTから冪等に再enqueueする。生存中の同一RQ jobは重複させず、字幕確認完了後はworkerのprovider送信前・結果保存前に中止する。
- OpenAI SDK内蔵retryを無効化し、120秒timeoutと外側最大3retryへ一本化した。失敗してもメインJob状態は変更しない。
- 主な変更ファイル: `backend/app/scoring/title_hook_suggestions.py`、`backend/app/jobs/title_hook_suggestions.py`、`backend/app/api/jobs.py`、`backend/app/jobs/queue.py`、`backend/app/jobs/subtitle_review.py`、通常・exact renderer、`frontend/components/TitleHookSuggestionPanel.tsx`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、API型、関連test、`README.md`、`STATUS.md`。

### 検証

- backend対象test: `46 passed`。backend全体: `612 passed, 1 skipped`。ruff、compile/import、`git diff --check -- backend`: pass。
- frontend typecheck、lint、production build: pass。
- GPU Composeでbackend / worker / frontendをbuild・再作成し、backend healthy、`/health=ok`、frontend HTTP 200: pass。
- worker GPU preflight: `cuda / float16 / NVIDIA GeForce RTX 5070 Ti`、fallbackなし。
- 合成4秒動画を使い、実FFmpegで代表frame 4枚を抽出し、既存`OPENAI_API_KEY`による実Responses APIで3案を取得した。strict contractは3案すべてpass。ユーザー動画は送信していない。確認用artifactは削除済み。
- 1821x1272のin-app browserで字幕確認画面を再読込し、公開用/動画内タイトル、AI生成ボタン、フックなし、既存メインpreviewとの配置を確認した。console warning/error 0件。ユーザーJobの生成・保存操作は未実施。
- 独立レビューで指摘された旧overlay互換、SDK二重retry、raw字幕cache、RQ消失時の停止、確認完了後の不要送信を修正し、各再現testを追加した。最終再レビュー: P0/P1/P2なし。

### 未解決・制限

- ユーザーの実Jobを変更する`生成`、案の適用、`OK`保存は未実施。HTTP→Redis→worker→画面反映の実Job E2Eとユーザー受入は未確認。
- AI候補はAPI利用料が発生する明示操作。ChatGPT/Codexのログインではなく、既存の`OPENAI_API_KEY`を使用する。

## 2026-08-27 Task 125 手動ショートの画角変更と自動人物優先

### 目的

- 完成clipを元に手動作成したショートでも、字幕確認画面から人物アップ、中央拡大、全体表示を選び、完成動画と同じ画角で確認できるようにする。

### 観測事実・原因

- 対象Jobは`shortLayout=auto`、1920x1080、字幕なしだった。
- 顔7件が横に広い判定になり、話者追跡が使えない場合、強い被写体検出があっても`blur_background`へ落ちていた。
- レンダラーは4種類の画角に対応済みだったが、字幕確認Document/API/UIに`shortLayout`の変更導線がなかった。

### 変更

- 字幕確認のメインpreview上部へ`ショート画角`を追加した。`自動（人物を優先） / 人物アップ（顔を追従） / 中央を拡大 / 全体表示（ぼかし背景）`を選べる。
- 選択値をJob設定とsubtitle review artifactへ保存し、対象ショートpreviewを自動再生成する。最終レンダリングも同じJob設定を使用する。
- 初回の字幕確認DocumentにもJobの`shortLayout`を保持し、旧artifactは`auto`で読み込む。
- `auto`で顔群が広い場合、話者に続いて人物・被写体信号も評価し、信頼できる対象があれば縦型cropを優先する。
- 新規作成画面にも既存Backendの`face_tracking_crop`を`人物アップ（顔を追従）`として追加した。
- 主な変更ファイル: `backend/app/schemas.py`、`backend/app/api/jobs.py`、`backend/app/jobs/runner.py`、`backend/app/jobs/subtitle_review.py`、`backend/app/render/crop_strategy.py`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/components/SettingsPanel.tsx`、`frontend/lib/types.ts`、関連test、`README.md`、`STATUS.md`。

### 検証

- backend全test: `614 passed, 1 skipped, 1 warning`。全ruff: pass。`git diff --check`: errorなし。
- frontend: typecheck / lint / production build: pass。
- 実素材の読み取り専用判定で、顔7件を確認した。`人物アップ（顔を追従）`指定時は`face_tracking_crop`が先頭戦略になることを確認した。`auto`は同素材では`ambiguous_subject_signal`により全体表示のまま。
- Dockerのbackend/frontendだけを再build・再起動し、backend health=`ok`、frontend HTTP=`200`を確認した。workerは停止・再起動していない。
- 実ブラウザで字幕確認画面に4種類の`ショート画角`が表示され、メインpreview上部へ収まることを確認した。

### 未解決・制限

- `人物アップ（顔を追従）`は顔検出不能時に安全なfallbackを使う。人物をクリックして指定する手動パン操作は未実装。
- 現状の画角設定はJob内の全ショート共通。clipごとの個別画角は未実装。
- ユーザーJobの設定変更は行っていない。画面から`人物アップ（顔を追従）`を選択後の実previewと完成動画はユーザー受入未確認。

## 2026-08-27 Task 126 完成動画の1本限定再編集・通常からショートへの変換

### 目的

- 完成結果から選択した動画1本だけを再編集し、元Jobの通常2本・ショート3本を強制的に再編集する挙動を解消する。
- 完成した通常動画を、再編集画面でショートへ切り替えて画角・字幕・タイトル・フックを編集できるようにする。

### 観測事実・原因

- 変更前の`matchedClipId`は字幕確認画面の初期選択にしか使われず、Backendは元Job全体のsubtitle reviewを再開して全clipを未確認へ戻していた。
- 同じJob内で対象clipだけを差し替えると、出力名・ZIP・review履歴・selectionの衝突が発生するため、元Jobを維持したまま1本専用の再編集Jobへ分離した。

### 変更

- 結果画面の各動画へ`この動画だけ再編集`を追加した。選択時に元Jobを変更せず、対象clip 1本だけを含む子Jobを作成する。
- 完成MP4をアップロードする再編集導線も、照合した対象clip 1本だけの子Jobを作る方式へ変更した。
- 子Jobには選択clipに必要なtranscript、candidate、selection、subtitle reviewだけを再構築し、親Jobの動画・Export・ZIP・確認状態を変更しない。
- 通常clipの1本再編集画面へ`範囲を決めてショート化`を追加した。短いclipは全体、長いclipは現在の再生位置から最大60秒を初期値にし、開始・終了をclip内の秒数で調整できる。
- 冒頭複製を含む合計を`shortMaxDuration`以内に検証する。選択範囲外の字幕を除外し、見せ場映像が範囲外なら複製だけを解除する。
- 変換前に未保存の字幕・公開タイトル・動画内タイトル・フック・文字サイズ・色・位置を自動保存し、short用の解像度・preview contractだけを再計算する。
- candidate、selection、Job設定、候補summaryをnormal 0 / short 1へ同期する。途中失敗時はartifactとDB設定を変換前へ戻す。
- 子Jobは再編集レンダーとして扱い、初回書き出しに失敗してもterminal failedにせず字幕確認へ戻して再試行できる。
- 変換後はshort用の画角、字幕、タイトル、フック、帯設定を使ってpreview・最終レンダリングできる。
- 主な変更ファイル: `backend/app/api/jobs.py`、`backend/app/jobs/subtitle_review.py`、`backend/app/schemas.py`、`backend/tests/test_api_routes.py`、`frontend/app/results/[jobId]/page.tsx`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/components/ResultVideoCard.tsx`、`frontend/components/ShortConversionEditor.tsx`、`frontend/lib/api.ts`、`frontend/lib/types.ts`、`STATUS.md`。

### 検証

- backend対象test: `test_api_routes.py=80 passed`。
- backend全test: `622 passed, 1 skipped`。全ruff: pass。
- frontend: typecheck / lint / production build: pass。
- 複数clipの親Jobから1本だけの子Jobが作られること、親Jobがcompletedのまま変化しないこと、100秒の通常clip内から50秒をshort化できること、編集済み字幕・タイトル・フック・3種類の文字styleを保持することをAPI testで確認した。
- 変換途中の書込み失敗で全artifactとDB設定が元へ戻ること、Export 0件の子Jobでレンダー失敗後に字幕確認へ復帰できることをtestで確認した。
- 処理待ち・実行中がともに0件の状態でGPU Composeのbackend / worker / frontendをbuild・再作成した。backend health=`ok`、frontend HTTP=`200`、worker=`cuda / float16 / NVIDIA GeForce RTX 5070 Ti`、fallbackなしを確認した。
- 実ブラウザで完成結果の`この動画だけ再編集`から子Jobを作成し、`範囲を決めてショート化`を開いて25秒の検証clipをshortへ変換した。画面は通常0本 / ショート1本へ切り替わり、人物アップを含む4画角が表示された。完成表示preview=`ready`、console warning/error 0件、親Job=`completed`、子Job=`awaiting_subtitle_review`、子clip=1本を確認した。最終レンダリングは開始していない。

### 未解決・制限

- 許可済みユーザー実動画による長尺範囲指定と、子Jobの最終MP4・ZIPまでの実E2E、ユーザー受入は未確認。

## 2026-08-27 Task 127 旧再編集Jobの1本分離互換

### 目的

- 旧方式でJob全体を再編集状態へ戻した後でも、完成MP4から対象動画1本だけの再編集Jobを作成できるようにする。
- 実データが残っているのに「元動画または編集データが残っていない」と表示される誤判定を解消する。

### 観測事実・原因

- 対象MP4はExportとSHA-256が完全一致し、元動画、`subtitle_review.json`、`selected_clips.json`、`transcript_segments.json`、対象candidateも残っていた。
- 元Jobは旧方式で`awaiting_subtitle_review`、reviewは`awaiting_review`へ戻っていた。
- Task 126の1本分離処理が`completed / completed`だけを再編集元として許可したため、保存データ完備でも409へ変換されていた。

### 変更

- 1本分離再編集の元状態として、`completed / completed`に加え、再オープン履歴がある`awaiting_subtitle_review / awaiting_review`を許可した。
- 初回字幕確認Jobとの混同を防ぐため、旧状態は`reopenedAt`設定済みかつ`renderRevision > 1`の場合だけ許可する。
- 可変状態の元Jobはsource側のdocument lock内でreview、candidate、transcript、補助artifactを同じ時点のsnapshotとして読み取る。
- 子Job作成後も親Jobの状態、設定、編集JSON、Export、ZIPを変更しない。
- 再編集不能時の表示を、保存データ不足と処理状態非対応の両方を区別できる文面へ修正した。
- 変更ファイル: `backend/app/api/jobs.py`、`backend/tests/test_api_routes.py`、`STATUS.md`。

### 検証

- focused test: `3 passed`。`test_api_routes.py`: `83 passed`。
- backend全test: `625 passed, 1 skipped`。backend全ruff: pass。
- frontend typecheck、lint、production build: pass。
- 独立レビューで初回字幕確認Jobまで許可するP2を検出し、再オープン履歴条件と拒否testを追加した。最終再レビュー: P0/P1/P2なし。
- GPU Composeのbackendをbuild・再作成し、`/health=ok`を確認した。
- 直前に409となった同一MP4を再送し、`job_a7c9385e583c4eb7ab33d59ada785462`を作成した。対象clip 1本、review=`awaiting_review`、元Job=`awaiting_subtitle_review`のまま、元reviewのSHA-256不変を確認した。

### 未解決・制限

- 作成した子Jobの字幕確認後から最終MP4・ZIPまでのユーザー受入は未確認。

## 2026-08-27 Task 128 ショート帯の安全領域とclip別画角調整

### 目的

- 上帯タイトル・下帯ロゴを基本構成にしつつ、帯による人物の頭切れを防ぐ。
- 自動畫角だけで合わないショートを、clipごとに左右・上下・拡大率で微調整できるようにする。

### 観測事実・原因

- 変更前は上下帯を完成映像へ重ねていたため、上帯の下に人物の頭が隠れる素材があった。
- 画角はJob共通の4種類だけで、clipごとの位置・拡大調整値を保存する契約がなかった。
- 顔・人物などの検出に失敗した場合、帯の間の実表示領域ではなく固定`1080x1920`を基準にfallbackを選んでいた。

### 変更

- 新規Jobの上帯・下帯を既定ONへ変更した。既存Jobに保存済みのON/OFF値は維持する。
- 上帯・下帯を各`360px`の予約領域として扱い、映像を帯の間へ配置する。両帯ON時の映像領域は`1080x1200`、片側のみON時は`1080x1560`、帯なしは従来どおり`1080x1920`。
- 上帯ON時は動画内タイトルを表示し、下帯ON時はロゴ帯を表示する既存契約を維持した。
- 字幕確認画面へ、選択中ショートだけに効く`左右 -100〜100`、`上下 -100〜100`、`拡大 100〜160%`と`自動値へ戻す`を追加した。
- 画角値はclip単位で保存し、そのclipだけ完成表示previewを再生成する。保存失敗時も下書きを保持し、未保存画角がある間はclip確定・最終レンダリングを禁止する。
- 顔・人物・話者・被写体の追跡、冒頭複製、即時preview、完成表示preview、最終MP4へ同じ安全領域と画角値を渡す。
- 検出なしで帯内cropが素材を破壊する場合は`blur_background`を優先する。Export JSONには画角値と実描画後のcrop座標を保存する。
- 両帯ON時のショート字幕既定位置を`68.75%`へ変更し、下帯へ重なりにくくした。
- 旧Jobに帯・字幕位置の3項目が保存されていない場合、再試行・再選定・手動確定では旧契約の`上帯OFF / 下帯OFF / 字幕位置未指定`を補完し、新規既定を混入させない。
- 主な変更ファイル: `backend/app/render/crop_strategy.py`、`backend/app/render/render_short.py`、`backend/app/render/render_exact_review_preview.py`、`backend/app/jobs/subtitle_review.py`、`backend/app/api/jobs.py`、`backend/app/schemas.py`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/components/SettingsPanel.tsx`、`frontend/lib/api.ts`、`frontend/lib/types.ts`、関連test、`STATUS.md`。

### 検証

- backend全test: `636 passed, 1 skipped`。backend全ruff: pass。
- frontend: typecheck / lint / production build: pass。
- GPU Composeのbackend / worker / frontendをbuild・再作成し、backend health=`ok`、frontend HTTP=`200`、worker起動を確認した。
- 最新backendコンテナで、上端に頭領域を置いた合成`1080x1920`動画をFFmpegで実レンダリングした。出力=`1080x1920`、戦略=`face_tracking_crop`、`crop_y=0`、上帯直下の画素が頭領域の赤色であることを確認した。
- 同じ合成動画で検出0件時の戦略が`blur_background`になることを確認した。
- 実ブラウザで字幕確認画面にclip別の左右・上下・拡大、自動値へ戻す、`上下帯（基本ON）`が表示されることを確認した。
- 独立監査でP0/P1なし。検出失敗時fallback、実crop座標、未保存画角保持、保存契機、旧Jobへの新規既定混入のP2を修正後、関連test=`170 passed`。

### 未解決・制限

- 許可済みユーザー実動画によるclip別調整から最終MP4・ZIPまでの実E2Eと、頭位置・字幕位置のユーザー受入は未確認。
- 既存Jobは保存済みの帯設定を維持するため、自動で上下帯ONへ書き換えない。

## 2026-08-27 Task 129 字幕編集previewの重なり解消・タイトル／フック手動2行

### 目的

- 縦動画previewが下段のタイトル・字幕設定を覆う状態を解消し、同じ画面で編集操作を続けられるようにする。
- 動画内タイトルと冒頭フックを、入力者が指定した位置で最大2行表示し、即時previewと完成動画を一致させる。

### 観測事実・原因

- `2xl`表示では固定された1段目へ画角設定、9:16動画、再生操作を縦積みし、動画下端が2段目へ約85px越境していた。
- 字幕確認保存、タイトルfallback、ASS生成で改行を空白へ変換していたため、入力した改行位置が完成動画まで残らなかった。

### 変更

- `2xl`表示ではショート画角設定を左、動画previewを右へ配置した。動画サイズを維持しつつ、1段目の境界内へ収める。
- 動画内タイトルを2行textareaへ変更し、タイトル・フックともEnter位置を最大2行として即時previewへ反映する。
- CRLF、CR、Unicode改行、既存`\\N`を同じ改行として扱う。3行目以降は第2行へ空白結合する。
- 保存、Candidate、title fallback、exact preview、normal／short完成ASSへ同じ改行を渡す。改行なしの既存データは従来の自動折返しを維持する。
- 公開用タイトルは従来どおり1行を維持する。
- exact preview renderer contractを`v5`へ更新した。文字なしのlive preview動画hashは文字変更で変えない。
- 変更ファイル: `backend/app/overlay_text.py`、`backend/app/candidates/title_fallback.py`、`backend/app/jobs/subtitle_review.py`、`backend/app/render/subtitles_ass.py`、`backend/app/render/render_exact_review_preview.py`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/lib/subtitlePreview.ts`、関連test、`STATUS.md`。

### 検証

- backend関連test: `133 passed`。backend全test: `642 passed, 1 skipped`。backend全ruff: pass。
- frontend: typecheck、lint、production build: pass。
- Dockerのbackend／worker／frontendをbuild・再作成し、backend health=`healthy`、worker／frontend起動を確認した。
- 実ブラウザ`1821x900`で、動画previewと2段目の重なり=`0px`、動画高さ=`392.7px`、再生操作表示、字幕textareaのfocusを確認した。
- タイトルは再生5秒位置、フックは0秒位置で、Enter指定位置から2行の即時previewになることを確認した。テスト入力は再読込で破棄し、Jobへ保存していない。
- browser console warning／error=`0件`。

### 未解決・制限

- 許可済み実動画で改行を保存し、exact previewから最終MP4まで目視する実E2Eとユーザー受入は未確認。

## 2026-08-28 storage容量整理

### 目的

- `C:\BOT\AutoClipper Web` の動画・一時生成物・Git object蓄積を切り分け、DB参照と完成物を壊さず`C:`の空きを回復する。

### 観測事実・原因

- 整理前はworkspace=`123.44GB`、`storage/temp=8.34GB`、`.git=18.71GB`。
- `storage/uploads`、`outputs`、`temp`、`youtube`、`ID146_*`の100MB以上をSHA-256照合し、同一内容=`90ファイル / 26組`、1コピーだけ残す場合の重複候補=`53.02GB`を確認した。
- upload APIは毎回新しい`video_id`と保存先を作る。DBは動画168件に対し、同名再投入の追加行が136件あった。
- Gitはloose object=`17.87GiB`、garbage=`854.83MiB`。現行indexの`youtube`追跡は0件だが、到達可能な履歴にMP4 7 object / `10.52GB`、到達不能なlarge blob 4 object / `7.48GB`が残っていた。

### 変更

- AutoClipper関連process 0件、Git lock 0件、非完了job 31件を確認し、非完了job名と一致するtempを保護した。
- `storage/temp`の30日超対象`312ファイル / 13フォルダ / 7.90GB`を、削除失敗時に戻せるよう`E:\BOT_DATA_ARCHIVE\AutoClipper_Web_cleanup_20260828\temp`へ退避した。`Y:`は確認時に切断中だったため使用していない。
- `.gitignore`へ`youtube/`を追加し、未追跡動画の再混入を防止した。
- 履歴を書き換えず`git gc --prune=now`を実行し、到達不能objectとgarbageを整理した。
- `storage/uploads`、`storage/outputs`、`youtube`、`ID146_*`、DB、非完了jobのtempは削除していない。

### 検証

- `storage/temp`: `8.34GB -> 0.44GB`。退避先=`1498ファイル / 7.90GB`、移動失敗0件。
- `.git`: `18.71GB -> 10.47GB`。`count=0`、`in-pack=2343`、`size-pack=10.46GiB`、`garbage=0`。
- workspace: `123.44GB -> 107.31GB`、今回のAutoClipper整理分=`16.13GB`。
- `git fsck --full`: exit 0、non-dangling problem 0件。`git check-ignore`で`youtube/`適用を確認。
- SQLite `PRAGMA integrity_check=ok`。`export_items=337`の実動画欠損0件。
- `C:`空きは最終`177.8GB / 19.2%`。整理開始時`110.7GB / 11.9%`からの差には、今回の`16.13GB`以外の同時変動も含む。`pagefile.sys=74.05GB`は未変更。

### 未解決・制限

- ハッシュ一致の重複候補`53.02GB`はDB参照を壊すため未削除。削減にはvideo/job/export参照とheatmap sidecarを保つDB-aware dedupが必要。
- Git履歴内の到達可能なMP4約`10.52GB`は残る。削除には履歴書き換えが必要なため未実施。
- `vid_ce03f95de3a549e08f28f868b1f0ae14.mp4`は整理前から欠損し、2026-06-28のfailed job 1件が参照している。今回のtemp/Git整理による欠損ではない。

## 2026-08-28 完了済みJobのsource-only整理

### 目的

- 完成後のJobは再編集しない運用に合わせ、元YouTube動画を残して完了・失敗Jobの作業コピーと生成物を整理する。

### 観測事実・対象

- 整理前のJob=`177件`。保護対象は`awaiting_clip_review=16`、`awaiting_subtitle_review=14`、`generating_candidates=1`の計`31件`。
- 整理対象は`completed=128`、`failed=18`の計`146件`、これらだけが参照するvideo record=`140件`。
- 整理対象のupload実体=`139ファイル / 18.14GB`。うち既存`youtube`と一致しない元素材=`17組 / 4.10GB`。
- 整理対象のoutput=`154対象 / 11.48GB`、非保護temp=`0.34GB`。

### 変更

- 整理前DBを`E:\BOT_DATA_ARCHIVE\AutoClipper_Web_cleanup_20260828\autoclipper_before_terminal_cleanup.db`へ退避した。
- 既存`youtube`と一致しない元素材17本を`youtube\_source_archive\<SHA-256先頭16桁>\`へ移動し、同じ素材のheatmap sidecarも同じ単位へ退避した。
- 完了・失敗Job=`146件`、それらだけが参照するvideo record=`140件`、関連export record=`318件`をDBから削除した。
- 対応するupload作業コピー、output、非保護tempを削除した。C:上の対象は恒久削除、DBと固有元素材は上記退避先から復旧可能。
- 作業中31件のupload、output、temp、DB参照は維持した。Git履歴は変更していない。

### 検証

- workspace: `107.31GB -> 81.45GB`、削減=`25.86GB`。
- 現在値: `storage/uploads=37.19GB`、`storage/outputs=2.22GB`、`storage/temp=0.10GB`、`youtube=22.63GB`、`.git=10.47GB`。
- 現行DB: `integrity_check=ok`、foreign key違反0件、Job=`31件`、video=`28件`、export=`19件`。
- 作業中31件は元動画欠損0件、output folder欠損0件。exportのvideo/subtitle/metadata欠損0件。
- 固有元素材=`17本 / 4.10GB`、整理前DB backup=`integrity_check=ok`。
- 再計画結果はterminal job、削除候補、未退避素材とも0件。`git diff --check`と`git fsck --full`はexit 0。
- `C:`空き=`215.71GB / 23.3%`。

### 未解決・制限

- 作業中31件が終端状態になるまでは、そのupload=`37.19GB`、output=`2.22GB`、temp=`0.10GB`を保持する。
- Git履歴内の到達可能なMP4約`10.52GB`は残る。削除には履歴書き換えが必要。
- 完了・失敗Jobの編集状態と生成物は現行DBから除去したため、画面から再表示・再ダウンロードできない。必要時は退避DBと元素材から再生成する。

## 2026-08-28 完成済みID146 project退避

- `ID146_【警告】2026年、この工務店に頼むと家が建たなくなります-20260708T195305Z-3-001`は`69ファイル / 7.565GB`、Git未追跡、`youtube`・作業中uploadとの完全一致0件だった。
- 完成用script 3本から絶対パス参照が残るが、完成後は再編集しない運用に基づき、folder全体を`E:\BOT_DATA_ARCHIVE\SSD_cleanup_20260828\AutoClipper_Web_completed_project\`へ退避した。
- 検証: 退避先=`69ファイル / 7.565GB`、C:側folderなし。AutoClipperのDB・作業中31件・`youtube`は変更していない。
- 制限: 上記3本の旧完成用scriptを再実行する場合は、退避先から戻すか絶対パスの変更が必要。

## 2026-08-28 Git履歴MP4除去

### 目的

- 元YouTube動画をworkspace側に残し、Git履歴だけに重複保存されたMP4を除去して`C:`を削減する。

### 変更

- 書き換え前の全refを`E:\BOT_DATA_ARCHIVE\SSD_cleanup_20260828\AutoClipper_Web_git_history_before_mp4_rewrite\AutoClipper_Web_all_refs_before_mp4_rewrite.bundle`へ退避した。bundle=`10.469GB`、`git bundle verify`成功。
- `git-filter-repo 2.47.0`を導入し、`*.mp4`／`*.MP4`を全履歴から除外した。全ref合算の対象はunique MP4 object=`8件 / 約10.52GB`。
- filter対象外だったCodex checkpoint tree ref 2本もtreeを再構築し、各refのMP4 7件を除外した。
- 書き換え前の構成に合わせ、local branch=`44`、remote ref=`72`、tag=`29`、Codex ref=`2`を維持した。`origin`設定も復元した。remoteへのpushは実施していない。
- reflogを失効し、`git gc --prune=now`で旧MP4 objectを物理削除した。

### 検証

- `.git`: `10.469GB -> 0.025GB`、pack=`25.24MiB`。削減=`約10.44GB`。
- `git rev-list --objects --all`のMP4=`0件`。対象8 objectは全て`missing`、`git fsck --full`はexit 0。
- `git diff --check`はexit 0。current branch=`codex/task-124-ai-title-hooks`、作業中だった`.gitignore`と`STATUS.md`は履歴書き換え前の内容を保持してから本記録だけを追記した。
- SQLiteは`integrity_check=ok`、foreign key違反0件。Job=`31件`、video=`28件`、export=`19件`で変更なし。

### 未解決・制限

- remote側の旧履歴は未変更。remoteの容量も削減する場合は、影響範囲を確認した上で履歴のforce pushが必要。
- 書き換え前履歴は上記bundleから復旧可能。共有HDD上で`10.469GB`を使用する。

## 2026-08-28 新規作業前source-only全整理

### 目的

- 新しい動画作業を空のJob一覧から開始できるよう、作業中31件を含む全Jobと作業copy／生成物を整理し、元素材だけを残す。

### 観測事実・保護計画

- 整理前DBはJob=`31件`、video=`28件`、export=`19件`。状態は`awaiting_clip_review=16`、`awaiting_subtitle_review=14`、`generating_candidates=1`。
- 作業領域は`uploads=37.19GB`、`outputs=2.22GB`、`temp=0.10GB`、transcript 8件。
- upload動画28本を既存`youtube`とSHA-256照合した。既存source一致=`24本 / 37.00GB`、upload内重複=`2本 / 0.10GB`、既存sourceなし=`2本 / 101,549,497 bytes`。
- 整理前DBとhash計画を`E:\BOT_DATA_ARCHIVE\AutoClipper_Web_cleanup_20260828\before_new_work_cleanup_20260828_151445\`へ退避し、backup DBの`integrity_check=ok`、foreign key違反0件を確認した。

### 変更

- 既存sourceなしの2本を`youtube\_source_archive\<SHA-256先頭16桁>\`へ移動し、hash一致を確認した。
- 現行DBからexport、Job、videoを全削除して`VACUUM`した。
- `storage\uploads`、`outputs`、`temp`、`transcripts`の未追跡作業fileを削除した。削除=`1,032ファイル / 42,334,028,690 bytes（約39.43GB）`、失敗0件。
- 各作業folderのtracked `.gitkeep`は維持した。Docker Desktopは停止状態を維持した。

### 検証

- 現行DBは`integrity_check=ok`、foreign key違反0件、Job=`0`、video=`0`、export=`0`。
- 元uploadの全unique hashが現行`youtube`に存在し、欠損hash=`0件`。新規退避2本も個別SHA-256一致。
- `uploads`、`outputs`、`temp`、`transcripts`は`.gitkeep`各1件だけ。`git diff --check`はexit 0。
- workspace=`63.44GB -> 24.01GB`。`C:`空き=`412.95GB / 44.6%`。

### 制限

- 削除した作業copy、編集状態、生成物は復元不可。共有HDDのDB backupはJob metadataの確認用で、削除済みoutput実体は含まない。
- 元素材は`youtube`と`youtube\_source_archive`に保持しているため、必要時は新規Jobとして再投入する。

## 2026-08-28 AutoClipper保存ライフサイクル改善

### 目的

- 同一動画の重複保存と完了後データの無期限保持を防ぎ、容量増加を画面で把握できるようにする。

### 現在状態・変更

- uploadをSHA-256単位の`storage/uploads/.blobs/<sha256><拡張子>`へ集約した。同一bytes・同一拡張子は複数Videoで1実体を共有し、APIとVideo IDは従来どおりuploadごとに分離する。
- blob作成はhardlinkを優先し、非対応filesystemでは排他copyへ自動fallbackする。既存blobはsizeとSHA-256を再検証し、不一致時は共有しない。
- heatmap sidecarを`storage/heatmaps/<video_id>.heatmap.json`へ分離した。旧Videoは従来の隣接sidecarをfallback参照する。
- `completed`／`failed`かつ更新から7日超のJobだけを整理対象とした。処理中・確認待ちJobは対象外。Job削除後に参照がなく、作成から24時間超のVideo、関連output／temp／heatmapを整理する。
- cleanup対象Jobは削除直前にstatusと期限を再確認してclaimし、同時に再編集へ戻ったJobを削除しない。削除失敗fileはDBなし残骸として次回cleanupで再検出する。
- uploadのblob公開からVideo DB commitまでとcleanup全体を`storage/.storage-lifecycle.lock`で直列化し、copy fallback中の未登録blobを並行cleanupが削除しないようにした。
- 孤立Videoは削除時にJob／Export不存在と期限を再確認する。SQLite全connectionで外部キー制約を有効化し、同時Job作成による参照切れを防止する。
- Docker構成では成功したupload後に期限切れcleanupを実行する。明示cleanupは`POST /api/storage/cleanup`、画面の`期限切れを整理`から実行する。破壊POSTには専用headerを必須化し、公開portを`127.0.0.1`へ限定した。
- 容量表示は`storage`と`youtube`を合算し、物理hardlinkを二重計上しない。警告基準=`50GiB`、SSD空き=`20%未満`。upload画面に使用量、空き、整理対象Job／元動画を表示する。
- Docker build contextから`youtube`、runtime DB、heatmapを除外した。設定値を`.env.example`と`docker-compose.yml`へ追加した。
- Docker bind mount上の一部directoryが`OSError`になる場合、容量走査全体を500にせず読取可能範囲を集計し、画面へ「一部の保存先を読み取れないため、使用量は参考値です。」と表示する。

### 変更ファイル

- backend: `app/api/storage.py`、`app/api/videos.py`、`app/api/jobs.py`、`app/storage/content.py`、`app/storage/lifecycle.py`、`app/storage/locking.py`、`app/storage/usage.py`、`app/storage/paths.py`、`app/video/heatmap.py`、`app/jobs/runner.py`、`app/config.py`、`app/db.py`、`app/schemas.py`、`app/main.py`
- frontend: `app/upload/page.tsx`、`lib/api.ts`、`lib/types.ts`
- 運用: `.dockerignore`、`.env.example`、`.gitignore`、`docker-compose.yml`、`storage/heatmaps/.gitkeep`
- test: storage lifecycle／dedup／容量API／storage lock／SQLite外部キーの新規testとheatmap参照先の回帰test

### 最小検証

- backend pytest: `667 passed / 1 skipped`。既知のStarlette deprecation warning 1件のみ。
- backend Ruff: pass。
- frontend typecheck／lint／build: pass。
- `docker compose config --quiet`: pass。`git diff --check`: pass。
- Docker DesktopのAF_UNIX socket残骸をworkspace外で退避後、`docker compose up -d --build`を実行。backend healthy、frontend、Redis、workerの4containerが起動した。
- 実API: `/health=200`。`/api/storage/status=200`、AutoClipper保存=`24,258,268,383 bytes`、空き=`433,681,666,048 bytes / 43.58%`、整理対象Job=`0`、元動画=`0`。読取不能領域があるため参考値警告あり。
- 実画面: `http://localhost:3000/upload`で使用量、SSD空き、整理対象0件、参考値警告、無効化された`期限切れを整理`buttonを確認。console error／warning=`0`。
- 隔離container E2E: 本番DB・storageを使わずtmpfsへ1件uploadし、`201`、整理対象=`1`、cleanupでVideo=`1`／file=`1`／`58 bytes`削減、error=`0`、整理後対象=`0`を確認。隔離containerとtmpfsは削除済み。

### 未解決事項

- `youtube\_source_archive\ceb121c1febb20a7`はWindows側で読めるが、Docker bind mount内のdirectory列挙が`OSError: [Errno 5] Input/output error`になる。容量表示は当該領域を除外し警告する。動画実体は変更していない。
- schedulerは追加していない。期限切れ整理は成功upload後、または画面の明示操作で実行する。

## 2026-08-28 Docker Desktop更新後の再確認

- Docker Desktopを`4.78.0`から`4.88.1`へ更新後、Engine=`29.7.2 / API 1.55`、Compose=`v5.4.0`でCompose構成を再作成した。
- backend healthy、frontend、Redis、workerの4containerが起動。`/upload=200`、`/health=ok`、容量API成功、整理対象Job=`0`、元動画=`0`、直近Traceback／ERROR／Exception=`0`。
- 本番DB・storageを使わないtmpfs隔離containerで再検証し、upload=`201`、整理対象動画=`1`、cleanupで動画=`1`／file=`1`削除、error=`0`、整理後対象=`0`を確認した。隔離containerとtmpfsは削除済み。
- AutoClipperのsource、image、volume、DB、storage実体は更新していない。既知の`_source_archive` bind mount読取警告は継続する。

## 2026-08-28 loopback容量表示・archive filename修復

### 目的

- `http://127.0.0.1:3000/upload`でも容量情報を表示し、Dockerから読めなかったarchive 1件を内容を失わず利用可能にする。

### 原因・変更

- backend CORSが`http://localhost:3000`だけを許可していたため、`127.0.0.1`で開いたfrontendから`http://localhost:8000`への容量API取得がbrowserに拒否されていた。既定値、`.env.example`、Compose環境値へ`http://127.0.0.1:3000`を追加した。許可先はlocal 2 originだけで、外部originへ拡大していない。
- Next.js開発server用に`allowedDevOrigins: ["127.0.0.1"]`を追加した。production APIのCORS制御には使用しない。
- `youtube\_source_archive\ceb121c1febb20a7`の旧MP4名は`136文字 / UTF-8 316 bytes`で、Docker/Linuxの1 filename上限`255 bytes`を超えていた。archive 19file中の超過はこの1件だけだった。
- MP4を同一directory内で`ceb121c1febb20a7.mp4`へ原子的にrenameした。file内容、file ID、作成日時、更新日時は変更していない。旧filenameは既存の実動画E2E履歴に残る。

### 変更ファイル

- `.env.example`
- `backend/app/config.py`
- `backend/tests/test_config.py`
- `docker-compose.yml`
- `frontend/next.config.ts`
- source rename: `youtube/_source_archive/ceb121c1febb20a7/ceb121c1febb20a7.mp4`

### 検証

- CORS: `http://localhost:3000`と`http://127.0.0.1:3000`の両方で`200`、`Access-Control-Allow-Origin`が要求originと一致。
- 実browser: `http://127.0.0.1:3000/upload`で保存=`22.8GB`、SSD空き=`43.5%`、整理対象Job／元動画=`0 / 0`を表示。参考値警告なし、console error／warning=`0`。
- source保全: size=`204,999,257 bytes`、SHA-256=`CEB121C1FEBB20A70E6764E7C0BCDC90912D7FB399E3FA20B69FFC63E47A17D4`がrename前後・Windows・Dockerで一致。削除・複製・DB変更なし。
- Docker backendでarchive directory列挙、MP4読込、全SHA-256計算に成功。容量API=`24,463,267,640 bytes`、`warning=False`、reason空、整理対象=`0 / 0`。
- backend pytest=`668 passed / 1 skipped`、Ruff=pass。frontend typecheck／lint／build=pass。`docker compose config --quiet`、`git diff --check`=pass。
- Composeはbackend healthy、frontend、Redis、workerの4serviceが稼働。

### 未解決事項

- 今回の2件に未解決なし。期限切れcleanupの実行条件は従来どおり成功upload後または画面操作。

## 2026-08-28 Windows LauncherのGPU起動待機短縮

### 目的

- デスクトップ起動時にAutoClipperが起動しないように見える長時間待機を解消する。

### 原因・変更

- ショートカット、Python、Docker daemon、Compose、各serviceは正常だった。
- LauncherはGPU profileを選んだだけでGPU worker imageを毎回`--build`していた。実測では22:15:21開始、22:21:52完了で6分31秒かかり、途中進捗がないため起動不能に見えていた。
- GPUという理由だけの無条件buildを廃止した。明示的な`再ビルドして起動`、CPU/GPU profile切替、GPU worker検証失敗からの修復では従来どおりbuildする。

### 変更ファイル

- `launcher/controller.py`
- `backend/tests/test_windows_launcher.py`

### 最小検証

- Windows Launcher test: `42 passed`。
- 稼働中GPU profileに対する起動処理は`8.21秒`、`already_running=True`、`ready=True`。workerの作成日時、起動日時、image IDは前後一致し、再build／再作成なし。
- backend `/health=200`、frontend `/upload=200`。backend、frontend、Redis、workerの4serviceは稼働中。

### 未解決事項

- Docker Desktop停止状態からのcold startは、稼働serviceを停止しないため今回は未実施。既存の自動起動経路とtestは維持している。

## 2026-08-29 Codex初期clip選定をアップロード工程へ統合

### 目的

- 再提案ではなく、新規動画のアップロード工程からChatGPT認証済みCodexを使い、通常切り抜きとショートの初期区間を直接選定する。

### 現在状態・変更

- 新規の自動作成は`Codexで初期選定`を既定ONにした。手動作成・完成動画の再編集は従来選定を維持する。
- ローカルで動画確認、文字起こし、scene検出、人気区間JSON読込を終えた後、時刻付き全文字幕・heatmap・作成本数・狙う場面・除外条件をCodexへ渡す。
- JSON区間モードONではJSON区間との重なりを必須条件、OFFでは補助情報として扱う。Codexが返した区間は字幕時刻、動画長、本数、重複、JSON条件をbackendで再検証してから既存の境界補正へ渡す。
- `品質優先`は信頼度`0.6`未満を採用せず、本数不足を許可する。品質優先OFFは指定本数の一致を必須にする。
- `品質優先`で通常／ショートの片方が0本になっても、もう片方に有効な候補があればJSON区間モードの誤失敗にしない。全種類0本は従来どおり停止する。
- Docker内の処理からWindowsホストのChatGPTログイン済みCodex CLIへ、`storage/codex_bridge`のrequest／responseを介して接続する。API keyをDockerへ渡さず、job単位のCodex会話IDをホスト専用台帳へ保存する。
- bridgeはread-onlyで実行し、shell・browser・MCP・plugin等を無効化した。bridge停止、timeout、出力不正時は理由を記録して従来選定へfallbackし、本体起動は継続する。
- bridgeは処理中に1秒間隔でrequest ID付きheartbeatを共有する。未起動は約12秒、terminal状態は約2秒、処理中heartbeat停止は約17秒で検出し、正常な長時間処理は待機を継続する。
- 進捗画面にCodexの待機中・選定中・完了・fallbackと選定本数を表示する。

### 変更ファイル

- backend: `app/candidates/codex_initial_selection.py`、`app/jobs/runner.py`、`app/api/jobs.py`、`app/schemas.py`
- frontend: `app/upload/page.tsx`、`components/ClipSelectionEditor.tsx`、`components/JobProgress.tsx`、`components/SettingsPanel.tsx`、`components/UploadActionBar.tsx`、`lib/types.ts`
- Windows Launcher: `launcher/codex_bridge.py`、`launcher/controller.py`
- test: `tests/test_codex_initial_selection.py`、`tests/test_codex_host_bridge.py`、`tests/test_real_pipeline.py`、`tests/test_api_routes.py`、`tests/test_windows_launcher.py`

### 最小検証

- backend pytest: `716 passed / 1 skipped`。
- backend Ruff、launcher Ruff、frontend typecheck／lint／build: pass。
- `docker compose config --quiet`、`git diff --check`: pass。
- ChatGPTログイン済みCodex CLIの実接続smokeで、架空字幕から通常`18.0-108.0秒`、ショート`108.0-144.0秒`を構造化出力し、job会話IDの保存を確認した。
- `docker compose up -d --build backend frontend worker`後、backend healthy、frontend、Redis、workerが稼働。`/health=200`、`/upload=200`。
- 実browserの`/upload`で`初期選定: Codex（文字起こし後）`、checkedの`Codexで初期選定`、通常`2本`、ショート`3本`を確認。console error／warning=`0`。

### 未解決事項

- 第1段階では動画frameそのものをCodexへ送らず、時刻付き文字起こし、scene境界、人気区間JSONで選定する。映像内容の直接判定は未実装。
- Windows Launcher経由のhost bridgeが稼働していない場合は従来選定へfallbackする。

## 2026-08-29 ショート候補の重複防止と自動補充

### 目的

- Codex初期選定で、数秒ずれただけの同じ場面を複数のショートとして採用しない。

### 現在状態・変更

- 要求本数の最大3倍、上限24件までショート候補をCodexへ要求する。例: 3本作成時は最大9候補。
- 各ショート候補へ`momentKey`、完成区間を含む親区間、根拠字幕ID、heatmap区間IDを保持する。
- 全候補の境界補正後に、完成区間の重複が1秒超、同一moment、親区間の高重複、根拠字幕／本文の高類似を除外する。
- JSON区間モードONでは同じheatmap区間の重複採用も除外する。OFFではheatmap一致だけを除外理由にしない。
- 上位候補が重複した場合は次順位の独立候補で補充する。独立候補が足りない場合は重複で水増しせず、本数不足と理由を記録する。
- Codex候補のうち、元動画範囲、親区間、字幕根拠、heatmap根拠、ID等が不正なshortはその候補だけを除外し、他の有効候補を維持する。normal候補の不正は従来どおり全体エラーとする。
- Codex停止時の従来選定と切り抜き予定の再選定も、全自動候補の境界補正後に同じhard重複判定を実行する。重複を除外して再選定し、次候補で補充する。
- 通常clip、手動候補、hook複製はショート同士の重複判定対象外とした。通常との重複検査は既存の`crossTypeOverlapDedupe=true`時だけ維持する。
- Codexの全候補poolを候補fileへ保持し、最終選定後の本数をsummaryへ反映する。Codex失敗時の従来選定fallbackは維持する。

### 変更ファイル

- backend: `app/candidates/codex_initial_selection.py`、`app/candidates/merge_boundaries.py`、`app/candidates/short_diversity.py`、`app/jobs/runner.py`
- Windows Launcher: `launcher/codex_bridge.py`
- test: `tests/test_codex_initial_selection.py`、`tests/test_short_diversity.py`、`tests/test_real_pipeline.py`

### 最小検証

- 対象test: `141 passed`。
- backend全test: `741 passed / 1 skipped`。
- backend／launcher Ruff、frontend typecheck／lint／build: pass。
- response schema hashはbackend／host bridgeで`a419f3346e5a666d393a6c22a55ee980a1db1f48646b3c545c596b34962165e3`に一致。
- Compose再構築後、backendはhealthy、workerは`autoclipperweb-worker-gpu`かつGPU device requestあり、`/health=ok`。
- host bridgeを再起動し、`schemaVersion=1`、`state=ready`、処理中requestなしを確認した。

### 未解決事項

- 実際の1時間動画を使った新規jobで、3本すべてが内容面でも独立するかの受入確認は未実施。
- 再選定はCodexを再呼出ししない既存仕様のまま。保存済み候補を使う再選定にも最終重複排除は適用する。

## 2026-08-29 自動化モード契約と判断manifest（Phase 1）

### 目的

- 既存の手動確認フローを保ったまま、段階的な完全自動化へ進む共通モードと判断追跡契約を追加する。

### 現在状態・変更

- `automationMode`を`manual / shadow / guarded / auto`で共通定義した。既定は`manual`。
- `manual`は既存のreview flagと処理遷移を変更しない。
- `shadow`は選択可能。字幕焼き込み、切り抜き予定確認、字幕確認を必須にし、既存出力を変えず自動判断の入力・役割・制限を記録する。
- `guarded / auto`は品質ゲート未実装のため、frontendで選択不可、backend APIでも`422`としてfail closedにした。
- job開始時に`automation_manifest.json`を原子的に保存し、`schemaVersion`、要求／実効モード、`decisionInputHash`、工程別の担当、未接続機能を記録する。ZIPとjob詳細からも追跡できる。
- manual upload、manual workflow、完成clip再編集は`manual`へ固定し、旧payloadで`automationMode`が欠ける場合も`manual`として互換処理する。

### 変更ファイル

- backend: `app/schemas.py`、`app/jobs/automation.py`、`app/jobs/runner.py`、`app/api/jobs.py`
- frontend: `lib/types.ts`、`components/SettingsPanel.tsx`、`app/upload/page.tsx`
- test: `tests/test_automation_contract.py`、`tests/test_api_routes.py`、`tests/test_real_pipeline.py`

### 最小検証

- backend全test: `754 passed / 1 skipped`。
- backend／launcher Ruff、frontend typecheck／lint／build: pass。
- `docker compose config --quiet`、`git diff --check`: pass。
- frontend／backend／GPU workerを再構築し、backend healthy、worker runtime=`gpu`、`/health=ok`を確認した。
- 実browserで`manual / shadow`選択、`shadow`時の確認項目強制、確認解除時の`manual`復帰、`guarded / auto`無効、fresh tabのconsole error／warning=`0`を確認した。

### 未解決事項

- `guarded / auto`に必要なローカル品質ゲートは未実装。
- タイトル／フックの自動決定、最終画角・帯・字幕・音声の自動品質判定は未接続。
- 実際の1時間動画を使ったGPU jobのPhase 1受入確認は未実施。

## 2026-08-29 Guarded品質ゲート（Phase 2）

### 目的

- 全件手動確認から、構造的に安全と判定できた工程だけを自動通過させ、問題・不明点だけ人へ戻す。

### 現在状態・変更

- `guarded`を選択可能にした。字幕焼き込み、切り抜き予定確認、字幕確認を必須とし、`auto`は引き続き選択不可・API `422`でfail closedにした。
- `selection / content / post_render`の3段階で、`pass / fail / unknown`、route、check、入力hashを`quality_gate/*.json`へ原子的に保存する。
- selectionの本数、範囲、長さ、hard重複、JSON条件を構造判定する。`guarded`でselectionがpassなら切り抜き予定確認を省略し、fail／unknownは確認画面へ戻す。
- 現時点の内容正確性、タイトル／フック妥当性、字幕正確性、最終画角は未接続のため`unknown`となり、字幕確認で停止する。`shadow`は判断を記録するだけで従来遷移を変えない。
- post-renderは要求本数との完全一致、render failure 0件、公開先MP4の存在・hashを検証し、不完全な出力を完成扱いにしない。
- 再レンダーは一意なstagingへ出力し、動画、字幕、metadata、render failure、ZIP、DB行を一括昇格する。途中失敗は旧出力へrollbackする。
- rollback失敗またはworker異常終了時は永続publication markerを残し、job status／error文言がフック編集で変わってもresults、個別export、ZIPを公開しない。既存marker付き再試行は完全成功時だけ解除する。
- job詳細に現在の品質ゲート段階、判定、理由を返し、進捗画面に自動通過／人手確認の理由を表示する。

### 変更ファイル

- backend: `app/jobs/quality_gate.py`、`app/jobs/publication_state.py`、`app/jobs/automation.py`、`app/jobs/runner.py`、`app/api/jobs.py`、`app/api/exports.py`、`app/schemas.py`
- frontend: `app/jobs/[jobId]/page.tsx`、`components/JobProgress.tsx`、`components/SettingsPanel.tsx`
- test: `tests/test_guarded_quality_gate.py`、`tests/test_guarded_quality_gate_integration.py`、`tests/test_guarded_rerender_promotion_gate.py`、`tests/test_api_routes.py`、`tests/test_automation_contract.py`、`tests/test_real_pipeline.py`

### 最小検証

- backend全test: `796 passed / 1 skipped`。
- backend Ruff、frontend typecheck／lint／build: pass。
- rollback失敗、既存marker付き再試行失敗、フック更新成功／queue失敗、staging非公開、ZIPを含むrollbackの回帰test: pass。
- `docker compose config --quiet`、`git diff --check`: pass。
- backend／frontend／GPU workerを再構築し、backend healthy、frontend、Redis、workerが稼働。`/health=200`、`/upload=200`。
- 実browserで`問題だけ確認`を選択し、説明文、切り抜き予定確認・字幕確認の強制ON／無効化を確認。再構築後の`/upload`表示とconsole error／warning=`0`も確認した。
- 独立差分監査: P0／P1なし。

### 未解決事項

- 内容正確性、タイトル／フック、字幕、最終画角の自動判定は未接続。このため現行`guarded`は字幕確認を自動通過しない。
- 同一jobの再レンダーworkerが二重実行された場合のattempt所有leaseは未実装。通常の単一RQ workerでは低頻度だが、Phase 3でjob単位leaseまたはattempt ID付きmarkerへ更新する。
- 実際の1時間動画を使ったGPU jobのPhase 2受入確認は未実施。

## 2026-08-29 内容確認証拠と再レンダー排他（Phase 3）

### 目的

- 人のOK操作と現行preview artifactを追跡可能な品質証拠として扱い、内容ゲートの判定抜けと同一revisionの二重再レンダーを防ぐ。

### 現在状態・変更

- 全clipが人のOK済みで、現在のexact／live preview artifactも生成済みの場合、タイトル／フック、字幕、ショート画角を`human_review_confirmation`として`pass`にする。未確認・preview未完成は`unknown`のままにし、preview spec hashを判断証拠へ残す。人がexact previewを再生した証拠とは扱わない。
- `guarded`の内容判定をレンダー前へ移動した。decision保存失敗またはrouteが`continue`以外なら、字幕・selected clips・MP4・ExportItemへ触れず`awaiting_subtitle_review`へ戻す。
- 字幕レンダーRQ job IDを`jobId + renderRevision + attempt`で一意化した。同じrevisionのactive jobは追加せず、terminal attemptは削除せず次attempt IDを使う。worker異常終了時はRQが同revisionを最大2回自動再投入する。古いrevisionと初回完了済みreviewの遅延配送は無変更で終了する。
- render workerの`renderRevision`を必須化した。更新前にqueue済みのrevisionなしpayloadは処理開始前に拒否し、revision照合の迂回を防ぐ。
- 再レンダー開始時にjob単位の非blocking OS advisory leaseを取得する。Windowsは`msvcrt.locking`、POSIXは`fcntl.flock`を使い、process終了時にOSが解放する。lock前にlease fileへ書き込まず、競合中のpayload破損を防ぐ。
- publication markerをattempt ID付きversion 2にし、現在の所有attemptだけが解除できる。既存version 1 markerは失敗時に保持し、完全成功時だけlease保持中に解除する。
- reviewを`completed`へ保存した直後にworkerが停止しても、markerが残る同revisionの再配送はlease取得後に`render_queued`へ戻して再開する。lease取得自体の例外では既存owner markerを保持する。
- `auto`は引き続き無効。人の確認を音声照合や自動意味判定として扱わない。

### 変更ファイル

- backend: `app/jobs/quality_gate.py`、`app/jobs/publication_state.py`、`app/jobs/queue.py`、`app/jobs/runner.py`、`app/api/jobs.py`
- test: `tests/test_api_routes.py`、`tests/test_guarded_quality_gate.py`、`tests/test_guarded_quality_gate_integration.py`、`tests/test_guarded_rerender_promotion_gate.py`、`tests/test_job_queue.py`、`tests/test_manual_workflow.py`、`tests/test_real_pipeline.py`、`tests/test_rerender_publication_lease.py`

### 最小検証

- backend全test: `822 passed / 1 skipped`。既定SQLite親directory不在を避けるため、repo内一時SQLiteを明示して全件実行しpass。一時DBは削除済み。
- Phase 3対象test: `213 passed`。内容gate、render前停止、post-render、RQ重複／terminal retry、stale revision、lease busy、marker所有権、completed+marker回復、process終了後lease再取得、rerender rollbackを確認した。
- backend Ruff、frontend typecheck／lint／build、`docker compose config --quiet`、`git diff --check`: pass。
- backend／GPU workerを再構築し、backend healthy、workerはCUDA `float16`で起動。`/health=200`、`/upload=200`。Linux worker内でも`fcntl.flock`の競合拒否と解放後再取得を確認した。

### 未解決事項

- 音声との再照合による字幕正確性、タイトル／フックの意味品質、人物見切れの自動判定は未接続。現状の`pass`は人のOKと現在のpreview artifact生成済みを組み合わせた証拠に限定する。
- Windowsではprocess終了後のlease解放、Linux workerでは`fcntl.flock`の競合拒否と解放後再取得を確認済み。Linux workerの異常終了後再取得は未確認。
- 実際の1時間動画を使ったGPU jobのPhase 3受入確認は未実施。

## 2026-08-29 投稿用タイトル群・YouTube説明欄の自動生成

### 目的

- 字幕確認中のclip内容を根拠に、投稿時に使うタイトル候補群、推奨タイトル、YouTube説明欄、ハッシュタグをCodexで生成し、選択・編集・保存・書き出しまで一続きにする。

### 現在状態・変更

- clipごとに`事実重視 / 興味喚起 / 短文`のタイトル候補3件、推奨候補、YouTube説明欄、3〜5件のハッシュタグ、根拠字幕IDを生成する契約を追加した。
- 字幕確認画面を開いた時、提案未生成のclipだけを最大2件並列で自動生成する。手動再生成時は同じCodex taskを再利用する。
- AI案の適用、候補選択、タイトル／説明欄／ハッシュタグの手動編集、個別コピー／一括コピーを追加した。
- 字幕やclip範囲からrevision hashを作り、古いAI案の保存を`422`で拒否する。字幕変更後に投稿文を未指定で保存した場合も古い投稿文を残さない。
- 選択結果をsubtitle review、candidate、render metadata、results APIへ伝播する。レンダー時に`youtube_posting_packages.json`と`youtube_posts.md`を生成し、ZIPへ同梱する。
- タイトル／フックの即時previewとASS焼き込みで同じ幅計算、2行分割、縮小規則を使う共通fit契約を追加した。手動改行は維持し、収まらない場合は切り捨てず警告する。
- 通常字幕も既存の文字数分割後に同じ実幅fit契約へ通す。解決済みフォント、左右余白、縁取り、影、横位置を使って最大2行の実幅を計算し、必要な長文だけ指定サイズから縮小する。即時previewとASSへ同じ改行・実効文字サイズを反映する。
- 通常字幕の最小文字サイズもタイトル／フックと同じ既定下限に揃えた。下限でも収まらない極端な長文は1pxまで縮めず、既存の警告契約を維持する。
- host bridge用JSON SchemaからCodex CLI非対応の`uniqueItems`を除き、証拠IDの一意性は既存Pydantic validatorで維持した。schema固定hashも実体に合わせ、回帰testを追加した。
- 公開タイトルを手編集した場合は`publicationTitle`を推奨候補より優先し、JSON／Markdownへ同じ採用文を書き出す。候補なしの手動タイトルだけでも投稿artifactを生成する。
- 字幕revision変更時は旧AI候補、推奨／選択ID、根拠ID、revision hashを失効させる。明示送信された公開タイトル、説明欄、hashtagsは手動値として保持し、`postMetadataSource=manual`へ切り替える。
- タイトル候補と説明欄の根拠segment IDをreview、candidate、render metadata、results、投稿JSONまで保持する。通常clipからshortへ変換した場合は旧AI投稿情報を引き継がない。
- 旧job・旧artifactは投稿用項目なしでも読み込める後方互換を維持した。

### 変更ファイル

- backend: `app/posting_metadata.py`、`app/scoring/title_hook_suggestions.py`、`app/scoring/codex_title_hook_suggestions.py`、`app/jobs/title_hook_suggestions.py`、`app/jobs/subtitle_review.py`、`app/jobs/runner.py`、`app/api/jobs.py`、`app/schemas.py`、候補／render／字幕fit関連module
- frontend: `app/jobs/[jobId]/subtitles/page.tsx`、`components/TitleHookSuggestionPanel.tsx`、`components/ResultVideoCard.tsx`、`components/ClipTextStyleEditor.tsx`、`lib/api.ts`、`lib/types.ts`、`lib/subtitlePreview.ts`
- host bridge: `launcher/codex_bridge.py`
- test: 投稿用metadata、Codex bridge、subtitle review、API、overlay text、ASS、frontend golden fixture関連test

### 最小検証

- backend全test: workspace内一時SQLiteを明示して再実行し、`845 passed / 1 skipped / 0 failed`。
- backend／launcher Ruff、frontend typecheck／lint／build: pass。
- 通常字幕fitのPython対象testは`43 passed`。frontendの共有golden testを`test:overlay-fit`としてnpm scriptとCIへ接続し、preview／ASSの幅計算差を継続検知できるようにした。
- 投稿用metadata／Codex bridge／subtitle reviewの対象test: `79 passed`。字幕fitはPythonとfrontendで同じgolden fixtureを使用した。
- backend／frontend／GPU workerを再構築し、backend healthy、`/health=200`、`/upload=200`、Redis／worker稼働を確認した。
- host Codex bridgeは`state=ready`で再起動した。
- 実browserで既存resultsを再読込し、旧metadataの表示互換、画面崩れなし、console error／warning=`0`を確認した。
- 実動画job `job_de3b8d4bb40f4f299d7a272b92d686fb`で、Codex候補3件生成、推奨案適用、説明欄／hashtags保存、hook付きpreview再生成、字幕確定、GPU再レンダー、results再表示まで完走した。
- 同jobのZIPに`metadata/youtube_posting_packages.json`と`metadata/youtube_posts.md`が含まれ、候補3件、推奨／採用、説明欄、hashtags 4件、生成元`codex`を確認した。
- 完成MP4は`1080x1920`、`44.878167秒`。0.5秒frameでhook、3.5秒frameで2行titleへの切替と上下帯を確認した。
- 再現動画を1本だけ再編集した実job `job_170fa69fed9c49b08d508654b27cd29f`で、長文通常字幕の即時previewは`fits=true`、表示枠360pxに対して実幅約290pxだった。GPU再レンダーは100%完了し、ASSは同字幕を2行・`76px→48px`で出力した。完成MP4の2.9秒frameでも左右約95pxを残し、欠けがないことを確認した。
- 最終修正後にbackend／frontend／GPU workerを再構築し、backend healthy、frontend／Redis／worker稼働、`/health=ok`を確認した。結果画面も再読込して残した。
- 手編集優先、stale AI情報失効、根拠ID伝播の独立再監査でP0／P1なし。関連test `96 passed`。

### 未解決事項

- 既に完成済みの旧出力へ投稿用JSON／Markdownを追加するには、そのclipの再編集・再レンダーが必要。
- 通常字幕のEnter改行はevent分割前に空白へ正規化される既存仕様。previewと完成動画は一致するが、任意位置の改行保持には時間event分割・結合・文字数配分をPython／TypeScript双方で変更する必要があるため、別タスクとする。

## 2026-08-29 frontend依存脆弱性の解消

### 目的

- `npm audit`が報告したhigh 6件を修正版へ更新し、frontendの依存監査を0件にする。

### 現在状態・変更

- `npm audit fix`のmajor更新を伴わない範囲で依存を更新した。
- 直接依存の最低版をNext.js `16.3.3`、PostCSS `8.5.23`へ更新し、`eslint-config-next`もNext.jsと同じ`16.3.3`へ揃えた。
- 間接依存はSharp `0.35.4`、Nano ID `3.3.18`、js-yaml `4.3.2`、brace-expansion `5.0.9`／`1.1.18`へ更新した。
- `package-lock.json`を更新し、`npm ci`でも修正版が再現されるよう固定した。

### 変更ファイル

- `frontend/package.json`
- `package-lock.json`

### 最小検証

- `npm audit --audit-level=high`: `found 0 vulnerabilities`。
- frontend overlay fit test、typecheck、lint、Next.js `16.3.3` build: pass。
- backend全test: `845 passed / 1 skipped`。backend／launcher Ruff、`docker compose config --quiet`: pass。
- frontendコンテナを再構築し、コンテナ内Next.js `16.3.3`、`npm ci`監査0件、`/upload=200`、backend `/health=ok`を確認した。

### 未解決事項

- なし。新しいadvisory追加時は`npm audit`で再確認する。

## 2026-08-30 完全自動化 Phase 4 と68分実動画受入

### 目的

- `auto`モードで初期選定からタイトル／フック／投稿情報、字幕品質確認、書き出し、ZIP作成まで進め、証拠不足のclipだけを人へ戻す。
- 68分実動画とheatmap JSONで通常2本・ショート3本を作り、例外確認数、完成媒体、投稿artifactを受け入れ確認する。

### 現在状態・変更

- `manual / shadow / guarded / auto`を共通契約化し、upload／job画面へ`auto`を追加した。autoはCodex初期選定とタイトル／フック／YouTube説明欄生成を使う。
- selection／content／post-renderの品質判定を追加した。強制モードはfail／unknownを通過させず、clip確認または字幕確認へ戻す。
- 字幕構造、ASR confidence、タイトル／フック根拠、実際のASS event配置、媒体本数／identity／duration／stream、ショート画角・追従geometryを証拠化した。
- clip単位の人確認を自動判定の上書き証拠として扱い、1件だけ確認した後は残りclipを未確認のまま再評価し、自動書き出しへ再開する。`apply`／`confirm`／preview完了の各経路を接続した。
- 長文字幕gateをraw segment単位から、preview／ASSと同じ実際の分割event単位へ変更した。
- Codex推奨案IDを正規化後の候補indexへ対応付け、推奨案と採用案がずれないよう修正した。
- AI／手動で確定済みのタイトルへASR文字補正を再適用しない。語尾`ブロッコリー`の長音`ー`が書き出しmetadataだけで欠落する不整合を修正した。
- auto再開中にZIP作成失敗／worker中断が起きても、job未完了なら`review=completed`を終端扱いせず、未公開成果を破棄して`awaiting_review`へ整合復旧できるようにした。

### 変更ファイル

- backend: `app/api/jobs.py`、`app/candidates/title_fallback.py`、`app/jobs/automation.py`、`app/jobs/quality_gate.py`、`app/jobs/runner.py`、`app/jobs/subtitle_review.py`、`app/jobs/title_hook_suggestions.py`、render／schema関連module
- frontend: `app/jobs/[jobId]/page.tsx`、`components/JobProgress.tsx`、`components/SettingsPanel.tsx`、`lib/automationQuality.ts`、`lib/types.ts`
- test: auto契約、3段階gate、API再開、preview runner、title／hook、short metadata、overlay fit関連test

### 最小検証

- backend全test: `912 passed / 1 skipped / 0 failed`。backend Ruff: pass。
- frontend: automation UI test、overlay fit test、typecheck、lint、Next.js `16.3.3` build: pass。`npm audit --audit-level=high`: `found 0 vulnerabilities`。
- GPU構成を再構築し、backend `/health=ok`、workerはRTX 5070 Ti／CUDA `float16`／fallbackなしで起動した。
- 実動画job `job_837e02c2b37f4be3960190f8b6904e2b`は、元動画68:33・1920x1080・60fps、heatmap JSON 100区間を適用し、Codex初期選定で通常2本・ショート3本を生成した。ショート間重複は`0.0秒`。
- ASR p10=`0.4794`の通常clip 1件だけを人確認し、残り4件は未確認のまま自動通過した。content gate=`pass/continue`、post-render gate=`pass/continue`、clip plan=`approved`。
- 5clipすべてにタイトル候補3件、推奨＝採用、説明欄、hashtags、根拠字幕ID、`postMetadataSource=codex`を確認した。
- 完成媒体は通常2本=`1920x1080/H.264/AAC`、ショート3本=`1080x1920/H.264/AAC`。durationは`330.70 / 359.93 / 49.03 / 45.48 / 59.67秒`。
- ZIPは49項目で、MP4 5本、ASS 5本、個別metadata 5件、投稿JSON 5件、投稿Markdown 5見出し、automation manifest、承認済みclip plan、content／post-render判定を確認した。
- in-app browserでjob=`completed/100%`、工程全項目OK、resultsに通常2本・ショート3本と再編集／download導線が表示されることを確認した。

### 未解決事項

- selection自動判定はこの実jobで証拠不足となり、人がclip planを承認した。承認後の最終ZIPは`clip_plan.json`を選定証跡とし、初回の`selection.json`は保持しない現行仕様。
- タイトル／フック意味品質はCodexの字幕segment provenance、字幕正確性はASR confidence、人物追従はrenderer geometryによる間接証拠。完成pixelからの独立再検出は未接続。

## 2026-08-30 YouTube説明欄テンプレートと投稿タグ

### 目的

- AIの自由文だけでなく、元配信・出演者・固定ハッシュタグ・検索タグを含む定型のYouTube説明欄をclipごとに生成する。
- タイトル、説明欄、ハッシュタグ、YouTubeタグを字幕確認、完成画面、ZIPへ同じ内容で引き継ぐ。

### 現在状態・変更

- upload画面へ`YouTube投稿情報`を追加した。元配信タイトル／URLはjobごと、出演者／所属／固定ハッシュタグ／ショート用ハッシュタグ／固定タグは次回も再利用する。
- Downloader形式の動画ファイル名にYouTube動画IDがある場合、元配信タイトルとURLを自動入力する。検出できない場合は手入力できる。
- 説明欄を`元配信`、配信タイトル、URL、`出演`、出演者／所属の順で生成する。通常／ショートで共通ハッシュタグを使い、ショートだけ`#shortsfunny`等のショート用ハッシュタグを追加する。
- Codexが抽出した話題語はYouTubeタグへ再利用する。タグは重複除去し、YouTube上限500文字以内へ制限する。
- 字幕確認画面で説明欄／ハッシュタグ／タグを編集・コピーできる。完成画面はタイトル、説明欄、タグ、全部のコピーを分離した。
- 通常clipからショートへ変換した場合、説明欄とタグをショート条件で再生成する。
- ZIP投稿artifactをversion 2へ更新し、`youtubeTags`をJSON／Markdownへ追加した。
- 投稿profile APIを追加し、旧job／旧artifactは投稿profileやタグがなくても従来表示できる後方互換を維持した。

### 変更ファイル

- backend: `app/posting_metadata.py`、`app/schemas.py`、`app/api/preferences.py`、`app/api/jobs.py`、候補／subtitle review／title hook／runner／render関連module
- frontend: `app/upload/page.tsx`、`app/jobs/[jobId]/subtitles/page.tsx`、`components/YouTubePostingSettingsPanel.tsx`、`components/ResultVideoCard.tsx`、`components/SettingsPanel.tsx`、`lib/youtubePosting.ts`、`lib/api.ts`、`lib/types.ts`
- test: `backend/tests/test_posting_metadata.py`、`backend/tests/test_api_routes.py`、`frontend/tests/youtubePosting.test.ts`

### 最小検証

- backend全test: `915 passed / 1 skipped / 0 failed`。backend Ruff: pass。
- frontend: YouTube投稿helper test、automation UI test、overlay fit test、typecheck、lint、Next.js `16.3.3` build: pass。
- `npm audit`: `found 0 vulnerabilities`。`git diff --check`、GPU compose config: pass。
- backend／frontend／GPU workerを再構築し、backend healthy、frontend／Redis／GPU worker稼働を確認した。
- in-app browserでupload投稿設定の表示と入力、完成画面のタイトル／説明欄／タグ／全部コピー導線、画面崩れなし、console error／warning=`0`を確認した。

### 未解決事項

- 既存jobには新しい投稿profileとYouTubeタグがないため、完成画面のタグコピーは無効。新規job、または新設定で再編集したclipから有効になる。
- ファイル名から元配信タイトル／URLを特定できない動画はupload画面で手入力が必要。

## 2026-08-31 `normal_01` YouTubeサムネイル作成

### 目的

- 現在の`normal_01.mp4`に合わせ、前回の黒・深緑・銅色のサムネイル構成を踏襲した新規画像を作る。

### 現在状態・変更

- 動画内容をフレーム確認し、残ったバジルソースとブロッコリーをリゾットへ展開する切り抜きとして構成した。
- 人物を右、料理を右下、左に`らでん飯 / 残りソースが / リゾットに変身`を配置した。
- 旧`normal_01_youtube_thumbnail.jpg`は上書きせず、`normal_01_youtube_thumbnail_v2.jpg`を追加した。
- 生成背景と決定的テキスト合成の来歴を`normal_01_youtube_thumbnail_v2.manifest.json`へ保存した。

### 変更ファイル

- `youtube/thumbnails/normal_01_youtube_thumbnail_v2.jpg`
- `youtube/thumbnails/normal_01_youtube_thumbnail_v2.manifest.json`
- `STATUS.md`

### 最小検証

- `1280x720 / JPEG / yuvj420p / 226305 bytes`を確認した。
- 目視で文字欠け、人物の顔への文字かぶり、主要要素のフレーム外切れがないことを確認した。
- 最終SHA256=`11864B72AE8E009F24B27C98C8667DFD6639374AEC1D3A7151DAD687AFEF1B7E`。

### 未解決事項

- YouTubeへの実アップロード後の縮小表示は未確認。

## 2026-08-31 `normal_02` YouTubeサムネイル作成

### 目的

- 現在の`normal_02.mp4`に合わせ、直前に作成した黒・深緑・銅色のサムネイル構成で2本目を作る。

### 現在状態・変更

- 動画内容をフレーム確認し、福岡の警固公園での待ち合わせと「恥ずかしいからやめて」の発言を主題にした。
- 人物を右、左に`よかれと思ったのに / 恥ずかしいから / やめて`を配置した。
- 旧`normal_02_youtube_thumbnail.jpg`は上書きせず、`normal_02_youtube_thumbnail_v2.jpg`を追加した。
- 生成背景と決定的テキスト合成の来歴を`normal_02_youtube_thumbnail_v2.manifest.json`へ保存した。

### 変更ファイル

- `youtube/thumbnails/normal_02_youtube_thumbnail_v2.jpg`
- `youtube/thumbnails/normal_02_youtube_thumbnail_v2.manifest.json`
- `STATUS.md`

### 最小検証

- `1280x720 / JPEG / yuvj420p / 200982 bytes`を確認した。
- 目視で文字欠け、人物の顔への文字かぶり、主要要素のフレーム外切れがないことを確認した。
- 最終SHA256=`0A6B1151CB94E3FE383A490EA0C0F31C7467C0B5AA15D1D5A0B2E2E7BB65BCB9`。

### 未解決事項

- YouTubeへの実アップロード後の縮小表示は未確認。

## 2026-08-31 `normal_02` サムネイル文字訴求強化

### 目的

- `normal_02_youtube_thumbnail_v2.jpg`の文字占有率と視線誘導を、既存の`痛風`／`まだ本編`サムネイル相当まで強める。

### 現在状態・変更

- 長文`恥ずかしいから`を`恥ずかしい / やめて`へ分け、主見出しを画面左半分へ大きく拡張した。
- 赤橙の斜めブラシ、白／黄色の文字、黒＋青緑の二重縁取りを使い、旧版よりコントラストを強めた。
- 人物を右へ寄せ、文字と顔の競合を避けた。
- `normal_02_youtube_thumbnail_v3.jpg`と生成来歴manifestを追加し、v2は保持した。

### 変更ファイル

- `youtube/thumbnails/normal_02_youtube_thumbnail_v3.jpg`
- `youtube/thumbnails/normal_02_youtube_thumbnail_v3.manifest.json`
- `STATUS.md`

### 最小検証

- `1280x720 / JPEG / yuvj420p / 277339 bytes`を確認した。
- 目視で文字欠け、左端の縁取り切れ、人物の顔への文字かぶりがないことを確認した。
- 最終SHA256=`EB9F54E62C1598941A8B8401496B56F71C43384E3EC43098DAFBD2A6C20D4D70`。

### 未解決事項

- YouTubeへの実アップロード後の縮小表示は未確認。

## 2026-08-31 `normal_02` サムネイル斜め文字化

### 目的

- `痛風`サムネイルの見せ方を反映し、v3の水平な主見出しを左下から右上へ傾ける。

### 現在状態・変更

- `恥ずかしい`を`-5度`、`やめて`を`-6度`回転し、赤橙ブラシの方向と文字の視線誘導を揃えた。
- 背景、人物、配色、正確な文言はv3から維持した。
- 透明文字レイヤーを使い、回転後の黒い矩形が残らないよう合成した。
- `normal_02_youtube_thumbnail_v4.jpg`と生成来歴manifestを追加し、v3以前は保持した。

### 変更ファイル

- `youtube/thumbnails/normal_02_youtube_thumbnail_v4.jpg`
- `youtube/thumbnails/normal_02_youtube_thumbnail_v4.manifest.json`
- `STATUS.md`

### 最小検証

- `1280x720 / JPEG / yuvj420p / 257198 bytes`を確認した。
- 目視で文字欠け、左端切れ、透明レイヤーの黒矩形、人物の顔への文字かぶりがないことを確認した。
- 最終SHA256=`B3A1E7827F108876CF9CEA696411F4E9DC82670F600F7DB58DCBF2EBDE1F3CD5`。

### 未解決事項

- YouTubeへの実アップロード後の縮小表示は未確認。

## 2026-08-31 `normal_01` サムネイル斜め文字強化

### 目的

- `normal_01_youtube_thumbnail_v2.jpg`の文字訴求を、既存の`痛風`／`まだ本編`サムネイル相当へ強める。

### 現在状態・変更

- `残りソースが`を小見出しへ移し、主見出しを`リゾットに / 変身`へ短縮した。
- `リゾットに`を`-5度`、`変身`を`-6度`回転し、赤橙ブラシと同じ方向へ視線を誘導した。
- 人物とブロッコリー料理を右へまとめ、左側を巨大文字へ割り当てた。
- `normal_01_youtube_thumbnail_v3.jpg`と生成来歴manifestを追加し、v2以前は保持した。

### 変更ファイル

- `youtube/thumbnails/normal_01_youtube_thumbnail_v3.jpg`
- `youtube/thumbnails/normal_01_youtube_thumbnail_v3.manifest.json`
- `STATUS.md`

### 最小検証

- `1280x720 / JPEG / yuvj420p / 275386 bytes`を確認した。
- 目視で文字欠け、左端・右端・下端切れ、透明レイヤーの黒矩形、人物や料理への文字かぶりがないことを確認した。
- 最終SHA256=`EB3DBD851FE0DD25E91900FDDCE9CA48D63C5E4C9ECB86AB3CFEE0612EEF1532`。

### 未解決事項

- YouTubeへの実アップロード後の縮小表示は未確認。

## 2026-08-31 通常切り抜き公開タイトルの固定末尾

### 目的

- 通常切り抜きのYouTube公開用タイトル末尾へ`儒烏風亭らでん【ReGLOSS切り抜き】`を常に付ける。
- 動画内タイトルと字幕フォント設定は変更しない。

### 現在状態・変更

- 通常切り抜きの公開タイトルと3件のタイトル候補へ固定末尾を重複なく付与する共通処理を追加した。
- 初期生成、手入力保存、AI提案、自動／手動再編集、投稿用JSON／Markdown出力へ共通処理を適用した。
- 100文字を超える場合はYouTubeタイトル上限内で本文側だけを切り詰め、固定末尾を保持する。
- 通常切り抜きをショートへ変換した場合は固定末尾を外す。
- AI生成指示を`title_hook_suggestions_v3`へ更新し、通常切り抜きだけに固定末尾を付ける契約を追加した。
- 品質ゲートのAI提案一致判定も固定末尾適用後の公開タイトルを基準にした。

### 変更ファイル

- `backend/app/posting_metadata.py`
- `backend/app/jobs/subtitle_review.py`
- `backend/app/jobs/title_hook_suggestions.py`
- `backend/app/jobs/quality_gate.py`
- `backend/app/scoring/title_hook_suggestions.py`
- `backend/tests/test_posting_metadata.py`
- `backend/tests/test_subtitle_review.py`
- `backend/tests/test_title_hook_suggestions.py`
- `STATUS.md`

### 最小検証

- `cd backend; python -m ruff check .`: 成功。
- `cd backend; python -m pytest -q`: `918 passed, 1 skipped`。
- 通常切り抜きのみ固定末尾、重複防止、100文字上限、動画内タイトル非変更、投稿用出力を自動テストで確認した。

### 未解決事項

- 実ブラウザで既存ジョブを開いた際の表示確認は未実施。

## 2026-08-31 YouTube説明欄の内容要約・チャプター強化

### 目的

- 伸びた通常切り抜きと同程度に、内容が分かる要約とクリップ内チャプターを備えた説明欄を標準生成する。

### 現在状態・変更

- AIが生成した内容要約を、元配信・出演テンプレート適用時にも先頭へ保持するよう修正した。
- 通常切り抜きは2〜4文の具体的要約と、`00:00`から始まる4〜8件のクリップ相対チャプターを生成する指示へ変更した。
- ショートは1〜2文の具体的要約のみとし、不要なチャプターを付けない。
- 元配信、出演、ハッシュタグ、タグは既存の固定処理を維持し、AIに創作させない。
- AI生成指示を`title_hook_suggestions_v4`へ更新し、旧キャッシュを再利用しないようにした。
- 2000文字上限を超える場合は固定の元配信・出演情報を残し、内容本文側を上限内へ収める。

### 変更ファイル

- `backend/app/posting_metadata.py`
- `backend/app/scoring/title_hook_suggestions.py`
- `backend/tests/test_posting_metadata.py`
- `STATUS.md`

### 最小検証

- `cd backend; python -m pytest tests/test_posting_metadata.py tests/test_title_hook_suggestions.py -q`: `43 passed`。
- `cd backend; python -m ruff check .`: 成功。
- `cd backend; python -m pytest -q`: `918 passed, 1 skipped`。
- 内容要約・チャプターが元配信・出演より前に保持されることを自動テストで確認した。

### 未解決事項

- 実ブラウザでの表示確認と、今日公開済み2本のYouTube説明欄への反映は未実施。

## 2026-09-01 切り抜き境界の時分秒入力と双方向調整

### 目的

- 1時間超の元動画でも、文字起こし時刻と同じ基準で切り抜き開始・終了を調整できるようにする。
- 開始を後ろ、終了を前へもワンクリックで動かせるようにする。

### 現在状態・変更

- 開始・終了入力を`時・分・秒`へ統一した。
- 開始・終了の両方へ`1秒 / 5秒 / 15秒 / 30秒`の前後移動ボタンを追加した。
- 入力値の分・秒を`0〜59`へ制限し、開始は終了の1秒前まで、終了は開始の1秒後から元動画尺までに制限した。
- 有効表示幅`1900px`未満では境界編集が動画下へ移動していたため、横並び条件を`1800px`へ変更し、アプリ内ブラウザの`1861px`幅でも動画右側へ配置した。
- 左のclip一覧を`280px`から`240px`へ縮小し、境界編集を`480px`から`520px`へ拡張した。動画幅を維持したまま時・分・秒入力の見切れを解消した。

### 変更ファイル

- `frontend/components/ClipBoundaryEditor.tsx`
- `frontend/app/jobs/[jobId]/clips/page.tsx`
- `frontend/lib/clipBoundaryTime.ts`
- `frontend/tests/clipBoundaryTime.test.ts`
- `STATUS.md`

### 最小検証

- `npm exec --workspace frontend -- tsx tests/clipBoundaryTime.test.ts`: 成功。
- `npm run typecheck --workspace frontend`: 成功。
- `npm run lint --workspace frontend`: 成功。
- `npm run build --workspace frontend`: 成功。
- `npm audit --workspace frontend --audit-level=high`: `found 0 vulnerabilities`。
- 実ブラウザで`1:25:26.0`が`1時25分26秒`、`1:27:08.58`が`1時27分8.58秒`として表示されることを確認した。
- 実ブラウザで開始`+5秒`と終了`-5秒`が反映されることを確認し、保存せず元の値へ戻した。
- 実ブラウザで`1分`ボタンがなく、開始`+1秒`と終了`-1秒`が反映されることを確認し、保存せず元の値へ戻した。
- アプリ内ブラウザの`innerWidth=1861px`で境界編集が動画右側へ配置されることを目視確認した。
- 分入力の実幅を`clientWidth=43px / scrollWidth=47px`から`49px / 49px`へ改善し、数値が見切れないことを実ブラウザで確認した。

### 未解決事項

- なし。

## 2026-09-01 予定確認でショート1本を通常切り抜きへ変更

### 目的

- 切り抜き予定の確認中に、選択したショート1本だけを通常切り抜きへ変更できるようにする。

### 現在状態・変更

- 選択clipへ`通常切り抜きに変更`ボタンを追加した。
- clipのID・タイトル・開始終了区間は維持し、ショート専用の複製フックだけ解除する。
- `clip_plan.json`、`selected_clips.json`、job本数設定を同期し、字幕確認後も通常切り抜きとして扱う。
- 保存失敗時は変更前のartifactへ戻す。
- 通常切り抜きへ変更後は、予定確認画面の複製フック編集を表示しない。
- OpenAI API、再文字起こし、確認動画の再生成は実行しない。
- Dockerのbackend/frontendを再buildし、既存storageを維持したまま反映した。

### 変更ファイル

- `backend/app/api/jobs.py`
- `backend/app/candidates/select_candidates.py`
- `backend/app/jobs/clip_plan.py`
- `backend/app/schemas.py`
- `backend/tests/test_api_routes.py`
- `frontend/app/jobs/[jobId]/clips/page.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `STATUS.md`

### 最小検証

- `cd backend; python -m pytest tests/test_api_routes.py tests/test_clip_plan.py -q`: `106 passed`。
- `cd backend; python -m ruff check app/api/jobs.py app/schemas.py app/candidates/select_candidates.py app/jobs/clip_plan.py tests/test_api_routes.py`: 成功。
- `cd backend; python -m pytest -q`: `919 passed, 1 skipped`。
- `cd backend; python -m ruff check .`: 成功。
- `cd frontend; npm run typecheck`: 成功。
- `cd frontend; npm run lint`: 成功。
- `cd frontend; npm run build`: 成功。
- Dockerのbackendは`healthy`、frontendは起動済み。対象jobが`awaiting_clip_review`のまま保持されることを確認した。
- 実ブラウザで2本目選択時に変更ボタンが表示・有効、見切れなし、console error 0件を確認した。
- 自動テストで対象1本だけの通常化、フック解除、再実行の冪等性、字幕確認への種別引き継ぎを確認した。

### 未解決事項

- 実ジョブの2本目は未変更。ユーザー操作で変更する。
- 通常切り抜きからショートへの逆変換は今回の対象外。

## 2026-09-01 動画内タイトルの空欄保存・非表示対応

### 目的

- 字幕確認／再編集画面で動画内タイトルを空欄にし、タイトルなしで保存・プレビュー・書き出しできるようにする。
- 公開用タイトルは別項目として保持する。

### 現在状態・変更

- フロントの動画内タイトル必須判定を解除し、公開用タイトルだけを保存必須にした。
- APIとsubtitle review artifactで空の動画内タイトルを受け付けるようにした。
- 通常／ショート書き出しと完成表示プレビューで、明示した空文字を公開用タイトルへ戻さないようにした。
- 動画内タイトルが空の場合は`overlayTitleExpected=false`とし、品質ゲートと書き出しmetadataを一致させた。
- 入力欄へ`空欄なら非表示`の案内を追加した。
- backend、frontend、GPU workerを再buildし、既存storageを保持したまま反映した。

### 変更ファイル

- `frontend/app/jobs/[jobId]/subtitles/page.tsx`
- `backend/app/schemas.py`
- `backend/app/jobs/subtitle_review.py`
- `backend/app/candidates/title_fallback.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `backend/app/render/render_exact_review_preview.py`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_subtitle_review.py`
- `backend/tests/test_render_normal_selected.py`
- `backend/tests/test_title_fallback.py`
- `backend/tests/test_render_exact_review_preview.py`
- `STATUS.md`

### 最小検証

- 対象backendテスト: `152 passed`。
- backend全テスト: `923 passed, 1 skipped`。
- `python -m ruff check .`: 成功。
- frontend `typecheck`、`lint`、`build`: 成功。
- Dockerのbackendは`healthy`、frontend／GPU workerは起動済み。
- 実ブラウザで非表示案内の反映とconsole error 0件を確認した。
- ユーザーの編集中タイトルは変更していない。

### 未解決事項

- なし。

## 2026-09-01 動画内タイトル空欄時の保存ボタン修正

### 目的

- 動画内タイトルを空欄にした状態で、字幕確認の保存ボタンを有効化する。

### 現在状態・変更

- 保存処理とAPIは空欄対応済みだったが、フロントのボタン無効化条件に動画内タイトル必須判定が残っていた。
- 無効化条件を公開用タイトル必須へ変更した。
- frontendを再buildし、既存storageを保持したまま反映した。
- 対象jobで動画内タイトルを空欄のまま保存し、確認済み状態と完成表示プレビュー更新まで完了した。

### 変更ファイル

- `frontend/app/jobs/[jobId]/subtitles/page.tsx`
- `STATUS.md`

### 最小検証

- frontend `typecheck`、`lint`、`build`: 成功。
- 実ブラウザで`動画内タイトル=""`、公開用タイトルあり、保存ボタン有効を確認した。
- 実保存後に`確認 1 / 1`、`保存済み`、完成表示プレビュー更新完了を確認した。
- 再読込後も動画内タイトル空欄と保存済み状態が保持された。

### 未解決事項

- なし。

## 2026-09-01 再編集後Resultsから元の完成動画一覧へ戻る導線

### 目的

- 1本だけ再編集した子jobの完成画面から、元jobの完成動画一覧へ直接戻れるようにする。

### 現在状態・変更

- Results APIへ`reeditSourceJobId`を追加した。
- 子jobのsubtitle review artifactから元job IDを取得し、元jobが存在する場合だけ返す。
- 子job Resultsのヘッダーへ`元の完成動画一覧へ戻る`リンクを追加した。
- 通常の完成jobではリンクを表示しない。
- backend/frontendを再buildし、既存storageを保持したまま反映した。

### 変更ファイル

- `backend/app/api/jobs.py`
- `backend/app/schemas.py`
- `backend/tests/test_api_routes.py`
- `frontend/app/results/[jobId]/page.tsx`
- `frontend/lib/types.ts`
- `STATUS.md`

### 最小検証

- backend対象テスト: `1 passed`。
- backend Results関連テスト: `2 passed`。
- backend対象ruff: 成功。
- frontend `typecheck`、`lint`、`build`: 成功。
- Dockerのbackendは`healthy`、frontendは起動済み。
- Chromeで子job Resultsにリンクが表示され、元job Resultsへ遷移することを確認した。
- 遷移後に通常3本・ショート2本・再編集ボタン5件を確認した。

### 未解決事項

- なし。

## 2026-09-01 Chrome ERR_BLOCKED_BY_CLIENTの同一オリジンダウンロード対応

### 目的

- Results画面のMP4／ZIPをChromeでクリックした際、通常ページ遷移や事前HEAD確認によるブロックを回避する。

### 現在状態・変更

- Results画面は`localhost:3000`からbackendの`localhost:8000`へ直接遷移しており、Chrome側で`ERR_BLOCKED_BY_CLIENT`となっていた。
- frontendへ同一オリジンの`/backend-api/[...path]`プロキシを追加した。
- MP4、Open、Metadata、Subtitle、ZIPのリンクを`localhost:3000/backend-api/...`経由へ統一した。
- 同一オリジン化後も本人クリックでは公開URL末尾の`/download`へのページ遷移が`ERR_BLOCKED_BY_CLIENT`になったため、公開URLを`video.mp4`／`archive.zip`へ変更した。backend内部では従来のdownload endpointへ変換する。
- MP4／ZIPリンクへ`download`属性を追加したが、ユーザー操作ではChrome管理ポリシーの`FILE_BLOCKED`が発生したため、標準ダウンロード経路を廃止した。
- MP4／ZIP保存を`showSaveFilePicker()`→`fetch()`→`response.body.pipeTo()`へ変更した。Chromeのダウンロード管理を使わず、ファイル全体をメモリへ保持しない。
- MP4は`normal_XX.mp4`／`short_XX.mp4`、ZIPは`job_ID.zip`を保存候補名にする。
- backendのdownload endpointがHEAD非対応で`405`だったため、frontend proxyのHEADはupstreamへ`Range: bytes=0-0`を要求し、総サイズを復元して`200`を返すようにした。
- Range／キャッシュ条件付きリクエストをbackendへ転送し、動画再生・分割取得に必要なレスポンスヘッダーを保持した。
- Docker内frontendからbackendへ接続する`BACKEND_INTERNAL_URL=http://backend:8000`を追加した。

### 変更ファイル

- `docker-compose.yml`
- `frontend/app/backend-api/[...path]/route.ts`
- `frontend/app/results/[jobId]/page.tsx`
- `frontend/components/ResultVideoCard.tsx`
- `frontend/components/SaveFileButton.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/browserFileSave.ts`
- `frontend/tests/browserFileSave.test.ts`
- `frontend/package.json`
- `STATUS.md`

### 最小検証

- frontend `typecheck`、`lint`、`build`: 成功。
- `docker compose config --quiet`: 成功。
- 公開URL変換: exportは`/video.mp4`、job ZIPは`/archive.zip`、metadataは従来経路になることを確認した。
- MP4のHEAD: `200`、`Content-Length: 54641581`、`Content-Disposition: attachment`。
- ZIPのHEAD: `200`、`Content-Length: 54798129`。1byteだけ取得するため約`71ms`で完了した。
- MP4のRange取得: `206`、`Content-Range: bytes 0-0/54641581`。
- 標準ダウンロードはブラウザ自動操作では保存できたが、ユーザー操作ではChromeの「組織でブロックされました」が発生したため、合格扱いを撤回した。
- 保存helperテスト: picker→fetch→stream書込順、キャンセル時fetchなし、HTTPエラーを確認した。
- Chrome実画面でMP4／ZIPの保存API対応が`true`、ボタン有効を確認した。
- MP4保存ボタンからネイティブ保存先ダイアログが開き、Results画面に留まることを確認した。

### 未解決事項

- ネイティブ保存先ダイアログでユーザーが保存を確定した後の、保存ファイルサイズ／SHA-256確認が未完了。

## 2026-09-01 高校美術・美学切り抜き用YouTubeサムネイル

### 目的

- `高校で美術を学ぶ理由を「美学」から考える儒烏風亭らでん【ReGLOSS切り抜き】.mp4`用の通常動画サムネイルを作成する。

### 現在状態・変更

- 実動画の48.92秒付近から、正面を向いて話す表情を参照フレームとして選定した。
- 既存サムネイルの黒・深緑・金・青緑・赤橙の斜め構図を参照し、人物を右側、見出しを左側へ配置した。
- 画像生成では文字なし背景と人物構図だけを作り、日本語コピーは後段で決定論的に合成した。
- コピーは`高校で学ぶ理由`／`美術って`／`必要なの？`とした。
- 既存ファイルは上書きしていない。

### 生成ファイル

- `youtube/thumbnails/highschool_art_aesthetics_20260901/highschool_art_aesthetics_youtube_thumbnail_v1.jpg`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/manifest.json`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/generated_base_v1.png`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/frame_06_048.92s.jpg`

### 最小検証

- 完成画像: `1280x720`、JPEG、`377487 bytes`。
- SHA-256: `f98e94df31936758b814cbd78d4174783b3298dde4a77fbceb4cfff48d05c649`。
- 文字列、人物の顔、左右の安全余白、コントラストを原寸表示で確認した。

### 未解決事項

- なし。

## 2026-09-01 高校美術サムネイルv2・文字階層と背景修正

### 目的

- 2行の主見出しが同程度の大きさに見える問題を直し、背景を既存の`痛風オールバック`サムネイルへ合わせる。

### 現在状態・変更

- `美術って`を100px、`必要なの？`を154pxとし、2行目を主見出しにした。
- 背景を濃緑の幾何学柄、金枠・金雲、赤い筆跡、白い斜め速度線へ変更した。
- 人物の右側配置と日本語コピーは維持した。
- v1は残し、v2を新規作成した。

### 生成ファイル

- `youtube/thumbnails/highschool_art_aesthetics_20260901/highschool_art_aesthetics_youtube_thumbnail_v2.jpg`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/generated_base_v2.png`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/manifest_v2.json`

### 最小検証

- 完成画像: `1280x720`、JPEG、`373994 bytes`。
- SHA-256: `56e551babcad94560e520f10ca33432d013993986acd64139b8a17e7a66a0692`。
- 2行のサイズ差、背景参照、文字列、人物の顔、安全余白を原寸表示で確認した。

### 未解決事項

- なし。

## 2026-09-01 高校美術サムネイルv3・参照画像に合わせた文字バランス修正

### 目的

- `normal_01_youtube_thumbnail.jpg`の見た目バランスへ合わせる。

### 現在状態・変更

- `美術って`を154px、`必要なの？`を148pxとし、短い上段を大きく、長い下段を少し小さくして見た目幅を揃えた。
- 上部の小見出し枠を拡大し、左側の文字要素を一つの塊として配置した。
- `痛風オールバック`系の背景と人物の右側配置は維持した。
- v1・v2は残し、v3を新規作成した。

### 生成ファイル

- `youtube/thumbnails/highschool_art_aesthetics_20260901/highschool_art_aesthetics_youtube_thumbnail_v3.jpg`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/manifest_v3.json`

### 最小検証

- 完成画像: `1280x720`、JPEG、`351084 bytes`。
- SHA-256: `e9f83c66cdb5b815066492c80a38ca7050a37a48e33fc82a1b79f58b2f3b00fa`。
- 2行の見た目幅、上部枠、人物の顔、安全余白を原寸表示で確認した。

### 未解決事項

- なし。

## 2026-09-01 高校美術サムネイルv4・行間圧縮と主見出し強調

### 目的

- 主見出し2行の上下間隔を詰め、片方を明確に大きくする。

### 現在状態・変更

- `美術って`を142px、`必要なの？`を168pxとし、下段を主役化した。
- 2行の開始位置差を130pxに縮め、縁取りが接する密度へ変更した。
- 背景、人物、上部枠、文言は維持した。
- v1からv3は残し、v4を新規作成した。

### 生成ファイル

- `youtube/thumbnails/highschool_art_aesthetics_20260901/highschool_art_aesthetics_youtube_thumbnail_v4.jpg`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/manifest_v4.json`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/render_v4.py`

### 最小検証

- 完成画像: `1280x720`、JPEG、`502947 bytes`。
- SHA-256: `2be9993d406b38ad7033a027b5bb519baf108f321c547be8384d6e4efe32f5a3`。
- 2行の間隔、下段のサイズ差、文言、人物の顔、安全余白を原寸表示で確認した。
- manifestのSHA-256一致を確認した。

### 未解決事項

- なし。

## 2026-09-01 高校美術サムネイルv5・文字重なり解消

### 目的

- v4で重なりすぎた主見出し2行を、近接したまま分離する。

### 現在状態・変更

- 上段142px、下段168pxのサイズ差は維持した。
- 下段の開始位置を326pxから382pxへ下げ、縁取り間に約3pxの空きを確保した。
- 背景、人物、上部枠、文言は維持した。
- v4は残し、v5を新規作成した。

### 生成ファイル

- `youtube/thumbnails/highschool_art_aesthetics_20260901/highschool_art_aesthetics_youtube_thumbnail_v5.jpg`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/manifest_v5.json`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/render_v5.py`

### 最小検証

- 完成画像: `1280x720`、JPEG、`499387 bytes`。
- SHA-256: `9a1e947588a45dc2244c0ff5926dbce6878408addf8a24d9d9c3a019d04d5cd4`。
- 2行が重ならないこと、下段のサイズ差、文言、人物の顔、安全余白を原寸表示で確認した。
- manifestのSHA-256一致を確認した。

### 未解決事項

- なし。

## 2026-09-01 高校美術サムネイルv6・主見出し斜め配置

### 目的

- 主見出し2行を少し斜めにし、動きのある配置へ変える。

### 現在状態・変更

- 主見出し2行を一つの文字塊として右上がり3度に回転した。
- 上段142px、下段168pxのサイズ差と、重ならない近接間隔を維持した。
- 背景、人物、上部枠、文言は維持した。
- v5は残し、v6を新規作成した。

### 生成ファイル

- `youtube/thumbnails/highschool_art_aesthetics_20260901/highschool_art_aesthetics_youtube_thumbnail_v6.jpg`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/manifest_v6.json`
- `youtube/thumbnails/highschool_art_aesthetics_20260901/render_v6.py`

### 最小検証

- 完成画像: `1280x720`、JPEG、`503513 bytes`。
- SHA-256: `107cc6171c022cff5722fe311315b6a88451e9f3b063346d9f4c93e64341ff91`。
- 主見出しが右上がり3度であること、2行が重ならないこと、文言、人物の顔、安全余白を原寸表示で確認した。
- manifestのSHA-256一致を確認した。

### 未解決事項

- なし。

## 2026-09-01 分かりやすく話す2つのこと・YouTubeサムネイル

### 目的

- `分かりやすく話すために意識する2つのこと｜儒烏風亭らでん【ReGLOSS切り抜き】.mp4`用の通常動画サムネイルを作成する。

### 現在状態・変更

- 実動画は140.5秒、1920x1080、60fps。12点を確認し、正面寄りの笑顔がある19.67秒を人物参照に選定した。
- 既存の黒・深緑・金・赤筆跡の通常切り抜きサムネイル様式を維持し、人物を右、文字を左へ配置した。
- 文字なし背景と人物を画像生成し、日本語は決定論的に合成した。
- コピーは`伝わる話し方`／`意識するのは`／`この2つ`とした。
- 上段122px、下段206pxとし、主見出し全体を右上がり3度にした。

### 生成ファイル

- `youtube/thumbnails/clear_speaking_two_points_20260901/clear_speaking_two_points_youtube_thumbnail_v1.jpg`
- `youtube/thumbnails/clear_speaking_two_points_20260901/generated_base_v1.png`
- `youtube/thumbnails/clear_speaking_two_points_20260901/manifest.json`
- `youtube/thumbnails/clear_speaking_two_points_20260901/render_thumbnail.py`
- `youtube/thumbnails/clear_speaking_two_points_20260901/source_metadata.json`
- `youtube/thumbnails/clear_speaking_two_points_20260901/contact_sheet.jpg`

### 最小検証

- 完成画像: `1280x720`、JPEG、`451347 bytes`。
- SHA-256: `ec98225532984e3c51725380860a14531fc78516199f7306e96b1e92aa500a9a`。
- 文言、サイズ差、右上がり3度、人物の顔、安全余白を原寸表示で確認した。
- manifestのSHA-256一致を確認した。

### 未解決事項

- なし。

## 2026-09-01 らでんだけ見てて・YouTubeサムネイル

### 目的

- `「らでんだけ見てて」と思う？リスナーへの答えを明かす儒烏風亭らでん【ReGLOSS切り抜き】.mp4`用の通常動画サムネイルを作成する。

### 現在状態・変更

- 実動画は124.0秒、1920x1080、60fps。12点を確認し、正面寄りで表情が強い86.80秒を人物参照に選定した。
- 他配信者も見てよいという回答につながる内容を確認し、結論を隠す疑問形コピーにした。
- コピーは`リスナーへの本音`／`らでんだけ`／`見ててほしい？`とした。
- 上段155px、下段112pxで見た目幅を揃え、主見出し全体を右上がり3度にした。
- 文字なし背景と人物を画像生成し、日本語は決定論的に合成した。

### 生成ファイル

- `youtube/thumbnails/raden_only_listener_answer_20260901/raden_only_listener_answer_youtube_thumbnail_v1.jpg`
- `youtube/thumbnails/raden_only_listener_answer_20260901/generated_base_v1.png`
- `youtube/thumbnails/raden_only_listener_answer_20260901/manifest.json`
- `youtube/thumbnails/raden_only_listener_answer_20260901/render_thumbnail.py`
- `youtube/thumbnails/raden_only_listener_answer_20260901/source_metadata.json`
- `youtube/thumbnails/raden_only_listener_answer_20260901/contact_sheet.jpg`

### 最小検証

- 完成画像: `1280x720`、JPEG、`438041 bytes`。
- SHA-256: `0853ddcf1bf46126c820f4d45f588eb6625766af24ff6443ab163e9fb1f260e1`。
- 文言、サイズ差、右上がり3度、人物の顔、安全余白を原寸表示で確認した。
- manifestのSHA-256一致を確認した。

### 未解決事項

- なし。

## 2026-09-02 完成時サムネイル自動生成

### 目的

- 通常切り抜きとショートの完成時に、投稿用サムネイルを同時生成する。

### 現在状態・変更

- 通常切り抜きは、既存実績の深緑和柄・金枠・赤橙アクセント・人物右／文字左を `raden_normal_v1` テンプレート化した。
- 通常サムネは `1280x720 JPEG`。字幕焼込み前の元動画フレーム、小見出し、主見出し2行、clip内場面秒を使用する。長文は実幅で縮小する。
- 小見出し・主見出しは空欄なら非表示。場面秒が空欄ならclip長の38%を使用し、許容上限の長文も縮小して描画を継続する。
- ショートは画像生成せず、完成MP4の冒頭フック字幕が表示されている区間中央を元解像度のJPEGとして切り出す。
- 字幕確認画面へ通常サムネ4項目と即時プレビューを追加し、AI提案の採用内容にも接続した。即時プレビューも空欄・38%自動場面・長文縮小を完成描画へ合わせた。
- 結果画面へサムネ表示、生成状態、単体保存を追加した。旧成果物の未生成表示はコンパクトにし、URL不整合・画像読込失敗も区別する。
- ZIPとYouTube投稿JSON/Markdownにもサムネ情報を含め、状態源をexport metadataへ統一した。ZIPは同一job配下のサムネだけを収録する。
- 再編集書き出しでは動画・字幕・メタデータ・サムネ・YouTube投稿JSON/Markdownを同一の原子的昇格対象にした。サムネ失敗時は旧JPEGを残さず、rollback時だけ復元する。
- サムネ生成だけ失敗した場合は動画完成を失敗にせず、`thumbnail_status=failed` とエラーをメタデータへ残す。
- サムネ取得APIはjob出力ディレクトリ外のパスを拒否する。

### 変更ファイル

- `backend/app/render/render_thumbnail.py`
- `backend/app/jobs/thumbnails.py`
- `backend/app/assets/thumbnail_templates/raden_normal_v1/`
- `backend/app/jobs/runner.py`
- `backend/app/api/exports.py`
- `backend/app/api/jobs.py`
- `backend/app/posting_metadata.py`
- `backend/app/schemas.py`
- `backend/app/candidates/merge_boundaries.py`
- `backend/app/scoring/title_hook_suggestions.py`
- `backend/app/jobs/title_hook_suggestions.py`
- `backend/app/jobs/subtitle_review.py`
- `backend/app/render/render_normal.py`
- `backend/app/render/render_short.py`
- `frontend/app/jobs/[jobId]/subtitles/page.tsx`
- `frontend/components/ResultVideoCard.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `launcher/codex_bridge.py`
- `backend/tests/test_thumbnail_rendering.py`
- `backend/tests/test_thumbnail_integration.py`
- `backend/tests/test_posting_metadata.py`
- `backend/tests/test_guarded_rerender_promotion_gate.py`

### 最小検証

- backend全体: `945 passed, 1 skipped`。
- backend ruff: 成功。
- サムネ描画再検証: `9 passed`。空欄、許容上限長文、片側1行だけの描画も成功した。
- サムネ・投稿・再編集の回帰セット: `39 passed`、関連拡張セット: `88 passed`。
- frontend: `typecheck`、`lint`、`build`、関連テスト成功。
- Docker: backend/worker/frontend/redisを再build・起動し、backend healthy、health `200`。
- Docker内FFmpeg実行: 通常 `1280x720`、ショート `960x540` のJPEG生成成功。
- 実画像を目視し、通常の和柄・金枠・2行文字・人物配置と文字切れなしを確認した。
- ブラウザ確認: 通常サムネ編集欄、38%自動場面、即時プレビュー、結果画面のコンパクトな旧成果物 `サムネ未生成` 表示を確認。console error/warn 0件。
- `git diff --check`: 成功。

### 未解決事項

- 既に完成済みの旧成果物は自動遡及生成しない。新規完成または再編集書き出し時に生成する。

## 2026-09-03 JSONを人気度参考へ限定した内容選定

### 目的

- JSON区間を切り抜き境界や候補元にせず、文字起こしと会話内容を基準に通常切り抜き・ショートを選定する。

### 現在状態・変更

- JSON ONは人気度の参考情報だけをCodexへ渡す。開始・終了、尺、採否は内容基準で決める。
- JSON OFFは文字起こし・会話内容だけで選定する。
- JSONが実行中に欠損・破損した場合もjobを失敗させず、内容選定へフォールバックする。
- 同一JSON区間に含まれる候補を重複として強制排除する判定を廃止した。
- 再選定は旧候補の並べ替えではなく、文字起こしと任意の人気度参考から候補を再生成する。
- Codex再選定に失敗した場合は従来の内容評価へフォールバックする。
- 初期選定と再選定の要約を別ファイルへ保存し、初期選定結果を上書きしない。
- アップロード、clip再選定、進捗表示の文言を「JSONを参考」「内容のみ」に統一した。

### 変更ファイル

- `backend/app/candidates/codex_initial_selection.py`
- `backend/app/jobs/runner.py`
- `backend/app/jobs/quality_gate.py`
- `backend/app/api/jobs.py`
- `launcher/codex_bridge.py`
- `frontend/app/upload/page.tsx`
- `frontend/app/jobs/[jobId]/clips/page.tsx`
- `frontend/components/JobProgress.tsx`
- `backend/tests/test_api_routes.py`
- `backend/tests/test_codex_initial_selection.py`
- `backend/tests/test_heatmap_interval_candidates.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_runner_short_diversity.py`

### 最小検証

- backend全体: `942 passed, 1 skipped`。
- backend/launcher ruff: 成功。
- frontend: `typecheck`、`lint`、`build` 成功。
- Docker: backend/worker/frontendを再build・起動し、backend health `200`、frontend `200`。
- ブラウザ確認: `人気度JSONを参考にする`、OFF時の内容選定説明を確認した。
- `git diff --check`: 成功。

### 未解決事項

- 既存jobの候補は自動で選び直さない。新規jobまたは再選定の実行時から新方式を使う。
- 旧JSON候補生成モジュールは互換維持のため残しているが、製品の実行経路からは呼び出さない。

## 2026-09-03 Codex選定失敗の可視化とBridge互換性復旧

### 目的

- Codex初期選定が失敗した場合にローカル仮選定をおすすめ結果として誤認させず、Bridge更新差分による失敗を起動時に自動復旧する。

### 現在状態・変更

- Codex Bridgeのbuild・contract・task schema fingerprintをstatus、request、responseへ追加した。
- launcher起動時にBridge契約不一致を検出し、旧プロセスの終了を確認してから現行Bridgeを再起動する。
- 初期選定を最大2回実行し、再試行時は新しいrequestIdを使う。
- 初期選定要約へphase、promptVersion、requestId、attemptCount、hostErrorCodeを保存し、APIへ公開する。
- Job進捗画面と切り抜き予定画面へ共通の選定状態表示を追加した。
- Codex失敗時は `ローカル仮選定` と `おすすめ結果ではありません` を常時表示する。
- 現在稼働中のBridgeを現行契約版へ更新し、ready状態を確認した。

### 変更ファイル

- `launcher/codex_bridge.py`
- `launcher/controller.py`
- `backend/app/candidates/codex_initial_selection.py`
- `backend/app/api/jobs.py`
- `frontend/components/InitialSelectionStatusBanner.tsx`
- `frontend/lib/initialSelectionStatus.ts`
- `frontend/components/JobProgress.tsx`
- `frontend/app/jobs/[jobId]/clips/page.tsx`
- `frontend/lib/types.ts`
- `frontend/package.json`
- `backend/tests/test_windows_launcher.py`
- `backend/tests/test_codex_host_bridge.py`
- `backend/tests/test_codex_initial_selection.py`
- `backend/tests/test_api_routes.py`
- `frontend/tests/initialSelectionStatus.test.ts`

### 最小検証

- backend全体: `952 passed, 1 skipped`。
- backend/launcher ruff: 成功。
- Bridge/初期選定/API関連: `202 passed`。
- launcher停止待機の追加回帰: `50 passed`。
- frontend: 選定状態UIテスト、`typecheck`、`lint`、`build` 成功。
- Docker: backend/worker/frontendを再build・起動し、backend healthy、health `200`、frontend `200`。
- 稼働中Bridge: build・contract・initial-selection schema fingerprint設定済み、state `ready` を確認。
- Chrome実画面: 既存fallback jobで `ローカル仮選定`、`おすすめ結果ではありません`、エラーコードを確認し、候補一覧・動画・時刻入力との重なりなし。

### 未解決事項

- 既存jobの候補は自動再選定しない。表示だけ正しい状態へ更新される。
- 実Jobを変更するCodex再選定は未実行。次回の新規選定またはユーザー操作による再選定で成功経路を実運用確認する。

## 2026-09-03 尺収束廃止・通常Short分離・長尺二段階Codex選定

### 目的

- 通常150秒／Short 42秒付近への候補収束を廃止し、内容の自然な境界と用途別の公開価値で選定する。
- 長尺文字起こしを一括投入せず、ローカル話題要約から重要話題を選んだ後、その周辺字幕だけで境界を精密化する。

### 現在状態・変更

- min/maxを目標尺ではなく制約として扱い、話題開始、質問、回答完了、無音を候補境界にした。
- 候補保持枠を通常 `90–180 / 180–300 / 300–600秒`、Short `20–35 / 35–50 / 50–75秒` に分け、生成済みの長い良質候補が上限処理で消えないようにした。
- `minDuration == maxDuration` の明示的な固定尺だけ、自然終端がない場合に `start + duration` を最終手段として許可する。可変尺では使用しない。
- 通常は主要テーマ、質問から結論までの完結性、単独理解を評価し、名前読み、連続お礼、スパチャ読みだけの区間を減点する。
- Shortは反応、驚き、オチ、短い完結を評価し、コメント・スパチャ由来も許可する。
- 通常は別 `topicKey` かつ区間重複50%未満から選ぶ。
- `selectionPolicy` 未指定時を `strict_quality` に変更し、良質候補不足時は本数不足を許容する。明示的な `fill_requested` の互換動作は残した。
- 長尺選定を、ローカル話題ブロック作成、Codex重要話題選定、選定周辺の元字幕による境界精密化の二段階にした。
- 非連続の `topicBlockIds` を拒否し、精密化入力を選定topicの周辺字幕だけに限定した。
- Codexが返した有効候補poolでは、最終選定候補を保持した上で各尺帯の候補枠を予約する。最終選定尺の人工的な分散は行わない。
- 通常候補poolもShortと同様に全件を境界補正へ渡し、補正後に `strict_quality`、`topicKey`、重複率で最終選定する。
- Codex候補1件の不正で全体をfallbackせず、その候補だけを除外する。
- 実Job成果物を変更しない読み取り専用回帰スクリプトを追加した。
- frontend依存関係を監査修正し、npm脆弱性0件にした。

### 変更ファイル

- `backend/app/candidates/merge_boundaries.py`
- `backend/app/candidates/select_candidates.py`
- `backend/app/candidates/codex_initial_selection.py`
- `backend/app/jobs/runner.py`
- `backend/app/scoring/clip_preferences.py`
- `backend/app/scoring/rule_score.py`
- `backend/app/scoring/openai_score.py`
- `backend/app/schemas.py`
- `backend/tests/test_candidate_generation.py`
- `backend/tests/test_quality_gate_and_selection.py`
- `backend/tests/test_scoring_and_deduplicate.py`
- `backend/tests/test_codex_initial_selection.py`
- `backend/tests/test_real_pipeline.py`
- `backend/tests/test_regression_selection_from_artifacts.py`
- `scripts/regression_selection_from_artifacts.py`
- `scripts/smoke_runtime.py`
- `package-lock.json`

### 最小検証

- backend全体: `980 passed, 1 skipped`。警告3件は既存のStarlette/Pillow非推奨警告。
- backend/launcher/scripts ruff: 成功。
- frontend: 選定状態UIテスト、`typecheck`、`lint`、`build` 成功。
- `npm audit --audit-level=high`: `0 vulnerabilities`。
- Docker: backend/worker/frontendを再build・起動し、backend healthy、health `200`、実Jobclip画面 `200`。
- 稼働中Codex Bridge: 現行build・contractで `ready`。
- 実Job `job_12504e9baec64c5c8d5d83edac44797c` のローカル回帰は成功。通常候補は旧 `1199 / 1 / 0` から各尺帯 `400 / 400 / 400`、Short候補は旧 `19 / 1168 / 13` から `400 / 400 / 400` になった。
- 同Jobの孤立Codex回帰は話題ブロック118件から7話題を選び、元字幕489区間だけで精密化した。有効選定は通常2本 `245.28秒 / 483.26秒`、Short 4本 `20.16–50.64秒`。親区間違反のShort 1本は個別除外した。
- 通常2本は別 `topicKey`、相互重複0、連続お礼・スパチャ読み0。現代アート・キュビズムの説明区間を選定した。
- 実Jobの対象artifact 8件は前後SHA-256一致。DB、動画処理、元成果物書込み、OpenAI APIは使用していない。
- `git diff --check`: 成功。

### 未解決事項

- 既存Jobの保存済み候補は自動置換しない。新規Jobまたはユーザー操作による再選定から新方式を使う。
- 孤立Codex回帰で除外したShort 1本は、無理に代替候補で本数を埋めていない。

## 2026-09-03 通常サムネの実績テンプレ化と単体再生成

### 目的

- 通常サムネを承認済みサンプルと同じ基本形へ揃え、完成動画を変えずに結果画面から1枚だけ再生成する。

### 現在状態・変更

- 承認済みサンプルから人物だけを除いた背景・装飾を固定ベースへ採用した。
- 人物は元動画から毎回取得し、顔検出時は顔基準、未検出時は配信画面の右下人物基準で拡大する。
- `サムネだけ再生成`を押すたびに6つの時刻候補を巡回し、人物の表情・場面を切り替える。
- 左上の小見出しと白／黄の2行見出しを、承認済みの位置・色・縁取り・傾きへ揃えた。
- 見出し幅を制限し、右側の人物の顔へ重ならないようにした。
- 結果画面の各通常動画へ`サムネだけ再生成`を追加した。Shortには追加していない。
- 再生成はRQ background jobで1枚だけ処理し、完成MP4と他サムネは変更しない。
- 再生成中は旧サムネを維持し、成功後にrevision付きURLで新画像へ更新する。
- 先頭サムネをpriority読込にし、結果画面のLCP warningを防止した。

### 変更ファイル

- `backend/app/assets/thumbnail_templates/raden_normal_v1/background.png`
- `backend/app/assets/thumbnail_templates/raden_normal_v1/template.json`
- `backend/app/jobs/thumbnail_frame_selection.py`
- `backend/app/render/render_thumbnail.py`
- `backend/app/jobs/thumbnail_regeneration.py`
- `backend/app/jobs/thumbnails.py`
- `backend/app/jobs/thumbnails.py`
- `backend/app/jobs/queue.py`
- `backend/app/api/exports.py`
- `backend/app/api/jobs.py`
- `backend/app/schemas.py`
- `backend/tests/test_thumbnail_rendering.py`
- `backend/tests/test_thumbnail_integration.py`
- `backend/tests/test_thumbnail_frame_selection.py`
- `frontend/app/results/[jobId]/page.tsx`
- `frontend/components/ResultVideoCard.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `design-qa.md`

### 最小検証

- backend全体: `984 passed, 1 skipped`。workspace内のテストDBを明示して全件成功。
- backend/launcher/scripts ruff: 成功。
- frontend: `typecheck`、`lint`、`build` 成功。
- 実Job `job_c3929427d1414bb6a9a05ec82c57d5ab`: 1本目を連続再生成し、フレーム`42.270秒 -> 126.809秒 -> 211.348秒 -> 274.752秒`と画像SHA-256が毎回変化することを確認。
- 完成MP4 SHA-256: 再生成前後とも`C46325670A81F2304D9E6EA376E5618670CCD0EC22132F092AA1C72036A3C261`。
- 参照・実装サムネを同じ`1280x720`で並べ、背景、人物位置、文字階層、顔との非干渉を確認。
- 結果画面: 再生成後のサムネ表示、操作部の重なりなし、Browser console error`0`・warning`0`を確認。
- Docker: backend / frontend / workerを最新実装で再buildし、backend health `200`を確認。

### 未解決事項

- 儒烏風亭らでん以外の出演者用テンプレは未実装。
- ユーザー受入は未確認。

## 2026-09-03 通常サムネの胴体誤検出修正・顔寄り選択

### 目的

- サムネ再生成で人物の顔ではなく胴体だけが大写しになる問題を防ぎ、顔寄り構図も選べるようにする。

### 現在状態・変更

- 実Jobの顔検出結果を確認し、上側の実顔より大きい衣装部分の誤検出を選んでいたことを特定した。
- 候補選定と描画時クロップの両方で、右側・上側・最小寸法を満たす顔を優先する。
- 顔検出済み候補が6件未満でも、未検証時刻で穴埋めせず、顔が確認できた時刻だけを巡回する。
- 結果画面の再生成操作を`別場面（上半身）`と`別場面（顔寄り）`へ分けた。
- 顔寄りは顔の表示高を`0.34`、上半身は`0.25`として同じテンプレ内で切り替える。
- 選択した寄り方を`thumbnail_crop_mode`へ保存し、workerの描画へ渡す。

### 変更ファイル

- `backend/app/api/exports.py`
- `backend/app/jobs/thumbnail_frame_selection.py`
- `backend/app/jobs/thumbnail_regeneration.py`
- `backend/app/render/render_thumbnail.py`
- `backend/app/schemas.py`
- `backend/tests/test_thumbnail_frame_selection.py`
- `backend/tests/test_thumbnail_integration.py`
- `backend/tests/test_thumbnail_rendering.py`
- `frontend/app/results/[jobId]/page.tsx`
- `frontend/components/ResultVideoCard.tsx`
- `frontend/lib/api.ts`
- `design-qa.md`
- `STATUS.md`

### 最小検証

- thumbnail関連: `26 passed`。
- backend全体: `988 passed, 1 skipped`（workspace内basetempで再実行）。
- ruff: 対象4ファイルで成功。
- frontend: `typecheck`、`lint`、`build`成功。
- Docker: backend / workerを`raden_normal_v4`を含む最新版で再buildし、backend health `200`を確認。
- 実Job `job_c3929427d1414bb6a9a05ec82c57d5ab`: `normal_02`を`130.283秒`、`normal_03`を`60.991秒`で再生成し、両方とも頭・顔・上半身が表示されることを画像確認した。
- 画像SHA-256: `normal_02`は`168FB1... -> 6C676B...`、`normal_03`は`AD5B04... -> D7123D...`へ変化した。
- `normal_01`で顔寄りを実行し、`thumbnail_crop_mode=close`、`thumbnail_template_version=raden_normal_v4`、フレーム`274.75秒`、顔・頭の余白、文字との非干渉を確認した。
- 完成MP4 SHA-256は`C46325670A81F2304D9E6EA376E5618670CCD0EC22132F092AA1C72036A3C261`のままで不変。
- Browser console: error`0`・warning`0`。

### 未解決事項

- ユーザー受入は未確認。

## 2026-09-07 承認済み旧Jobの容量整理

### 目的・変更

- ユーザーが削除を承認した8 Jobに対象を固定し、更新日時・参照関係を再確認した。
- `job_94f59bdad538465783074aaca14da152`は編集中Jobから参照されていたため保護。残り7 Job、対応Export 16件、未参照Videoレコード5件を削除した。
- 共有元動画4.13 GiBは残存Videoが使用しているため保護。元動画実体3ファイルを含む459ファイル、8.178 GiBを削除した。当初12.62 GiBの見積もりは親Job・共有実体の保護を反映していなかったため訂正。
- 対象は`storage/outputs`、`storage/temp`、`storage/uploads/.blobs`、`storage/heatmaps`の検証済み絶対パスのみ。`youtube`は変更していない。
- 実行記録: `.codex_tmp/cleanup-20260907/manifest.json`、`result.json`。削除前DB: 同ディレクトリの`autoclipper-before.db`。運用用スクリプト: `.codex_tmp/cleanup-approved-20260907.ps1`。
- DBバックアップは整合性とSHA-256を確認。動画実体の退避コピーは作成していないため、このバックアップだけでは削除動画は復元できない。

### 最小検証結果

- storage: 34.312 -> 26.134 GiB。C:空き258.50 GiB（27.89%）。
- 残存Job 26件（completed 22、予定確認3、字幕確認1）、Video 7件、Export 40件。
- DB `integrity_check=ok`、`foreign_key_check`違反0。残存Job/Exportの全行が削除前と一致。
- 残存成果物1222ファイルの存在・サイズ一致、編集中JSON 91件のSHA-256一致、残存元動画の存在を確認。

### 未解決事項

- アプリの自動清掃は今回変更していない。既存清掃の親Job参照保護は未実装であり、今回の整理は参照保護付きの限定スクリプトで行った。

## 2026-09-07 字幕1件ごとの書式・二重縁取り・ショート顔アップ

### 目的・仕様変更

- 通常/ショート共通の字幕書式を維持し、選択した字幕1件だけフォント・色・サイズ・位置・縁を上書きする。部分文字列単位の変更は対象外。
- 字幕一覧の「この字幕の書式」で該当位置へ移動し、書式エディタを個別モードへ切り替える。「共通書式を編集」「個別設定を解除」を用意。OKまで即時プレビュー、OKで対象clipのみ保存。
- 文字色・内縁色/幅に外縁色/幅を追加。外縁幅0が既定。タイトル・フック・通常字幕すべて対応。
- ショートの拡大上限160%→300%。標準100%・顔アップ180%・顔アップ強240%の選択肢を追加。上下左右の既存調整と組み合わせる。

### 変更ファイル・実装

- backend: `candidates/merge_boundaries.py`、`schemas.py`、`jobs/subtitle_review.py`、`api/jobs.py`、`render/subtitles_ass.py`、`render/crop_strategy.py`、`overlay_text.py`。
- frontend: `app/jobs/[jobId]/subtitles/page.tsx`、`components/ClipTextStyleEditor.tsx`、`lib/types.ts`、`lib/api.ts`、`lib/clipTextStyle.ts`、`lib/subtitlePreview.ts`、`app/globals.css`。
- 個別書式は元字幕のstart/endと紐付けてclip単位で保持。API省略時は保持、空配列で解除。別clip・隣接/重複字幕への流出を防ぎ、再編集からCandidate/ASSまで引き継ぐ。
- ASSの二層Dialogueとブラウザの二層文字を実装。改行/fit計算に外縁幅も含める。CSS strokeはASS半径に合わせて直径換算。
- 851チカラヨワク、けいふぉんと！、無心、暗黒ゾン字、たぬき油性マジックを公式配布由来の未改変ファイルで追加。ライセンスは`frontend/public/fonts/README.md`と同梱文書に記録。
- キルゴUかなNBは原配布readmeで再配布禁止のためローカルのみ導入。TTFはgitignore/dockerignore対象。別PCへの同梱やイメージ配布はしない。Dockerではローカルfontsディレクトリをread-only mount。
- 検証追加: `backend/tests/test_phrase_styles.py`、`frontend/tests/phraseStyles.test.ts`。

### 検証結果

- backend全体: `996 passed, 1 skipped`。ruff成功。テスト用DB/storageを`.codex_tmp`配下へ隔離。
- 初回はroot cwd由来のDB相対パス不一致で既存manual workflow 2件失敗。隔離した絶対パスを指定して再実行し成功。本番DB/編集中Jobは変更していない。
- frontend: typecheck、lint、build、overlay-fit golden、phraseStylesテスト成功。
- 分離したQAデータを使い、Chromeで個別書式選択→色/サイズ/外縁変更→OK保存payloadを確認。共通書式nullのまま、個別1件だけ保存。pageerror 0。
- ローカルFFmpeg/libassで追加6書体の二重縁取りPNGを出力。けいふぉんとの同一保存設定を比較し、赤文字bboxは1080×1920換算で最大4.1px差（ブラウザ縮小表示に伴う丸めを含む）。全書体のピクセル完全一致を保証した結果ではない。
- QA記録: `.codex_tmp/phrase-qa/`。QA用3009サーバーは停止。Next devが今回自動生成したfrontendのAGENTS/CLAUDEファイルのみ除去し、無関係な変更は残していない。

### 未解決事項

- やさしさゴシックは公式BOOTHログインが必要。ユーザーに原本ZIP/フォントを依頼済み。未追加であり、似たフォントへの代替はしていない。
- Dockerエンジンに接続できず、compose通常起動環境への反映・実素材での顔アップ受入は未確認。Docker設定の起動成功とは扱わない。
- この作業のcommit/PUSHは未実施。

## 2026-09-08 字幕個別書式のPUSH・再起動試行

- 目的: 検証済みの字幕個別書式・二重縁取り・顔アップ変更をPUSHし、通常環境へ反映する。
- PUSH: `dc07537` を `origin/codex/task-132-content-first-selection` へ送信成功。既存の未追跡サムネ素材・storage/qaは対象外。再配布禁止フォントは含めていない。
- 検証: `git diff --check` 成功。前項のテスト結果を引き継ぎ、実装コードへの追加変更なし。
- 再起動: Docker Desktop起動コマンドを実行したが、Dockerエンジンは未起動。起動ログに `sailor-ingest.sock` の削除/アクセス失敗とbackend終了を確認。Docker API用named pipeへ接続不可、WSLのdocker-desktopはStopped。
- 未解決: Docker実行環境の復旧が必要。compose更新版の起動・通常環境への反映は未完了。workspace外のソケット削除、Docker初期化、動画データ削除は実施していない。

## 2026-09-08 Docker実行用ソケット復旧・更新版起動

- 目的: ユーザー承認を受け、Dockerの起動障害を復旧し、PUSH済み更新版を通常環境へ反映する。
- 観測: Dockerプロセス/WSL停止中でも実行用ソケット参照がError 1920。runフォルダーACLはユーザーFullControl。最初のソケット退避後、docker-secrets-engine/engine.sockでも同じ起動エラーを確認。
- 対応: Docker停止確認後、LocalAppData/Docker/runとLocalAppData/docker-secrets-engineを同じ親の`.stale-20260908-*`へ退避。空フォルダーを再作成しDocker Desktopを起動。途中の退避先も削除せず保持。Docker初期化、WSLディスク削除、動画/DB/ボリューム削除は行っていない。
- 結果: 2か所を同時に退避した後、Docker Engine 29.7.2が応答。LauncherController.start(rebuild=True, open_browser=False)で更新版を再ビルド/起動成功。
- 最小検証: backend/frontend/redis/workerの4サービスrunning、backend healthy。GET /healthとfrontend /uploadはHTTP 200。worker profile=gpu、CUDA devices=1。Codex bridge ready。コンテナ内でsubtitle_styles、outer_outline_width、framing_zoom上限3.0を確認。ローカル限定キルゴフォントのread-only mountも存在確認。
- 変更ファイル: STATUS.mdのみ。アプリコードの追加変更なし。既存の未追跡サムネ素材・storage/qaは対象外。
- 未確認: 再起動後の実素材での新規書き出しは未実施。やさしさゴシック原本待ちは継続。ソケットが残存した元の原因までは確定していない。

## 2026-09-10 Codex更新後の投稿案生成エラー対策

- 目的: 長時間起動したCodexブリッジが旧CLIパスを保持し、Desktop更新後に投稿案生成が失敗する問題を修正する。
- 観測: ブリッジは09:12起動、現在のCLIは22:17更新。23:24以降の失敗応答はthreadIdなし。更新後CLIの直接実行は前段診断で成功。旧パスの起動失敗は従来コードで汎用`codex_failed`になる。
- 変更ファイル: `launcher/codex_bridge.py`、`backend/tests/test_codex_host_bridge.py`、`STATUS.md`。
- 変更内容: リクエストごとにCLIパスを検出。検出中に消えた旧ファイルは除外。起動自体に失敗して新パスを発見した場合のみ1回再試行。タイムアウト・生成中の失敗・停止要求では再試行しない。CLI不在と起動失敗を専用コードで区別する。
- 最小検証: ブリッジ/Windowsランチャー/タイトルフック連携テスト`90 passed`。対象ruff、`git diff --check`成功。起動後・同一キュー内のCLI更新、起動直前/検出中の更新、再試行回数制限、停止/失敗時の非再試行を確認。
- 反映: 待機/処理中リクエスト0件を確認し、LauncherControllerでブリッジを再起動。新版PIDのreadyとbuild fingerprint一致を確認。backend healthはHTTP 200。
- 実動作: `job_edd7a387d63749adad9ac8a5db28b87b`の直近失敗clip `cand_normal_1718040_1836080_164305f38e`を既存APIから再生成し、23:57にready、投稿案3件、説明欄276文字、errorなしを確認。入力/draft hashを維持し、`subtitle_review.json`のSHA-256は再生成前後で一致。候補の自動適用はしていない。
- 現在状態: 修正・稼働ブリッジ反映・直近失敗clipの実生成確認まで完了。他5 clipの失敗案は今回再生成していない。commit/PUSHは未実施。

## 2026-09-11 保存時に投稿用セットが欠落する不具合

- 目的: 通常/ショートで、字幕確認中に採用した投稿用セットが完成画面で消え、再編集が必要になる問題を修正する。
- 原因: frontendが未保存字幕の有無だけで投稿案の候補・採用ID・revisionを消去しmanualへ変更。未保存字幕から生成した最新案まで対象になり、backendのCodex用元配信/タグ補完も実行されなかった。右側のスーラ通常clipと財布ショートは最終字幕revision=生成revision、公開タイトル/説明文=生成案であり、表示・書き出し漏れではなく保存時消去と確認。
- 変更ファイル: `frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/lib/youtubePosting.ts`、`frontend/components/ResultVideoCard.tsx`、`frontend/tests/youtubePosting.test.ts`、`backend/app/api/jobs.py`、`backend/app/posting_metadata.py`、`backend/tests/test_title_hook_suggestions.py`、`backend/tests/test_posting_metadata.py`、`STATUS.md`。
- 修正: 未保存だけでは投稿案を削除せずbackendで実際の保存予定字幕revisionを検証。手修正時も元字幕revisionを保持し、最新案の候補を維持。manual投稿文の元配信/出演情報と空のタグを補完し、既存の定型文は重複させない。候補がない手入力タイトルも完成画面の投稿セットに表示。
- 仕様変更: 本当に古いCodex案は同時字幕保存でも422で止め、候補を黙って消して完成扱いにしない。手修正文は保持し、古いAI根拠のみ無効化する従来挙動を維持。
- 検証: backend全体`1015 passed, 1 skipped`。backend ruff成功。frontendの投稿用payloadテスト、typecheck、lint、build成功。通常/ショート×Codex/手修正で未保存字幕から生成→同時保存→投稿用JSON/Markdown引継ぎと二重保存時の非重複を検証。
- 反映: backend/frontendをDockerで再build・再作成。health 200。進行中の動画処理を保護しworker/redisは同一コンテナで継続。今回の保存API/完成画面の修正は反映済み。
- 既存データ復元: 表示中`job_edd7a387d63749adad9ac8a5db28b87b`のスーラ通常clipと財布ショートは、現字幕revisionと生成案の一致・公開タイトル/説明文の一致を確認して候補3件と採用IDを復元。地獄蒸しプリン通常clipは字幕revision不一致のため古い候補は戻さず、現行手入力文へ出典/タグのみ補完。未採用/生成失敗の2 clipは対象外。
- 更新成果物: 該当clipのreview、selected metadata/summary、export metadata、投稿用JSON/Markdown、download.zip。MP4/字幕ファイル全12件のSHA-256は前後一致。ZIPは全entryを維持し、差替メタデータ一致と未変更entryのCRC/size一致、testzip成功を確認。
- 復元作業の初回はZIP内コピーでZipInfoのheader offsetが変更され停止。反映前だったため元成果物は不変。ZipInfoを複製して再試行し成功。変更前ファイル・ZIPは`.codex_tmp/posting-save-20260911/completed-backup/`に保持。実行/結果記録も同QAディレクトリに保存。
- ブラウザ検証: ユーザーが開いていたChromeの完成画面を更新し、通常/ショート両方で3候補・採用表示・元配信URL・タグを確認。
- 現在状態: 修正・反映・対象既存データの復元と表示確認まで完了。commit/PUSHは未実施。

## 2026-09-11 同じ元動画の再アップロード時に使用済み区間を除外

- 目的: 再ダウンロードで画質・形式・ファイル内容が変わっても、同じYouTube動画の過去の書き出し区間を自動選定から除外する。
- 現在状態: 実装・隔離環境テスト・backend/GPU workerへの反映・実保存履歴を用いた動作確認まで完了。commit/PUSHは未実施。
- 変更ファイル: `backend/app/source_clip_history.py`、`backend/app/candidates/used_ranges.py`、`backend/app/models.py`、`backend/app/db.py`、`backend/app/storage/lifecycle.py`、`backend/app/candidates/codex_initial_selection.py`、`backend/app/jobs/runner.py`、`backend/tests/test_source_clip_history.py`、`backend/tests/test_real_pipeline.py`、`STATUS.md`。
- 仕様: 元ファイル名のYouTube動画IDを優先し、元配信URL、同一ファイルのSHA-256の順に照合。タイトル文字列だけでは一致させない。通常/ショート共通で過去の完成区間と1ms超重なる自動候補を除外。端点が接するだけなら許可。
- 保存: `source_clip_usage`に元動画識別子・元動画時刻のstart/end・種別・job ID・元動画尺だけを記録。ジョブ/動画への外部キーを持たず、保存期限による動画/ジョブ削除後も残す。起動・選定・cleanup前に既存のcompleted成果物から補完。未完成/失敗/未採用候補は記録しない。
- 選定: Codexと従来経路の両方で入力・候補を除外し、境界補正後も再検証。Codex再選定にも適用。本数不足を使用済み場面で埋めない。同一ジョブの再試行・既存clipの再編集・手指定区間は妨げない。
- 時間ずれ対策: 同じ識別子で元動画尺が過去と1秒超異なる場合は`source_history_timeline_changed`で停止。時間がずれた旧区間を黙って流用しない。
- 検証: backend全体`1035 passed, 1 skipped`、ruff成功。別エンコード相当の同一動画IDによる初期選定/再選定、通常/ショート横断除外、境界補正後の除外、完成時保存、二重登録防止、cleanup後保持、異なる動画の非除外、手動/再編集例外、元動画尺変更を検証。テストDB/storageは`.codex_tmp`に隔離。
- 反映前保護: SQLite backupを`.codex_tmp/source-history-20260911/before-history.db`へ作成、integrity_check=ok。RQ worker idle、started/queued=0を確認。DBに残る`generating_candidates` 1件は2026-09-10更新のまま、今回変更しない。
- 反映結果: backend/GPU workerをbuild・再作成。backend health=200、worker idle・新しい履歴コードのimport成功・CUDA devices=1。frontend/redisは再作成していない。起動時に2元動画・23件の使用履歴を既存completed成果物から取り込み。
- 実環境確認: 保存済み朝活配信のIDを持つ別形式の仮想入力（DBへ追加せず）で履歴11件/結合後6区間を照合し、使用済み通常/ショート候補の残数0を確認。既存jobs/videos/export_items/app_preferencesは反映前backupと全行一致、SQLite integrity_check=ok。新規の実動画アップロード・AI再選定・MP4再書き出しは実行していない。
- 制限: 導入前に成果物とDB記録が既に削除された場面は復元できない。ID/元配信URL不明の再エンコードは識別不可。同じ尺のまま元配信が編集された場合の時間ずれ検出、および未完成ジョブ同士の同時予約は対象外。今回の変更のcommit/PUSHは未実施。


## 2026-09-12 アップロード設定の10枠保存・字幕/フック/タイトル書式

- 目的: ブラウザ指摘に対応し、保存テンプレートを3→10件へ拡張。会話字幕・フック・タイトルの初期書式に内縁/外縁の幅・色を用意。上部の処理モード/動画タイプ/作成種別/通常本数/ショート本数をデスクトップで1行へ集約。APIを使う内容判定・字幕校正をアップロード導線から除去。
- 現在状態: 実装、検証、backend/frontend/GPU workerへの反映、表示確認まで完了。branch=`codex/task-133-upload-style-settings`。既存の未コミット変更を保持。今回のcommit/PUSH/PR作成は未実施。
- 変更ファイル: `frontend/components/SubtitleStyleEditor.tsx`、`ClipTextStyleEditor.tsx`、`SettingsPanel.tsx`、`ClipSelectionEditor.tsx`、`frontend/lib/uploadTextStyles.ts`、`subtitleStylePresets.ts`、`types.ts`、`frontend/app/upload/page.tsx`、`globals.css`、`backend/app/schemas.py`、`backend/app/render/subtitles_ass.py`、`backend/tests/test_upload_text_styles.py`、`test_api_routes.py`、`frontend/tests/uploadTextStyles.test.ts`、`STATUS.md`。
- 実装: 既存のクリップ書式エディタを初期設定にも使用。通常/ショート×字幕/フック/タイトルを独立保存。新規の6書式はPydantic ClipTextStyleで検証し、JobSettings→SubtitleLayout→共通resolverで確認プレビューと最終ASSへ引き継ぐ。クリップ個別設定を優先。旧字幕設定は新形式を編集するまで有効。
- 保存互換: 既存version=1・3枠の保存文書を10枠へ展開し、後ろ7枠は空欄。既存設定の値は維持。10枠を超える入力は422。フロントのブラウザ保存とbackendのSQLite保存の両方を拡張。
- API非使用: 内容判定とOpenAI字幕校正の選択UIを除去し、アップロード送信時に`useOpenAIScoring=false`、`ensureSelectedOpenAIScored=false`、`subtitleCorrectionMode=off`を固定。Codex初期選定は維持。既存ジョブの設定・backendの従来API契約は変更しない。
- 検証コマンド: `python -m pytest backend/tests -q`、`python -m ruff check backend`、`npm --workspace frontend run typecheck`、`npm --workspace frontend run lint`、`npm --workspace frontend run build`、`npm --workspace frontend exec -- tsx tests/uploadTextStyles.test.ts`、`git diff --check`。
- 検証結果: backend全体`1039 passed, 1 skipped`、ruff、frontend型検査/lint/build、新規移行テスト、diff検査成功。旧3枠・10枠目の保存/再取得、6書式と二重縁取りのASS反映、クリップ個別設定優先を確認。初回の新規テストは字幕がフックと重なり仕様どおり非表示だったため、字幕時間をフック後へ修正。全体初回は既存テスト1件の一時ファイルreplaceでWinError 5が発生し、コード変更なしの単独再実行と全体再実行で成功。
- 実描画: 新backendイメージをネットワークなしの隔離コンテナで起動し、通常1920x1080/ショート1080x1920の5秒H.264 MP4を生成。内縁3/外縁7、黄文字/黒内縁/白外縁、タイトル/字幕の描画をPNGで確認。成果物・スクリプトは`.codex_tmp/upload-style-settings/`。
- 反映: 処理中/待機中ジョブ0件を確認。DBを`.codex_tmp/upload-style-settings/before.db`へバックアップしintegrity_check=ok。3サービスをbuild/recreate、Redisは継続。backend healthとupload画面HTTP 200、稼働workerの新書式resolverを確認。
- ブラウザ: 指定された埋め込みブラウザで5項目の1行配置、2/10保存済み、保存枠1〜10、フック/タイトル/通常の切り替えと設定独立を確認。検証用に入力した外縁7は個別設定解除で戻した。既存保存済み2件のSQLite行は更新前と完全一致、DB integrity_check=ok。更新前に選択されていた人物アップ画角も戻した。
- 未解決/制限: 実素材を新規アップロードして文字起こしから完成まで通すE2Eは今回未実施。初期書式の追加は今後作成するジョブに適用し、過去の完成MP4は変更しない。

## 2026-09-12 外縁カラーを色欄へ移動

- 目的: 外縁の色を「書体・サイズ」から「色」欄へ移し、定番色を選べるようにする。
- 変更ファイル: `frontend/components/ClipTextStyleEditor.tsx`、`STATUS.md`。
- 変更: 文字色・内縁色の下に外縁色を配置。任意色ピッカーと白/黄/水色/ピンク/緑/黒の6色ボタン、選択中表示を追加。共通エディタを使う初期設定・クリップ編集の両方へ適用。
- 検証: frontend typecheck/lint/build、frontend Docker image build成功。埋め込みブラウザで移動後の配置と6色を確認し、黄を選択→color inputが#FFF200へ変化→元の白へ復帰を確認。入力中のタイトル位置Y650、人物アップ画角、保存済み2/10を維持。
- 反映: 稼働frontendの同一ソースへ反映しFast Refreshを使用。ブラウザの再読込やコンテナ再起動を避け入力状態を保持。次回再作成用イメージも更新。backend/workerは変更なし。
- 現在状態: 修正・画面反映・表示操作確認まで完了。今回の追加テストコードはなし。commit/PUSHは未実施。


## 2026-09-12 名前付きショート帯の保存と確認・長さ設定の横並び

- 目的: らでん専用だった上下帯を出演者・用途別に保存し、「ショート画面」「開始後の確認」「詳細な長さ設定」をデスクトップで1行に収める。
- 現在状態: ローカル実装・稼働環境への反映・最小検証完了。ユーザーによる別出演者用画像での実運用は未確認。
- 変更ファイル: `frontend/components/ShortBannerPresetManager.tsx`、`frontend/lib/shortBanners.ts`、`frontend/components/SettingsPanel.tsx`、`frontend/components/SubtitleStyleEditor.tsx`、`frontend/lib/types.ts`、`backend/app/short_banners.py`、`backend/app/api/short_banners.py`、`backend/app/api/jobs.py`、`backend/app/main.py`、`backend/app/schemas.py`、`backend/app/storage/paths.py`、`backend/app/render/render_short.py`、`backend/app/render/render_exact_review_preview.py`、関連テスト3ファイル、本ファイル。
- 実装・仕様変更: 帯プリセットを名前・上下画像・上下ON/OFFの組で最大10件保存。らでん用標準帯は継続利用可能。PNG/JPEG/WebPを10MB・1600万画素まで受け付け、PNG化した内容ハッシュでstorage/banner_assetsへ保存。プリセットの上書き・削除で過去ジョブの画像は変更しない。ジョブ設定へ画像IDを保存し、最終レンダー・exact/live previewのキャッシュキーと実レンダー・字幕確認の画像配信に反映。
- UI: ショート画面・開始後の確認・詳細な長さ設定・字幕焼き込みを同じ行へ移動。狭い幅では折り返す。帯の保存・画像編集は直下の開閉欄へ配置。初期字幕プレビューにも実際の帯画像を表示。
- 検証: backend全体 `1042 passed, 1 skipped`。`python -m ruff check backend`、frontend typecheck/lint/build成功。合成2秒動画でカスタム上帯シアン・下帯赤を最終MP4とexact previewに出力し、1080x1920と上下の色を確認。検証記録は `.codex_tmp/short-banner-presets/`。
- 稼働確認: Docker backend/frontend/GPU workerイメージをビルド。キュー0・実行中0を確認後backend/worker更新、frontendはFast Refreshで反映。backend healthy、4サービスrunning、帯画像配信HTTP200。画面で「らでん用」を保存・再呼び出しし、DB/APIにも1件保存を確認。既存タイトル設定88px/Y650、顔追従設定を保持。
- 未解決事項: 別出演者用の実画像による運用確認は未実施。素材は利用者が帯の編集欄から選ぶ。

## 2026-09-12 キャラ別の投稿情報・帯・タイトル末尾・サムネイル一括保存

- 目的: 複数キャラ・別チャンネルのショート運用で同じ設定を毎回入力せず、保存名を選ぶだけで呼び出せるようにする。
- 現在状態: 実装、backend/GPU workerとfrontendへの反映、保存・切替・再読込確認まで完了。既存の未コミット変更を保持。commit/PUSH/PR作成は未実施。
- 新規ファイル: `backend/app/api/character_presets.py`、`backend/app/thumbnail_style.py`、`backend/tests/test_character_presets.py`、`frontend/components/CharacterPresetManager.tsx`、`frontend/components/CharacterThumbnailSettings.tsx`、`frontend/lib/characterPresets.ts`、`frontend/tests/characterPresets.test.ts`。
- 変更ファイル: `backend/app/main.py`、`schemas.py`、`posting_metadata.py`、`api/jobs.py`、`jobs/subtitle_review.py`、`jobs/title_hook_suggestions.py`、`jobs/quality_gate.py`、`jobs/thumbnails.py`、`jobs/thumbnail_regeneration.py`、`jobs/runner.py`、`scoring/title_hook_suggestions.py`、`render/render_thumbnail.py`、`backend/tests/test_codex_host_bridge.py`、`test_thumbnail_integration.py`、`test_title_hook_suggestions.py`、`frontend/lib/types.ts`、`frontend/components/YouTubePostingSettingsPanel.tsx`、`SettingsPanel.tsx`、`ShortBannerPresetManager.tsx`、`frontend/app/upload/page.tsx`、本ファイル。
- 仕様: 最大50件をSQLite AppPreferenceに保存。管理用チャンネル名・出演者/所属/ハッシュタグ/タグ・上下帯画像とON/OFF・通常タイトル末尾・通常サムネイル背景と配色・字幕/タイトル/フック書式・通常/ショート本数を一括保存。元配信タイトルとURLは保存対象外で、キャラ切替時にも維持。最後に選んだキャラを再読込時に復元。
- 初期値/互換: 新しいキャラは通常0本/ショート3本、出演者等空欄、帯なし、末尾なし、単色サムネイル。既存らでん投稿設定を1件として取り込み、現在の字幕書式も初回保存。旧ジョブの未指定タイトル末尾・サムネイルは従来動作を維持。新規ジョブへ設定を複製するため、プリセット上書き/削除で過去ジョブの設定は変化しない。
- サムネイル: 既存らでん背景・単色・アップロード画像を選択し、背景色/見出し2色/外縁色を保存。人物を右・見出しを左に置く既存レイアウトを使用。通常タイトル末尾は生成候補・確認編集・投稿情報・品質検査へ同じ設定を引き継ぐ。
- 修正履歴: 色ピッカーの変更を保存した際に値が残らないケースを実画面で検出し、onInput対応を追加。設定切替時の帯表示を実際の画像/ON/OFFから判定し、別キャラの帯なしを表示。旧投稿プロファイルの独立読込を除き、キャラ復元との競合を解消。
- 検証: backend全体 `1048 passed, 1 skipped`、`python -m ruff check backend`、frontend lint/typecheck/build、`npx tsx frontend/tests/characterPresets.test.ts`、`git diff --check`成功。保存/選択/旧データ取込/ジョブ独立、動画情報維持、末尾なしとカスタム末尾、生成入力・投稿反映、単色/画像サムネイルの実画像ピクセル、再生成への設定継承を検証。
- テスト再試行: Windows上のstatus heartbeat JSON読込が一時PermissionErrorになる既存テストを、既存の監視期限内で再読込する形に修正し観測必須条件は維持。別の既存atomic replaceテストで一度WinError 5が発生したため単独再実行し成功、最終全体実行も成功。ランタイムのbridge処理は今回変更していない。
- 実画面確認: 確認用別キャラを作成し、投稿情報・末尾・背景色を保存。らでんとの相互切替、別キャラの帯なし/ショートのみ、再読込後の末尾と背景色#2255aaの復元を確認。確認用キャラだけを削除し、らでん1/50・帯1/10・字幕2/10へ戻した。QA記録/バックアップは `.codex_tmp/character-presets/`。
- 稼働確認: キュー/実行中0件確認後backend/GPU workerを更新。frontendはファイル反映とFast Refreshを使用し、最終変更を含むDocker imageもビルド。backend healthy・health HTTP200、frontend/worker/redis running。
- 未解決/制限: 新規の実素材アップロードから文字起こし・最終MP4生成までのE2Eは未実施。サムネイルは背景/配色の保存であり自由配置エディタではない。チャンネル名は管理用でYouTubeの投稿先アカウントを自動切替する機能ではない。

## 2026-09-12 キャラ設定・アップロード設定と未送信修正のPUSH

- 目的: ユーザー指示「PUSH」に従い、検証済み変更を `origin` の `codex/task-133-upload-style-settings` へ送信する。
- 対象: 本日のキャラ一括保存・帯保存・字幕書式/UI調整、および本ファイルに記録した未送信の投稿情報保存修正・使用済み区間除外・Codex更新時のブリッジ修正。変更ファイルは各作業項目に記載。
- 除外: `storage/qa/` の検証画像、未参照の `backend/app/assets/thumbnail_templates/raden_normal_v1/base.png`、`.codex_tmp/` 内のDB/ログ/動画。ローカルファイルは保持。
- 検証: 直前実装のbackend全体 `1048 passed, 1 skipped` とfrontend lint/typecheck/build成功を確認。PUSH前にbackend/launcher ruff、frontend overlay-fit、差分検査を実行し成功。Docker 4サービスrunning、backend healthy。
- 制限: 今回はブランチのPUSH。mainへのマージとPR作成は実施しない。現行CIはpull_requestまたはmainへのpushで起動する設定のため、このブランチへのpush単独では起動しない。

## 2026-09-12 帯単独の呼び出し・保存UIを削除

- 目的: キャラ別一括保存に集約し、不要になった帯単独の呼び出し導線を外す。
- 変更ファイル: `frontend/components/ShortBannerPresetManager.tsx`、`STATUS.md`。
- 変更: 「帯だけ呼び出す」の選択欄、帯単独の保存名/保存/削除/件数表示、単独プリセット取得・更新処理をUIから削除。「帯画像を編集」に上下プレビューと画像選択を残し、キャラ一括保存へ案内。上下ON/OFFも維持。既存の保存データとbackend APIは変更しない。
- 検証: frontend lint/typecheck/build、Docker frontend image build成功。稼働frontendへFast Refreshで反映し、実画面で選択欄の消失、画像編集欄とキャラ一括保存ボタンの維持を確認。
- 現在状態: ローカル修正・画面反映済み。この追加変更は未コミット/未PUSH。

## 2026-09-13 字幕修正画面で選択語句を一括修正

- 目的: 字幕中で選んだ誤字を、同じジョブの通常/ショートの字幕へまとめて修正する。ユーザーの訂正により、選定画面は閲覧・範囲調整のまま維持し、字幕確認画面に実装。
- 変更ファイル: `frontend/components/SubtitleBulkCorrection.tsx`、`frontend/lib/subtitleBulkCorrection.ts`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/lib/api.ts`、`backend/app/schemas.py`、`backend/app/api/jobs.py`、`backend/tests/test_subtitle_bulk_correction.py`、`frontend/tests/subtitleBulkCorrection.test.ts`、本ファイル。
- UI: 字幕の入力欄で語句を選択→正しい表記を入力→一致数/字幕数/影響clip数と修正前後を確認→一括修正・保存。固有名詞に限定せず、完全一致の文字列を対象とする。複数clipで共有する字幕は一度だけ数える。正規表現/類似語の推測変換は行わない。対象字幕内の未保存文は一緒に保存し、他の未保存字幕・タイトル・書式は保持。
- 保存: `PATCH /api/jobs/{job_id}/subtitle-review/segments`を追加。既存の文書ロック下で全対象のID/更新前本文/重複/編集状態を先に検証し、競合時は全件を拒否。対象字幕を一括保存し、影響clipだけ確認済みを解除・プレビュー更新。文字時刻と元本文は保持。新しい字幕は既存の確認/最終レンダー経路で反映。
- 取り消し: 直前の一括修正を保存付きで戻せる。操作後に対象字幕を再編集した場合は取り消しを無効化し、別の修正を巻き戻さない。取り消し履歴は現在の画面内だけ保持。
- 検証: backend API既存/新規テスト `109 passed`、backend/launcher ruff、frontend lint/typecheck/build、文字列置換テスト、diff検査成功。新規テストは共有字幕への反映・他clip不変・取り消し・競合/存在しないID/重複/完了ジョブの全件拒否を確認。初回テストではpreview入力ファイル不足のfixtureを修正し、実際のpreview spec生成経路で再検証。
- 実画面検証: `.codex_tmp/bulk-ui/` の隔離DB/storageとlocalhost:18000/3001を用意し、仮のアカネ3か所をキーボード選択からあかねへ一括保存、取り消しで原文復帰を確認。実ジョブの字幕は変更していない。仮の動画バイトは再生不可のためMP4表示は検証対象外。検証用サーバー2本とタブは停止/閉鎖。next devが自動生成したAGENTS/CLAUDEとnext-env差分も元に戻した。
- 反映: キュー/処理中0件を確認後backendを再作成、frontendはFast Refreshで反映。両Docker imageをビルド。4サービスrunning、backend healthy/health200。既存完了ジョブの字幕確認画面に一括修正欄が表示されることを確認し、その画面を開いている。
- 制限: 今開いている完了ジョブは確認履歴なので編集不可。実素材の最終MP4再生成は未実施。一括修正の対象は字幕確認文書に含まれる字幕で、選定外の元動画全文や別ジョブには適用しない。今回の変更は未コミット/未PUSH。

## 2026-09-13 文字起こしを既定で全角へ統一

- 目的: キャラに関係なく、新しく作成する文字起こしの英数字・記号・半角カナを全角へそろえる。
- 変更ファイル: `backend/app/audio/transcript_postprocess.py`、`backend/app/schemas.py`、`backend/app/jobs/runner.py`、`backend/app/scoring/rule_score.py`、`backend/app/candidates/deduplicate.py`、`backend/app/candidates/boundary_refinement.py`、`backend/tests/test_transcript_postprocess.py`、`backend/tests/test_real_pipeline.py`、`frontend/lib/types.ts`、本ファイル。
- 実装: 共通設定 `transcriptNormalizeFullwidth=true` を既定値へ追加。従来のNFKC正規化・辞書補正後にASCII英数字/印字記号を全角化し、半角カナと濁点を合成。任意の追加校正後も幅変換だけを再適用して辞書の二重適用を防止。空白は通常の区切りを維持し、内部改行を潰さない。時刻・confidence・clipIdを維持。raw transcriptは元のまま保存。
- 例: `ABC 123!?` → `ＡＢＣ １２３！？`、`ｶﾞｯﾂﾎﾟｰｽﾞ` → `ガッツポーズ`。半角へ戻す必要があるAPI利用では新設定falseで従来幅へ切替可能。後処理全体を無効にした場合は従来どおり無加工。
- 回帰対応: 全角英字で既存の単語判定が外れないよう、反復異常検出・ルール得点・重複判定・境界の英文判定をNFKC化した比較用文字列で実行。保存字幕の全角表記は保持。
- 検証: 関連52テスト成功後、backend全体 `1056 passed, 1 skipped`。backend/launcher ruff、frontend typecheck、diff検査成功。全角/半角で同じ内容判定・字幕時刻維持・冪等性・辞書順序・改行保持・設定無効化を検証。API校正を含む注入依存pipelineの出力も全角を確認。
- 再試行: 最初は旧半角を期待するテストと、英字判定の回帰を検出して修正。境界判定へのimport漏れも修正して再検証。全体テスト初回の2件は既定SQLite参照先がworkspace外を指して開けなかったため、DATABASE_URL/STORAGE_ROOT/SOURCE_LIBRARY_ROOTを`.codex_tmp`へ明示して再実行し全件成功。workspace外へファイルを作成していない。
- 稼働反映: `autoclipper`キュー/started=0を確認し、backend/GPU workerをbuild・再作成。稼働workerで既定trueとサンプル全角化を確認。frontend/redisは再作成しない。backend health HTTP200。
- 制限: 新しい文字起こしから適用。既存ジョブの字幕や完成MP4は変換していない。新規実素材の文字起こしから最終MP4までのE2Eは未実施。今回の変更は未コミット/未PUSH。

## 2026-09-13 選定画面の文字起こしスクロールを維持

- 目的: 開始・終了調整のたびに文字起こし欄が先頭へ戻る問題と、欄の端でページ全体へスクロールが移る問題を修正。再選定欄は初期表示を折りたたむ。
- 変更ファイル: `frontend/app/jobs/[jobId]/clips/page.tsx`、`frontend/components/ClipTranscriptList.tsx`、本ファイル。
- 原因: 時刻入力の更新ごとに取得済み一覧をnullへ戻し、一覧DOMを再作成していた。内側スクロールの伝播抑止もなく、固定計算の欄高さが上部見出し分だけ画面下へはみ出していた。
- 変更: 同一clipの取得中は一覧を保持し、表示中データの時刻と更新中表示を維持。更新後は末尾付近なら末尾へ追従し、途中なら表示中の発話時刻と位置を復元。別clipは先頭から表示。「先頭へ」「末尾へ」を追加。overscroll-y-containで伝播を抑止し、実際の上端とviewportから欄の高さを調整。
- 再選定: 設定フォームを閉じたdetailsへ格納。「字幕確認へ」の説明・ボタンは折りたたみ外に維持。
- 検証: frontend lint/typecheck/build、Docker frontend image build、diff検査成功。隔離DB/storageのQAジョブで終了+15秒/-30秒後の末尾追従、開始-15秒後の同一発話位置維持、別clip切替時の先頭表示、末尾の追加スクロールでpageY不変を確認。実画面でも最終行下端1191px、viewport1272px内に収まること、再選定の折りたたみ、次画面ボタン維持を確認。
- QA再試行: 最初の仮データでboundaryRefinedと共通設定の項目不足を検出し、fixtureに既定値を補完して再確認。実ジョブは変更していない。
- 反映: 稼働frontendへFast Refreshで反映。TOPの設定入力は再読込せず保持。検証用サーバー2本とタブは停止/閉鎖。
- 制限: 実ジョブは完了状態で時刻編集不可のため、時刻変更操作は隔離QAジョブで検証。実動画の再生成は行っていない。未コミット/未PUSH。

## 2026-09-13 動画種別の切替を選定画面へ集約

- 目的: 選定画面で通常/ショートを双方向に変更し、字幕確認画面の変換操作を外す。
- 変更ファイル: `backend/app/api/jobs.py`、`backend/app/schemas.py`、`backend/app/jobs/clip_plan.py`、`backend/app/candidates/select_candidates.py`、`backend/tests/test_clip_plan_type_conversion.py`、`frontend/lib/types.ts`、`frontend/app/jobs/[jobId]/clips/page.tsx`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、本ファイル。
- 変更: 既存type更新APIにshortを追加。対象1本だけを通常/ショートの候補配列へ移し、plan・候補・job設定の本数を同期。ID/タイトル/範囲を維持し、新たなショート化時の複製フック映像は未指定。通常化時は従来どおり複製フックを解除。次の字幕確認には変更後の種別が渡る。
- 制約: ショート化は保存設定shortMaxDuration以内、通常最大12本/ショート最大24本。範囲入力が未反映ならプレビュー更新を案内し、入力を捨てない。選定確認待ちだけ編集可で、完了ジョブは変更しない。手動作成の独立フローは今回対象外。
- 字幕画面: 再編集ジョブ向けのShortConversionEditor表示と変換ハンドラー/状態を削除。通常編集/ショート編集タブは対象の表示切替として維持。既存API利用者の互換性維持のため、旧字幕変換APIとサーバー処理は削除していない。
- 検証: backend全体 `1061 passed, 1 skipped`、backend ruff、frontend lint/typecheck/build成功。新規5テストで双方向・同方向再実行・他clip不変・字幕確認への引継ぎ・長さ/本数超過の無変更拒否・完了状態の拒否を確認。初回APIテストは無関係の既存帯設定テストがWindowsのatomic replaceでWinError 5となり、全体再実行で成功。
- 画面検証: 隔離QAジョブで通常→ショート→通常、未保存範囲変更の保護、再ショート化後に字幕確認へ進み通常1本/ショート2本と変換ボタン0件を確認。QAサーバー2本/タブを停止・閉鎖。仮動画のため映像再生成は検証外。
- 稼働反映: backend/frontend/GPU worker image build成功。autoclipperキュー/started=0確認後backend/worker再作成、frontendはFast Refreshで反映。利用中の選定画面で「ショートに変更」の表示を確認。TOP入力は再読込しない。
- 制限: 今開いている完了ジョブは種別変更ボタン無効のまま。実素材の最終MP4生成は未実施。未コミット/未PUSH。

## 2026-09-13 字幕確認の作業配置と区間編集

- 目的: 字幕保存後も同じclipでタイトル・フックを調整し、字幕の結合/分割と１行表示を指定する。デスクトップではページ全体をスクロールさせず、各作業欄で操作する。
- 変更ファイル: `frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/app/globals.css`、`frontend/components/SubtitleSegmentActions.tsx`、`frontend/lib/{api,types,subtitlePreview}.ts`、`frontend/tests/subtitleStructure.test.ts`、`backend/app/api/jobs.py`、`backend/app/schemas.py`、`backend/app/audio/transcribe_faster_whisper.py`、`backend/app/jobs/{subtitle_structure,subtitle_review,subtitle_review_preview,runner,quality_gate}.py`、`backend/app/render/{subtitles_ass,render_exact_review_preview}.py`、`backend/tests/{test_subtitle_structure,test_guarded_rerender_promotion_gate}.py`、本ファイル。
- 保存導線: 「この内容を保存してOK」で同じclipに残り、「次のclipへ」で明示的に移動。タイトル・フックは入力と候補を左右に配置し、書式・位置・色を別タブにした。clip切替で入力欄を先頭へ戻す。保存中を「書き出し中」と誤表示していた判定も修正。
- 表示: 1280px以上でviewport内の３列/２段に収め、動画・タイトル編集・字幕一覧・clip一覧の高さを可変化。字幕一覧/各編集欄のスクロール伝播を抑止。プレビュー更新時に字幕一覧を先頭へ戻す処理を外し、clip選択時だけ初期化する。
- 区間操作: 各字幕の「区間の結合・分割」から次区間との結合、文字カーソル位置での分割、１行表示/自動改行を保存可能。分割時刻は文字数比の仮値を入力し、秒数または再生位置で調整する。対象の未保存文も同時に保存。共有字幕は対象clipへ反映し、共有範囲が異なる２区間の結合は拒否。編集競合・空の分割・範囲外時刻・完了状態は変更せず拒否する。
- 書き出し: 手動の区切り/１行指定を字幕document、プレビュー、ASS、品質検査へ引継ぎ、自動の再結合/再分割/表示時間延長を抑止。元のindexに依存する処理はreview作成日時別のsource snapshotを使い、書き出し後の再プレビュー/再試行でもずれない。未指定フラグを旧JSON/specへ追加せず、既存保存値とプレビューhashの互換性を維持。
- 検証: backend全体 `1069 passed, 1 skipped`。その後のspec互換性追加を含む関連テスト `26 passed`。backend ruff、frontend lint/typecheck/build、字幕イベント回帰、overlay golden成功。結合/分割後のASS区切り、共有clipの確認解除、通常修正との併用、source snapshotの再利用、１行指定のhash変更を検証。
- 画面検証: 実画面2085x1272と1922x960でdocument寸法=viewport、字幕欄を末尾まで大量スクロールしてpageY=0、通常/ショート/書式タブ切替を確認。隔離DB/storageの仮動画で保存後の同一clip維持、結合→カーソル指定分割→保存→再読込、１行指定解除、「次のclipへ」を確認。仮動画のプレビュー生成と投稿案生成は検証対象外。
- 修正過程: 旧JSON期待値に追加falseフラグが混ざる問題、再レンダリングのテスト用reviewにcreatedAtがない問題、React keyの重複を修正。最終読み直し後のclip/タブ切替で新たなブラウザエラーなし。テスト用サーバーはloopbackに限定して起動し、終了後サーバー２本とタブを閉じた。
- 稼働反映: backend/frontend/GPU worker image build成功。キュー/started=0でbackend/workerを再作成、health HTTP200。稼働backendの区間編集API、workerの手動区切り/１行指定を確認。frontendはFast Refreshで反映し、完了済みの字幕確認タブだけ再読込。TOP入力は再読込していない。viewport指定を解除し、元の確認画面を表示。
- 制限: 現在開いているジョブは完了済みのため閲覧のみ。実ジョブの字幕/完成MP4は変更せず、実素材での最終MP4生成は未実施。未コミット/未PUSH。

## 2026-09-13 通常サムネイルの３段書式設定

- 目的: 通常サムネイルの見出し・上行・下行で、書体・文字サイズ・文字色を個別に設定する。
- 変更ファイル: `backend/app/thumbnail_style.py`、`backend/app/render/{thumbnail_fonts,render_thumbnail}.py`、`backend/app/api/{exports,jobs}.py`、`backend/app/jobs/{thumbnails,thumbnail_regeneration}.py`、`backend/app/schemas.py`、`backend/tests/test_thumbnail_text_styles.py`、`frontend/components/{ThumbnailTextStyleEditor,CharacterThumbnailSettings,ResultVideoCard}.tsx`、`frontend/lib/{thumbnailStyle,types,api}.ts`、`frontend/app/results/[jobId]/page.tsx`、`frontend/tests/thumbnailTextStyles.test.ts`、本ファイル。
- 変更: 結果画面の「サムネイルの調整」に３段別の書体12種・サイズ・色選択を追加。「文字設定でサムネを更新」で現在のフレーム/寄り方を保ち、JPEGだけ再生成する。設定は対象サムネのmetadataに保存し、後の別場面への変更でも維持する。TOPの「通常動画のタイトル末尾・サムネイル」でも設定でき、キャラ設定の保存・呼び出しに含む。
- 描画: 見出し12〜96px、上行/下行12〜180px（1280×720基準）。長文は横幅へ自動縮小し、最大文字サイズで２行が縦にはみ出す場合も枠内へ縮小。許可済みの同梱フォントのみ選択可能。未設定の既存デザイン・文字色・書体を維持。
- 検証: backend全体 `1077 passed, 1 skipped`。最後の高さ調整を含む関連35テスト成功。backend ruff、frontend lint/typecheck/build、キャラ設定roundtripテスト成功。３段の異なる書体ファイル/サイズとJPEGの３色、API→worker→結果への保存、別フレーム再生成後の設定保持、完成動画の不変、不正設定の無変更拒否を検証。生成した検証JPEGを目視確認。
- 検証制限: 隔離QA用frontendの起動が自動承認レビューで拒否（詳細理由なし）。ブラウザからの保存操作は未検証。隔離backendは停止済み。実ジョブのサムネ/完成動画は再生成していない。未コミット/未PUSH。
- 画面検証: 実際の結果画面で見出し・上行・下行を異なる書体/サイズへ変更し、上行のみ色を変えて独立した入力を確認。保存ボタンは押さず、確認用入力を元の設定へ戻した。３段と更新ボタンが読める配置をスクリーンショットで確認。ブラウザエラーなし。
- 稼働反映: backend/frontend/GPU worker image build成功。キュー/started=0確認後backend/worker再作成、health HTTP200。稼働workerで12書体の存在、既存３本の結果APIで３段の文字/設定/寄り方の取得を確認。frontendは変更ファイルをFast Refreshで反映し、結果タブだけ再読込して設定欄を開いた。TOPタブへの再読込操作なし。

## 2026-09-13 サムネ文言の生成・選択・手動編集を結果画面へ集約

- 目的: 完成した通常動画を根拠にサムネ文言３案を生成・再生成し、結果画面で選択・手動編集・書式変更・JPEG更新を完結させる。生成案をそのまま使う操作を標準とする。
- 変更ファイル: `backend/app/{api/exports,schemas,jobs/queue,jobs/thumbnail_copy,scoring/thumbnail_copy,scoring/codex_title_hook_suggestions}.py`、`launcher/codex_bridge.py`、`backend/tests/test_thumbnail_copy.py`、`frontend/components/{ResultThumbnailEditor,ResultVideoCard}.tsx`、`frontend/lib/{api,types}.ts`、`frontend/app/results/[jobId]/page.tsx`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、本ファイル。
- 生成: 完了済み通常exportの公開タイトル、切り抜き範囲に一致するcompleted字幕reviewの保存済み本文だけを入力。reviewがない旧exportは保存済みtranscriptから当該範囲/clipを抽出する。元の誤字本文や動画内タイトル・フックは入力しない。確定範囲の不一致、字幕欠落、未完了、通常以外は生成しない。
- Codex: サムネ文言専用task/schemaを既存bridgeへ追加し、schema指紋を固定登録。OpenAI APIへのフォールバックなし。３案それぞれに見出し/上行/下行・理由・根拠字幕の引用を要求し、ID、引用の実在、根拠にない数値を検証。生成の前後で完成MP4の更新時刻/サイズ・範囲・字幕・公開タイトルのhashを比較し、変更後の古い結果を破棄する。候補は専用ファイルへ保存し、字幕review・export metadataを変更しない。
- UI: 「文言３案を生成」「文言を３案作り直す」、３案比較と「この案を使う」、見出し/上行/下行の手動入力、書体/サイズ/色を同じサムネ欄へまとめた。新規生成後はおすすめ案を自動入力する。候補選択だけではJPEGを変えず、「サムネを保存・更新」で文言と書式を保存してJPEGだけ再生成。別場面への変更でも現在の入力を使用する。字幕確認の通常サムネ入力/仮プレビューを外し、結果画面で調整する案内を表示。初期生成の既存文言は維持する。
- 検証: backend全体 `1085 passed, 1 skipped`。関連55テスト、backend/launcher ruff、frontend lint/typecheck/build成功。修正字幕の使用・範囲外除外・空の動画内タイトル/フック、３案生成/キャッシュ/再生成、手動修正→JPEG更新、MP4/review不変、架空引用・数値・別segment・生成中の動画変更の拒否を確認。初回の新規テストはbridge validatorの関数名を誤記し、修正後に全件成功。
- 稼働反映: backend/frontend/GPU worker image build成功。キュー/started=0、Codex bridge idleを確認し、bridgeを既存controllerで更新、backend/worker再作成。health HTTP200。frontendはFast Refreshで反映。TOP再読込操作なし。
- 実機: 現在の最初の通常動画について修正済み82区間を入力し、実Codex bridgeで３案生成成功。ブラウザでおすすめの自動入力、案２の選択、下行の手直し、案１への復帰を確認。入力中だった見出し書体851チカラヅヨクを維持。実ジョブのサムネ/MP4/reviewは更新せず、文言候補と入力案だけを準備した。
- 制限: 候補の意味の妥当性すべてを機械的に保証するものではなく、根拠字幕を画面で確認可能。実ジョブのJPEG更新は未実施（保存処理は隔離テストで確認）。既存ZIPの再構成処理は今回未変更で、更新後のサムネは個別保存が必要。未コミット/未PUSH。

## 2026-09-13 サムネのプレビュー・文言・書式を横並びに変更

- 目的: 文言候補を開いたまま、保存済みサムネと見出し・上行・下行のフォント/サイズ/色を同時に確認する。
- 変更ファイル: `frontend/app/results/[jobId]/page.tsx`、`frontend/components/{ResultVideoCard,ResultThumbnailEditor}.tsx`、本ファイル。
- 変更: 通常動画を１行１本の横長カードにし、デスクトップでは左に追従するサムネ、右に文言と常時展開した書式設定を配置。文言候補は開閉可能な高さ256pxまでの独立スクロール欄に変更し、スクロール伝播を抑止。画像への反映は既存の「サムネを保存・更新」で行うことを明示。小さい幅では列数を減らす。
- 検証: frontend typecheck/lint/build、Docker frontend image build、差分の空白検査成功。稼働frontendへFast Refreshで反映。2085x1272の実画面でプレビュー・３候補欄・文言入力・３段の書式・更新ボタンを同時表示。候補欄の末尾までスクロール後、さらにスクロールしてもpageY=330を維持。ブラウザエラーなし。
- 入力保持: レイアウト切替前に画面の入力を読み取り、再マウントで戻った最初の通常動画の上行「絶賛した句の背景は」と見出し書体851チカラヅヨクを復元。他の設定は変更なし。実ジョブの保存/再生成は行っていない。
- 制限: 今回はフロントエンドの配置変更のみ。サムネ画像の即時描画は追加していない。未コミット/未PUSH。

## 2026-09-13 サムネ編集中の画像と画面全体を固定

- 目的: 編集欄をスクロールしてもサムネ画像が動かないようにする。
- 原因: 前回のsticky表示はページ内カードの範囲だけで追従し、文言・書式欄の多くはページ全体のスクロールを使っていた。カードの範囲を越えると画像も移動する構造だった。
- 変更ファイル: `frontend/components/{ResultThumbnailWorkspace,ResultThumbnailEditor,ResultVideoCard}.tsx`、`frontend/app/results/[jobId]/page.tsx`、本ファイル。
- 変更: 結果一覧の「サムネを編集」からviewport全体を使う編集dialogを開く。編集中は背景ページのスクロールを停止し、プレビューを独立した固定領域に配置。文言・書式はそれぞれ独立してスクロールし、狭い画面では設定側を共通スクロールにする。「結果一覧へ戻る」で通常表示へ戻す。編集UIは閉じてもマウントを保ち、同じ結果ページ内で入力案を維持する。
- 検証: frontend typecheck/lint/build成功。稼働frontendへFast Refreshで反映。1366x768で書式欄を末尾（scrollTop=39.33）へ、候補欄を末尾（188.67）へ進め、画像上も含めて複数回スクロールしても画像top=77.33、left=12.67、pageY=190.67、dialog scrollTop=0を維持。2085x1272でも全体配置を確認。
- 入力保持: 更新前の３本の全入力を照合。最初の通常動画で選択中だった案２の文言と851チカラヅヨクを復元し、dialogを閉じて再度開いても全入力が一致。終了時に背景スクロール制限が解除されることを確認。検証用viewport指定は解除。
- 制限: 文言・書式の保存APIとサムネ画像生成は今回未変更。実ジョブの保存/再生成は行っていない。未コミット/未PUSH。

## 2026-09-13 サムネの文言・書式を保存前に自動プレビュー

- 目的: 更新ボタンを押さなくても、文言・書体・サイズ・色の変更結果を固定プレビューで確認できるようにする。
- 原因: 編集欄の変更が画像描画につながっておらず、保存済みJPEGを表示するだけだった。
- 変更ファイル: `backend/app/api/exports.py`、`backend/app/jobs/{queue,thumbnail_preview}.py`、`backend/app/render/render_thumbnail.py`、`backend/tests/test_thumbnail_preview.py`、`frontend/components/{LiveThumbnailPreview,ResultThumbnailWorkspace,ResultThumbnailEditor,ResultVideoCard,ThumbnailTextStyleEditor}.tsx`、`frontend/lib/api.ts`、本ファイル。
- 変更: 編集画面を開いたときにworkerで対象場面の静止画を準備し、一時領域にキャッシュする。以後は入力変更から180ms後に、保存時と同じ描画処理でJPEGプレビューを返す。数値欄は有効な入力中にも反映し、連続変更で古い応答を表示しない。保存は既存の「サムネを保存・更新」で確定するときだけ行う。プレビュー処理は完成動画・保存済みサムネ・metadataを書き換えない。
- 検証: backend全体 `1089 passed, 1 skipped`、関連42テスト、backend ruff、frontend typecheck/lint/build、backend/frontend/GPU worker image build成功。保存時のJPEGとのバイト一致、文言/書体/サイズ/色の反映、動画抽出をHTTPで実行しないこと、場面キャッシュの失効、失敗後の再試行、不正入力の拒否を検証。
- 稼働反映: キュー/started=0でbackend/workerを再作成し、health HTTP200。frontendをFast Refreshで反映。転送途中にAPI関数未反映の一時コンパイルエラーが出たが、全ファイル転送後は解消し実画面を表示。TOPの再読込操作なし。
- 実画面: 案２と見出し851チカラヅヨク、手動文言、上行の水色、サイズ140→100→80を保存ボタンなしで描画。サイズ欄にフォーカスしたまま80の画像へ変わることを確認。検証後に元の入力へ戻し、閉じて再度開いた後も３本の全入力が作業前と一致。保存済みJPEG/metadataのSHA256と完成MP4のサイズ/更新時刻は作業前と一致。
- 制限: 初回の場面準備はworkerの空きを待つ。実ジョブでの確定保存は行っていない（保存との描画一致は隔離テストで確認）。未コミット/未PUSH。

## 2026-09-13 サムネの手動サイズが自動縮小で変化しない問題を修正

- 目的: 見出し・上行・下行のサイズ入力が、指定した大きさとしてプレビューと保存画像に反映されるようにする。
- 原因: サイズが自動縮小の上限として使われていた。今回の下行では112/114/140を指定しても実描画がすべて96となり、入力だけが変わって見た目が変わらなかった。
- 変更ファイル: `backend/app/thumbnail_style.py`、`backend/app/render/render_thumbnail.py`、`backend/tests/test_thumbnail_text_styles.py`、`frontend/components/ThumbnailTextStyleEditor.tsx`、`frontend/lib/types.ts`、`frontend/tests/thumbnailTextStyles.test.ts`、本ファイル。
- 変更: 各行に後方互換の`autoFit`設定（未設定はtrue）を追加。手動サイズ変更ではその行の自動縮小を解除し、実際の文字サイズを入力値に一致させる。固定サイズの行を含む文字レイヤーの後段の横圧縮・一括縮小も停止する。「枠に収める（自動縮小）」を各行で切り替え可能とし、枠を越えた場合の戻し方を表示。設定はキャラ保存・サムネ保存にも保持する。
- 検証: backend全体 `1092 passed, 1 skipped`、関連25テスト、変更backendのruff、frontend typecheck/lint/build、キャラ設定roundtripテスト成功。３行それぞれで、自動縮小なら同一JPEGになる長文・サイズの組み合わせが、固定サイズでは指定した実フォントサイズと異なるJPEGになることを確認。
- 稼働反映: backend/frontend/GPU worker image build成功。キュー/started=0でbackend/worker再作成、health HTTP200。frontendの型と書式欄をFast Refreshで反映し、TOPは再読込していない。
- 実画面: 下行を140→112→114へ変更し、すべて保存操作なしでプレビューが変化。140の拡大を目視し、112→114でも新しい画像への変更を確認。新たなブラウザエラーなし。元の文言・書体・色・サイズを保持し、下行だけ指定サイズ114を優先する状態で表示している。
- 制限: 固定サイズは枠内への収まりを強制しないため、大きくしすぎた場合は画像内で見切れる。実ジョブの確定保存は未実施。未コミット/未PUSH。

## 2026-09-13 ショート画角を枠の直接操作と即時プレビューで調整

- 目的: 画角の数値がどの位置に対応するかを見えるようにし、位置・倍率を試すたびの動画再生成待ちをなくす。
- 原因: 左右・上下・倍率スライダーのpointerup/keyup/blurごとに保存APIを呼び、対象clipの字幕入り・字幕なしプレビュー動画を再生成していた。
- 変更ファイル: `frontend/components/ShortFramingWorkspace.tsx`、`frontend/lib/{shortFraming,shortFramingApi}.ts`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`frontend/tests/shortFraming.test.ts`、`backend/app/{main.py,api/framing_guide.py,jobs/short_framing_guide.py,render/render_short.py}`、`backend/tests/test_short_framing_guide.py`、本ファイル。
- 変更: 「画角を見ながら調整」で画面全体のdialogを表示。元映像に青い表示範囲と三分割線を重ね、クリック・ドラッグ・左右/上下/倍率スライダーで縦型の構図を即時描画する。別の時刻の静止画も確認可能。位置変更ではサーバー通信・動画生成を行わず、「この画角を保存」で既存の保存APIを一度呼ぶ。閉じる操作は試した値を破棄する。完了済みレビューでも試し表示できるが保存不可。
- 画角解析: レンダラーの画角選択処理を共通関数へ切り出し、workerで一度解析して一時領域にキャッシュ。位置・倍率ではキャッシュを失効させず、元動画・区間・配置・帯の表示範囲が変わったら再解析する。古いworkerの結果が新しい要求を上書きしない。完成動画・字幕確認データ・選定データは解析処理で変更しない。
- 検証: backend全体 `1098 passed, 1 skipped`（独立したDATABASE_URL/STORAGE_ROOTを指定）、変更backendのruff、frontend typecheck/lint/build、画角計算テスト成功。中心/人物追従/ぼかし背景・倍率・端への移動・クリックから数値への変換、キャッシュ再利用と失効、競合結果の破棄、完了済みレビューの不変を確認。最初の全体テストは起動時の相対DBパスで２件失敗し、隔離DBを明示した再実行で全件通過。
- 稼働反映: backend/frontend/GPU worker image build成功。キュー/started=0を確認してbackend/workerを再作成しhealth HTTP200。frontendは変更した画角関連ファイルだけFast Refreshで反映し、TOPとサムネ編集中のタブは再読み込みしていない。
- 実画面: 対象ジョブのショート１で元映像と縦型構図を同時表示。初回のworker解析は約1.06秒。倍率100→180→210%と元映像のクリック・ドラッグで範囲枠と縦型画像が即座に変わることを目視確認。調整中の保存PATCHなし、動画生成キュー/started=0、レビューJSONのSHA256は操作前後一致。React開発時のeffect再実行でdialogが閉じる問題を検出して修正し、再度開けることを確認。
- 制限: 表示は静止画による画角確認用で、字幕・帯の絵柄は省略。初回の解析と元映像の読み込み、別時刻への移動には待ち時間がある。保存後の動画再生成速度自体は未変更。実ジョブは完了済みのため確定保存・最終書き出しは今回未実施。未コミット/未PUSH。

## 2026-09-13 編集画面修正のコミット準備

- 目的: ユーザーが確認した字幕編集・サムネ編集・ショート画角調整の一連の修正をGitへまとめる。
- 対象: `C:\BOT\AutoClipper Web`、branch `codex/task-133-upload-style-settings`、remote `origin`（`yoyowasa/AutoClipper-Web`）。fetch後のHEAD/upstreamは一致し、リモート側の追加コミットなし。
- 収録内容: 帯単独UIの整理、文字起こしの全角化と同語句修正、区間結合/分割/１行表示、選定画面での通常/ショート切替、編集画面のスクロール改善、サムネ文言/書式/即時プレビュー、ショート画角の直接操作と即時プレビュー。変更ファイルは前項までの各タスクに記録。
- 検証: 直前の全体backend `1098 passed, 1 skipped`、frontend typecheck/lint/build、Docker image buildと実画面確認を継承。今回backend全体/launcherのruff、overlay-fit goldenを追加実行して成功。Docker４サービス稼働、backend health HTTP200を再確認。
- ローカル保持: 既存の未追跡素材 `backend/app/assets/thumbnail_templates/raden_normal_v1/base.png` と `storage/qa/` は今回の修正コードから参照されていないためコミット対象外。実ジョブの設定・出力動画は変更しない。

## 2026-09-13 編集画面修正をPUSH

- 実装コミット: `bcac19215ec73435f33a595670d61d1c052b50e3`（69ファイル）。`origin/codex/task-133-upload-style-settings`へ送信し、`git ls-remote`で実装コミットとの一致を確認した。
- 送信前確認: ステージ対象の照合、差分の空白検査、既知の資格情報パターン検査が成功。修正コードの未ステージ変更なし。検証用素材は前項のとおりローカル保持。
- CI: このコミットのGitHub Actions実行はなし。現行workflowは`pull_request`と`main`へのpushが対象。ローカル検証・実画面確認の結果は前項までに記録済み。

## 2026-09-14 main統合と日本語Windows導入手順

- 目的: ユーザー承認済みの編集画面修正をmainへ統合し、別のWindows PCでGitHubから導入できる日本語手順を提供する。
- 対象: `C:\BOT\AutoClipper Web`。`origin/main`は作業HEADの祖先で、確認時点で追加70コミット。作業branchは`codex/task-134-main-japanese-setup`。
- 変更ファイル: `README.md`、`docs/WINDOWS_SETUP_JA.md`、`docs/WINDOWS_LAUNCHER.md`、本ファイル。
- 変更: README冒頭に日本語手順を追加。WSL 2/Docker Desktop/Python/Codexの準備、mainのZIP取得、Intel内蔵GPUでのCPU起動、短い動画による確認、終了、更新、設定移行、障害確認を記載。英語手順のCPU言語を実装どおりjaへ修正。
- 最小検証: ローカルMarkdownリンクとコードフェンス、ランチャー実在、CPU設定とCodex検出・ログイン処理、環境設定ファイル未作成時の警告動作をコードと照合。差分の空白検査成功。Docker/Python/Codexの導入事項は公式資料と照合。
- 引継ぎ検証: 実装コミットbcac192のbackend 1098 passed/1 skipped、ruff、frontend typecheck/lint/buildと実画面確認は前項に記録済み。今回は文書変更のみ。
- 未確定: 新規PCでの実インストール・動画処理は未実施。この記録時点ではPRのCI・mainへの統合は未実施。既存の未追跡base.pngとstorage/qaはローカル保持する。

## 2026-09-15 画角・基本配置の試し表示で再生成待ちを減らす

- 目的: 画角調整を開く際と基本配置を切り替える際の待ち時間を減らす。
- 現在地・対象: `C:\BOT\AutoClipper Web`、`codex/task-135-framing-preview-latency`。既存の未追跡素材は対象外。
- 原因: 基本配置を選ぶたびに全ショートの字幕入り/字幕なしプレビューが同じRQキューへ入り、画角解析も後ろで待機する。調査時の完了履歴ではプレビュー１本12.96〜33.76秒、画角解析0.06〜0.97秒。元映像の確認フレームもdialogを閉じるたび破棄していた。
- 変更: 基本配置の選択で試し表示dialogを開き、保存前の選択では設定変更・動画生成をしない。中央/ぼかし配置は寸法のみで即時に基準を返し、人物配置は解析済み結果を再利用。解析要求をキュー先頭へ追加する。dialog内では同じ元映像を使い続け、開き直し時にも直前のフレームを再利用する。元映像URLへ開始位置のmedia fragmentを付ける。
- 保存: 配置（全ショート共通）と位置・倍率（選択clipのみ）を既存framing APIの追加任意フィールドでまとめて確定。保存時に最終設定のプレビューだけを要求し、選択clipを先に並べる。旧形式のAPI呼び出しは維持。完了済みレビューは試し表示のみ。
- 変更ファイル: `frontend/components/ShortFramingWorkspace.tsx`、`frontend/lib/{shortFramingApi,types}.ts`、`frontend/app/jobs/[jobId]/subtitles/page.tsx`、`backend/app/api/{framing_guide,jobs}.py`、`backend/app/jobs/short_framing_guide.py`、`backend/app/schemas.py`、関連backendテスト２ファイル、本ファイル。
- 検証: backend全体1102 passed/1 skipped。追加の１本/５本でのまとめ保存テスト２件成功。設定不変・非同期解析の再利用・古いworkerの上書き防止・既存framing保存も確認。frontend typecheck/lint/build・画角計算テスト、backend ruff、差分空白検査成功。
- 制限: 実行中の動画処理は中断しないため、初回の人物解析がその終了を待つ場合はある。構図は静止画。保存後の動画エンコード速度そのものは変更していない。この記録時点でDocker反映・実画面確認は進行中。未コミット/未PUSH。
- 稼働確認: backend/frontend/GPU worker image build成功。RQ queued/started=0を確認してbackend/workerを再作成し、health HTTP200。frontend変更ファイルを稼働コンテナへ反映。既存ChromeタブはFast Refreshが届かず旧表示のままだったため、入力を保護して残し、同じジョブの更新画面を別タブで開いた。
- 実画面確認: 基本配置から試し表示dialogが開くこと、中央→ぼかし背景→人物への構図切替、拡大100→150%、保存せず閉じると人物/100%に戻ること、開き直した際に画像と操作が復帰することを確認。更新画面を画角調整が開いた状態で残した。
- 性能と不変性: localhostのIPv4経由で配置基準APIを計測し、中央36ms、ぼかし32ms、解析済み人物34ms。これはAPI応答時間であり初回画像取得・画面全体の完了時間ではない。操作前後のレビューJSONのSHA256が一致し、RQ queued/started=0。実ジョブで確定保存・最終書出しは行っていない。未コミット/未PUSH。

## 2026-09-15 画角調整に標準上下帯の目安を表示

- 目的: らでん用と同じ上下各360pxの帯を仮定し、画角調整中に中央1080×1200pxの映像範囲を確認できるようにする。
- 対象: `C:\BOT\AutoClipper Web`。変更ファイル: `frontend/components/ShortFramingWorkspace.tsx`、`frontend/lib/shortFramingBannerGuide.ts`、本ファイル。
- 変更: 構図プレビューに帯領域の半透明表示・黄色の破線・上帯/下帯の目安ラベルを常時描画。元映像上にも対応する領域と境界を投影。実際の帯ON/OFFを別記し、目安は書き出しに含めない。
- 検証: frontend typecheck/lint/build、Docker frontend image build、差分空白検査成功。稼働画面で上下の目安ラベル・黄色境界を確認。HMR後に倍率を一時変更して再描画を確認し、元の175%に復帰。左右79・上下-3・確認位置22.4秒・ぼかし背景の編集中状態を保持。保存操作や動画生成は行っていない。
- 現在状態: 稼働frontendへ反映済み。実際の帯は上下OFFのまま。未コミット/未PUSH。


## 2026-09-15 投稿案生成のhost bridge停止から復旧

- 目的: 投稿案生成のcodex_title_hook_bridge_unavailableを解消する。
- 観測: Web/backend/workerは稼働。Windows側bridge statusの最終更新は同日04:10:49 JST、記録PID43848は存在せず、生成依頼7件が未処理。連携プロセス停止が直接原因。終了理由はstderrを破棄する既存起動方式のため未確定。
- 対応: 既存LauncherController.ensure_codex_bridge_runningでhost bridgeのみ再起動。未処理だった過去依頼は一時画像が既にないためimage_not_foundで終了。現在のブラウザの「現在の字幕から投稿案を生成」で新しい依頼を送信した。
- 最小検証: host bridge ready、生成中heartbeat更新を確認。編集中ジョブのショート1で実際のCodex生成が成功し、事実重視・興味喚起・短く強いの3案と採用ボタンが画面に表示された。字幕・タイトルの手入力は保持し、候補の採用や確定保存はしていない。
- 変更: 稼働プロセスの復旧と本ファイルの記録のみ。アプリコード変更・Docker再起動・画面再読込なし。既存の未コミット変更を保持。
- 未解決: プロセスが終了した契機は未確定。恒久的な再発防止を実装済みとは扱わない。


## 2026-09-15 人気度JSONの空データを選択時に明示

- 目的: 人気度JSONの読み込み失敗とデータ未収録を区別し、空JSONで動画をアップロードしてから失敗する操作を防ぐ。
- 原因: 対象AMa84AwGLykのアップロード済みJSONはheatmap_available=false、heatmap=[]。JSONの認識・動画との照合は成功し、人気度参考ONでのジョブ作成がheatmap_unavailableで拒否されていた。Downloaderが人気度を取得できなかった理由は未調査。
- 変更ファイル: frontend/app/upload/page.tsx、frontend/components/HeatmapFileNotice.tsx、frontend/lib/heatmapFileStatus.ts、frontend/tests/heatmapFileStatus.test.ts、本ファイル。
- 変更: JSON選択時に空データ・形式不正・データありを表示。参考ON時はアップロード前に同じ確認を実行。backendでの契約・動画SHA256照合は維持。利用設定を自動でOFFへ変更せず、ユーザーが選択できる状態とする。
- 検証: 空配列・値0・BOM付き正常データ・JSON構文不正・別形式・File読込のテスト成功。frontend typecheck/lint/build、Docker frontend image build、差分空白検査成功。稼働コンテナへ反映済み。
- 未確定: 現在のブラウザは更新が届いておらず新表示未確認。選択中動画・JSON・設定を保護するため再読み込みや処理開始は行っていない。未コミット/未PUSH。


## 2026-09-15 編集再開したジョブでも帯画像を変更

- 目的: TOP画面に戻らず、途中の5本の字幕確認画面で上下帯の画像を設定できるようにする。
- 原因: 字幕確認の設定APIは帯ON/OFFのみ受付、画像選択UIもTOP画面だけにあった。
- 変更ファイル: backend/app/schemas.py、backend/app/api/jobs.py、backend/tests/test_api_routes.py、frontend/lib/types.ts、frontend/app/jobs/[jobId]/subtitles/page.tsx、frontend/components/ReviewBannerImages.tsx、本ファイル。
- 変更: 既存設定APIへ画像IDの任意フィールドを追加し、形式・画像実在を検証してジョブに保存。画像選択で該当帯をONにして同ジョブの全ショートへ反映し、既存経路でプレビューを再生成。キャラ設定・他ジョブは変更しない。画像プレビューのURLへ更新時刻を付け、古い画像のキャッシュを回避。
- 検証: 関連backendテスト3件成功（画像差替え/GET一致、字幕・区間保持、旧形式ON/OFFの画像保持、不正ID/存在しない画像の拒否）。ruff、frontend typecheck/lint/build成功。backend/frontend image build成功、backend再作成後health200と稼働OpenAPIの追加フィールドを確認。frontendを稼働コンテナへ反映。
- 実画面: 前の5本の字幕確認を別タブで開き、「帯画像を変更」の上下画像選択欄を確認して展開した状態で残した。実ジョブの画像選択・確定保存は未実施。現在の新規選定タブは保持。未コミット/未PUSH。


## 2026-09-15 字幕確認でキャラ別一括設定を呼び出す

- 目的: 編集中ジョブの帯を個別アップロードする代わりに、TOP画面で保存したキャラ設定を選んで反映する。
- 変更ファイル: backend/app/api/review_character_settings.py、backend/app/api/jobs.py、backend/app/schemas.py、backend/tests/test_api_routes.py、frontend/components/ReviewCharacterPreset.tsx、frontend/app/jobs/[jobId]/subtitles/page.tsx、frontend/lib/types.ts、本ファイル。直前追加のReviewBannerImages.tsxは新UIへ置換。
- 変更: 設定APIに保存名を渡し、保存済みキャラから帯・ON/OFF・文字書式・投稿情報・通常タイトル末尾・サムネイル設定を同ジョブへ反映。個別文字書式はキャラの既定書式へ切替。字幕文章・タイトル/フック本文・切り抜き区間・本数・画角・元配信タイトル/URLを保持する。通常公開タイトルの既存末尾は新末尾へ置換。投稿文は旧設定と完全一致する自動クレジット部分のみ取り替え、説明本文を残す。
- 入力保護: ブラウザ上で未保存の文章を保持しつつ、サーバー反映済みの書式と変更前から未編集の投稿欄を同期する。選択だけでは保存せず「このジョブに反映」で実行。キャラ保存一覧・他ジョブは変更しない。
- 検証: 関連backend 4 tests passed、ruff、frontend typecheck/lint/build、差分空白検査成功。保存値反映、字幕・区間・本数・画角の保持、旧API互換、不正/不存在画像、存在しない保存名、元ジョブと保存一覧の不変を確認。既定配置の検証はDB未設定値とUI既定autoの比較条件を修正して成功。
- 稼働: backendへコード反映して再起動、health200・OpenAPIのcharacterPresetName追加を確認。frontend反映後、前の5本の字幕確認で「キャラ設定を読み込む」と保存済み2名の選択肢を確認。新規選定のタブを保持。
- 未確定: 実ジョブへのキャラ設定反映・動画の再生成はユーザーの選択待ち。未コミット/未PUSH。backend/frontendのDocker image再build成功。

## 2026-09-15 ショート画角再生成の重複処理削減と編集映像拡大

- 目的: 5本の画角更新の待ち時間を減らし、小さすぎる編集映像と映像上の状態表示を修正する。
- 観測: RQ完了記録で直近5本のpreview処理合計139.89秒、その後の1本54.43秒。編集用と保存済み用を別々に全編レンダリングしていた。画面は上段53%の高さから再生操作欄を引いており、1920px幅の確認時に縦映像の高さ272pxだった。
- 変更ファイル: backend/app/render/paired_preview.py、render_short.py、render_exact_review_preview.py、backend/tests/test_paired_preview.py、frontend/app/jobs/[jobId]/subtitles/page.tsx、frontend/app/globals.css、本ファイル。
- 変更: 両方のpreviewが未生成のショートは、デコード・画角・ぼかし・帯の合成を1回にして字幕付/無へ分岐し、同じ設定で2本を出力。片方のキャッシュがある場合と通常動画、最終書き出しの経路は維持。帯のループ入力時は両出力の尺を指定し、冒頭複製時は音声も分岐。
- UI: ショートのプレビューを作業領域の全高へ拡大し、左側に画角と文字編集を配置。編集中/保存済みの表示・切替ボタンは映像外の再生操作欄へ移動。書式設定は縦並びとし、各設定欄の内容の重なりを解消。
- 検証: 関連backend 87 tests passed、対象ruff、frontend typecheck/lint/build成功。実動画43.78秒・1080x1920/60fpsで旧55.278秒→新37.862秒（31.5%短縮）。新旧両出力の映像/音声尺一致、10秒位置の比較フレームはSSIM=1。別途帯なし/冒頭複製/帯あり冒頭複製の実FFmpeg出力で映像と音声が1秒/1.5秒に一致。
- 実画面: HMR反映後、1920x903で映像領域高さ570px、document高さ903px（画面全体スクロールなし）、映像内に状態表示と切替ボタンがないことを確認。未保存文章を維持し、ユーザーのジョブ設定・画角は変更していない。
- 稼働: workerの実行中/待機中ジョブが0件を確認後、変更コードを配置してworker再起動。frontendのコード・CSSを反映。backendにも同じrenderコードを配置。
- 制限: 実測は1クリップ1回ずつ。5本一括の改修後所要時間、全フレームの画質一致は未測定。長尺previewの生成待ちは残る。未コミット/未PUSH。
- 追加確認: backend/worker(GPU)/frontendのDocker image build成功。worker idle・backend health200を確認。次回コンテナ再作成用のimageにも変更を保存済み。

## 2026-09-15 ショートのタイトル・フック欄のホイール停止を修正

- 目的: ショート字幕編集のタイトル・フック欄をホイールで上下にスクロールできるようにする。
- 原因: 直前の縦並び化後も内側のfields/suggestionsにoverflow:autoとoverscroll-behavior:containが残り、内側自身の高さと内容高が同じ状態で外側へのホイール伝播を止めていた。
- 変更ファイル: frontend/app/globals.css、本ファイル。short条件内で内側2要素をoverflow:visible/overscroll:autoとし、外側の編集欄をスクロール主体にする。通常動画の独立した2列スクロール設定は維持。
- 最小検証: 実ブラウザで編集欄scrollTopが506→1409→506とホイールで上下に移動、ページ全体scrollTop=0。通常動画の別ジョブも開き、上に横長プレビュー・下に編集欄の従来配置を確認。確認用タブは閉じ、元の編集タブと未保存内容を保持。
- 稼働: CSSをHMR反映。frontend buildとDocker frontend image build成功。未コミット/未PUSH。

## 2026-09-15 編集再開・画角プレビュー修正のPUSH準備

- 目的: ユーザーが画面確認した今回までの23ファイルをfeature branchへまとめてPUSHし、PRのCIを確認する。
- 検証: backend全体1113 passed, 1 skipped（DATABASE_URL=sqlite:///:memory:、backendディレクトリでpytest）。ruff backend/launcher、frontend lint/typecheck/test:overlay-fit、heatmapFileStatusテスト、build成功。直前のDocker buildと4サービス稼働も確認。
- 初回失敗: リポジトリルートからのpytestで起動時DBの相対パスが作業領域外を向き、手動編集テスト2件がunable to open database file。メモリDBを明示し、該当5件と全体を再実行して成功。アプリの実データへの変更なし。
- コミット対象: 設定API・キャラ読込・画角ガイドとキャッシュ・二重preview生成の共有化・ショート編集配置/スクロール・空の人気度JSON表示・関連テスト・STATUS.md。
- 除外: 個人用サムネイルbase.png、storage/banner_assets、storage/qa。PUSH先はcodex/task-135-framing-preview-latency。GitHub CIはこの記録時点では未実行。

## 2026-09-16 基本配置・画角の保存をクリップごとに分離

- 目的: 次のショートの基本配置・画角を変更しても、保存済みの別ショートを変更しない。
- 原因: 画角保存APIのshortLayoutがジョブ共通設定と字幕確認文書の共通配置を書き換え、全ショートの確認状態・プレビューを無効化していた。
- 変更ファイル: backend/app/api/jobs.py、backend/app/candidates/merge_boundaries.py、backend/app/jobs/subtitle_review.py、backend/app/jobs/short_framing_guide.py、backend/app/render/render_exact_review_preview.py、backend/app/render/render_short.py、frontend/lib/types.ts、frontend/app/jobs/[jobId]/subtitles/page.tsx、frontend/components/ShortFramingWorkspace.tsx、関連backendテスト4ファイル、本ファイル。
- 変更: shortLayoutをクリップ単位で保存し、画角ガイド・プレビュー・最終書き出しで優先。保存対象1本だけを未確認・再生成対象にする。未設定の既存クリップは共通配置を継承し、見た目が同じ場合の既存プレビューハッシュを維持。
- 検証: 関連backendテスト213 passed、backend ruff、frontend typecheck/lint/build、git diff --check成功。1本目保存後に2本目の基本配置・位置・倍率を変更しても、1本目の全保存内容・確認状態が不変で2本目だけ再生成されるテストを実施。
- 稼働: 待機・実行中ジョブ0件を確認後、変更コードをbackend/worker/frontendへ配置しbackend/worker再起動。Docker backend/worker/frontend image build成功。health200、実ジョブ5本のpreviewState=readyと2本目confirmed=trueを読み取り確認。
- 未確定点: ユーザーの実ジョブに変更を加える再現テストは未実施。過去に共通設定変更で変わった画角の元の値は復元していない。未コミット/未PUSH。


- PUSH前検証: backend全体1115 passed, 1 skipped、backend/launcher ruff、frontend lint/typecheck/build成功。Docker Composeの4サービス稼働確認。個人素材とQA出力はPUSH対象外。

## 2026-09-15 文字色テンプレートを10色へ拡張

- 目的: タイトル・フック・字幕の文字色をテンプレートから10色選べるようにする。
- 変更ファイル: frontend/components/ClipTextStyleEditor.tsx、本ファイル。
- 変更: 従来の白・黄・水色・ピンク・黄緑・黒へ赤(#FF4040)・オレンジ(#FF9F43)・青(#4080FF)・紫(#B57BFF)を追加。共通一覧を使う外縁も10色。通常/ショート・TOP/字幕編集の共通部品に反映。
- 検証: frontend typecheck、対象ESLint、Docker frontend image build成功。稼働画面で文字色の10ボタンと配色を確認。既存の選択色・未保存文章は変更していない。
- 状態: codex/task-136-text-color-presets（PR79の変更を継承）で実装、HMR反映済み。今回追加分は未コミット/未PUSH。


## 2026-09-15 内縁の色テンプレートの追加漏れを修正

- 原因: 内縁だけ独立した4色配列を参照しており、前回の共通色一覧拡張が適用されなかった。
- 変更ファイル: frontend/components/ClipTextStyleEditor.tsx、本ファイル。内縁も文字色・外縁と同じ10色一覧を使用する。
- 検証: 稼働frontendへ反映し、実ブラウザで内縁の10色ボタンを確認。選択済みの色値は変更していない。未コミット/未PUSH。


- PUSH前検証: frontend lint/typecheck/build成功。文字・内縁・外縁の10色を含めてPUSH。

## 2026-09-16 結果画面で説明欄とタグをまとめてコピー

- 目的: 公開用タイトルを含めず説明欄・ハッシュタグ・タグを一度にコピーする。
- 原因: 既存の説明欄ボタンはハッシュタグまでを対象とし、タグ欄との一括コピー操作がなかった。
- 変更ファイル: frontend/components/ResultVideoCard.tsx、本ファイル。コピーボタンの先頭に「説明欄＋タグ」を追加。説明欄とハッシュタグに続けて「タグ: 」とタグ一覧を空行区切りでコピーする。既存ボタンは維持。
- 検証: frontend typecheck、対象ESLint、既存youtube-postingテスト、Docker frontend image build成功。稼働frontendへファイルを反映。
- 未確認: 実ブラウザのクリップボード貼り付け確認は未実施。未コミット/未PUSH。


## 2026-09-16 説明欄ボタンへ一括コピーを統合

- 目的: ユーザー訂正に従い、既存の「説明欄」で公開用タイトル以外をコピーする。
- 変更ファイル: frontend/components/ResultVideoCard.tsx、本ファイル。「説明欄」が説明文・ハッシュタグ・タグをまとめてコピーするよう変更。追加した「説明欄＋タグ」を削除して4ボタンへ戻した。
- 検証: frontend typecheck、対象ESLint、Docker frontend image build成功。稼働frontendへ反映。実ブラウザでの貼り付け確認は未実施。未PUSH。

- PUSH前検証: frontend lint/typecheck/build成功。説明欄ボタンへ統合した最終仕様をPUSH。

## 2026-09-16 Codex初期選定の時刻丸めによる入力エラーを修正

- 目的: 正常な極短発話が時刻の丸めで開始＝終了となり、Codex初期選定全体がローカル仮選定へ落ちる不具合を修正する。
- 原因: 該当ジョブの3019区間中1区間（7891.94〜7891.9400000000005秒）が小数3桁への丸めで同値となり、CodexTranscriptInputのend > start検証に失敗した。
- 変更ファイル: backend/app/candidates/codex_initial_selection.py、backend/tests/test_codex_initial_selection.py、本ファイル。丸めが正常区間を消す場合だけ元の精度を保持する。ヒートマップにも同じ保護を適用し、途中の丸めを除去。字幕本文と元データは変更しない。
- 検証: 関連40 tests passed、対象ruff、git diff --check成功。実ジョブの保存済み3019区間から入力と108話題ブロックの生成成功。極短区間2パターンで文字起こし・ヒートマップ両方のJSON往復を確認。
- 稼働: 待機/実行中0件を確認後backend/workerへ反映・再起動。稼働workerで該当区間の有効性とbackend health200を確認。
- 未確認: Codexによる実選定の再実行はまだ。現在表示中の仮選定は自動変更していない。未PUSH。
- 追加確認: backend/workerのDocker image build成功。次回コンテナ再作成時も修正を保持。

## 2026-09-16 キャラ文字書式を含むプレビューの生成失敗を修正

- 目的: キャラ設定の文字書式がある動画でプレビュー生成を復旧する。
- 原因: 保存用に辞書化されたSubtitleLayoutのdefault_title_style/default_hook_style/default_subtitle_styleを辞書のまま復元し、フォント解決時にAttributeError: dict object has no attribute font_presetが発生。
- 変更ファイル: backend/app/render/render_exact_review_preview.py、backend/tests/test_render_exact_review_preview.py、本ファイル。3種類の既定書式をClipTextStyleへ検証・復元してからASS字幕を生成する。
- 検証: 関連20 tests passed、対象ruff成功。通常/ショート双方で保存済み3書式からASS生成し、各フォントサイズが保持される回帰テストを追加。
- 稼働: 待機/実行中0件を確認後backend/workerへ配置・再起動。該当ジョブの失敗した5本のみ既存APIで再試行。字幕・書式・切り抜き区間を変更していない。
- 状態: 実動画の再生成結果は確認中。未PUSH。
- 復旧確認: 該当ジョブ5本すべてpreviewState=readyをAPIで確認。backend/workerのDocker image buildも成功。

## 2026-09-16 色欄にユーザー保存パレットを追加

- 目的: スポイトや手動で選んだ色を既存テンプレートの横へ保存・再利用する。
- 変更ファイル: frontend/components/SavedColorSwatches.tsx、frontend/components/ClipTextStyleEditor.tsx、本ファイル。文字色・内縁・外縁それぞれに保存色と「＋今の色を保存」を追加。共通パレットをlocalStorageへ永続化し、同じブラウザの各欄・タブで同期。重複防止、整理・削除、保存失敗の表示を実装。
- 検証: frontend typecheck/lint/build成功。稼働画面で現在の水色#50B4FFを保存し、3つの色欄へ同時表示・保存済み状態を確認。動画の文字書式や未保存文章は変更していない。
- 制限: 保存色は同一ブラウザ・同一オリジン内で共通。別ブラウザ・別PCへの同期はない。未PUSH。

## 2026-09-16 古い投稿案による字幕保存の拒否を修正

- 目的: 字幕修正後にAI投稿案のrevision不一致で保存全体が422になる問題を解消する。
- 原因: postMetadataSource=codexかつ投稿案hashと保存予定字幕hashが不一致の場合、一律に保存を拒否していた。
- 変更ファイル: backend/app/api/jobs.py、backend/tests/test_title_hook_suggestions.py、本ファイル。古い投稿案は手動文言として保存し、公開用タイトル・フック・説明文・タグと字幕修正を保持。古い候補・選択ID・根拠ID・hashのみ解除し、sourceをmanualにする。最新の投稿案は既存の検証・保存を維持。
- 検証: 関連43 tests passed、対象ruff成功。字幕を同時変更する場合・すでに投稿案が古い場合の双方を検証。旧422期待のテスト1件が初回失敗し、新仕様の文言保持・古い情報解除の検証へ更新後成功。
- 稼働: 待機/実行中0件確認後backend/workerへ配置、backend再起動。ブラウザの未保存入力には触れていない。実ユーザー画面での保存クリックは未実施。未PUSH。
- 追加検証: backend health200、backend/worker Docker image build成功。

## 2026-09-17 再選定で提示済み区間を避ける設定を追加

- 目的: 狙う場面を変更して再選定しても同じ区間が繰り返される挙動を改善する。
- 観測: プリセット・具体的方針はAPIからCodex制約へ渡される。一方、再選定時の前回候補除外はなかった。直近2ジョブのCodex再選定はcompleted/fallbackUsed=falseであり、仮選定エラーの使い回しではない。
- 変更ファイル: backend/app/schemas.py、backend/app/candidates/used_ranges.py、backend/app/jobs/runner.py、backend/tests/test_reselection_exclusions.py、frontend/lib/types.ts、frontend/app/jobs/[jobId]/clips/page.tsx、本ファイル。
- 仕様: 再選定画面の「これまでの候補を避けて選ぶ」を初期ON。現在候補と過去の再選定除外区間をジョブ内で累積し、Codex入力・ローカル候補・最終候補へ既存の区間除外を適用。OFFなら提示候補の除外を解除するが、書き出し済み素材の重複除外は維持。別候補がない場合は前の候補を保持して日本語理由を返す。既存API呼び出しは未指定時Falseで互換性維持。
- 検証: 再選定除外テストとreal_pipeline合計43 passed、対象ruff、frontend typecheck/lint/build成功。累積除外・OFF・元設定不変・選定方針伝達・Codexとローカル候補の両方を検証。
- 稼働: キュー待機/実行中0件を確認後backend/worker/frontendに反映、backend/worker再起動。ユーザーの現在候補は自動変更していない。
- 制限: 変更前の全再選定履歴は保存されていないため、今回表示中の候補から蓄積する。実動画のCodex再選定結果は未確認。未PUSH。
- 追加確認: 稼働APIのexcludePreviousSelection受付とhealth200を確認。

## 2026-09-17 候補キープと残りだけ再選定
- 目的: 5本中2本をキープし、残り3本だけ選び直せるようにする。
- 変更: backend/app/schemas.py、app/api/jobs.py、app/jobs/runner.py、app/jobs/reselection_keep.py、frontend/lib/types.ts、app/jobs/[jobId]/clips/page.tsx。候補ごとのキープ、対象本数表示、keptClipIds保存、種別ごとの残り本数選定、元の順番への差し込みを追加。
- 保持: キープ候補の区間・個別スタイル・画角設定・候補情報と既存プレビューを維持。キープ区間は置換候補から除外。全候補キープ／不明IDは422。代替候補ゼロの場合は前の候補に戻す。
- 検証: tests/test_reselection_keep.py、test_reselection_exclusions.py、test_real_pipeline.py 合計46 passed。2/5キープ、候補不足、通常/ショート別本数、API入力、既存プレビューの内容維持を検証。ruff、frontend typecheck/lint/build 成功。
- 反映: queue/active=0確認後、backend/workerへコード反映・再起動、frontendへ反映。health、選定画面HTTP200、稼働APIのkeptClipIds公開を確認。
- 未確認: ユーザーの実動画でキープを指定したCodex再選定は未実施。テストでは代替生成を模擬。勝手に現候補を再選定していない。
- 継続反映: Docker backend/worker-gpu/frontend のイメージビルド成功。git diff --check成功。

## 2026-09-17 指定5本・実候補4本で全キープすると不足1本を再選定できない問題
- 観測: 現行選定ジョブはshortCount=5、実候補4本。画面とAPIが実候補数だけで全キープ判定し、不足枠を無視していた。
- 修正: backend/app/jobs/reselection_keep.py、app/api/jobs.py、frontend/app/jobs/[jobId]/clips/page.tsx。指定数と実候補数の大きい方からキープ数を引く。候補が足りない枠も生成・追加対象にする。キープ候補は保持。
- 検証: 関連48件成功。4/4キープ・指定5本と4/5キープの双方で残り1本を生成して5本になる回帰テストを追加。追加APIテストでも不足枠あり全キープは202、不足枠なし全キープは422を確認。ruff、frontend typecheck/lint/build成功。
- 反映: queue/active=0確認後、backend/worker再起動とfrontend反映。health HTTP200。ユーザーの候補を実際に再選定する操作は未実施。
- 稼働workerで現行データの実候補4・指定5・全キープ時残り1を確認。Docker backend/worker-gpu/frontendのイメージビルド成功。

## 2026-09-17 ぶいすぽっ！許諾番号入力
- 目的: 許諾番号を手入力し、説明欄の元配信の直前に表示する。
- 変更: backend/app/posting_metadata.py、frontend/lib/types.ts、frontend/components/YouTubePostingSettingsPanel.tsx。youtubePostingProfile.vspoPermissionNumberを追加。既存のキャラ設定保存・呼出に含める。初期値は空欄。空欄は非表示。
- 説明欄: 「ぶいすぽっ！許諾番号：入力値」を元配信の上へ挿入。既に説明欄に元配信がある場合も同じ位置。再保存で重複せず、番号変更・削除を反映。
- 検証: test_posting_metadata.py / test_character_presets.py 14 passed（配置・再保存・変更・削除・キャラ設定保存読出）。ruff、frontend typecheck/lint/build成功。
- 反映: queue/active=0確認後backend/workerへコード反映・再起動、frontend反映。health/upload HTTP200、OpenAPI項目を確認。実動画の説明生成は未実施。保存済みジョブへの番号一括入力は実施していない。
- Docker backend/worker-gpu/frontend のイメージビルド成功。

## 2026-09-17 キープ再選定で新候補が繰り返し0件になる原因修正
- 観測: 対象ジョブはreselection_no_alternativesで元候補に復帰。直近3回のCodex応答selectedTopics=[]。応答理由は「有力な81.84秒の話題はShort上限75秒超過、部分指定できないため除外」。キープ処理以前の話題選定で候補を失っていた。
- 原因: 第1段階の指示で話題ブロックの文脈区間と完成動画の尺制約の区別が不足。実装は長いブロックから部分切り出し可能だが、AIがブロック全長にmaxDurationを適用していた。
- 変更: backend/app/candidates/codex_initial_selection.py。話題選定は文脈を選ぶ段階、min/maxは完成動画だけの制約、120秒の話題から30秒を切り出せることを明記。境界精密化にも部分切り出しを明記。
- 検証: test_codex_initial_selection.pyに長い話題から短い動画の精密化要求を作れる回帰テスト追加。キープ・除外関連含む48 passed、ruff成功。
- 反映: queue/active=0確認後backend/workerへコピー・再起動。通常2本キープを保持し同条件で実データ再選定を1回開始。結果確認中。
- 実データ確認: 話題候補0件から5件へ改善。境界精密化後、新規Short4本が選定されawaiting_clip_review（errorなし）。通常キープ2本はclip_plan情報の完全一致を確認。全6本。残り1本は最短20秒未満の見せ場のため不採用。Docker backend/workerイメージビルド成功。

## 2026-09-17 通常動画の字幕確認プレビュー拡大
- 原因: 通常画面がプレビュー53%・設定47%の高さ配分で、1920x903表示時の実映像は約454x256まで縮小していた。
- 変更: frontend/app/globals.css、frontend/app/jobs/[jobId]/subtitles/page.tsx。通常画面の設定欄を180〜240pxの独立スクロール領域とし、残りをプレビューへ。余白と操作欄の高さを削減。状態/切替は映像外に配置済みで、表示名を編集プレビュー／保存済みを見るに整理。
- 検証: typecheck、lint、build、Docker frontend build成功。ユーザーの通常字幕画面でHMR反映を撮影確認し、実映像は約756x425へ拡大（縦横約1.66倍）。字幕一覧と下の設定欄は画面内に維持。リロード・編集内容の保存操作は実施していない。

## 2026-09-17 字幕確認の上部clip切替・字幕欄縮小・黒余白除去
- 変更ファイル: frontend/app/jobs/[jobId]/subtitles/page.tsx、frontend/app/globals.css。
- 変更内容: clip一覧を形式切替直下の横並びへ移動。レンダリング操作も同列右端へ。左サイドバーを廃止し2列構成へ。字幕欄を最大460pxから360pxへ縮小。通常プレビューの枠幅を映像の16:9比率と利用可能高さに合わせる。映像自体はクロップしない。
- 検証: frontend typecheck/lint/build、Docker frontend build成功。稼働frontendへ反映。アプリ内ブラウザで上部clip切替、字幕欄の縮小、映像左右の大きな黒余白がない状態をスクリーンショット確認。保存操作・ページ再読み込みは未実施。

## 2026-09-17 字幕確認の通常編集を4列へ再配置
- 目的: clip一覧を細い左欄へ戻し、その上に形式切替、clipと映像の間にタイトル・フック編集を配置する。
- 変更ファイル: frontend/app/jobs/[jobId]/subtitles/page.tsx、frontend/app/globals.css。
- 変更内容: 形式切替をclip欄内へ移動。通常編集をclip・編集・映像・字幕の4列へ変更。編集欄は独立スクロール、映像は字幕側へ寄せ、16:9を維持。
- 検証: frontend typecheck / lint / build成功。Docker frontend build成功。稼働中frontendへ反映し、既存ブラウザの通常編集画面で配置と表示を確認。
- 未確認: 小画面での実操作、ショート編集の今回の実画面回帰確認。

## 2026-09-17 通常字幕画面の書式設定を映像下へ配置
- 目的: 映像と書体・位置・色を同時に確認する。
- 変更ファイル: frontend/app/globals.css。
- 変更内容: 通常のデスクトップ画面はタイトル・フックを左に常時表示。書体・サイズ、位置、色を映像下の3列へ移動し、各列を独立スクロールにした。
- 検証: frontend lint / build（TypeScript検証含む）、Docker frontend build成功。稼働コンテナに反映し2209x1272の既存画面で映像下3列と左タイトル欄の同時表示を確認。
- 未確認: 小画面の実操作。ショート用レイアウトは変更なし。

## 2026-09-17 通常プレビュー左右の空白を黒帯表示
- 目的: 編集プレビュー左右の空白を黒で埋める。
- 変更ファイル: frontend/app/globals.css。
- 変更内容: 通常プレビュー領域の背景を黒、映像を中央配置に変更。映像のサイズ・縦横比の計算は維持。
- 検証: Docker frontend build成功。稼働frontendへ反映し、既存ブラウザで左右黒帯を確認。
- 未解決事項: 本変更についてなし。

## 2026-09-17 PUSH前検証
- 対象: 選定・キープ・プレビュー修正、保存色、許諾番号、字幕確認レイアウトの累積変更。
- 検証: backend全体1128 passed / 1 skipped / 1 failed。失敗は許諾番号追加に伴う既存テスト期待値で、修正後の対象テスト1 passed。ruff成功。frontend typecheck / lint / build成功。Docker各サービス稼働確認。
- 追加変更: backend/tests/test_api_routes.pyの保存プロフィール期待値に空の許諾番号を追加。
- ローカル画像・storage配下の作業データはPUSH対象外。
