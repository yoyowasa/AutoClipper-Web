# AutoClipper Windows Launcher

日本語の初回導入手順: [Windows導入・起動手順](WINDOWS_SETUP_JA.md)

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

The desktop entrypoint automatically uses the recommended profile. The launcher:

1. Checks the Docker CLI and current daemon state.
2. Starts an installed Docker Desktop when needed and waits up to 180 seconds for `docker info`.
3. Checks Docker Compose, `.env`, ports, disk space, and NVIDIA GPU support.
4. Selects the GPU profile when the host GPU, Docker NVIDIA runtime, and GPU Compose override are available.
5. Starts the selected Compose profile and verifies the actual worker runtime.
6. Waits for backend `/health`, frontend `/upload`, worker, and Redis.
7. Opens `http://localhost:3000/upload` with the matching transcription settings selected.

Profiles:

```text
GPU recommended: turbo / ja / cuda / float16
CPU compatible:  base / ja / cpu / auto
```

In automatic mode, failed GPU host/runtime preflight selects CPU and displays the reason.
If GPU is selected explicitly, failed preflight stops startup and never falls back silently.

Use `Rebuild and Start` only after code or container dependencies change. It runs:

```powershell
docker compose up -d --build
```

## Buttons

- `推奨設定で起動`: retry automatic startup and select the verified GPU profile, or use CPU with a visible reason.
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

High-quality rendering uses local processing and the host login bridge.
The launcher has no paid API configuration display. Log redaction for historical secrets is retained.

The bridge engine is `codex` (default, Codex CLI with ChatGPT login) or `claude` (Claude Code CLI with a Claude subscription login).
Choose it on the top screen under 「AIの設定」 (task-256): engine, model and reasoning effort for each lane,
「通常の作業」 (selection, titles/hooks, framing, final review) and 「自己分析」. The screen saves
`storage/codex_bridge/engine.json`; the bridge re-reads it before every request, so a change applies to the next request
without a restart and a request already running keeps its engine. The status file reports what each lane uses
(`engine`/`model`/`reasoningEffort` and `analysisEngine`/`analysisModel`/`analysisReasoningEffort`) and the choices.
- Choices: Codex models listed in the Codex CLI's own model cache (`CODEX_HOME/models_cache.json`, ids and efforts only;
  `gpt-6.1-sol` when it cannot be read), Claude `claude-opus-5-5` / `claude-sonnet-5-5` / `claude-haiku-5-5` /
  `claude-fable-5-2` with efforts `low`〜`max`. A value outside the choices falls back to the engine default
  (`gpt-6.1-sol` / `claude-opus-5-5`, `medium`); the screen rejects it. Requests cannot choose a model.
- The older file form `{"engine": "claude"}` / `{"engine": "codex", "analysisEngine": "claude"}` keeps working (without
  `analysisEngine` the analysis lane uses the bridge engine). `AUTOCLIPPER_BRIDGE_ENGINE` still overrides the engine of
  the normal lane (and of the analysis lane when none is saved); the screen then shows 「反映待ち」.
- Both engines in use at start must be installed and logged in. An engine switched to later is checked before its
  first request (a success is reused for ten minutes); without the CLI or subscription login the request fails with
  `claude_cli_missing` / `claude_login_missing` / `codex_cli_missing` / `codex_login_missing` instead of running.
- The launcher no longer restarts the bridge for an engine change; it still restarts a bridge whose build differs
  (bridge, Claude engine and engine-settings modules are part of the build fingerprint). Without the launcher, stop the
  bridge and start `python launcher/codex_bridge.py serve --project-root <root>` again after a code update.

- Claude engine: the chosen model and effort (default `claude-opus-5-5`, `medium`), all built-in tools disabled (`--tools ""`), `--safe-mode`, no MCP. Only the structured-output tool may appear.
- The child process never receives `ANTHROPIC_*`, Bedrock/Vertex or cloud credentials. A run that reports an API key source, uses any other tool, or returns no structured output fails without output.
- A thread created by the other engine is not resumed; the request starts a new session. Self-analysis runs without session persistence.
- Rate-limit rejection is reported as `claude_rate_limited`. Engines are not switched automatically.

## Errors

- `Docker CLIが見つかりません`: install Docker Desktop and restart Windows Terminal.
- `Docker Desktopを自動起動できませんでした`: verify that Docker Desktop is installed. The launcher never installs or resets Docker Desktop.
- `Docker daemonの準備がtimeout`: check Docker Desktop for an agreement prompt, WSL update, or Windows restart request.
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
the actual NVIDIA runtime path passed independently. The desktop entrypoint now starts Docker
Desktop automatically after Windows restart when the daemon is stopped.

Installer packaging, bundled Python, Docker Desktop installation, and automatic updates remain out
of scope. Docker Desktop must already be installed.
