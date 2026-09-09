-- Usage statistics schema for the Online XSD Viewer (docs/USAGE_STATS.md).
-- Apply once by hand as the owning role; the app never issues DDL.
--   psql "postgresql://xsdviewer@62.238.116.11:5432/xsdviewer_stats?sslmode=require" -f backend/sql/usage_stats.sql

CREATE TABLE IF NOT EXISTS usage_event (
  event_id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  received_at      timestamptz NOT NULL DEFAULT now(),
  event_type       text        NOT NULL CHECK (event_type IN ('page_view','schema_load','validate','export')),
  visitor_hash     text,                 -- sha256(daily salt | ip | user-agent), first 32 hex chars; no raw IP
  country_code     char(2),              -- ISO-3166-1 alpha-2 via GeoLite2, NULL if unknown
  user_agent       text,                 -- truncated to 255
  device           text,                 -- desktop | mobile | bot | unknown
  status_code      int,
  app_version      text,
  path             text,                 -- page_view: SPA path served
  referrer         text,                 -- scheme://host/path, no query
  source           text,                 -- schema_load: upload|text|url|release ; validate: upload|text|url|sample ; export: html|formatted|sample
  schema_name      text,                 -- basename / URL without query / release tag+file (never file content)
  target_namespace text,
  input_bytes      int,
  file_count       int,
  element_count    int,
  type_count       int,
  diagnostic_count int,
  error_count      int,                  -- validate: number of validation errors
  duration_ms      int,
  status           text,                 -- ok | invalid | parse_error | rejected
  error_detail     text                  -- exception message, truncated to 255
);

CREATE INDEX IF NOT EXISTS idx_usage_event_received  ON usage_event (received_at);
CREATE INDEX IF NOT EXISTS idx_usage_event_type_time ON usage_event (event_type, received_at);
CREATE INDEX IF NOT EXISTS idx_usage_event_visitor   ON usage_event (visitor_hash);
CREATE INDEX IF NOT EXISTS idx_usage_event_country   ON usage_event (country_code);

-- User feedback submitted through the in-app dialog (POST /api/feedback).
-- Same anonymisation as usage_event; the email is optional and typed in voluntarily.
CREATE TABLE IF NOT EXISTS feedback (
  feedback_id   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  received_at   timestamptz NOT NULL DEFAULT now(),
  message       text        NOT NULL,   -- ≤ 4000 chars, enforced by the API
  email         text,                   -- optional reply address, user-provided
  page          text,                   -- SPA path the dialog was opened from
  schema_name   text,                   -- schema loaded at the time, if any
  error_detail  text,                   -- error message the user was looking at, if any
  visitor_hash  text,
  country_code  char(2),
  user_agent    text,
  device        text,
  app_version   text
);

CREATE INDEX IF NOT EXISTS idx_feedback_received ON feedback (received_at);

-- Why a generated sample XML document did not come out right
-- (docs/USAGE_STATS.md, app/usage/sample_issue.py). Written only when the
-- generator degraded or its output failed the schema check, so the table is
-- a work list for fixing the generator rather than a traffic log.
--
-- Unlike usage_event this table does keep content, and deliberately so:
--   * sample_xml is the generated document -- synthetic data we produced;
--   * xsd_excerpts holds only the few XSD lines around the declarations the
--     errors point at, never whole schema files.
CREATE TABLE IF NOT EXISTS sample_issue (
  issue_id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  first_seen_at    timestamptz NOT NULL DEFAULT now(),
  last_seen_at     timestamptz NOT NULL DEFAULT now(),
  occurrences      int         NOT NULL DEFAULT 1,   -- bumped by the upsert below
  fingerprint      text        NOT NULL UNIQUE,      -- sha256 over app_version+schema+element+options+errors+reasons
  kind             text        NOT NULL,             -- invalid | not_well_formed | degraded | abstract_root | setup_error | generator_error
  app_version      text,                             -- part of the fingerprint: a fixed bug starts a new row
  visitor_hash     text,                             -- same anonymisation as usage_event; no raw IP
  country_code     char(2),
  device           text,
  schema_id        text,                             -- sha256(payload)[:32]; groups repeats of one schema
  schema_name      text,                             -- basename / URL without query (never file content)
  target_namespace text,
  xsd_version      text,                             -- 1.0 | 1.1 | unknown; 1.1 explains most setup_error rows
  file_count       int,
  schema_bytes     int,                              -- size of the schema, not its content
  element_id       text,                             -- declaration the sample was rooted at
  element_qname    text,
  include_optional boolean,                          -- the SampleOptions in effect
  repeat_count     int,
  max_depth        int,
  generation_ms    int,
  sample_bytes     int,
  sample_truncated boolean,                          -- sample_xml hit the 1 MB cap
  error_count      int,                              -- validator errors
  degradation_count int,                             -- spots the generator had to fudge
  errors           jsonb,                            -- full ValidationErrorItem list
  report           jsonb,                            -- SampleReport: counts + entries, each generator_limit or schema_incomplete
  diagnostics      jsonb,                            -- what our own parser complained about
  xsd_excerpts     jsonb,                            -- [{file, first_line, last_line, snippet}], capped at 16 kB
  sample_xml       text,                             -- the generated document, capped at 1 MB
  traceback        text                              -- kind='generator_error' only
);

CREATE INDEX IF NOT EXISTS idx_sample_issue_kind ON sample_issue (kind, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_sample_issue_seen ON sample_issue (last_seen_at);

-- The rows that are worth fixing first: our own limitations, most-hit first.
--   SELECT kind, occurrences, schema_name, element_qname,
--          report -> 'counts' AS degradations, error_count
--     FROM sample_issue
--    WHERE kind IN ('invalid','not_well_formed','generator_error')
--    ORDER BY occurrences DESC LIMIT 20;
