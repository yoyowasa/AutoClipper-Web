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
- verifies normal MP4 files have a valid duration close to the export metadata
- prints runtime metrics: upload, transcription, candidate generation, scoring, render, and total time
- prints pipeline metrics: transcript length, candidate counts, hard-gate pass count, selected counts, and backfilled count
- prints diagnostic summary JSON files when they exist

Expected outputs:

```text
storage/outputs/{job_id}/transcript_segments.json
storage/outputs/{job_id}/transcript_summary.json
storage/outputs/{job_id}/audio_feature_summary.json
storage/outputs/{job_id}/candidate_summary.json
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
- `quality gate rejection`: check `selected_clips.json` and `rejection_summary.json`; in `strict_quality` mode, low scores can intentionally leave selected outputs at zero.
- `render failure`: check `render_failures.json` and `docker compose logs worker`.
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
    "selectionPolicy": "fill_requested"
  }
}
```

Production-safe defaults remain:

- `normalMinDuration`: `90`
- `normalMaxDuration`: `600`
- `shortMinDuration`: `20`
- `shortMaxDuration`: `75`
- `selectionPolicy`: `fill_requested`

For development and E2E checks with shorter spoken videos, set `normalMinDuration` to `20` or `30` and keep `normalMaxDuration` at or below the input duration.

Selection policy:

- `fill_requested`: default. Hard gates still reject unusable candidates, but low `final_score` is used as ranking, not as a hard rejection. If the requested count is not filled by candidates above `minFinalScore`, the worker backfills from hard-gate-passing candidates and marks each selected clip with `below_quality_threshold=true`, `quality_warning=below_min_final_score`, and `selection_reason=backfill_below_quality_threshold`.
- `strict_quality`: preserves strict behavior. Candidates below `minFinalScore` are rejected, so a job may complete analysis with zero selected outputs.

## Generation Diagnostics

Each completed or expected-failure job writes compact summary files under:

```text
storage/outputs/{job_id}/
```

Summary files:

- `transcript_summary.json`: transcript segment count, text length, speech duration, confidence, first segments, engine, fixture flag.
- `audio_feature_summary.json`: duration, silence ratio, speech density, volume peak, silent seconds, speech seconds.
- `candidate_summary.json`: total/normal/short candidate counts, transcript text coverage, hard gate counts, backfill counts, duration stats, rule/final score stats, score percentiles, top selected candidates, top rejected candidates by reason.
- `rejection_summary.json`: quality gate rejection counts and render failure counts.
- `selected_clips_summary.json`: selected normal/short counts, selected IDs, durations, scores, quality warnings, selection reasons, output paths.

The E2E scripts print these summaries:

```powershell
python scripts/e2e_sample_video.py
python scripts/e2e_real_video.py --video path\to\spoken_sample.mp4
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
