# Technical reference

Operator-facing notes for self-hosting, configuring, securing, and developing
the Online XSD Viewer. For a feature tour, see the
[README](../README.md). For the deeper code-level walk-through, see
[ARCHITECTURE.md](ARCHITECTURE.md).

## Self-hosting

Run the latest published image:

```bash
docker run --rm -p 8080:8080 ghcr.io/karlkauc/online-xsd-viewer:latest
```

Open <http://localhost:8080> and drop an XSD file into the browser.

### docker-compose

```bash
docker compose up
```

The bundled `docker-compose.yml` builds `online-xsd-viewer:latest` and binds
it to `127.0.0.1:8091` — intended as a local sandbox, not for public exposure.

### Google Cloud Run

A step-by-step guide for deploying this container to Cloud Run (build,
sizing, env vars, smoke test, rollback) lives in
[DEPLOY_GCLOUD.md](DEPLOY_GCLOUD.md).

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | HTTP listen port |
| `MAX_UPLOAD_MB` | `50` | Maximum upload size in MB |
| `ALLOWED_SCHEMA_HOSTS` | *(empty)* | Empty = any public host allowed. Set to a regex (or comma-separated list of regexes) to lock URL fetching down to a whitelist. |
| `SCHEMA_CACHE_TTL_MIN` | `60` | In-memory parse-cache TTL in minutes |
| `SCHEMA_CACHE_MAX_ENTRIES` | `32` | Max. number of cached parsed schemas |
| `LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

### Locking URL fetching down to specific hosts

By default the `/api/schema/url` endpoint accepts any public http(s) URL —
private/loopback IPs and non-http schemes are always blocked. To restrict it
to a whitelist for hardened deployments, set `ALLOWED_SCHEMA_HOSTS` to one or
more host regexes:

```bash
docker run --rm -p 8080:8080 \
  -e ALLOWED_SCHEMA_HOSTS='^schemas\.example\.com$' \
  ghcr.io/karlkauc/online-xsd-viewer:latest
```

## Security

Every parse happens with hardened lxml settings:

- External entity resolution disabled (XXE protection)
- DTD loading disabled, `no_network=True` at parse time
- Billion-Laughs / XML-bomb rejection
- URL fetching limited to `http(s)` only, with DNS-based private-IP-block
  protection (loopback, link-local, ULA, cloud metadata, etc.), per-fetch
  timeout, redirect cap and response-size cap. An optional
  `ALLOWED_SCHEMA_HOSTS` whitelist can lock the endpoint down further for
  hardened deployments.

No uploads are persisted to disk; parsed schemas live in an in-memory cache
with TTL. The viewer does **not** provide authentication — put a reverse
proxy (`oauth2-proxy`, nginx Basic Auth, etc.) in front of it when exposing
beyond a trusted network.

## Architecture

```
┌─────────────────────────────────────────┐
│ Browser (React SPA)                     │
│   Tree | Diagram | Text   (shared sel.) │
└────────────────┬────────────────────────┘
                 │ REST + JSON
┌────────────────▼────────────────────────┐
│ FastAPI (Python 3.12)                   │
│   POST /api/schema   (upload/url/text)  │
│   GET  /api/schema/:id                  │
│   POST /api/schema/:id/export/*         │
│   XSD Parser (lxml, hardened)           │
│   In-memory LRU+TTL cache               │
└─────────────────────────────────────────┘
```

For the full breakdown of the parser, model, and store, see
[ARCHITECTURE.md](ARCHITECTURE.md).

## Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev   # Vite dev server proxies /api to the backend

# E2E
cd e2e
npm install
npx playwright install
npm test
```

### Recording the README demo GIFs

The README's animated demos are produced by `scripts/record_demo.mjs`, which
drives the local sandbox via Playwright and writes WebM recordings to
`docs/media/_raw/`. Convert them to GIF with ffmpeg:

```bash
# Bring the sandbox up
docker compose up -d --build

# Record both scenes
node scripts/record_demo.mjs overview
node scripts/record_demo.mjs fundsxml

# Convert (run once per scene)
cd docs/media/_raw
ffmpeg -y -i overview.webm -vf "fps=10,scale=900:-1:flags=lanczos,palettegen=stats_mode=diff" overview.palette.png
ffmpeg -y -i overview.webm -i overview.palette.png \
  -lavfi "fps=10,scale=900:-1:flags=lanczos[v];[v][1:v]paletteuse=dither=none:diff_mode=rectangle" \
  ../overview.gif
```

## License

MIT — see [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
