# AutoClipper Web

有料のOpenAI Platform APIは使わない。CodexはChatGPTログインの経路を使用する。

## 日本語で始める（Windows）

**[Windows導入・起動手順（日本語）](docs/WINDOWS_SETUP_JA.md)** — 必要ソフト、GitHubからの取得、CPUでの初回起動、Codex連携、更新・設定移行を説明しています。

Intel内蔵GPUのPCは「CPU互換設定で起動」を使います。Codexのインストールだけでは動作しません。Docker DesktopとPythonも必要です。

AutoClipper Web is a video clipping web app with automatic and manual creation flows.

The v1 flow is:

- upload a long video
- create a background job
- either analyze/transcribe/score/select clip candidates automatically, or set normal/short ranges manually from the uploaded source
- choose automatic subtitles, no conversation subtitles, or one editable manual subtitle per clip in the manual flow
- render normal clips and 9:16 shorts with subtitles
- download generated MP4 files or a ZIP

Full timeline editing, approve/reject workflow management, auth, billing, and social posting are out of scope for v1.

## Stack

- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI
- Worker: RQ
- Queue: Redis
- Database: SQLite
- Processing: FFmpeg / ffprobe, faster-whisper, local rule scoring and Codex selection
- Storage: local filesystem under `storage/`

## Requirements

- Docker Desktop
- Docker Compose
- Python 3.11+ for the Windows launcher, local tests, or host-side scripts

## Windows Launcher

Windows users can start and stop the existing Docker-based application without entering Compose commands manually.

Double-click:

```text
Start AutoClipper.cmd
```

The desktop entrypoint starts an installed Docker Desktop when its daemon is stopped, waits for the engine, starts the recommended four-service profile, waits for the app, and opens `/upload`. On a compatible NVIDIA system, the recommended profile uses the GPU worker and preselects `turbo / ja / cuda / float16`. Otherwise it starts the CPU-compatible profile and shows the reason. An explicit GPU start never falls back silently. The launcher can also retry a selected profile, show logs, and open the uploads/outputs folders. Normal stop uses `docker compose stop` and preserves SQLite, Redis data, uploads, outputs, and the Whisper model cache.

The launcher MVP requires Python 3.11+. Docker Desktop remains required. See `docs/WINDOWS_LAUNCHER.md` for controls and troubleshooting.

## Docker Compose Runtime

Copy the example environment file if you want local overrides:

```powershell
Copy-Item .env.example .env
```

Video uploads default to a maximum of 8 GiB. Override
`MAX_UPLOAD_SIZE_BYTES` in `.env` when a different local limit is required.
Optional YouTube heatmap sidecars default to 5 MiB. Override
`MAX_HEATMAP_SIDECAR_SIZE_BYTES` when required.

Start all services:

```powershell
docker compose up -d --build
```

Show service status:

```powershell
docker compose ps
```

Expected services:

- `frontend`: `http://localhost:3000`
- `backend`: `http://localhost:8000`
- `worker`: RQ worker process
- `redis`: queue backend

Stop all services:

```powershell
docker compose down
```

Follow logs:

```powershell
docker compose logs -f backend frontend worker redis
```

Run or restart only the worker:

```powershell
docker compose up -d worker
docker compose logs -f worker
```

### NVIDIA GPU worker

The default Compose file keeps the existing CPU worker. On Windows with Docker Desktop,
WSL2 GPU support, and a compatible NVIDIA driver, start the CUDA 12.8 worker with:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec -T worker `
  python -m app.audio.gpu_preflight
```

The GPU override changes only the worker image. CPU and GPU workers use distinct,
Compose-project-scoped local image names so switching profiles or checkouts cannot reuse the
wrong base image. Backend and frontend remain on their smaller default images. Whisper model
downloads are retained in the
`whisper_model_cache` volume.

Use `transcriptionDevice=cuda` for an explicit GPU requirement. That mode fails with
`transcription_cuda_unavailable` instead of silently using CPU. `transcriptionDevice=auto`
uses CUDA when available and records a CPU fallback reason otherwise.

The Windows launcher can select this override automatically. `Recommended Start` uses it only
after the host NVIDIA GPU and Docker NVIDIA runtime pass preflight; `GPU Required Start` stops
on failure instead of silently switching to CPU. Profile changes rebuild and recreate the worker.
An already-running GPU worker is rechecked before reuse, including loading
`libcublas.so.12` and `libcudnn.so.9`. The preflight payload is versioned, so an older worker is
rebuilt instead of reused. A GPU worker runs the same check before it connects to RQ and cannot
take a queued job with an invalid CUDA runtime. This startup check runs in a separate process so
the RQ parent remains CUDA-uninitialized before it forks a job process. `CPU Compatible Start`
always uses the default Compose worker. The launcher opens Upload with the matching
transcription profile selected.

## Local subtitle correction benchmark

Task 68 provides an offline Ollama benchmark for `qwen3.5:9b` and optional `qwen3:14b`.
It evaluates deterministic safety escalation without changing the pipeline. Both tested models failed the safety or utility gates,
so local LLM correction is not integrated. See `docs/TASK68_LOCAL_LLM_BENCHMARK.md`.

## Health Checks

Backend:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

API health endpoint:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

Frontend:

```powershell
Invoke-WebRequest http://localhost:3000 -UseBasicParsing
```

## Runtime Smoke Test

After `docker compose up -d --build`, run:

```powershell
python scripts/smoke_runtime.py
```

The smoke test verifies:

- `frontend`, `backend`, `worker`, and `redis` are running
- `GET /health` returns ok
- the frontend is reachable
- backend and worker use the same SQLite URL
- backend and worker share `/app/storage/uploads`, `/app/storage/temp`, and `/app/storage/outputs`
- `ffmpeg` exists in backend and worker containers
- `ffprobe` exists in backend and worker containers
- a tiny generated MP4 can be created and probed inside the runtime container
- the worker can see and probe the same generated MP4 via shared storage

Keep the generated MP4 for manual upload testing:

```powershell
python scripts/smoke_runtime.py --keep-test-video
```

Generated file:

```text
storage/temp/smoke_runtime/smoke.mp4
```

For the v1 release smoke checklist, see:

```text
docs/V1_RELEASE_CHECKLIST.md
```

After a real-video E2E job completes, run the lightweight release smoke helper:

```powershell
python scripts/v1_smoke_check.py --job-id JOB_ID
```

This verifies backend health, frontend reachability, results metadata, subtitle
and ZIP download endpoints, and local subtitle sidecar autoload risk. Processing
uses local functions and the Codex host bridge.

## Upload A Small Test Video

With the app running, open:

```text
http://localhost:3000/upload
```

For API-only upload using the smoke-generated MP4:

```powershell
python scripts/smoke_runtime.py --keep-test-video
curl.exe -F "file=@storage/temp/smoke_runtime/smoke.mp4;type=video/mp4" http://localhost:8000/api/videos/upload
```

The upload response includes `videoId`.

### Optional YouTube heatmap sidecar

For a video downloaded by `YouTubeDownloader`, the Upload UI can also send the
adjacent `<video filename>.heatmap.json` file. The API equivalent is an optional
multipart part named `heatmap`:

```powershell
curl.exe -F "file=@sample.mp4;type=video/mp4" -F "heatmap=@sample.mp4.heatmap.json;type=application/json" http://localhost:8000/api/videos/upload
```

AutoClipper validates sidecar schema v1, source, original filename, byte size,
SHA-256, finite ordered intervals, and the normalized `0..1` value range before
saving it. The worker revalidates the binding and accepts `duration_seconds`
within `max(2 seconds, 0.1% of the probed duration)`. `JSON区間モード` is OFF by
default. When OFF, a valid value is only a supporting score signal (up to +10);
missing or invalid data falls back to the existing subtitle/audio/video scoring
path. When ON, positive heatmap intervals seed the candidate pool and are ranked
by their normalized in-video value before existing quality filters are applied.
Missing, unavailable, invalid, or unusable interval data stops the job explicitly
instead of falling back. Manual time ranges still take priority for their output
type. The value is not a view count and cannot bypass existing quality gates.
Validation and mode decisions are recorded in
`heatmap_validation_summary.json`.

During clip-plan review, `候補基準` can switch reselection between `従来評価`
and `JSON区間`. Changing the mode rebuilds the candidate pool from the saved
transcript, audio, scene, and visual analysis; it does not upload or transcribe
the video again. Switching OFF returns to the legacy candidate generators while
keeping a valid heatmap value as the bounded supporting score described above.
Reselection remains deterministic, so OFF changes the candidate source but does
not promise a different scene when the resulting evidence still ranks the same
range highest.

Create a job:

```powershell
curl.exe -H "Content-Type: application/json" -d '{"videoId":"VIDEO_ID_FROM_UPLOAD","settings":{}}' http://localhost:8000/api/jobs
```

Poll job status:

```powershell
curl.exe http://localhost:8000/api/jobs/JOB_ID_FROM_CREATE
```

Read results:

```powershell
curl.exe http://localhost:8000/api/jobs/JOB_ID_FROM_CREATE/results
```

The results response includes per-clip metadata when available: title source, scores, selection reason, boundary refinement status, resolution, audit warnings, subtitle link, and metadata JSON link. If `audit/output_audit_report.json` exists for the job, the response also includes `auditSummary`.

For a full real-content E2E, use a short video that has audible speech. A generated tone-only smoke video is useful for upload/probe checks, but may not produce usable clips because candidate generation depends on transcript and speech features.

## Real Sample Video E2E

Start the runtime:

```powershell
docker compose up -d --build
```

Generate a reproducible 25 second MP4 with a video test pattern and sine wave audio:

```powershell
python scripts/generate_sample_video.py
```

Generated file:

```text
storage/temp/e2e_sample.mp4
```

Run the API E2E path:

```powershell
python scripts/e2e_sample_video.py
```

Or start compose and run the E2E in one command:

```powershell
python scripts/e2e_sample_video.py --start
```

The script verifies:

- backend `/health`
- frontend reachability
- docker compose services
- sample MP4 generation through runtime `ffmpeg`
- upload through `POST /api/videos/upload`
- job creation through `POST /api/jobs`
- worker status polling until `completed` or a clear expected failure
- MP4 download
- ZIP download
- downloaded MP4 probing through worker `ffprobe`

Because the generated sample has sine audio but no real speech, the E2E script creates the job with `e2eFixtureTranscript=true`. This setting is for reproducible runtime validation only. It is disabled by default and does not change production quality gates.

E2E outputs:

```text
storage/outputs/{job_id}
storage/temp/e2e_download.mp4
storage/temp/e2e_download.zip
```

## Real Spoken-Video E2E

Use this when you want to exercise the real faster-whisper transcription path. The input should be:

- 1-3 minutes
- MP4
- clear spoken voice
- audible speech for most of the video
- not music-only or tone-only

Start the runtime:

```powershell
docker compose up -d --build
```

Run the low-cost first pass:

```powershell
python scripts/e2e_real_video.py --video path\to\spoken_sample.mp4
```

Useful options:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_sample.mp4 `
  --normal-count 1 `
  --short-count 1 `
  --mode low_cost `
  --profile talk `
  --timeout 1800
```

For a shorter spoken sample, request normal clip generation below the default 90 seconds:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_60s_sample.mp4 `
  --normal-count 1 `
  --short-count 0 `
  --normal-min-duration 20 `
  --normal-max-duration 60 `
  --selection-policy fill_requested
```

For a 10 minute spoken video, use a longer timeout and keep local scoring enabled:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_10min_sample.mp4 `
  --normal-count 1 `
  --short-count 1 `
  --normal-min-duration 90 `
  --normal-max-duration 600 `
  --short-min-duration 20 `
  --short-max-duration 75 `
  --selection-policy fill_requested `
  --mode low_cost `
  --timeout 3600
```

For a 30 minute spoken video, use the built-in validation profile. It keeps local scoring enabled by default and expands to `normalCount=2`, `shortCount=3`, `normalMinDuration=90`, `normalMaxDuration=600`, `shortMinDuration=20`, `shortMaxDuration=75`, `selectionPolicy=fill_requested`, `mode=low_cost`, and `timeout=7200`.

Recommended input:

- 25-35 minutes
- MP4
- clear spoken voice
- audible speech throughout most of the video
- not music-only, tone-only, or long silent-screen capture

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_30min_sample.mp4 `
  --validation-profile 30min
```

Equivalent explicit command:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_30min_sample.mp4 `
  --normal-count 2 `
  --short-count 3 `
  --normal-min-duration 90 `
  --normal-max-duration 600 `
  --short-min-duration 20 `
  --short-max-duration 75 `
  --selection-policy fill_requested `
  --mode low_cost `
  --timeout 7200
```

For a 1 hour spoken video, keep local scoring enabled first and use a longer timeout. Candidate generation is bounded by time buckets and chunked generation, so this path should reach selection/rendering instead of building unbounded raw candidates in memory.

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_1hour_sample.mp4 `
  --normal-count 5 `
  --short-count 10 `
  --normal-min-duration 90 `
  --normal-max-duration 600 `
  --short-min-duration 20 `
  --short-max-duration 75 `
  --selection-policy fill_requested `
  --mode low_cost `
  --timeout 14400
```

Validated 58-minute full-render reference run:

- Date: 2026-06-30
- Mode: `low_cost`
- Request: normal `5`, short `10`, `selectionPolicy=fill_requested`
- Job: `job_6e0b6c7539644c679e853eccfcb77039`
- Result: `REAL VIDEO E2E PASSED`
- Total runtime: `627.141s`
- Candidate generation: `52.704s`, `12` chunks, peak memory `466.258 MB`, memory guard `false`
- Selection: normal `5/5`, short `10/10`
- Render failures: `0`
- Render time: normal `111.219s`, shorts `87.281s`
- ZIP packaging: `22.266s`
- ZIP size: `385749028 bytes` (`367.88 MB`)
- Job output size: `790240046 bytes` (`753.63 MB`)
- Disk free: `180.39 GB` before run, `177.99 GB` after run
- Shorts: all downloaded MP4s verified as `1080x1920`
- Normal clips: all downloaded MP4s had valid dimensions and durations
- Required artifacts present: `candidate_generation_summary.json`, `selected_clips.json`, `selected_clips_summary.json`, `download.zip`

Long-video candidate generation defaults:

- `maxRawCandidatesPerType`: `250000`
- `maxKeptCandidatesPerType`: `1200`
- `maxCandidatesPerTimeBucket`: `100`
- `candidateTimeBucketSeconds`: `300`
- `candidateChunkSeconds`: `600`
- `candidateChunkOverlapSeconds`: `75`
- `maxCandidateGenerationMemoryMb`: `12000`

For diagnostics or constrained machines, override these from the E2E script:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_1hour_sample.mp4 `
  --normal-count 3 `
  --short-count 5 `
  --mode low_cost `
  --timeout 14400 `
  --max-kept-candidates-per-type 800 `
  --max-candidates-per-time-bucket 60 `
  --max-candidate-generation-memory-mb 9000
```

For transcript correction tests, pass a JSON replacement dictionary:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_sample.mp4 `
  --mode low_cost `
  --transcript-replacements-json path\to\transcript_replacements.json
```

The JSON file must be an object:

```json
{
  "チャットGPT": "ChatGPT",
  "ニューズピックス": "NewsPicks"
}
```

### Raw transcription benchmark

The compatibility default is `whisperModelSize=base`, `transcriptionLanguage=ja`,
`transcriptionDevice=cpu`, and `transcriptionComputeType=auto`.
For a real-video job, the raw faster-whisper profile can be changed without enabling transcript correction:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_sample.mp4 `
  --whisper-model-size turbo `
  --transcription-language ja `
  --transcription-device cuda `
  --transcription-compute-type float16 `
  --mode low_cost
```

Supported model sizes are `base`, `small`, `medium`, `large-v3`, and `turbo`. The
transcription language is fixed to `ja`. Device modes are `cpu`, `cuda`, and `auto`; compute
types are `auto`, `int8`, `float16`, and `int8_float16`.

The selected and actual runtime values are written to `transcript_summary.json`, including
model load time, transcription time, GPU name, peak VRAM proxy, and fallback diagnostics.

To compare raw transcription accuracy inside the worker, first prepare a mono 16 kHz WAV under the shared `storage` directory:

```powershell
docker compose exec worker ffmpeg -y `
  -i /app/storage/uploads/spoken_sample.mp4 `
  -t 120 -vn -ac 1 -ar 16000 `
  /app/storage/temp/transcription_benchmark/sample.wav
```

For a cached GPU comparison:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec -T worker `
  python -m app.audio.benchmark_transcription `
  --audio /app/storage/temp/transcription_benchmark/sample.wav `
  --profile small:ja:cuda:float16 `
  --profile medium:ja:cuda:float16 `
  --profile large-v3:ja:cuda:float16 `
  --profile turbo:ja:cuda:float16 `
  --reference-file /app/storage/temp/transcription_benchmark/reference.txt `
  --keyword ChatGPT `
  --output-dir /app/storage/outputs/transcription_benchmarks/sample
```

The Task 59 reference result is documented in `docs/TRANSCRIPTION_BENCHMARK_2026-07-10.md`.
The Task 67 GPU result is documented in `docs/GPU_TRANSCRIPTION_BENCHMARK_2026-07-19.md`.
On the tested RTX 5070 Ti, `turbo + ja + cuda + float16` is the current GPU recommendation.
It reduces correction demand but does not eliminate transcription errors or the need for
optional remote correction on important material.

## Job Settings

`POST /api/jobs` accepts advanced duration settings in `settings`:

```json
{
  "videoId": "vid_example",
  "settings": {
    "normalClipCount": 1,
    "shortCount": 1,
    "normalMinDuration": 90,
    "normalMaxDuration": 600,
    "shortMinDuration": 20,
    "shortMaxDuration": 75,
    "maxCandidates": 1200,
    "maxRawCandidatesPerType": 250000,
    "maxKeptCandidatesPerType": 1200,
    "maxCandidatesPerTimeBucket": 100,
    "candidateTimeBucketSeconds": 300,
    "maxCandidatesPerStartBucket": 5,
    "candidateStartBucketSeconds": 15,
    "candidateChunkSeconds": 600,
    "candidateChunkOverlapSeconds": 75,
    "maxCandidateGenerationMemoryMb": 12000,
    "normalClipSelectionPreset": "important",
    "shortClipSelectionPreset": "funny",
    "normalClipGuidance": "休んだ理由と復帰後の予定を優先",
    "shortClipGuidance": "驚きや笑いが一言で伝わる場面",
    "excludeIntroOutro": true,
    "excludePromotionalContent": false,
    "selectionPolicy": "fill_requested",
    "crossTypeOverlapDedupe": false,
    "enableBoundaryRefinement": true,
    "boundaryLeadingPaddingSeconds": 0.4,
    "boundaryTrailingPaddingSeconds": 0.6,
    "maxBoundaryExpansionSeconds": 3,
    "allowBoundaryExpansionBeyondMaxDuration": false,
    "enableTranscriptPostProcessing": true,
    "transcriptNormalizeUnicode": true,
    "transcriptNormalizeWhitespace": true,
    "transcriptNormalizePunctuation": true,
    "useDefaultTranscriptDictionary": true,
    "transcriptReplacements": {
      "チャットGPT": "ChatGPT"
    },
    "whisperModelSize": "base",
    "transcriptionLanguage": "ja",
    "transcriptionDevice": "cpu",
    "transcriptionComputeType": "auto",
    "normalSubtitleFontName": "Noto Sans CJK JP",
    "normalSubtitleFontSize": 65,
    "normalSubtitleOutline": 4,
    "normalSubtitlePrimaryColor": "#FFFFFF",
    "normalSubtitleOutlineColor": "#000000",
    "normalSubtitleAlignment": 2,
    "normalSubtitleLowerMargin": 86,
    "shortSubtitleFontName": "Source Han Sans JP Heavy",
    "shortSubtitleFontSize": 76,
    "shortSubtitleOutline": 5,
    "shortSubtitlePrimaryColor": "#FFF200",
    "shortSubtitleOutlineColor": "#000000",
    "shortSubtitleAlignment": 2,
    "shortSubtitleLowerMargin": 250
  }
}
```

Production-safe defaults remain:

- `normalMinDuration`: `90`
- `normalMaxDuration`: `600`
- `shortMinDuration`: `20`
- `shortMaxDuration`: `75`
- `maxCandidates`: `1200`
- `maxRawCandidatesPerType`: `250000`
- `maxKeptCandidatesPerType`: `1200`
- `maxCandidatesPerTimeBucket`: `100`
- `candidateTimeBucketSeconds`: `300`
- `maxCandidatesPerStartBucket`: `5`
- `candidateStartBucketSeconds`: `15`
- `candidateChunkSeconds`: `600`
- `candidateChunkOverlapSeconds`: `75`
- `maxCandidateGenerationMemoryMb`: `12000`
- `normalClipSelectionPreset`: `auto`
- `shortClipSelectionPreset`: `auto`
- `normalClipGuidance`: empty
- `shortClipGuidance`: empty
- `excludeIntroOutro`: `true`
- `excludePromotionalContent`: `false`
- `selectionPolicy`: `fill_requested`
- `crossTypeOverlapDedupe`: `false`
- `enableBoundaryRefinement`: `true`
- `boundaryLeadingPaddingSeconds`: `0.4`
- `boundaryTrailingPaddingSeconds`: `0.6`
- `maxBoundaryExpansionSeconds`: `3`
- `allowBoundaryExpansionBeyondMaxDuration`: `false`
- `enableTranscriptPostProcessing`: `true`
- `transcriptNormalizeUnicode`: `true`
- `transcriptNormalizeWhitespace`: `true`
- `transcriptNormalizePunctuation`: `true`
- `useDefaultTranscriptDictionary`: `true`
- `transcriptReplacements`: `{}`
- `whisperModelSize`: `base`
- `transcriptionLanguage`: `ja`（固定）
- `transcriptionDevice`: `cpu`
- `transcriptionComputeType`: `auto`

For development and E2E checks with shorter spoken videos, set `normalMinDuration` to `20` or `30` and keep `normalMaxDuration` at or below the input duration.

Selection policy:

- `fill_requested`: default. Hard gates still reject unusable candidates, but low `final_score` is used as ranking, not as a hard rejection. Selection runs in phases: first candidates above `minFinalScore`, then below-threshold hard-gate-passing backfill, then overlap-relaxed backfill only if the requested count is still unfilled. Overlap-relaxed clips are marked with `selection_reason=backfill_overlap_relaxed`, `overlap_relaxed=true`, and `overlap_ratio_used`.
- `strict_quality`: preserves strict behavior. Candidates below `minFinalScore` are rejected, so a job may complete analysis with zero selected outputs.
- Normal clips deduplicate against normal clips. Shorts deduplicate against shorts. By default, normal and short outputs do not block each other by overlap because they serve different formats.
- Set `crossTypeOverlapDedupe=true` only when you explicitly want normal and short selections to block each other by timeline overlap.
- Long-video selection prefers time diversity. Candidates are bucketed into timeline clusters, and the selector takes the best candidate per cluster before taking additional candidates from the same cluster.

Boundary refinement:

- Runs after final candidate selection and before rendering.
- Expands selected clip boundaries to nearby transcript segment starts/ends when the clip starts or ends inside speech.
- Adds small leading/trailing padding when safe.
- Can expand earlier when the first text starts with weak continuation markers such as `だから`, `それで`, `まあ`, `あの`, or `そうですね`.
- Keeps `normalMinDuration` / `normalMaxDuration` and `shortMinDuration` / `shortMaxDuration` unless `allowBoundaryExpansionBeyondMaxDuration=true`.
- Selected clip metadata records `original_start`, `original_end`, `refined_start`, `refined_end`, `boundary_refined`, `boundary_refinement_reason`, and `boundary_expansion_seconds`.

Transcript post-processing:

- Runs after transcription and before transcript usability checks, candidate generation, scoring, and subtitle rendering.
- Keeps the original faster-whisper output in `raw_transcript_segments.json`.
- Writes corrected text to the existing `transcript_segments.json`.
- Writes `transcript_postprocess_summary.json` with changed segment counts, before/after character counts, replacement counts, and normalization settings.
- Default processing is local and deterministic: Unicode NFKC normalization, whitespace cleanup, repeated punctuation cleanup, and a conservative dictionary for common terms such as `ChatGPT`, `YouTube`, `NewsPicks`, and `ReHacQ`.
- Add project-specific replacements with `transcriptReplacements`; this runs locally.
- Disable with `enableTranscriptPostProcessing=false` when raw transcription text is needed for debugging.


## Generation Diagnostics

Each completed or expected-failure job writes compact summary files under:

```text
storage/outputs/{job_id}/
```

Summary files:

- `transcript_summary.json`: transcript segment count, text length, speech duration, confidence, first segments, engine, fixture flag.
- `transcript_postprocess_summary.json`: transcript post-processing enablement, changed segment count, before/after character counts, replacement counts, and dictionary settings when transcription reached post-processing.
- `transcript_correction_summary.json`: correction mode, scope, model, target/context counts, corrected/unchanged/low-confidence segment counts, fallback status, API calls, actual token usage, schema failures, processing time, and timestamp/count preservation flags.
- `transcript_suspicion_summary.json`: local filter threshold, suspicious ratio, target/context counts, unique segments sent, score/rescue selection counts, rescue reason counts, and explicit filter failure state.
- `audio_feature_summary.json`: duration, silence ratio, speech density, volume peak, silent seconds, speech seconds.
- `candidate_summary.json`: total/normal/short candidate counts, transcript text coverage, hard gate counts, requested/selected counts, overlap diagnostics, timeline cluster diagnostics, backfill counts, duration stats, rule/final score stats, score percentiles, top selected candidates, top rejected candidates by reason.
- `rejection_summary.json`: quality gate rejection counts, high-overlap counts by type, cross-type overlap counts, and render failure counts.
- `selected_clips_summary.json`: requested/selected normal/short counts, unfilled counts, selected IDs, durations, scores, quality warnings, selection reasons, boundary refinement fields, overlap relaxation flags, timeline clusters, and output paths.

The E2E scripts print these summaries:

```powershell
python scripts/e2e_sample_video.py
python scripts/e2e_real_video.py --video path\to\spoken_sample.mp4
```

## Output Quality Audit

Use this after a job completes to summarize generated clips and identify likely quality issues before manual viewing.
The audit reads existing artifacts only. It does not change selection, scoring, rendering, or job state.

```powershell
python scripts/audit_outputs.py --job-id job_ID
```

Default outputs:

```text
storage/outputs/{job_id}/audit/output_audit_report.json
storage/outputs/{job_id}/audit/output_audit_report.md
```

Useful options:

```powershell
python scripts/audit_outputs.py `
  --job-id job_ID `
  --output storage\outputs\audits\job_ID `
  --format both
```

The report includes:

- per-clip file path, duration, resolution, selected start/end, transcript excerpts, scores, selection reason, title, title source, overlay title, subtitle path, and historical score source
- short verification for `1080x1920`
- normal verification for valid dimensions and duration
- subtitle existence and readability density checks
- subtitle density reasons and worst subtitle density samples when detected
- aggregate warning counts by clip type
- clips requiring human visual inspection

Heuristic warnings include:

- `very_short_transcript_text`
- `likely_abrupt_start`
- `likely_abrupt_ending`
- `subtitle_too_dense`
- `no_subtitle_file`
- `missing_title`
- `generic_fallback_title`
- `below_quality_threshold`
- `backfilled_clip`
- `rule_only_clip_in_high_quality_mode`
- `short_duration_outside_recommended_range`
- `normal_duration_outside_recommended_range`
- `short_resolution_not_1080x1920`

58-minute full-render audit reference:

- Job: `job_6e0b6c7539644c679e853eccfcb77039`
- Result: generated reports under `storage/outputs/job_6e0b6c7539644c679e853eccfcb77039/audit/`
- Generated clips: normal `5`, short `10`
- Shorts: all resolved as `1080x1920`
- Clips requiring human visual inspection: `15`
- Dominant warnings: generic fallback titles on older artifacts, subtitle density, likely abrupt starts, one below-threshold backfill clip

Title fallback behavior:

Subtitle readability behavior:

- Shorts default to `maxCharsPerLineShort=16`, `maxLines=2`.
- Normal clips default to `maxCharsPerLineNormal=28`, `maxLines=2`.
- Long transcript segments are split into multiple ASS subtitle events and timed by character count.
- Very short adjacent transcript segments are merged when the timing gap is small enough.
- Advanced API settings: `maxCharsPerLineShort`, `maxCharsPerLineNormal`, `maxLines`, `minSubtitleDuration`, `maxSubtitleDuration`, `minGapBetweenSubtitles`.
- Task 35 subtitle-only 58-minute smoke regenerated ASS files without re-rendering MP4 and reduced subtitle density warnings to normal `1`, short `0`.
- Backend and worker containers install `fonts-noto-cjk`; generated ASS files use `Noto Sans CJK JP` by default so Japanese subtitles do not render as missing-glyph boxes.
- Subtitle font selectors group bundled fonts into normal-subtitle and short-emphasis choices. Normal choices include `Noto Sans JP Black`, `Source Han Sans JP Heavy`, `M PLUS 1 ExtraBold`, and `Rounded Mplus 1c ExtraBold`. Emphasis choices include `851CHIKARA-DZUYOKU-KANA-A`, `Dela Gothic One`, and `Corporate-Logo-Bold-ver3`.
- Docker mounts `frontend/public/fonts` read-only into backend and worker containers and passes the directory to FFmpeg/libass. Source, license, and SHA-256 details are recorded in `frontend/public/fonts/README.md`.

Short composition fallback behavior:

- `shortLayout=auto` first uses reliable face tracking when face detections fit safely inside a 9:16 crop.
- If face detections are too wide to fit a vertical crop, AutoClipper checks stable speaker, person, and motion / edge / saliency signals before preserving the full frame with `blur_background`.
- If face groups are too wide but transcript timing exposes a stable single dialogue region, AutoClipper can use `speaker_tracking_crop`.
- If no reliable face / speaker crop is available, AutoClipper samples optional person detections and uses `person_tracking_crop` only when the detected person box is confident, stable, and unambiguous.
- If person detection is unavailable or ambiguous, AutoClipper samples lightweight motion / edge / saliency signals and uses `subject_tracking_crop` only when confidence and stability are sufficient.
- If person / subject signals are weak, source dimensions are missing, or the face signal is too weak on a landscape video, `blur_background` is preferred before `center_crop`.
- Explicit `shortLayout=center_crop` still forces center crop first.
- Explicit `shortLayout=face_tracking_crop` forces the detected face group into a 9:16 crop when a usable face signal is available.
- Short metadata records `crop_strategy`, `crop_signal_source`, `crop_confidence`, `crop_fallback_reason`, `crop_x`, `crop_y`, `crop_detection_count`, `crop_sampled_frames`, `crop_subject_x`, `crop_stability_score`, `person_detection_count`, `person_detection_confidence`, `person_box`, `speaker_window_count`, `speaker_region_confidence`, `speaker_region_box`, and `crop_attempted_strategies`.

Subtitle burn-in smoke:

```powershell
docker compose up -d --build backend worker

python scripts/smoke_subtitle_burn_in.py `
  --docker-service worker `
  --source-job-id job_6e0b6c7539644c679e853eccfcb77039 `
  --output-job-id job_6e0b6c7539644c679e853eccfcb77039_task35b_burnin `
  --normal-count 1 `
  --short-count 2 `
  --normal-duration-limit 120 `
  --short-layout center_crop

python scripts/audit_outputs.py `
  --job-id job_6e0b6c7539644c679e853eccfcb77039_task35b_burnin `
  --format both
```

Task 35b burn-in validation result:

- normal render: `1/1`
- short render: `2/2`
- render failures: `0`
- shorts: `1080x1920`
- subtitle density warnings: normal `0`, short `0`
- visual frame checks confirmed Japanese subtitles render with glyphs, not boxes.

High-quality overlay title burn-in smoke:

```powershell
python scripts/smoke_subtitle_burn_in.py `
  --docker-service worker `
  --job-id job_HIGH_QUALITY_ID `
  --mode high_quality `
  --normal-count 1 `
  --short-count 2 `
  --normal-duration-limit 120 `
  --require-overlay-title `
  --force-overlay-title "日本語タイトル確認 {number}" `
  --short-overlay-title-mode always `
  --short-layout center_crop
```

The script writes representative short frames under:

```text
storage/outputs/{smoke_job_id}/audit_frames/
```


```powershell
python scripts/smoke_subtitle_burn_in.py `
  --video path\to\spoken_sample.mp4 `
  --docker-service worker `
  --mode high_quality `
  --normal-count 1 `
  --short-count 2 `
  --timeout 1800 `
  --require-overlay-title `
  --force-overlay-title "日本語タイトル確認 {number}"
```

Task 35c overlay validation result:

- high_quality source job: `job_dfd13dd8435a401f9ab9773fa217bd18`
- smoke job: `job_dfd13dd8435a401f9ab9773fa217bd18_task35c_overlay_burnin`
- normal render: `1/1`
- short render: `2/2`
- render failures: `0`
- shorts: `1080x1920`
- short overlay titles: `2/2`
- ASS title/subtitle vertical gap: `1172px`
- short audit warnings: `0`
- extracted frames confirmed top title and lower subtitles do not overlap.

## Compare low_cost and high_quality runs

Use this after running both modes on the same source video. The comparison reads existing artifacts only and does not change selection behavior.

```powershell
python scripts/compare_runs.py `
  --low-cost-job-id job_LOW_COST_ID `
  --high-quality-job-id job_HIGH_QUALITY_ID
```

Default outputs:

```text
storage/outputs/comparisons/{low_cost_job_id}_vs_{high_quality_job_id}/comparison_report.json
storage/outputs/comparisons/{low_cost_job_id}_vs_{high_quality_job_id}/comparison_report.md
```

Useful options:

```powershell
python scripts/compare_runs.py `
  --low-cost-job-id job_LOW_COST_ID `
  --high-quality-job-id job_HIGH_QUALITY_ID `
  --output storage\outputs\comparisons\my_run `
  --format both
```

The report compares:

- selected normal and short counts
- requested versus selected count fulfillment
- selected clip time ranges
- low_cost / high_quality time overlap
- rule, AI, and final scores
- titles and overlay titles
- selection reason, quality warning, fallback, backfill, and historical score source
- render failure counts
- high_quality selected clips using AI score, fallback, or no score

To run both modes and then compare:

```powershell
python scripts/e2e_compare_quality.py `
  --video path\to\spoken_30min_sample.mp4 `
  --normal-count 2 `
  --short-count 3 `
```

## Storage

Host paths:

```text
storage/uploads
storage/temp
storage/outputs
storage/autoclipper.db
```

Container paths used by both backend and worker:

```text
/app/storage/uploads
/app/storage/temp
/app/storage/outputs
/app/storage/autoclipper.db
```

`docker-compose.yml` mounts the same host `./storage` directory into backend and worker as `/app/storage`.

Generated clip outputs avoid same-folder subtitle sidecars because common video players auto-load
`short_01.ass` when opening `short_01.mp4`, causing duplicate subtitles after burn-in.

```text
storage/outputs/{job_id}/normal/normal_01.mp4
storage/outputs/{job_id}/normal/normal_01.json
storage/outputs/{job_id}/shorts/short_01.mp4
storage/outputs/{job_id}/shorts/short_01.json
storage/outputs/{job_id}/subtitles/normal/normal_01.ass
storage/outputs/{job_id}/subtitles/shorts/short_01.ass
```

ZIP downloads use the same separation:

```text
videos/normal/*.mp4
videos/shorts/*.mp4
subtitles/normal/*.ass
subtitles/shorts/*.ass
metadata/normal/*.json
metadata/shorts/*.json
metadata/*.json
```

Check a completed job for subtitle sidecars that players may auto-load:

```powershell
python scripts/check_subtitle_sidecar_risk.py --job-id job_ID
```

## Runtime Requirements Inside Containers

Backend and worker are built from `backend/Dockerfile`.

The Dockerfile installs:

```text
ffmpeg
ffprobe
```

Verify manually:

```powershell
docker compose exec backend ffmpeg -version
docker compose exec backend ffprobe -version
docker compose exec worker ffmpeg -version
docker compose exec worker ffprobe -version
```

## Local Tests

Backend:

```powershell
cd backend
python -m pip install -e ".[dev]"
ruff check .
pytest
```

Frontend:

```powershell
npm ci
npm --workspace frontend run lint
npm --workspace frontend run typecheck
npm --workspace frontend run build
```

CI runs on pull requests and pushes to `main`.

## Troubleshooting

Docker command not found:

- Restart the terminal after installing Docker Desktop.
- Verify `C:\Program Files\Docker\Docker\resources\bin` is on PATH.

Docker daemon not running:

- `Start AutoClipper.cmd` normally starts Docker Desktop and waits up to 180 seconds.
- If startup times out, check Docker Desktop for an agreement prompt, WSL update, or Windows restart request.
- Manual fallback:

```powershell
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
docker info
```

WSL not ready:

```powershell
wsl -l -v
```

Expected Docker distro:

```text
docker-desktop    Running    2
```

Port already in use:

- backend uses `8000`
- frontend uses `3000`
- redis uses `6379`

Find the process and stop it, or change the compose port mapping.

Redis or worker issues:

```powershell
docker compose logs -f redis worker
docker compose restart redis worker
```

Backend cannot find files:

- Confirm backend and worker both use `STORAGE_ROOT=/app/storage`.
- Confirm `docker compose ps` shows both services running from the same compose project.
- Run `python scripts/smoke_runtime.py` to verify shared storage.

Long-form transcription recovery:

- For CUDA jobs at least 30 minutes long, the worker checks transcript coverage, text density, confidence, and repeated low-information segments after the normal whole-file transcription.
- When that quality check fails, recovery is automatic: the same model retries in 90-second chunks with 5-second overlap, then `small + ja` retries in chunks only if the result is still unusable.
- Chunk timestamps are merged and overlapping duplicate segments are removed. The quality threshold is not lowered.
- Recovery details are written to `transcription_recovery_summary.json`.

No usable clips after selection:

- `no_usable_selection` means analysis completed but selection produced zero clips. The failed-job screen offers `同じ動画・設定で再処理`.
- The retry reuses the stored video, heatmap sidecar, and settings in a new job. No re-upload or setting re-entry is required.
- A source job can create only one retry. A second deterministic failure does not offer another retry.
- Render failures remain `no_usable_output` and do not use this full-pipeline retry path.
