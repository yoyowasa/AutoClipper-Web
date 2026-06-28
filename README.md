# AutoClipper Web

AutoClipper Web is a full-auto video clipping web app scaffold.

This repository currently contains only the Task 01 foundation:

- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: FastAPI
- Queue dependency: Redis service in Docker Compose
- Storage directories for uploads, temporary files, and outputs

Real video processing is intentionally not implemented yet.

## Requirements

- Docker Desktop
- Docker Compose v2

## Local Setup

Copy the example environment file if you want local overrides:

```powershell
Copy-Item .env.example .env
```

Start all services:

```powershell
docker compose up --build
```

Open the frontend:

```text
http://localhost:3000
```

Check the backend health endpoint:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

The API health endpoint is also available at:

```text
http://localhost:8000/api/health
```

## Services

- `frontend`: Next.js app on port `3000`
- `backend`: FastAPI app on port `8000`
- `worker`: RQ worker for dummy AutoClipper jobs
- `redis`: Redis on port `6379`

## Repository Layout

```text
.
├── frontend/
│   └── Next.js app
├── backend/
│   └── FastAPI app
├── storage/
│   ├── uploads/
│   ├── temp/
│   └── outputs/
├── docker-compose.yml
├── .env.example
├── AGENTS.md
└── STATUS.md
```

## Development Notes

- Do not run video processing inside HTTP requests.
- Do not hardcode storage paths outside backend configuration or storage modules added later.
- Keep v1 scope focused on upload, background job flow, generated clips, subtitles, and ZIP export.
- Manual editing, authentication, billing, and social posting are out of scope for v1.

## CI

GitHub Actions workflow: `.github/workflows/ci.yml`

Backend checks:

```powershell
cd backend
python -m pip install -e ".[dev]"
ruff check .
pytest
```

Frontend checks:

```powershell
npm ci
npm --workspace frontend run lint
npm --workspace frontend run typecheck
npm --workspace frontend run build
```

CI runs on pull requests and pushes to `main`.
