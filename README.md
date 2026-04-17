# Online XSD/XML Viewer

A self-hosted, read-only web viewer for XSD schemas with a UI modelled after XMLSpy and Oxygen. Runs as a single Docker container.

## Features (MVP — XSD)

- **Three synchronized views** — Tree, Diagram (XMLSpy-style), and Text (syntax-highlighted XML).
- **Full XSD information** — elements, attributes, simple/complex types, facets, restrictions, `xs:annotation` / `xs:documentation`, `xs:appinfo`, XML comments, source file and line numbers.
- **Multi-file schemas** — upload a ZIP containing the main XSD plus its `xs:import` / `xs:include` / `xs:redefine` targets.
- **URL loading** — fetch XSD (and its references) over HTTP, with an explicit host allowlist.
- **Navigation** — full-text search (⌘/Ctrl-K), type filter, breadcrumb, *Find Usages*, URL deep-links.
- **Export** — diagram as PNG/SVG, complete schema as HTML documentation, pretty-printed XML.
- **Responsive** — Desktop, Tablet, and Mobile-friendly layouts.
- **Themes** — Light / Dark with `prefers-color-scheme` detection.
- **Handles large schemas** — up to ~50 MB with virtual scrolling and lazy diagram rendering.

XML viewing with optional schema validation is planned for Phase 2.

## Quick start

```bash
docker run --rm -p 8080:8080 ghcr.io/karlkauc/online-xsd-viewer:latest
```

Open http://localhost:8080 and drop an XSD file into the browser.

### With URL fetching enabled

```bash
docker run --rm -p 8080:8080 \
  -e ALLOWED_SCHEMA_HOSTS='^https://schemas\.example\.com/' \
  ghcr.io/karlkauc/online-xsd-viewer:latest
```

### docker-compose

```bash
docker compose up
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | HTTP listen port |
| `MAX_UPLOAD_MB` | `50` | Maximum upload size in MB |
| `ALLOWED_SCHEMA_HOSTS` | *(empty)* | Regex (or comma-separated regex list) of host names permitted for URL fetching |
| `SCHEMA_CACHE_TTL_MIN` | `60` | In-memory parse-cache TTL in minutes |
| `SCHEMA_CACHE_MAX_ENTRIES` | `32` | Max. number of cached parsed schemas |
| `LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

## Security

Every parse happens with hardened lxml settings:

- External entity resolution disabled (XXE protection)
- DTD loading disabled, `no_network=True` at parse time
- Billion-Laughs / XML-bomb rejection
- URL fetching restricted to hosts matching `ALLOWED_SCHEMA_HOSTS`, with private-IP-block protection, per-fetch timeout and response-size cap

No uploads are persisted to disk; parsed schemas live in an in-memory cache with TTL.

This tool does **not** provide authentication. Put a reverse proxy (`oauth2-proxy`, nginx Basic Auth, etc.) in front of it when exposing beyond a trusted network.

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
npm run dev

# E2E
cd e2e
npm install
npx playwright install
npm test
```

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

## License

MIT — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
