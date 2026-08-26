#!/usr/bin/env python3
"""Print a read-only usage overview of the XSD viewer from the stats Postgres.

Reads the `usage_event` table (docs/USAGE_STATS.md) on the Hetzner VPS and
prints aggregates: volume per day, sources, visitors, countries, referrers,
top schemas, error rate, parse-duration percentiles, feedback, DB size. No writes.

Connection (env-overridable; defaults match the Cloud Run deploy):
    USAGE_DB_HOST  (default 62.238.116.11)
    USAGE_DB_NAME  (default xsdviewer_stats)
    USAGE_DB_USER  (default xsdviewer)
Password: $USAGE_DB_PASSWORD or $PGPASSWORD, else
    gcloud secrets versions access latest --secret=xsdviewer-usage-db-password --project xsd-viewer-495407

Requires: pip install --user "psycopg[binary]"

Usage:
    python3 tools/usage_report.py             # everything
    python3 tools/usage_report.py --days 30   # last N days
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

try:
    import psycopg
except ImportError:
    sys.exit('psycopg not installed. Run:  pip install --user "psycopg[binary]"')

DEFAULT_HOST = "62.238.116.11"
DEFAULT_NAME = "xsdviewer_stats"
DEFAULT_USER = "xsdviewer"
PW_SECRET = "xsdviewer-usage-db-password"
GCP_PROJECT = "xsd-viewer-495407"


def resolve_password() -> str:
    pw = os.environ.get("USAGE_DB_PASSWORD") or os.environ.get("PGPASSWORD")
    if pw:
        return pw
    try:
        out = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest",
             f"--secret={PW_SECRET}", f"--project={GCP_PROJECT}"],
            check=True, capture_output=True, text=True,
        )
        return out.stdout.strip("\n")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        sys.exit(f"No DB password. Set $USAGE_DB_PASSWORD or authenticate gcloud.\n{detail}")


def main() -> None:
    ap = argparse.ArgumentParser(description="XSD viewer usage overview (read-only).")
    ap.add_argument("--days", type=int, default=None, help="restrict to the last N days")
    args = ap.parse_args()

    where = f"WHERE received_at > now() - interval '{int(args.days)} days'" if args.days else ""
    and_ = where.replace("WHERE", "AND", 1) if where else ""

    dsn = (
        f"host={os.environ.get('USAGE_DB_HOST', DEFAULT_HOST)} "
        f"dbname={os.environ.get('USAGE_DB_NAME', DEFAULT_NAME)} "
        f"user={os.environ.get('USAGE_DB_USER', DEFAULT_USER)} "
        f"password={resolve_password()} sslmode=require"
    )
    scope = f"last {args.days} days" if args.days else "all time"
    print(f"Online XSD Viewer — usage overview ({scope})")

    queries = [
        ("Totals", f"""
            SELECT count(*) FILTER (WHERE event_type='page_view') page_views,
                   count(*) FILTER (WHERE event_type='schema_load') schema_loads,
                   count(*) FILTER (WHERE event_type='validate') validations,
                   count(*) FILTER (WHERE event_type='export') exports,
                   count(DISTINCT (received_at::date, visitor_hash)) visitor_days,
                   min(received_at)::date first_event, max(received_at)::date last_event
            FROM usage_event {where};"""),
        ("Per day (max. 14)", f"""
            SELECT received_at::date d,
                   count(*) FILTER (WHERE event_type='page_view') views,
                   count(DISTINCT visitor_hash) FILTER (WHERE device <> 'bot') visitors,
                   count(*) FILTER (WHERE event_type='schema_load') loads,
                   count(*) FILTER (WHERE event_type='schema_load' AND status='ok') loads_ok
            FROM usage_event {where} GROUP BY 1 ORDER BY 1 DESC LIMIT 14;"""),
        ("Schema loads by source & status", f"""
            SELECT source, status, count(*) n, round(avg(duration_ms)) avg_ms,
                   round(avg(input_bytes)/1024) avg_kb
            FROM usage_event WHERE event_type='schema_load' {and_} GROUP BY 1,2 ORDER BY 1,3 DESC;"""),
        ("Parse duration percentiles (ok loads)", f"""
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) p50,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) p95,
                   max(duration_ms) max_ms, max(input_bytes)/1024 max_kb
            FROM usage_event WHERE event_type='schema_load' AND status='ok' {and_};"""),
        ("Top schemas", f"""
            SELECT coalesce(schema_name,'?') schema_name, count(*) n
            FROM usage_event WHERE event_type='schema_load' {and_} GROUP BY 1 ORDER BY 2 DESC LIMIT 15;"""),
        ("Top target namespaces", f"""
            SELECT coalesce(target_namespace,'(none)') tns, count(*) n
            FROM usage_event WHERE event_type='schema_load' AND status='ok' {and_}
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15;"""),
        ("Countries (non-bot)", f"""
            SELECT coalesce(country_code,'??') cc, count(DISTINCT visitor_hash) visitors, count(*) events
            FROM usage_event WHERE device <> 'bot' {and_} GROUP BY 1 ORDER BY 2 DESC LIMIT 15;"""),
        ("Referrers (page views)", f"""
            SELECT coalesce(referrer,'(direct)') referrer, count(*) n
            FROM usage_event WHERE event_type='page_view' {and_} GROUP BY 1 ORDER BY 2 DESC LIMIT 15;"""),
        ("Devices", f"""
            SELECT device, count(*) events, count(DISTINCT visitor_hash) visitors
            FROM usage_event {where} GROUP BY 1 ORDER BY 2 DESC;"""),
        ("Recent errors", f"""
            SELECT received_at::timestamp(0) at, event_type, source, status, left(error_detail, 80) detail
            FROM usage_event WHERE status IN ('parse_error','rejected') {and_}
            ORDER BY received_at DESC LIMIT 10;"""),
        ("Feedback (latest 20)", f"""
            SELECT received_at::timestamp(0) at, left(message, 100) message, email, page,
                   left(error_detail, 60) error_detail, country_code cc
            FROM feedback {where} ORDER BY received_at DESC LIMIT 20;"""),
        ("DB size", """
            SELECT pg_size_pretty(pg_total_relation_size('usage_event')) table_size,
                   pg_size_pretty(pg_database_size(current_database())) db_size,
                   (SELECT count(*) FROM usage_event) rows;"""),
    ]

    with psycopg.connect(dsn, connect_timeout=20) as conn:
        for title, sql in queries:
            print(f"\n### {title}")
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
                widths = [len(c) for c in cols]
                for r in rows:
                    for i, v in enumerate(r):
                        widths[i] = max(widths[i], len("" if v is None else str(v)))
                print("  ".join(c.ljust(widths[i]) for i, c in enumerate(cols)))
                for r in rows:
                    print("  ".join(("" if v is None else str(v)).ljust(widths[i]) for i, v in enumerate(r)))
                if not rows:
                    print("(no rows)")


if __name__ == "__main__":
    main()
