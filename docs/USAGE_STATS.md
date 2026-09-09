# Anonymous usage statistics

The public site records **aggregate, anonymous** usage so the viewer can be
improved based on real use: how many people load schemas, from where, which
schemas, how big they are and how long they take to parse. **Schema files are
never stored**, and the raw client IP is neither stored nor logged.

One narrow exception exists so the sample-XML generator can be fixed: when a
generated sample document fails its own schema check, the generated document
(synthetic data we produced) and a few XSD lines around the declarations the
errors point at are recorded in `sample_issue` — see
[Sample diagnostics](#sample-diagnostics).

The feature is **off by default** — it only activates when `USAGE_DB_URL` is
set. Self-hosted installs without it record nothing.

## What is collected

One row per event in table `usage_event` (DDL: `backend/sql/usage_stats.sql`):

| Column | Meaning |
|---|---|
| `event_type` | `page_view` (SPA shell served), `schema_load`, `validate`, `export` |
| `visitor_hash` | `sha256(daily_salt ‖ ip ‖ user-agent)[:32]`; salt = `HMAC(USAGE_HASH_SECRET, date)` ⇒ same visitor within a day, unlinkable across days, not reversible |
| `country_code` | ISO-3166-1 alpha-2 derived server-side via MaxMind GeoLite2; NULL if unknown |
| `user_agent`, `device` | UA string (≤255) and a cheap classification `desktop`/`mobile`/`bot`/`unknown` |
| `referrer` | `scheme://host/path` of the `Referer` header, query dropped |
| `path` | page_view only — SPA path (`/`, `/paste`, `/url`, `/fundsxml`); unknown paths get a 404 and are not recorded. `/go/freexmltoolkit/docs` or `/go/freexmltoolkit/releases` with `source=freexmltoolkit` and `status_code=302` is an outbound click on a FreeXmlToolkit link (Learn more / Download) (counted redirect, see `app/api/go.py`) |
| `source` | `upload`/`text`/`url`/`release` (loads, validations); `html`/`formatted`/`sample` (exports — `sample` is a generated sample XML instance; `input_bytes` then holds the size of the generated document). A `validate` event with `source='sample'` is the automatic schema check the sample dialog runs on a generated document — only document roots are checked, so such an event marks the preceding sample export (same visitor, same `input_bytes`) as a whole-document sample; its `status` (`ok`/`invalid`/`rejected`) tells whether the generated XML was schema-valid |
| `schema_name` | upload/text: file **basename**; url: URL without query string (for `validate` events with `source='url'` this is the URL of the XML *document*); release: `tag/file`; sample export: main file of the loaded schema |
| `target_namespace` | of the main schema |
| `input_bytes`, `file_count`, `element_count`, `type_count`, `diagnostic_count` | sizes and counts |
| `error_count` | validate: number of validation errors |
| `duration_ms`, `status`, `status_code`, `error_detail` | timing and outcome (`ok`/`invalid`/`parse_error`/`rejected`); `error_detail` is the exception message, ≤255 chars |
| `app_version`, `received_at` | build version, server timestamp |

### Feedback

`POST /api/feedback` (💬 button in the app) writes one row per message to table
`feedback` (same DDL file): `message` (≤ 4000 chars), optional `email` (only
if the user typed one), `page`, `schema_name`, `error_detail` (the error the
user was looking at, prefilled by the UI), plus the same `visitor_hash`,
`country_code`, `user_agent`, `device`, `app_version` as above. The insert is
synchronous (the user gets a real success/failure) and rate-limited to
5/minute per IP; a hidden honeypot field drops naive bots. Without
`USAGE_DB_URL` the endpoint answers 503.

**Never collected:** whole schema files, XML you validate, raw IP, cookies,
anything from the browser beyond the standard request headers. There is no
client-side tracking script (the CSP forbids one anyway).

### Sample diagnostics

The sample-XML generator is best-effort: it walks a content model and fills in
placeholders. When the result does not validate we need to know whether *we*
gave up somewhere (a bug worth fixing) or the schema never offered what the
generator needed (nothing to fix). Table `sample_issue` answers that.

A row is written only when the generated sample failed its schema check or the
generator had to fudge its way to a valid one — never for an ordinary sample.
It holds:

| column | what |
| --- | --- |
| `kind` | `invalid`, `not_well_formed`, `degraded`, `abstract_root`, `setup_error` (the schema does not compile — usually XSD 1.1, which libxml2 cannot do), `generator_error` |
| `report` | the generator's own account of every spot it fudged, each classified `generator_limit` (our bug) or `schema_incomplete` (the schema's gap) |
| `errors` | the validator's errors, in full |
| `diagnostics` | what our parser complained about while reading the schema |
| `sample_xml` | the generated document — synthetic data, capped at 1 MB |
| `xsd_excerpts` | ±8 XSD lines around each declaration an error points at, capped at 16 kB — never whole files |
| `element_id`, `include_optional`, `repeat_count`, `max_depth`, `generation_ms` | how the sample was produced |
| `fingerprint`, `occurrences`, `first_seen_at`, `last_seen_at` | dedup: one row per defect per app version, with a hit counter |

The `fingerprint` covers the app version, so a defect that gets fixed stops
counting up and a regression starts a fresh row. The generator report reaches
the recording endpoint via the `X-Sample-Report` response header, which the
browser hands back with the validation request; it is treated as untrusted
input and rebuilt field by field (`app/usage/sample_issue.py`).

An **invalid sample with an empty report** is the most interesting row there
is: the generator believed it emitted faithful content and was wrong.

## Architecture

```
request → request_logging middleware binds RequestUsage(ip, ua, referrer)
        → router calls emit("schema_load", …)      (app/usage/context.py)
        → UsageRecorder queue (in-memory, 1000)     (app/usage/recorder.py)
        → background task: batched INSERT via psycopg, 3 attempts, then drop
```

- `emit()` never raises and is a no-op when no tracker is installed.
- Writes happen in a background task, but on Cloud Run the CPU is throttled
  once the response is sent and the task starves. The middleware therefore
  waits (bounded by `USAGE_DRAIN_SECONDS`, default 2 s) for pending writes
  **before** returning a response that emitted events — only those requests
  pay the ~50–150 ms round-trip to Helsinki; `/api/health`, assets and
  cache hits are unaffected. On SIGTERM the lifespan `stop()` flushes for ≤5 s.
- GeoLite2-Country is **not** in the image (MaxMind EULA). At startup the
  app uses `GEOIP_DB_PATH` if it exists, else downloads it in a background
  thread when `MAXMIND_LICENSE_KEY` is set, else leaves `country_code` NULL.
  Cloud Run's `/tmp` is in-memory, so each new instance downloads once (~6 MB).
  Attribution: *This product includes GeoLite2 data created by MaxMind,
  available from <https://www.maxmind.com>.*

## Configuration

| Env | Meaning |
|---|---|
| `USAGE_DB_URL` | libpq URL **without password**, e.g. `postgresql://xsdviewer@62.238.116.11:5432/xsdviewer_stats?sslmode=require`. Empty ⇒ feature off. |
| `USAGE_DB_PASSWORD` | DB password (Secret Manager on Cloud Run) |
| `USAGE_HASH_SECRET` | random secret for the daily salt; empty ⇒ warning, date-only salt |
| `MAXMIND_LICENSE_KEY` | free GeoLite2 key; empty ⇒ no country |
| `GEOIP_DB_PATH` | default `/tmp/geoip/GeoLite2-Country.mmdb`; the image sets `/app/geoip/GeoLite2-Country.mmdb`, which `scripts/deploy.sh` fills before each deploy (a per-instance runtime download hit MaxMind's daily limit with HTTP 429) |
| `USAGE_DRAIN_SECONDS` | default `2` — upper bound the middleware waits for pending writes on requests that emitted events |

## Production database

Shared **PostgreSQL 18** on the Hetzner VPS `tanzapp-prod` (62.238.116.11):

- DB `xsdviewer_stats`, role `xsdviewer` (owner). Password in
  `/home/deploy/xsdviewer-db-password.txt` on the server and in Secret Manager
  `xsdviewer-usage-db-password` (project `xsd-viewer-495407`).
- Cloud Run has no fixed egress IP ⇒ `pg_hba.conf` allows only
  `hostssl xsdviewer_stats xsdviewer 0.0.0.0/0 scram-sha-256` (TLS, this
  DB/role only). ufw already opens 5432/tcp; fail2ban jail `postgresql` bans
  after 5 failed logins / 10 min.
- Backups: Hetzner VM snapshots (daily, 7 rolling).

### One-time setup (already done for prod; repeat for a new environment)

```bash
# on the VPS
sudo -u postgres psql -c "CREATE ROLE xsdviewer LOGIN PASSWORD '…';" \
                      -c "CREATE DATABASE xsdviewer_stats OWNER xsdviewer;"
echo "hostssl xsdviewer_stats xsdviewer 0.0.0.0/0 scram-sha-256" | sudo tee -a /etc/postgresql/18/main/pg_hba.conf
echo "hostssl xsdviewer_stats xsdviewer ::/0      scram-sha-256" | sudo tee -a /etc/postgresql/18/main/pg_hba.conf
sudo systemctl reload postgresql
psql "postgresql://xsdviewer:…@127.0.0.1/xsdviewer_stats" -f backend/sql/usage_stats.sql

# GCP secrets + deploy
gcloud secrets create xsdviewer-usage-db-password --data-file=- --project xsd-viewer-495407
gcloud secrets create xsdviewer-usage-hash-secret --data-file=- --project xsd-viewer-495407
gcloud secrets create xsdviewer-maxmind-license-key --data-file=- --project xsd-viewer-495407
gcloud run deploy xsdviewer --source . --region europe-west1 --project xsd-viewer-495407 \
  --update-env-vars 'USAGE_DB_URL=postgresql://xsdviewer@62.238.116.11:5432/xsdviewer_stats?sslmode=require' \
  --update-secrets 'USAGE_DB_PASSWORD=xsdviewer-usage-db-password:latest,USAGE_HASH_SECRET=xsdviewer-usage-hash-secret:latest,MAXMIND_LICENSE_KEY=xsdviewer-maxmind-license-key:latest'
```

The Cloud Run service account needs `roles/secretmanager.secretAccessor` on
the secrets.

## Analysis

Quick overview: `python3 tools/usage_report.py [--days 30]` (read-only; password
from `$USAGE_DB_PASSWORD` or Secret Manager via gcloud).

Connect directly:
`psql "postgresql://xsdviewer:…@62.238.116.11:5432/xsdviewer_stats?sslmode=require"`
(or from the VPS via `127.0.0.1`). Useful queries:

```sql
-- Loads and visitors per day (bots excluded from visitors)
SELECT received_at::date d,
       count(*) FILTER (WHERE event_type='page_view') views,
       count(DISTINCT visitor_hash) FILTER (WHERE device<>'bot') visitors,
       count(*) FILTER (WHERE event_type='schema_load') loads
FROM usage_event GROUP BY 1 ORDER BY 1 DESC;

-- Input type & outcome
SELECT source, status, count(*), round(avg(duration_ms)) avg_ms, round(avg(input_bytes)/1024) avg_kb
FROM usage_event WHERE event_type='schema_load' GROUP BY 1,2 ORDER BY 1,3 DESC;

-- Error rate per source
SELECT source, count(*) FILTER (WHERE status<>'ok')*100.0/count(*) pct_failed
FROM usage_event WHERE event_type='schema_load' GROUP BY 1;

-- p50 / p95 parse duration
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) p50,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) p95
FROM usage_event WHERE event_type='schema_load' AND status='ok';

-- Which schemas / namespaces
SELECT schema_name, count(*) FROM usage_event WHERE event_type='schema_load' GROUP BY 1 ORDER BY 2 DESC LIMIT 25;
SELECT target_namespace, count(*) FROM usage_event WHERE event_type='schema_load' GROUP BY 1 ORDER BY 2 DESC LIMIT 25;

-- Countries, referrers, devices
SELECT country_code, count(DISTINCT visitor_hash) FROM usage_event WHERE device<>'bot' GROUP BY 1 ORDER BY 2 DESC;
SELECT referrer, count(*) FROM usage_event WHERE event_type='page_view' GROUP BY 1 ORDER BY 2 DESC LIMIT 25;
SELECT device, count(*) FROM usage_event GROUP BY 1;

-- Feedback
SELECT received_at::timestamp(0), left(message, 120), email, page, error_detail
FROM feedback ORDER BY received_at DESC LIMIT 20;

-- Sample-generator defects worth fixing first, most-hit first
SELECT occurrences, kind, schema_name, element_qname, error_count,
       report -> 'counts' AS degradations
FROM sample_issue
WHERE kind IN ('invalid', 'not_well_formed', 'generator_error')
ORDER BY occurrences DESC LIMIT 20;

-- Ours or theirs? Split the degradations by category
SELECT e ->> 'category' AS category, e ->> 'reason' AS reason, sum(occurrences)
FROM sample_issue, jsonb_array_elements(report -> 'entries') AS e
GROUP BY 1, 2 ORDER BY 3 DESC;

-- Size watch
SELECT pg_size_pretty(pg_total_relation_size('usage_event')), count(*) FROM usage_event;
SELECT pg_size_pretty(pg_total_relation_size('sample_issue')), count(*) FROM sample_issue;
```

Housekeeping (`usage_event` rows are small; a year is a few MB at current
traffic). `sample_issue` rows are larger but deduplicated, so the table grows
with the number of distinct defects rather than with traffic:

```sql
DELETE FROM usage_event WHERE received_at < now() - interval '24 months';
VACUUM (ANALYZE) usage_event;

-- Fixed defects: nothing seen since the release that fixed them
DELETE FROM sample_issue WHERE last_seen_at < now() - interval '12 months';
VACUUM (ANALYZE) sample_issue;
```

## Privacy

No personal data is persisted: the IP is hashed with a daily rotating salt and
discarded, the user agent is a standard browser string, and schema names are
whatever the user typed or the URL they pasted (never file content). The one
place content is kept is `sample_issue`, and only for a sample that came out
wrong: the generated document, which is synthetic, plus short XSD excerpts
around the declarations the errors point at — never whole schema files. The
README states this and links here.
