# Architecture

Online XSD/XML Viewer — a self-hosted web app that parses uploaded XSD schemas
and renders them as an interactive tree, diagram, and annotated source view.
Single-binary deployment: one FastAPI process serves the API and the built
React SPA.

## High-level shape

```
┌──────────────┐       HTTPS         ┌─────────────────────────────────────┐
│   Browser    │ ──────────────────▶ │     FastAPI (uvicorn, port 8080)    │
│ (React SPA)  │                     │                                     │
│              │ ◀────────────────── │  /api/schema/*      /api/export/*   │
└──────────────┘    SchemaModel JSON │  /api/health        /assets/* , /   │
                                     │                                     │
                                     │  ┌───────────────┐  ┌─────────────┐ │
                                     │  │  XsdParser    │  │  LRU+TTL    │ │
                                     │  │  (lxml walk)  │─▶│  cache      │ │
                                     │  └───────────────┘  └─────────────┘ │
                                     └─────────────────────────────────────┘
```

A single `SchemaModel` (Pydantic on the server, mirrored TypeScript on the
client) is the central data contract. The frontend never re-parses XSD — it
receives a pre-indexed, normalized model and renders it.

## Tech stack

| Layer    | Choice                                                   |
| -------- | -------------------------------------------------------- |
| Backend  | Python 3.12, FastAPI, uvicorn, Pydantic v2, **lxml**     |
| Frontend | React 18, TypeScript, Vite, Zustand, Tailwind            |
| Diagram  | `@xyflow/react` (React Flow)                             |
| Text     | `@uiw/react-codemirror` + `@codemirror/lang-xml`         |
| Tree     | `react-virtuoso` (virtualized, handles large schemas)    |
| Tests    | pytest + ruff · Vitest + jsdom · Playwright (e2e)        |
| Build    | Multi-stage Dockerfile, docker-compose, GHCR via GH Actions |

We intentionally use **lxml**, not `xmlschema`: we walk the tree ourselves to
preserve authoring metadata (annotations, appinfo, comments, source lines) that
xmlschema drops.

## Repo layout

```
backend/               FastAPI app + parser
  app/
    main.py            app init, middleware, SPA fallback, CSP headers
    config.py          Settings from env
    cache.py           Thread-safe LRU+TTL schema cache
    api/
      schema.py        Upload / URL / text / cached endpoints
      export.py        HTML snapshot export
    usage/             Optional anonymous usage statistics (docs/USAGE_STATS.md)
      events.py        Pure event builders: visitor hash, device, referrer, names
      recorder.py      Async queue + psycopg writer; inert without USAGE_DB_URL
      geoip.py         GeoLite2-Country lookup (downloaded at startup)
      context.py       Per-request ContextVar + `emit()` used by routers
    parser/
      xsd_parser.py    The lxml walker — the big one (~950 LOC)
      model.py         Pydantic models (SchemaModel et al.)
      security.py      SSRF guards for URL fetches
  tests/               pytest

frontend/              React SPA
  src/
    main.tsx           Vite entry
    App.tsx            Tab shell + deep-link hash sync
    api/client.ts      fetch wrappers for /api/schema/*
    stores/
      selectionStore.ts  Zustand: model, indexes, selection, tab, expand state
    lib/
      indexSchema.ts     Walks model → indexById + usagesByTarget
      expandAll.ts       Collects expandable element ids for the diagram
      deepLink.ts        URL-hash <-> selectedId
    components/
      Uploader.tsx       Drag-drop / file picker / URL entry
      TreeView/          Virtualized tree, per-kind filters
      DiagramView/       React Flow canvas, ElementNode, CompositorNode
      TextView/          CodeMirror, jumps to selected line
      DetailPanel.tsx    Selected node metadata, facets, usages
      SearchPalette.tsx  Ctrl/Cmd-K fuzzy search
      Diagnostics.tsx    Parse warnings/errors
      FeedbackDialog.tsx Modal feedback form → POST /api/feedback
      AboutDialog.tsx    Modal with version (GET /api/health), GitHub,
                         xml-viewer.online and license links
      UploadError.tsx    Classified upload errors + hints (lib/uploadErrors.ts)
    types/schema.ts    TypeScript mirror of SchemaModel
  tests/               Vitest

e2e/                   Playwright — golden-path.spec.ts
deploy/                Apache vhost + container wrapper
Dockerfile             Two-stage: node build → python runtime
docker-compose.yml     Single service
.github/workflows/     CI: backend, frontend, e2e, docker
```

## Backend

### Entrypoint & middleware

`backend/app/main.py` builds the FastAPI app, wires CORS, a request-id/logging
middleware, and mounts two routers under `/api`. In production, `main.py` also
mounts the built frontend at `/assets/*` (`app/spa.py`). The SPA fallback
returns `index.html` with a hardened `Content-Security-Policy`
(`default-src 'self'`, no inline scripts) **only for known client routes**
(`SPA_ROUTES`, mirrored from `frontend/src/lib/modeRoute.ts` — add new
client paths in both places). Any other path gets a plain 404, so scanner
probes like `/wp-login.php` neither see a 200 nor count as page views. In dev, Vite serves the SPA on a
separate port and proxies `/api` through.

The same middleware binds a per-request usage context (client IP, user agent,
referrer) that routers turn into `usage_event` rows via `app.usage.context.emit()`
— see [USAGE_STATS.md](USAGE_STATS.md). The recorder starts/stops in the app
lifespan and is a no-op unless `USAGE_DB_URL` is set, so tests and local dev
never touch a database. `POST /api/feedback` (`app/api/feedback.py`) writes
user feedback synchronously into the same database via `app.usage.feedback`
and answers 503 when it is not configured.

Parse failures reach the client as a plain-text `detail`; `app/parser/errors.py`
makes those messages human ("root element is `<games>`, not `<xs:schema>`",
"not an XML file"), and the frontend's `lib/uploadErrors.ts` classifies them
to show a matching hint (`components/UploadError.tsx`) — e.g. a link to the
sister project xml-viewer.online for XML documents. That link
(`XML_VIEWER_URL` in `lib/uploadErrors.ts`) is also in the header and the
About dialog; the GitHub repo URL lives in `components/AboutDialog.tsx`
(`GITHUB_REPO_URL`).

Modal dialogs (search palette, feedback, about) are mounted once in `App.tsx`
and opened from anywhere via window events (`xsdv:open-search`,
`xsdv:open-feedback`, `xsdv:open-about`) — helpers `openFeedback()` and
`openAbout()` wrap the dispatch.

### Endpoints

| Method | Path                                            | Purpose                              |
| ------ | ----------------------------------------------- | ------------------------------------ |
| POST   | `/api/schema/upload`                            | Upload `.xsd` or `.zip`              |
| POST   | `/api/schema/text`                              | Paste raw XSD text                   |
| POST   | `/api/schema/url`                               | Fetch XSD from URL (SSRF-guarded)    |
| GET    | `/api/schema/{schema_id}`                       | Retrieve cached schema               |
| POST   | `/api/schema/{schema_id}/export/html`           | Standalone HTML export               |
| GET    | `/api/schema/{schema_id}/file/{file_id}/formatted` | Syntax-highlighted source         |
| GET    | `/api/health`                                   | Liveness (used by Docker healthcheck)|
| GET    | `/api/docs`                                     | Auto-generated OpenAPI UI            |

All ingest endpoints share one pipeline in `backend/app/api/schema.py`: read
bytes (size-capped), call `parse_with_url_fallback(...)`, hash the serialized
model to produce a 32-char `schema_id`, stash the model in the cache, and
return `SchemaResponse { schema_id, model }`.

### Parser (`backend/app/parser/xsd_parser.py`)

The parser loads the root XSD with lxml, then discovers and resolves
`<xs:import>`, `<xs:include>`, `<xs:redefine>`, and `<xs:override>` references
through a chain of `SchemaResolver`s:

- `ZipResolver` — reads sibling files from an uploaded zip.
- `UrlResolver` — fetches remote files via the SSRF-hardened path in
  `parser/security.py` (only `http(s)`, no localhost, no link-local, no
  private ranges, redirect cap, size cap, timeout). Hosts are allowed by
  default; setting `ALLOWED_SCHEMA_HOSTS` switches to a strict whitelist.
- `ChainedResolver` — tries resolvers in order and records diagnostics on miss.

The tree walk produces a flat `SchemaModel` — one list per declaration kind —
with cross-references stored as stable IDs (see ID scheme below). Anonymous
inline types get synthetic IDs based on their parent path; every node retains
a `source_ref = { file_id, line }` pointing back to the original XSD location.

### Data model

`backend/app/parser/model.py` defines the Pydantic models. `SchemaModel` holds:

- `target_namespace`, `namespaces` (prefix → URI), form defaults
- `elements`, `attributes`, `simple_types`, `complex_types`, `groups`,
  `attribute_groups` — flat lists of declarations
- `files` — every file that fed the parse (id, name, content, checksum)
- `diagnostics` — non-fatal warnings and errors surfaced in the UI

The Pydantic models are JSON-serialized as the API response; the frontend
mirrors them as TypeScript interfaces in `frontend/src/types/schema.ts`. Any
change on one side must be reflected on the other — there is no codegen.

### Cache

`backend/app/cache.py` is an in-memory LRU + TTL cache (OrderedDict + Lock).
Defaults: 32 entries, 60-minute TTL. Keys are the SHA-256 hash of the
serialized model, so identical uploads collapse to one entry. There is **no
persistence**: restarting the container evicts everything, which is fine given
the upload-driven UX.

## Frontend

### Entry & shell

`src/main.tsx` mounts `<App />` into `#app`. `App.tsx` reads the URL hash on
load (`#id=<selectedId>`), renders the active tab (`tree` | `diagram` | `text`),
and writes the selected id back to the hash so links are shareable.

### State: the selection store

Everything view-related lives in a single Zustand store at
`frontend/src/stores/selectionStore.ts`. Important bits:

- `model`, `index`, `indexById`, `usagesByTarget` — populated once when a
  schema loads. `buildIndex(model)` (in `lib/indexSchema.ts`) walks the model
  and produces both an O(1) `id → entry` map and a reverse `qname → entries[]`
  map used by "Find Usages".
- `activeTab` — default is `"diagram"`. The tab bar is a simple setter; all
  tabs read from the same in-memory model, no refetch on switch.
- `selectedId`, `expandedIds` — selection is global across views: click a node
  in the tree, it lights up in the diagram and scrolls in the text view.
- `filterKinds`, `searchQuery` — drive the tree filter and the search palette.
- `setExpandedIds(ids)` — bulk replacement used by the diagram's
  Expand all / Collapse all buttons; the set of expandable element ids is
  computed once via `lib/expandAll.ts` (walks the particle graph, guarding
  against cycles through seen complex types).

### Data flow: upload to pixels

1. `Uploader` calls `uploadSchemaFile()` / `uploadSchemaText()` /
   `loadSchemaFromUrl()` in `src/api/client.ts`.
2. The response is `{ schema_id, model }`. `useSelection.setSchema(...)`
   stores the model and runs `buildIndex()` once.
3. The active tab re-renders from the store:
   - **DiagramView** calls `buildDiagramGraph(model, expandedIds)` to produce
     React Flow `nodes` + `edges`, then renders via custom node types
     (`ElementNode`, `CompositorNode`). Expansion is driven by
     `expandedIds`; clicking an element toggles it.
   - **TreeView** is a virtualized tree over `buildTreeRows(model, ...)` with
     per-kind filter chips.
   - **TextView** holds a ref to the CodeMirror `EditorView` and re-scrolls
     whenever the selected entry's `source_ref.line` changes — including
     auto-switching the file tab if the selection points into a different
     file.
4. `DetailPanel` reads `indexById.get(selectedId)` and renders type, facets,
   annotations, and a "Find Usages" list via `usagesByTarget`.

## Cross-cutting concerns

### ID scheme

All declarations are identified by `"{kind}:{qname-or-path}"`, e.g.:

- `element:{http://example.com/simple}Person`
- `complexType:{http://example.com/simple}PersonType`
- `element:{http://example.com/simple}PersonType/Address` (anonymous inline)

These IDs flow unchanged through the API, the Zustand index, the URL hash,
and React Flow node ids — so deep links, cross-view selection, and
tree/diagram synchronization all lean on the same primitive.

### Source locations

Every declaration carries a `SourceRef { file_id, line }` minted during the
lxml walk. `file_id` is the first 12 chars of a SHA-1 over the filename.
This is what lets `DetailPanel`'s "View in source" button jump to the Text tab
and scroll exactly to the declaration.

### Default tab & tab sync

`activeTab` defaults to `"diagram"` — the diagram is the headline view. Tab
switching is free (no network), and the `e2e/tests/golden-path.spec.ts` test
pins this behavior.

## Deployment

- **Dockerfile** — stage 1 (`node:20-alpine`) runs `npm ci && npm run build`;
  stage 2 (`python:3.12-slim`) installs libxml2/libxslt runtime libs, installs
  the backend package, copies the built SPA into `/app/static`, drops to UID
  1001, exposes 8080, and health-checks `/api/health`.
- **docker-compose.yml** — single `xsdviewer` service for local sandbox use;
  env: `LOG_LEVEL`, `MAX_UPLOAD_MB`, `ALLOWED_SCHEMA_HOSTS`.
- **Google Cloud Run** — production runs at <https://www.xsd-viewer.online/>
  (service `xsdviewer`, project `xsd-viewer-495407`, region `europe-west1`).
  See [docs/DEPLOY_GCLOUD.md](DEPLOY_GCLOUD.md) for build, sizing, env vars,
  domain mapping, smoke test and rollback.

## CI

`.github/workflows/ci.yml` runs four jobs:

1. **backend** — pip install, ruff lint, pytest.
2. **frontend** — `npm ci`, `tsc --noEmit`, Vitest, `npm run build`.
3. **e2e** — builds the frontend, starts the backend, runs the Playwright
   golden-path suite, uploads the HTML report on failure.
4. **docker** — multi-stage build; pushes to GHCR on `main` and tags (not on
   PRs).

## Extending the app

A quick map of where changes usually land:

| Change                                       | Start here                                         |
| -------------------------------------------- | -------------------------------------------------- |
| New XSD construct captured in the model      | `backend/app/parser/xsd_parser.py` + `model.py`, then mirror in `frontend/src/types/schema.ts` |
| New API endpoint                             | `backend/app/api/schema.py` (or a new router under `/api`) |
| New view or panel                            | `frontend/src/components/`, read state via `useSelection` |
| New cross-view selection behavior            | `frontend/src/stores/selectionStore.ts`            |
| Change how nodes are laid out in the diagram | `frontend/src/components/DiagramView/buildGraph.ts` |
| New e2e coverage                             | `e2e/tests/`                                       |
