# AutoClipper Web

AutoClipper Web is a full-auto video clipping web app.

The v1 flow is:

- upload a long video
- create a background job
- analyze/transcribe/score/select clip candidates
- render normal clips and 9:16 shorts with subtitles
- download generated MP4 files or a ZIP

Manual editing, approve/reject review flows, auth, billing, and social posting are out of scope for v1.

## Stack

- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI
- Worker: RQ
- Queue: Redis
- Database: SQLite
- Processing: FFmpeg / ffprobe, faster-whisper, optional OpenAI scoring
- Storage: local filesystem under `storage/`

## Requirements

- Docker Desktop
- Docker Compose
- Python 3.11+ only if you want to run local tests or `scripts/smoke_runtime.py` from the host

## Docker Compose Runtime

Copy the example environment file if you want local overrides:

```powershell
Copy-Item .env.example .env
```

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

For a 10 minute spoken video, use a longer timeout and keep OpenAI scoring off:

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

For a 30 minute spoken video, use the built-in validation profile. It keeps OpenAI scoring off by default and expands to `normalCount=2`, `shortCount=3`, `normalMinDuration=90`, `normalMaxDuration=600`, `shortMinDuration=20`, `shortMaxDuration=75`, `selectionPolicy=fill_requested`, `mode=low_cost`, and `timeout=7200`.

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

Expected runtime depends on CPU/GPU, disk speed, first-run faster-whisper model download, and render count. Start with the 30 minute profile before enabling OpenAI scoring.

For a 1 hour spoken video, keep OpenAI scoring off first and use a longer timeout. Candidate generation is bounded by time buckets and chunked generation, so this path should reach selection/rendering instead of building unbounded raw candidates in memory.

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

For a high-quality OpenAI Structured Outputs scoring check, put an existing key in `.env`:

```powershell
OPENAI_API_KEY=<your_openai_api_key>
docker compose up -d --build
```

Then run a small, cost-bounded E2E:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_sample.mp4 `
  --normal-count 1 `
  --short-count 1 `
  --mode high_quality `
  --use-openai-scoring true `
  --openai-candidate-limit 20 `
  --openai-model gpt-5.5 `
  --timeout 1800
```

For a 30 minute high-quality API-path validation, use the cost-bounded profile:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_30min_sample.mp4 `
  --validation-profile 30min_high_quality
```

Equivalent explicit command:

```powershell
python scripts/e2e_real_video.py `
  --video path\to\spoken_30min_sample.mp4 `
  --validation-profile 30min `
  --mode high_quality `
  --use-openai-scoring true `
  --openai-candidate-limit 20 `
  --openai-fallback-to-rule-score true `
  --ensure-selected-openai-scored true `
  --openai-finalist-scoring-limit 7 `
  --normal-count 2 `
  --short-count 3 `
  --selection-policy fill_requested `
  --timeout 7200
```

Cost controls:

- `--openai-candidate-limit` defaults to `20` in the E2E script.
- Backend default `openaiCandidateLimit` is `40`.
- The worker sends candidate transcript text plus audio/visual feature summaries only. It does not send uploaded video files or rendered MP4 files.
- The 30 minute high-quality profile first sends only the limited OpenAI preselection pool. It does not send all generated candidates.
- When `ensureSelectedOpenAIScored=true`, selected rule-only finalists are scored on demand before rendering, up to `openaiFinalistScoringLimit`.
- Use `--use-openai-scoring false` with `--mode high_quality` to exercise the rest of high-quality settings without API calls.

The script:

- uploads through `POST /api/videos/upload`
- creates a job through `POST /api/jobs`
- explicitly sets `e2eFixtureTranscript=false`
- waits for completion
- validates `storage/outputs/{job_id}/transcript_segments.json`
- fails if transcript text is empty, too short, or matches the synthetic fixture marker
- validates `selected_clips.json` when clips are generated
- downloads the ZIP
- downloads generated MP4 files
- probes downloaded MP4 files through worker `ffprobe`
- verifies short MP4 files are `1080x1920`
- verifies normal MP4 files have valid dimensions and a valid duration close to the export metadata
- validates `candidate_summary.json`, `selected_clips_summary.json`, and `selected_clips.json`
- prints runtime metrics: upload, transcription, scene detection, candidate generation, scoring, selection, normal render, short render, ZIP packaging, and total time
- prints pipeline metrics: video duration, transcript length, candidate counts, candidate generation chunks/raw/kept/dropped/caps, hard-gate counts, selected counts, backfilled count, render failure count, and ZIP size
- validates `openai_scoring_summary.json` when OpenAI scoring is enabled and prints model, candidate limit, finalist limit, preselection/finalist call counts, success/failure/fallback counts, schema failures, latency, text-size proxy, and selected clip score source counts
- prints diagnostic summary JSON files when they exist

Expected outputs:

```text
storage/outputs/{job_id}/transcript_segments.json
storage/outputs/{job_id}/transcript_summary.json
storage/outputs/{job_id}/audio_feature_summary.json
storage/outputs/{job_id}/candidate_generation_summary.json
storage/outputs/{job_id}/candidate_summary.json
storage/outputs/{job_id}/openai_scoring_summary.json
storage/outputs/{job_id}/rejection_summary.json
storage/outputs/{job_id}/selected_clips_summary.json
storage/outputs/{job_id}/selected_clips.json
storage/outputs/{job_id}/download.zip
storage/temp/e2e_real_{job_id}.zip
storage/temp/e2e_real_{job_id}_*.mp4
```

Troubleshooting:

- `audio_silent_or_unusable`: the audio track is silent, near-silent, or has too little measurable speech.
- `transcript_unusable`: faster-whisper ran, but the transcript was empty, too short, too low confidence, or repeated low-information text.
- `transcription_empty`: use a clearer spoken sample with audible voice.
- `no_candidates_found`: use a longer sample, ideally at least 90 seconds if normal clips are requested.
- `candidate_generation_memory_limit`: candidate generation exceeded `maxCandidateGenerationMemoryMb`. Lower `--max-kept-candidates-per-type` or `--max-candidates-per-time-bucket`, then retry.
- `worker_terminated_unexpectedly`: the worker heartbeat stopped while a job was running. Check `docker compose logs worker` for RQ work-horse termination, signal 9, or container restart.
- `quality gate rejection`: check `selected_clips.json` and `rejection_summary.json`; in `strict_quality` mode, low scores can intentionally leave selected outputs at zero.
- `openai_configuration_missing`: `OPENAI_API_KEY` is missing in the worker container. Update `.env`, then recreate services with `docker compose up -d --build`.
- `openai_scoring_failed`: OpenAI scoring failed and fallback was disabled. Check `openai_scoring_summary.json` and `docker compose logs worker`.
- OpenAI rate limit / timeout: lower `--openai-candidate-limit`, retry later, or use `--openai-fallback-to-rule-score true`.
- Structured output validation failure: check `openai_scoring_summary.json` error fields and keep the default strict schema.
- `render failure`: check `render_failures.json` and `docker compose logs worker`.
- 30 minute timeout: rerun with a larger `--timeout` if the worker is still making progress in `docker compose logs worker`.
- First run can be slow because faster-whisper may download the model.
- Use `--short-count 1 --normal-count 0` for a shorter first real run on a 1 minute sample.

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
    "candidateChunkSeconds": 600,
    "candidateChunkOverlapSeconds": 75,
    "maxCandidateGenerationMemoryMb": 12000,
    "selectionPolicy": "fill_requested",
    "crossTypeOverlapDedupe": false,
    "useOpenAIScoring": false,
    "openaiCandidateLimit": 40,
    "openaiModel": "gpt-5.5",
    "openaiFallbackToRuleScore": true,
    "ensureSelectedOpenAIScored": true,
    "openaiFinalistScoringLimit": 7,
    "enableBoundaryRefinement": true,
    "boundaryLeadingPaddingSeconds": 0.4,
    "boundaryTrailingPaddingSeconds": 0.6,
    "maxBoundaryExpansionSeconds": 3,
    "allowBoundaryExpansionBeyondMaxDuration": false
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
- `candidateChunkSeconds`: `600`
- `candidateChunkOverlapSeconds`: `75`
- `maxCandidateGenerationMemoryMb`: `12000`
- `selectionPolicy`: `fill_requested`
- `crossTypeOverlapDedupe`: `false`
- `useOpenAIScoring`: `false`
- `openaiCandidateLimit`: `40`
- `openaiModel`: `gpt-5.5`
- `openaiFallbackToRuleScore`: `true`
- `ensureSelectedOpenAIScored`: `true` in `high_quality`, `false` in `low_cost`
- `openaiFinalistScoringLimit`: requested output count plus a small buffer by default
- `enableBoundaryRefinement`: `true`
- `boundaryLeadingPaddingSeconds`: `0.4`
- `boundaryTrailingPaddingSeconds`: `0.6`
- `maxBoundaryExpansionSeconds`: `3`
- `allowBoundaryExpansionBeyondMaxDuration`: `false`

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

## Generation Diagnostics

Each completed or expected-failure job writes compact summary files under:

```text
storage/outputs/{job_id}/
```

Summary files:

- `transcript_summary.json`: transcript segment count, text length, speech duration, confidence, first segments, engine, fixture flag.
- `audio_feature_summary.json`: duration, silence ratio, speech density, volume peak, silent seconds, speech seconds.
- `candidate_summary.json`: total/normal/short candidate counts, transcript text coverage, hard gate counts, requested/selected counts, overlap diagnostics, timeline cluster diagnostics, backfill counts, duration stats, rule/final score stats, score percentiles, top selected candidates, top rejected candidates by reason.
- `openai_scoring_summary.json`: model, initial candidate limit, finalist scoring limit, eligible/selected/sent counts, preselection/finalist counts, successful structured scores, failed scores, fallback scores, schema validation failures, average/max/total latency, text length proxy, total API calls, selected clip score source counts, and not-scored reasons.
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

- per-clip file path, duration, resolution, selected start/end, transcript excerpts, scores, selection reason, title, title source, overlay title, subtitle path, and OpenAI score source
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

- OpenAI titles are preserved with `title_source=openai`.
- Low-cost and rule-only clips get deterministic local titles without calling OpenAI.
- Fallback priority is existing/OpenAI title, candidate transcript text, transcript segments within the clip range, then deterministic labels such as `Normal Clip 01` or `Short 01`.
- Generated `selected_clips.json`, `normal_XX.json`, and `short_XX.json` include `title` and `title_source`.
- Short metadata also includes `overlay_title`; fallback overlay titles are metadata only unless an existing/OpenAI overlay title is already part of the render path.
- Audit treats an empty title as `missing_title`; deterministic labels are reported as the weaker `generic_fallback_title`.

Subtitle readability behavior:

- Shorts default to `maxCharsPerLineShort=16`, `maxLines=2`.
- Normal clips default to `maxCharsPerLineNormal=28`, `maxLines=2`.
- Long transcript segments are split into multiple ASS subtitle events and timed by character count.
- Very short adjacent transcript segments are merged when the timing gap is small enough.
- Advanced API settings: `maxCharsPerLineShort`, `maxCharsPerLineNormal`, `maxLines`, `minSubtitleDuration`, `maxSubtitleDuration`, `minGapBetweenSubtitles`.
- Task 35 subtitle-only 58-minute smoke regenerated ASS files without re-rendering MP4 and reduced subtitle density warnings to normal `1`, short `0`.
- Backend and worker containers install `fonts-noto-cjk`; generated ASS files use `Noto Sans CJK JP` so Japanese subtitles do not render as missing-glyph boxes.

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
  --short-layout center_crop
```

The script writes representative short frames under:

```text
storage/outputs/{smoke_job_id}/audit_frames/
```

To create a new high-quality job first, pass `--video` instead of `--job-id`. This requires `OPENAI_API_KEY` and uses a small `--openai-candidate-limit` by default:

```powershell
python scripts/smoke_subtitle_burn_in.py `
  --video path\to\spoken_sample.mp4 `
  --docker-service worker `
  --mode high_quality `
  --openai-candidate-limit 5 `
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
- selection reason, quality warning, fallback, backfill, and OpenAI score source
- render failure counts
- high_quality selected clips using AI score, fallback, or no score

To run both modes and then compare:

```powershell
python scripts/e2e_compare_quality.py `
  --video path\to\spoken_30min_sample.mp4 `
  --normal-count 2 `
  --short-count 3 `
  --openai-candidate-limit 20 `
  --openai-finalist-scoring-limit 7
```

`e2e_compare_quality.py` runs a low_cost E2E first, then a high_quality E2E with limited OpenAI scoring, then writes the comparison reports. It requires `OPENAI_API_KEY` for the high_quality run. CI does not require an OpenAI key because tests use fixture JSON files.

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

OpenAI scoring failures:

- Set `OPENAI_API_KEY` in `.env` for OpenAI scoring.
- If OpenAI scoring fails, the worker falls back to rule scoring where possible.
