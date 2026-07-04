# AutoClipper Web v1 Release Smoke Checklist

This checklist is the minimum repeatable release smoke for v1. It does not tune
selection, scoring, rendering, or subtitle behavior.

## Scope

Run this before tagging or announcing a v1 release candidate.

Covered areas:

- Docker Compose runtime
- backend and frontend reachability
- low_cost real-video E2E
- optional high_quality OpenAI scoring smoke
- output audit report
- subtitle sidecar autoload risk
- results UI and download endpoints

Out of scope:

- manual trimming UI
- timeline editor
- approve/reject workflow
- scoring weight tuning
- crop/face-composition tuning

## Preconditions

- Docker Desktop is installed and running.
- The repo is checked out at the commit being validated.
- `.env` exists, or defaults from `.env.example` are acceptable.
- A short spoken MP4 is available for the required low_cost smoke.
- `OPENAI_API_KEY` is only required for the optional high_quality smoke.

Recommended sample:

- 1 to 3 minutes
- clear spoken audio
- MP4 container
- audible voice

Check disk space before long runs:

```powershell
Get-PSDrive -Name C
```

## 1. Start Runtime

```powershell
cd "C:\BOT\AutoClipper Web"
docker compose up -d --build
docker compose ps
```

Required services:

- backend
- frontend
- worker
- redis

## 2. Runtime Health

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-WebRequest http://localhost:3000 -UseBasicParsing
python .\scripts\smoke_runtime.py --skip-video
```

Expected:

- backend returns `{"status":"ok"}`
- frontend returns HTTP 200
- backend and worker share database and storage paths
- ffmpeg and ffprobe exist in backend and worker containers

## 3. Required low_cost Real-Video E2E

```powershell
python .\scripts\e2e_real_video.py `
  --video "C:\path\to\spoken_sample.mp4" `
  --mode low_cost `
  --normal-count 1 `
  --short-count 2 `
  --normal-min-duration 20 `
  --normal-max-duration 120 `
  --short-min-duration 20 `
  --short-max-duration 75 `
  --selection-policy fill_requested `
  --timeout 1800
```

Record the printed job id as `JOB_ID`.

Expected:

- job reaches `completed`
- render failures are `0`, or every failure has a clear reason
- at least one normal or short clip is produced when usable candidates exist
- shorts validate as `1080x1920`
- ZIP downloads successfully

## 4. Audit Outputs

```powershell
python .\scripts\audit_outputs.py `
  --job-id "JOB_ID" `
  --format both
```

Review:

- `storage/outputs/JOB_ID/audit/output_audit_report.md`
- `storage/outputs/JOB_ID/audit/output_audit_report.json`

Required checks:

- `missing_title = 0`
- `external_subtitle_autoload_risk = 0`
- no severe subtitle/title overlap regression
- boundary metadata is present when boundary refinement is enabled
- warnings are explainable if nonzero

## 5. Subtitle Sidecar Risk

```powershell
python .\scripts\check_subtitle_sidecar_risk.py `
  --job-id "JOB_ID" `
  --json
```

Expected:

- `risk_count = 0`

This covers the previous duplicate-subtitle failure where same-folder
same-basename `.ass` files were autoloaded by video players.

## 6. Results API and UI

Use the lightweight smoke helper:

```powershell
python .\scripts\v1_smoke_check.py --job-id "JOB_ID"
```

Manual API checks:

```powershell
$job = "JOB_ID"
$r = Invoke-RestMethod "http://localhost:8000/api/jobs/$job/results"
$r | ConvertTo-Json -Depth 8

$clips = @()
$clips += $r.normalClips
$clips += $r.shorts
$exportId = $clips[0].id

Invoke-RestMethod "http://localhost:8000/api/exports/$exportId/metadata" |
  ConvertTo-Json -Depth 8

Invoke-WebRequest "http://localhost:8000/api/exports/$exportId/subtitle" `
  -OutFile ".\tmp_subtitle_check.ass"

Invoke-WebRequest "http://localhost:8000/api/jobs/$job/download.zip" `
  -OutFile ".\tmp_job_download.zip"
```

Open:

```text
http://localhost:3000/results/JOB_ID
```

Expected in UI:

- clip title
- duration
- score
- title source
- AI/rule score source
- warning badges
- boundary refined status
- short overlay title status
- job-level audit summary when audit exists
- metadata and subtitle download links

## 7. Optional high_quality OpenAI Smoke

Run only when `OPENAI_API_KEY` is configured in `.env` and visible to the worker.

```powershell
python .\scripts\e2e_real_video.py `
  --video "C:\path\to\spoken_sample.mp4" `
  --mode high_quality `
  --use-openai-scoring true `
  --openai-candidate-limit 10 `
  --normal-count 1 `
  --short-count 2 `
  --normal-min-duration 20 `
  --normal-max-duration 120 `
  --selection-policy fill_requested `
  --timeout 3600
```

Expected:

- missing key fails clearly with `openai_configuration_missing`
- `openai_scoring_summary.json` is written when scoring runs
- selected clips use AI scores when API calls succeed
- fallback usage is reported when fallback is enabled
- low_cost behavior is unchanged

## 8. Known Previous Failure Modes Covered

- Docker Compose services not sharing DB/storage
- ffmpeg/ffprobe missing in processing containers
- no-speech videos failing too late
- unbounded candidate generation on long videos
- requested counts not filled because of overlap handling
- selected high_quality clips missing AI scores
- missing title metadata
- Japanese subtitle glyph or density regression
- same-basename subtitle sidecar causing duplicate subtitle display
- boundary metadata missing after refinement
- overlay title warning semantics mismatch
- results UI missing audit/metadata visibility

## Pass Criteria

The release smoke passes when:

- required low_cost real-video E2E completes
- backend `/health` returns ok
- frontend is reachable
- results UI opens for the new job
- metadata, subtitle, MP4, and ZIP downloads work
- `audit_outputs.py` runs
- `check_subtitle_sidecar_risk.py` reports `risk_count = 0`
- known warnings are documented and explainable
- CI passes

## STATUS.md Record Template

Add a task entry with:

- commit or branch under validation
- video used
- job id
- runtime
- normal/short counts
- render failures
- ZIP size
- audit warning counts
- sidecar risk count
- high_quality result if run
- unresolved items
