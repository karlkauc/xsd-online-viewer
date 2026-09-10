#!/usr/bin/env python3
"""Audit the sample XML generator against real-world schemas.

For every schema URL the tool parses the schema with the app's own loader
(same include/import resolution as POST /api/schema/url), generates a sample
for every global element -- once with required content only, once with
optional content -- validates each sample against the schema, and records what
went wrong together with the generator's own SampleReport. The results are the
work list for fixing app/parser/sample.py.

Output directory:
    results/<schema>.jsonl   one line per sample
    samples/<schema>/*.xml   every sample that did not validate
    summary.json             totals, per-schema counts, error clusters, report reasons

Downloaded schemas are cached as parsed models in --cache-dir (keep it outside
the repo; the schemas belong to their publishers).

URL list -- schemas users loaded by URL (read-only, stats DB, docs/USAGE_STATS.md):
    SELECT DISTINCT schema_name FROM usage_event
     WHERE event_type='schema_load' AND source='url' AND status='ok' ORDER BY 1;

Usage:
    python3 tools/sample_audit.py --urls urls.txt --out audit/before --cache-dir audit/cache
    python3 tools/sample_audit.py --urls urls.txt --out audit/after --cache-dir audit/cache --skip-over 5000
    python3 tools/sample_audit.py --compare audit/before audit/after   # exit 1 on regressions
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import signal
import sys
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.model import ElementDecl, SchemaModel  # noqa: E402
from app.parser.sample import (  # noqa: E402
    GENERATOR_LIMIT,
    SCHEMA_INCOMPLETE,
    SampleOptions,
    SampleReport,
    generate_sample_with_report,
)
from app.parser.validation import (  # noqa: E402
    ValidationSetupError,
    build_xmlschema,
    validate_xml,
)
from app.parser.xsd_parser import parse_url  # noqa: E402

MODES = {
    "required": SampleOptions(),
    "optional": SampleOptions(include_optional=True),
}
FAILED = ("invalid", "not_well_formed", "generator_error", "validator_error", "timeout")
MAX_SAVED_SAMPLE_BYTES = 2_000_000


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _digest(text: str, size: int = 24) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:size]


def _slug(url: str) -> str:
    tail = re.sub(r"[^A-Za-z0-9]+", "-", url.split("://", 1)[-1]).strip("-")
    return f"{tail[-60:]}-{_digest(url, 6)}"


def load_schema(url: str, cache_dir: Path) -> dict:
    """Parse ``url`` (or reuse the cached model) and describe the result."""
    path = cache_dir / f"{_digest(url)}.json"
    started = time.monotonic()
    if not path.exists():
        try:
            model = parse_url(url)
        except Exception as exc:  # noqa: BLE001 - every failure is a result here
            return {"url": url, "status": "fetch_error", "detail": f"{type(exc).__name__}: {exc}"[:500]}
        path.write_text(model.model_dump_json(), encoding="utf-8")
    model = SchemaModel.model_validate_json(path.read_text(encoding="utf-8"))
    # Same files under different URLs (a moved branch ref) are one schema.
    content_hash = _digest("\0".join(sorted(f.content or "" for f in model.files)), 32)
    return {
        "url": url,
        "status": "loaded",
        "cache": str(path),
        "content_hash": content_hash,
        "files": len(model.files),
        "elements": sum(1 for e in model.elements if e.name),
        "xsd_version": model.xsd_version,
        "target_namespace": model.target_namespace,
        "diagnostic_errors": [d.message for d in model.diagnostics if d.severity == "error"][:10],
        "load_ms": int((time.monotonic() - started) * 1000),
    }


# ---------------------------------------------------------------------------
# Sampling + validation
# ---------------------------------------------------------------------------


class _SampleTimeoutError(Exception):
    pass


def _on_alarm(_signum, _frame):  # noqa: ANN001, ANN202
    raise _SampleTimeoutError()


def _cause(report: SampleReport) -> str:
    """Whose fault an invalid sample most likely is."""
    categories = {entry.category for entry in report.entries}
    if not categories:
        return "silent"  # the generator believed its output was faithful
    if SCHEMA_INCOMPLETE not in categories:
        return GENERATOR_LIMIT
    if GENERATOR_LIMIT not in categories:
        return SCHEMA_INCOMPLETE
    return "mixed"


def _one_sample(
    model: SchemaModel,
    schema,  # noqa: ANN001 - etree.XMLSchema | None
    element: ElementDecl,
    mode: str,
    index: int,
    sample_dir: Path,
    timeout: float,
) -> dict:
    record: dict = {
        "element_id": element.id,
        "element": element.qname or element.name,
        "abstract": element.abstract,
        "mode": mode,
    }
    phase = "generate"
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        started = time.perf_counter()
        xml, report = generate_sample_with_report(model, element, MODES[mode])
        record["gen_ms"] = round((time.perf_counter() - started) * 1000, 1)
        record["report"] = {
            reason: {"n": n, "category": next(e.category for e in report.entries if e.reason == reason)}
            for reason, n in report.counts.items()
        }
        data = xml.encode("utf-8")
        record["sample_bytes"] = len(data)
        if schema is None:
            record["status"] = "unvalidated"
            return record
        phase = "validate"
        started = time.perf_counter()
        result = validate_xml(model, data, schema=schema)
        record["val_ms"] = round((time.perf_counter() - started) * 1000, 1)
        if result.is_valid:
            record["status"] = "valid"
            return record
        not_well_formed = any(e.kind == "not-well-formed" for e in result.errors)
        record["status"] = "not_well_formed" if not_well_formed else "invalid"
        record["cause"] = _cause(report)
        record["error_count"] = len(result.errors)
        record["errors"] = [
            {"type_name": e.type_name, "message": e.message, "path": e.path, "line": e.line}
            for e in result.errors[:10]
        ]
        sample_dir.mkdir(parents=True, exist_ok=True)
        sample_file = sample_dir / f"{index:05d}-{mode}.xml"
        text = result.reformatted_xml or xml
        sample_file.write_text(text[:MAX_SAVED_SAMPLE_BYTES], encoding="utf-8")
        record["sample_file"] = str(sample_file.relative_to(sample_dir.parent.parent))
    except _SampleTimeoutError:
        record["status"] = "timeout"
        record["phase"] = phase
    except Exception:  # noqa: BLE001
        record["status"] = "generator_error" if phase == "generate" else "validator_error"
        record["traceback"] = traceback.format_exc()[-4000:]
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return record


def audit_schema(
    meta: dict, out_dir: Path, max_elements: int | None, sample_timeout: float, budget: float
) -> dict:
    """Generate and validate every sample of one schema; write its results file."""
    signal.signal(signal.SIGALRM, _on_alarm)
    model = SchemaModel.model_validate_json(Path(meta["cache"]).read_text(encoding="utf-8"))
    key = meta["key"]
    started = time.monotonic()
    try:
        schema = build_xmlschema(model)
        setup_error = None
    except ValidationSetupError as exc:
        schema, setup_error = None, str(exc)[:1000]
    compile_ms = int((time.monotonic() - started) * 1000)

    elements = [e for e in model.elements if e.name]
    if max_elements:
        elements = elements[:max_elements]
    deadline = time.monotonic() + budget
    counts: Counter[str] = Counter()
    sample_dir = out_dir / "samples" / key
    with (out_dir / "results" / f"{key}.jsonl").open("w", encoding="utf-8") as fh:
        for index, element in enumerate(elements):
            for mode in MODES:
                if time.monotonic() > deadline:
                    record = {
                        "element_id": element.id,
                        "element": element.qname or element.name,
                        "mode": mode,
                        "status": "skipped_budget",
                    }
                else:
                    record = _one_sample(model, schema, element, mode, index, sample_dir, sample_timeout)
                record["schema"] = meta["url"]
                counts[f"{mode}:{record['status']}"] += 1
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return meta | {
        "setup_error": setup_error,
        "compile_ms": compile_ms,
        "audited_elements": len(elements),
        "counts": dict(counts),
        "audit_ms": int((time.monotonic() - started) * 1000),
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _template(message: str) -> str:
    """Error message with the instance-specific parts blanked out, for clustering."""
    text = re.sub(r"\{[^}]*\}", "", message)
    text = re.sub(r"'[^']*'", "'…'", text)
    text = re.sub(r"\( .* \)", "( … )", text)
    text = re.sub(r"\d+", "N", text)
    return text.strip()


def _iter_records(out_dir: Path):
    for path in sorted((out_dir / "results").glob("*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                yield json.loads(line)


def summarise(out_dir: Path, schemas: list[dict]) -> dict:
    totals: Counter[str] = Counter()
    clusters: dict[str, dict] = {}
    reasons: dict[str, dict] = {}
    for record in _iter_records(out_dir):
        status, mode = record["status"], record["mode"]
        totals[f"{mode}:{status}"] += 1
        failed = status in FAILED
        for reason, info in (record.get("report") or {}).items():
            entry = reasons.setdefault(
                reason,
                {
                    "category": info["category"],
                    "samples": 0,
                    "failed_samples": 0,
                    "occurrences": 0,
                    "schemas": set(),
                },
            )
            entry["samples"] += 1
            entry["occurrences"] += info["n"]
            entry["failed_samples"] += failed
            entry["schemas"].add(record["schema"])
        if status in ("invalid", "not_well_formed"):
            first = record["errors"][0]
            key = f"{first['type_name']} | {_template(first['message'])}"
        elif failed:
            last = (record.get("traceback") or "").strip().splitlines()[-1:] or [status]
            key = f"{status} | {_template(last[0])}"
        else:
            continue
        cluster = clusters.setdefault(
            key,
            {
                "key": key,
                "samples": 0,
                "causes": Counter(),
                "modes": Counter(),
                "schemas": set(),
                "examples": [],
            },
        )
        cluster["samples"] += 1
        cluster["causes"][record.get("cause", status)] += 1
        cluster["modes"][mode] += 1
        if record["schema"] not in cluster["schemas"] and len(cluster["examples"]) < 5:
            cluster["examples"].append(
                {
                    k: record.get(k)
                    for k in ("schema", "element", "mode", "errors", "report", "sample_file", "traceback")
                }
            )
        cluster["schemas"].add(record["schema"])

    def _jsonable(entry: dict) -> dict:
        return {
            k: (sorted(v) if isinstance(v, set) else dict(v) if isinstance(v, Counter) else v)
            for k, v in entry.items()
        }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "totals": dict(totals),
        "schemas": schemas,
        "clusters": sorted((_jsonable(c) for c in clusters.values()), key=lambda c: -c["samples"]),
        "reasons": dict(
            sorted(((k, _jsonable(v)) for k, v in reasons.items()), key=lambda kv: -kv[1]["failed_samples"])
        ),
    }


def _print_summary(summary: dict) -> None:
    totals = summary["totals"]
    for mode in MODES:
        row = {k.split(":", 1)[1]: v for k, v in totals.items() if k.startswith(f"{mode}:")}
        print(
            f"{mode:9} {sum(row.values()):6} samples  "
            + "  ".join(f"{k}={v}" for k, v in sorted(row.items()))
        )
    print()
    for meta in summary["schemas"]:
        counts = meta.get("counts") or {}
        cells = []
        for mode in MODES:
            total = sum(v for k, v in counts.items() if k.startswith(f"{mode}:"))
            cells.append(f"{mode[:3]} {counts.get(f'{mode}:valid', 0)}/{total}")
        note = (
            meta.get("setup_error")
            and "setup_error"
            or (meta["status"] if meta["status"] != "loaded" else "")
        )
        print(f"  {'  '.join(cells):24} {note:12} {meta['url']}")
    print("\nTop clusters:")
    for cluster in summary["clusters"][:25]:
        print(f"  {cluster['samples']:6}  {len(cluster['schemas']):2} schemas  {cluster['key'][:150]}")


# ---------------------------------------------------------------------------
# Compare two runs
# ---------------------------------------------------------------------------


def compare(before: Path, after: Path) -> int:
    def statuses(out_dir: Path) -> dict[tuple[str, str, str], str]:
        return {(r["schema"], r["element_id"], r["mode"]): r["status"] for r in _iter_records(out_dir)}

    old, new = statuses(before), statuses(after)
    shared = old.keys() & new.keys()
    improved = [k for k in shared if old[k] != "valid" and new[k] == "valid"]
    regressed = [k for k in shared if old[k] == "valid" and new[k] != "valid"]
    for label, table in (("before", old), ("after", new)):
        counts = Counter(table[k] for k in shared)
        print(f"{label:7} " + "  ".join(f"{s}={n}" for s, n in sorted(counts.items())))
    by_schema: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for key in improved:
        by_schema[key[0]][0] += 1
    for key in regressed:
        by_schema[key[0]][1] += 1
    print(f"\nimproved {len(improved)}, regressed {len(regressed)} (of {len(shared)} shared samples)")
    for schema, (up, down) in sorted(by_schema.items(), key=lambda kv: -kv[1][0]):
        print(f"  +{up:<6} -{down:<4} {schema}")
    for key in regressed[:50]:
        print(f"  REGRESSED {new[key]:16} {key[2]:9} {key[1]}  {key[0]}")
    return 1 if regressed else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def run(args: argparse.Namespace) -> int:
    urls = [
        line.strip()
        for line in Path(args.urls).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    out_dir, cache_dir = Path(args.out), Path(args.cache_dir)
    (out_dir / "results").mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    with ProcessPoolExecutor(args.jobs) as pool:
        loads = list(pool.map(load_schema, urls, [cache_dir] * len(urls)))
    schemas: list[dict] = []
    unique: dict[str, dict] = {}
    for meta in loads:
        if meta["status"] != "loaded":
            print(f"  {meta['status']}: {meta['url']} — {meta['detail']}")
            schemas.append(meta)
        elif args.skip_over is not None and meta["elements"] > args.skip_over:
            print(f"  skipped ({meta['elements']} global elements): {meta['url']}")
            schemas.append(meta | {"status": "skipped_large"})
        elif meta["content_hash"] in unique:
            unique[meta["content_hash"]]["duplicates"].append(meta["url"])
        else:
            unique[meta["content_hash"]] = meta | {"key": _slug(meta["url"]), "duplicates": []}

    audited: list[dict] = []
    with ProcessPoolExecutor(args.jobs) as pool:
        # Largest first, so the long runs start before the pool is busy with small ones.
        futures = {
            pool.submit(
                audit_schema, meta, out_dir, args.max_elements, args.sample_timeout, args.budget
            ): meta
            for meta in sorted(unique.values(), key=lambda m: -m["elements"])
        }
        for future in as_completed(futures):
            meta = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = meta | {"status": "audit_crash", "detail": f"{type(exc).__name__}: {exc}"[:500]}
            audited.append(result)
            valid = sum(v for k, v in (result.get("counts") or {}).items() if k.endswith(":valid"))
            total = sum((result.get("counts") or {}).values())
            print(
                f"  done {valid:6}/{total:<6} valid  {result.get('audit_ms', 0) / 1000:7.1f}s  {meta['url']}",
                flush=True,
            )

    summary = summarise(out_dir, schemas + sorted(audited, key=lambda m: m["url"]))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print()
    _print_summary(summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit generated sample XML against real schemas.")
    parser.add_argument("--urls", help="file with one schema URL per line (# comments allowed)")
    parser.add_argument("--out", help="output directory for this run")
    parser.add_argument(
        "--cache-dir", default=".sample-audit-cache", help="parsed-model cache (outside the repo)"
    )
    parser.add_argument("--jobs", type=int, default=4, help="worker processes")
    parser.add_argument(
        "--max-elements", type=int, default=None, help="cap global elements per schema (smoke runs)"
    )
    parser.add_argument(
        "--skip-over",
        type=int,
        default=None,
        metavar="N",
        help="leave out schemas with more than N global elements (taxonomies like US-GAAP)",
    )
    parser.add_argument("--sample-timeout", type=float, default=30.0, help="seconds per generate+validate")
    parser.add_argument(
        "--budget", type=float, default=3600.0, help="seconds per schema before skipping the rest"
    )
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="diff two output directories")
    args = parser.parse_args()
    if args.compare:
        return compare(Path(args.compare[0]), Path(args.compare[1]))
    if not args.urls or not args.out:
        parser.error("--urls and --out are required unless --compare is given")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
