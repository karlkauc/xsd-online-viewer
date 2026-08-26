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
  source           text,                 -- schema_load/validate: upload|text|url|release ; export: html|formatted
  schema_name      text,                 -- basename / URL without query / release tag+file (never content)
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
