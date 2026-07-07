# Insert-Image Deliverable Script

`scripts/create_insert_image_deliverable.py` is an optional helper for completed
AutoClipper jobs. It is not part of the default upload, worker, render, or
results pipeline.

The script overlays local still images onto an existing rendered clip before
burning the provided ASS subtitle file. It is intended for local preview or
deliverable preparation after a job has already completed.

## Inputs

- completed job id
- source MP4 path inside the Docker worker container
- base `filter_complex.txt` from an existing render or breath-cut helper
- ASS subtitle file
- one or more local image files

Local image files are copied into:

```text
storage/outputs/{job_id}/{output_subdir}/assets/
```

Generated helper artifacts are written into:

```text
storage/outputs/{job_id}/{output_subdir}/
```

## Dry Run

Use dry-run first to copy assets and inspect the generated filter/manifest
without rendering:

```powershell
python .\scripts\create_insert_image_deliverable.py `
  --job-id "job_x" `
  --base-filter ".\storage\outputs\job_x\breath_cut\filter_complex.txt" `
  --subtitle ".\storage\outputs\job_x\breath_cut\short_01_breath_cut.ass" `
  --image ".\local_image.png" "insert_01.png" 0.95 3.02 "opening" `
  --dry-run
```

## Render

Rendering uses the Docker Compose `worker` service by default:

```powershell
python .\scripts\create_insert_image_deliverable.py `
  --job-id "job_x" `
  --source-container-path "/app/storage/outputs/job_x/breath_cut/short_01_breath_cut.mp4" `
  --base-filter ".\storage\outputs\job_x\breath_cut\filter_complex.txt" `
  --subtitle ".\storage\outputs\job_x\breath_cut\short_01_breath_cut.ass" `
  --image ".\local_image.png" "insert_01.png" 0.95 3.02 "opening"
```

If `--duration` is omitted, the script probes the source video before rendering.

## Scope

This helper does not change candidate selection, scoring, subtitle generation,
short composition, API behavior, or the frontend results flow.

Client media, generated outputs, and font binaries must not be committed.
