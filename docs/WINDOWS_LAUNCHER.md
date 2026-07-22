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

## Distribution Acceptance

Task 70 validated the `v1.2.0-rc.2` tag ZIP as the v1.2.0 distribution candidate.

Clean CPU Windows acceptance passed:

- the launcher GUI started from an extracted tag ZIP outside the development checkout
- Python 3.11.9 and all 24 launcher tests passed
- the first Docker build started backend, frontend, worker, and Redis
- `/health`, `/upload`, normal output, short output, and ZIP download passed
- Stop, Windows restart, and Start passed
- SQLite, outputs, and the Whisper model cache were preserved
- no NVIDIA GPU was available, so the CPU-compatible profile was used

The development Windows 11 system separately passed the NVIDIA runtime path with an RTX 5070 Ti:

- recommended profile selected `turbo / ja / cuda / float16`
- worker verification returned `actual_device=cuda`, `actual_compute_type=float16`, and `fallback=false`
- GPU and CPU profile switching, service health, Stop/Start, and data preservation passed

A first-run test combining a clean Windows installation and NVIDIA GPU was not performed.
The release accepts this as a documented limitation because the clean distribution/CPU path and
the actual NVIDIA runtime path passed independently. Docker Desktop must be started manually after
Windows restart; the launcher detects and explains a stopped Docker daemon.

Installer packaging, bundled Python, Docker Desktop installation, and automatic updates remain out
of scope for v1.2.0.
