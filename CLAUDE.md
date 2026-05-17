# CLAUDE.md

Guidance for Claude Code when working in this repo.

## What this is

Online XSD/XML Viewer — FastAPI backend + React SPA, deployed as a single
Docker container. Upload an XSD, get a tree/diagram/text view.

For a deep dive on how the pieces fit together, read
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** first.

## Repo layout (cheatsheet)

- `backend/app/` — FastAPI app; parser lives in `app/parser/xsd_parser.py`,
  Pydantic models in `app/parser/model.py`.
- `frontend/src/` — React + Vite SPA; Zustand store in
  `stores/selectionStore.ts` is the single source of truth for views.
- `e2e/tests/` — Playwright golden-path test.
- `Dockerfile`, `docker-compose.yml`, `deploy/` — single-container deployment.

## Running locally

```bash
# Backend
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend && npm ci && npm run dev
# Vite dev-server proxies /api to the backend.
```

## Tests

- Backend: `cd backend && pytest` (also `ruff check`).
- Frontend: `cd frontend && npm run test` (Vitest) and `npm run build` for
  the TS typecheck via `tsc --noEmit`.
- E2E: `cd e2e && npm ci && npx playwright test` — requires both backend and
  the built frontend to be running.

## Deployment (read before redeploying)

There are **two independent containers** — don't confuse them:

- **Local sandbox** — `docker compose up -d --build` builds
  `online-xsd-viewer:latest` and runs a container on `127.0.0.1:8090`.
  For local testing only; **not** what the public site serves.
- **Public site** (`https://viewer.status20.net/`) — Apache reverse-proxies
  to `127.0.0.1:8180`, served by the container named `online-xsd-viewer`
  from image tag `online-xsd-viewer:test`, started via
  `deploy/run-container.sh` (see `deploy/viewer-status20-le-ssl.conf`).

To deploy a code change to the **public site**:

```bash
docker compose build                              # or: docker build -t online-xsd-viewer:latest .
docker tag online-xsd-viewer:latest online-xsd-viewer:test
bash deploy/run-container.sh                       # recreates the :8180 container
```

After deploying, hard-reload the browser (Ctrl+F5) — the SPA JS bundle is
cached and a soft reload can keep showing the old UI.

## Conventions worth knowing

- **ID scheme**: all declarations are `"{kind}:{qname-or-path}"` — see the
  ID-scheme section in `docs/ARCHITECTURE.md`. The same id flows through the
  API, Zustand index, URL hash, and React Flow node ids.
- **Model contract**: `SchemaModel` is mirrored by hand between
  `backend/app/parser/model.py` and `frontend/src/types/schema.ts`. Keep them
  in sync when changing shapes.
- **Parser choice**: we use lxml, not `xmlschema`, because we need to preserve
  annotations, appinfo, comments, and source line numbers.
- **Default tab is `diagram`** (`selectionStore.ts`), enforced by the e2e
  golden-path test.
