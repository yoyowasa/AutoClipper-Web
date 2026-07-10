# AutoClipper Windows Launcher

The Task57 launcher is a Windows GUI wrapper around the existing Docker Compose runtime.
It does not replace the Next.js frontend, FastAPI backend, RQ worker, Redis, or FFmpeg pipeline.

## Requirements

- Windows 10 or 11
- Docker Desktop with Docker Compose
- Python 3.11 or later for the launcher MVP

Task58 may package the launcher so a separate Python installation is not required.

## Start

Double-click:

```text
Start AutoClipper.cmd
```

Then select `Start AutoClipper`. The launcher:

1. Checks Docker CLI, Docker daemon, Docker Compose, `.env`, ports, and disk space.
2. Runs `docker compose up -d` from the repository root.
3. Waits for backend `/health`, frontend `/upload`, worker, and Redis.
4. Opens `http://localhost:3000/upload` after the runtime is ready.

Use `Rebuild and Start` only after code or container dependencies change. It runs:

```powershell
docker compose up -d --build
```

## Buttons

- `Start AutoClipper`: normal start without rebuilding images.
- `Rebuild and Start`: rebuild images, then start.
- `Open App`: open the upload page.
- `Open Outputs`: open `storage/outputs`.
- `Open Uploads`: open `storage/uploads`.
- `Docker Logs`: show recent Compose logs.
- `Launcher Log`: show the local launcher log.
- `Refresh`: refresh service and health state.
- `Stop Services`: run `docker compose stop`.

`Stop Services` preserves SQLite, Redis volume data, uploads, and outputs. The launcher does not expose `docker compose down -v` or automatic reset.

## High-quality Mode

The launcher only shows whether `OPENAI_API_KEY` is configured. It never displays or logs the key value.
When the key is missing, low-cost mode remains available. Configure the key in `.env` before using OpenAI-backed high-quality scoring.

## Errors

- `Docker CLIが見つかりません`: install Docker Desktop and restart Windows Terminal.
- `Docker daemonへ接続できません`: start Docker Desktop and wait until it reports that the engine is running.
- `port 3000/6379/8000`: stop the conflicting process, then refresh.
- `起動待機がtimeout`: open Docker logs and inspect backend, frontend, worker, and Redis.
- low disk warning: remove old ignored files under `storage/uploads` or `storage/outputs` after confirming they are no longer needed.

Project paths containing spaces are supported because commands use an explicit working directory and argument list rather than a shell command string.
