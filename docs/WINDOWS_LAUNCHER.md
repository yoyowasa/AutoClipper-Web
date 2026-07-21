# AutoClipper Windows Launcher

The Windows launcher is a GUI wrapper around the existing Docker Compose runtime.
It does not replace the Next.js frontend, FastAPI backend, RQ worker, Redis, or FFmpeg pipeline.

## Requirements

- Windows 10 or 11
- Docker Desktop with Docker Compose
- Python 3.11 or later for the launcher MVP

Future packaging work may bundle the launcher so a separate Python installation is not required.

## Start

Double-click:

```text
Start AutoClipper.cmd
```

Then select `推奨設定で起動`. The launcher:

1. Checks Docker CLI, Docker daemon, Docker Compose, `.env`, ports, disk space, and NVIDIA GPU support.
2. Selects the GPU profile when the host GPU, Docker NVIDIA runtime, and GPU Compose override are available.
3. Starts the selected Compose profile and verifies the actual worker runtime.
4. Waits for backend `/health`, frontend `/upload`, worker, and Redis.
5. Opens `http://localhost:3000/upload` with the matching transcription settings selected.

Profiles:

```text
GPU recommended: turbo / ja / cuda / float16
CPU compatible:  base / auto / cpu / auto
```

In automatic mode, failed GPU host/runtime preflight selects CPU and displays the reason.
If GPU is selected explicitly, failed preflight stops startup and never falls back silently.

Use `Rebuild and Start` only after code or container dependencies change. It runs:

```powershell
docker compose up -d --build
```

## Buttons

- `推奨設定で起動`: auto-select the verified GPU profile, or use CPU with a visible reason.
- `CPU互換設定で起動`: start the CPU-compatible profile explicitly.
- `GPU必須で起動`: require the GPU profile and stop when CUDA verification fails.
- `再ビルドして起動`: rebuild images, then start the recommended profile.
- `Open App`: open the upload page.
- `Open Outputs`: open `storage/outputs`.
- `Open Uploads`: open `storage/uploads`.
- `Docker Logs`: show recent Compose logs.
- `Launcher Log`: show the local launcher log.
- `Refresh`: refresh service and health state.
- `Stop Services`: run `docker compose stop`.

`Stop Services` preserves SQLite, Redis volume data, uploads, and outputs. The launcher does not expose `docker compose down -v` or automatic reset.

## High-quality Mode

The launcher only shows whether `OPENAI_API_KEY` is configured. It checks `.env`
and the launcher process environment, but never displays or logs the key value.
When the key is missing, low-cost mode remains available. Configure the key in
`.env` or the process environment before using OpenAI-backed features.

## Errors

- `Docker CLIが見つかりません`: install Docker Desktop and restart Windows Terminal.
- `Docker daemonへ接続できません`: start Docker Desktop and wait until it reports that the engine is running.
- `GPU必須profileの起動前確認に失敗`: verify the NVIDIA driver, WSL2 GPU support, Docker NVIDIA runtime, and `docker-compose.gpu.yml`; use CPU-compatible start if GPU is not required.
- `GPU workerのCUDA確認に失敗`: inspect Docker logs. Automatic recommended start may use CPU and shows the fallback reason; explicit GPU start remains stopped.
- `port 3000/6379/8000`: stop the conflicting process, then refresh.
- `起動待機がtimeout`: open Docker logs and inspect backend, frontend, worker, and Redis.
- low disk warning: remove old ignored files under `storage/uploads` or `storage/outputs` after confirming they are no longer needed.

Project paths containing spaces are supported because commands use an explicit working directory and argument list rather than a shell command string.

## Current Validation Boundary

Task 69 was validated on the development Windows 11 machine with an NVIDIA GeForce RTX 5070 Ti. GPU and CPU profile switching, CUDA FP16 verification, Stop/Start, service health, and SQLite/output preservation passed. A clean second Windows installation, first-time image/model downloads, Japanese paths, and restart-after-PC-reboot remain Task 70 distribution acceptance checks.
