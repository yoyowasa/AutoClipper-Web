# Breath-Cut Deliverable Script

`scripts/create_breath_cut_deliverable.py` is an optional helper for completed
AutoClipper jobs. It is not part of the default upload, worker, render, or
results pipeline.

The script reads existing job artifacts:

- `storage/outputs/{job_id}/video_metadata.json`
- `storage/outputs/{job_id}/transcript_segments.json`
- `storage/outputs/{job_id}/silence_segments.json`

It writes a separate deliverable folder:

- `storage/outputs/{job_id}/breath_cut/breath_cut_plan.json`
- `storage/outputs/{job_id}/breath_cut/filter_complex.txt`
- `storage/outputs/{job_id}/breath_cut/short_01_breath_cut.ass`
- optional rendered MP4 output

## Dry Run

Use dry-run first to inspect the planned cuts without rendering:

```powershell
python .\scripts\create_breath_cut_deliverable.py `
  --job-id "job_x" `
  --dry-run
```

## Render

Rendering uses the Docker Compose `worker` service by default. Pass the input
MP4 path as it appears inside the container:

```powershell
python .\scripts\create_breath_cut_deliverable.py `
  --job-id "job_x" `
  --source-container-path "/app/storage/outputs/job_x/shorts/short_01.mp4" `
  --output-name "short_01_breath_cut.mp4"
```

## Optional Controls

- `--min-cut-silence`: minimum silence duration to remove.
- `--keep-silence`: silence seconds to keep around each cut.
- `--speech-margin`: safety margin around transcript segment edges.
- `--protect-interval start:end`: source timeline interval to keep uncut.
- `--soft-cut-interval start:end:keep_seconds`: shorten a protected or special interval.
- `--font-file`: optional local font file copied into `storage/fonts`.

Font binaries, client media, and generated outputs must not be committed.

## Scope

This helper is for local deliverable preparation. It does not change candidate
selection, scoring, subtitle generation, short composition, API behavior, or the
frontend results flow.
