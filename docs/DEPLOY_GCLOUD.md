# Deployment auf Google Cloud Run

Diese Anleitung beschreibt, wie der XSD-Viewer-Container auf
[Google Cloud Run](https://cloud.google.com/run) deployed wird.

Cloud Run passt zu diesem Container, weil er **stateless** ist (in-memory
Cache), bereits auf `$PORT` hört (`backend/app/config.py`) und proxy-aware
gestartet wird (`Dockerfile`, `--proxy-headers --forwarded-allow-ips=*`).
Der Service skaliert auf Null, sodass im Idle-Betrieb keine Kosten
anfallen.

## Voraussetzungen

- Ein GCP-Projekt mit aktivierter Billing.
- [`gcloud` CLI](https://cloud.google.com/sdk/docs/install) installiert
  und authentifiziert (`gcloud auth login`).
- Aktives Projekt gesetzt: `gcloud config set project <PROJECT_ID>`.

Einmalig die nötigen APIs aktivieren:

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

## Quickstart (eine Zeile)

Aus dem Repo-Root:

```bash
gcloud run deploy xsdviewer \
  --source . \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --cpu-boost \
  --concurrency 20 \
  --min-instances 0 \
  --max-instances 5 \
  --timeout 60 \
  --port 8080 \
  --set-env-vars 'MAX_UPLOAD_MB=32,LOG_LEVEL=INFO'
```

Cloud Build baut anhand des bestehenden `Dockerfile`, lädt das Image in
Artifact Registry, deployed den Service und gibt am Ende eine
`https://xsdviewer-<hash>-ew.a.run.app` URL aus.

> **Hinweis zu `ALLOWED_SCHEMA_HOSTS`**: Standardmäßig ist URL-Fetching
> für jede öffentliche http(s)-URL erlaubt; private/Loopback-IPs werden
> weiterhin von der SSRF-Schutzschicht geblockt. Soll der Endpoint auf
> eine Whitelist beschränkt werden (Lockdown-Modus), enthält die
> Variable Komma-getrennte Regexes — `--set-env-vars` interpretiert
> Kommas aber als Variablentrenner. Workaround siehe
> [Env-Vars mit Kommas](#env-vars-mit-kommas-allowed_schema_hosts).

## Wichtige Cloud-Run-Limits

| Limit | Wert | Auswirkung |
|-------|------|------------|
| Max. Request-Größe | **32 MB** | `MAX_UPLOAD_MB` darf nicht größer sein, sonst akzeptiert das Backend Uploads, die der Cloud-Run-LB vorher schon ablehnt. |
| Max. Request-Timeout | 60 min (Default 5 min) | Die App antwortet typischerweise in <1 s; 60 s reichen mehr als aus. |
| Memory | 128 MiB – 32 GiB | 512 MiB ist hier der Sweet-Spot (siehe Sizing). |

## Sizing-Begründung

Worst-Case-Memory beim Parsen einer 32 MB XSD:

- Upload-Buffer (`BufferRequestBodyMiddleware` in `backend/app/main.py`): bis zu 32 MB
- lxml-Tree (~ 3× Roh-Größe): ~ 100 MB transient
- LRU-Cache (`SCHEMA_CACHE_MAX_ENTRIES=32` Standard, `backend/app/config.py`): ~ 5 MB pro Eintrag → bis zu 160 MB steady-state
- Framework-Overhead: ~ 20 MB

Macht **~210 MB Steady, ~360 MB Peak**. 512 MiB lassen genug Headroom,
ohne Memory zu verschwenden.

XSD-Parsing ist **CPU-bound** (lxml-Tree-Walks, Facetten-Regex). Eine CPU
pro Instanz reicht; Last-Spitzen werden horizontal über zusätzliche
Instanzen bedient.

| Flag | Wert | Begründung |
|------|------|------------|
| `--memory` | `512Mi` | Peak + Headroom, kein OOM-Risiko |
| `--cpu` | `1` | CPU-bound Workload, horizontal skalieren |
| `--min-instances` | `0` | Scale-to-zero, keine Idle-Kosten |
| `--max-instances` | `5` | Harter Deckel gegen Runaway-Billing |
| `--concurrency` | `20` | Verhindert CPU-Starvation pro Instanz (Default 80 ist zu hoch für CPU-bound) |
| `--timeout` | `60s` | App antwortet weit darunter |
| `--cpu-boost` | aktiv | Reduziert Cold-Start spürbar |
| `--region` | `europe-west1` | Niedrige Latenz aus DACH, EU-Daten |

## Env-Var-Referenz

Quelle der Defaults: `backend/app/config.py`. In Cloud Run per
`--set-env-vars` oder `--update-env-vars` setzen.

| Variable | Default | Cloud-Run-Empfehlung |
|----------|---------|----------------------|
| `PORT` | `8080` | nicht setzen — Cloud Run injiziert ihn |
| `MAX_UPLOAD_MB` | `50` | **`32`** (Cloud-Run-Limit) |
| `ALLOWED_SCHEMA_HOSTS` | leer | leer = jede öffentliche URL erlaubt; setzen, wenn der Endpoint auf eine Host-Whitelist beschränkt werden soll (Lockdown) |
| `SCHEMA_CACHE_TTL_MIN` | `60` | `60` ist OK |
| `SCHEMA_CACHE_MAX_ENTRIES` | `32` | `32` ist OK; bei Memory-Druck reduzieren |
| `LOG_LEVEL` | `INFO` | `INFO` |
| `STATIC_DIR` | `/app/static` | Default beibehalten |
| `FETCH_TIMEOUT_SECONDS` | `10` | Default beibehalten |
| `FETCH_MAX_RESPONSE_MB` | `10` | Default beibehalten |
| `FETCH_MAX_REDIRECTS` | `3` | Default beibehalten |
| `CORS_ALLOW_ORIGINS` | leer | nur setzen, wenn ein separates Frontend zugreift |

### Env-Vars mit Kommas (`ALLOWED_SCHEMA_HOSTS`)

Da `ALLOWED_SCHEMA_HOSTS` Komma-getrennte Regexes enthält, kollidiert
das mit dem Trenner von `--set-env-vars`. Zwei Wege:

**1) Custom-Trenner mit `^@^`:**

```bash
gcloud run deploy xsdviewer \
  --source . --region europe-west1 \
  --set-env-vars '^@^MAX_UPLOAD_MB=32@LOG_LEVEL=INFO@ALLOWED_SCHEMA_HOSTS=^raw\.githubusercontent\.com$,^github\.com$'
```

**2) Getrennt mit `--update-env-vars` nach dem Deploy:**

```bash
gcloud run services update xsdviewer --region europe-west1 \
  --update-env-vars '^@^ALLOWED_SCHEMA_HOSTS=^raw\.githubusercontent\.com$,^github\.com$'
```

## Smoke Test

```bash
URL=$(gcloud run services describe xsdviewer \
  --region europe-west1 --format='value(status.url)')

curl -fsS "$URL/api/health"      # → {"status":"ok",...}
curl -fsS "$URL/" | head         # → index.html der SPA
```

Anschließend `$URL` im Browser öffnen und ein XSD per Drag-&-Drop hochladen.
Default-Tab ist `diagram`.

## Logs & Monitoring

```bash
# Live-Logs
gcloud run services logs tail xsdviewer --region europe-west1

# Service-Status, URL, aktive Revision
gcloud run services describe xsdviewer --region europe-west1
```

Jeder Request bekommt eine Correlation-ID (`X-Request-ID`), die im
Backend-Log auftaucht — gut zum Debuggen einzelner Anfragen.

## Update / Redeploy

Identischer Befehl wie beim Initial-Deploy. Cloud Run baut ein neues Image,
erstellt eine neue Revision und schaltet den Traffic darauf um.

```bash
gcloud run deploy xsdviewer --source . --region europe-west1
```

## Rollback

```bash
# Verfügbare Revisionen anzeigen
gcloud run revisions list --service xsdviewer --region europe-west1

# 100 % Traffic auf eine ältere Revision
gcloud run services update-traffic xsdviewer \
  --region europe-west1 \
  --to-revisions xsdviewer-00003-abc=100
```

## Custom Domain (optional, später)

```bash
gcloud run domain-mappings create \
  --service xsdviewer \
  --domain viewer.example.com \
  --region europe-west1
```

Anschließend die ausgegebenen DNS-Records (CNAME / A / AAAA) im
DNS-Provider eintragen. Cloud Run stellt automatisch ein managed
TLS-Zertifikat aus (Let's Encrypt).

## Service löschen (Kosten-Sicherung)

```bash
gcloud run services delete xsdviewer --region europe-west1
```

Dabei werden auch alle Revisionen entfernt; das Container-Image bleibt
in der Artifact Registry und kann separat gelöscht werden:

```bash
gcloud artifacts docker images list \
  europe-west1-docker.pkg.dev/$(gcloud config get-value project)/cloud-run-source-deploy
```

## Kosten-Erwartung

Bei leichter Nutzung (≤ 500 Requests/Monat) bleibt der Service
typischerweise im **kostenlosen Cloud-Run-Free-Tier** — 2 Mio Requests,
360 000 GiB-s Memory, 180 000 vCPU-s pro Monat sind frei. Erwartete
Rechnung: **$0–2 / Monat**. Aktuelle Preise:
<https://cloud.google.com/run/pricing>.

Hauptstellschrauben gegen Kosten:

1. `--min-instances 0` (Default beibehalten) — keine Idle-Instanzen.
2. `--max-instances 5` — Deckel gegen Traffic-Spikes / Bots.
3. `MAX_UPLOAD_MB=32` — verhindert CPU-Verschwendung an Mega-Uploads.

## Folgeschritte (optional)

- **CI/CD**: GitHub-Actions-Workflow oder Cloud-Build-Trigger, der bei
  Push auf `master` automatisch deployed (Workload Identity Federation
  für sicheren Auth ohne Service-Account-Keys).
- **WAF**: Vor Cloud Run einen externen HTTPS-Load-Balancer mit Cloud
  Armor schalten (z. B. Rate-Limiting, IP-Allowlists).
- **Auth**: Wenn der Service später nicht mehr öffentlich sein soll,
  `--no-allow-unauthenticated` und Identity-Aware Proxy davorschalten.
