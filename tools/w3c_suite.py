#!/usr/bin/env python3
"""Run the W3C XML Schema test suite through the viewer's own code paths.

The suite (https://github.com/w3c/xsdtests, about 15,000 schema tests and
26,000 instance tests for XSD 1.0 and 1.1) says for every schema whether it
is valid, and for every instance document whether it is valid against its
schema. This tool feeds each test to the code the app runs for a user:

* the schema is loaded with ``parse_files_map`` (the upload path), which must
  never crash and should not warn about a schema the suite calls valid;
* ``validate_xml`` then says whether the schema compiles and whether each
  instance is valid -- libxml2 for XSD 1.0, the ``xmlschema`` worker for 1.1,
  chosen by the app's own version detection -- and the verdict is compared
  with the expected one;
* with ``--samples N`` a sample document is generated for the first N global
  elements of every valid schema and validated the same way.

Every disagreement is a line of the work list: a parser crash, a valid schema
or document we reject, an invalid one we accept, a 1.1 test the detection
sent to the 1.0 validator, a sample that does not validate.

The suite is not part of this repository (it belongs to the W3C and its
contributors, about 200 MB). ``--fetch`` clones it into ``--suite``.

Output directory:
    results.jsonl   one line per test
    summary.json    totals, per test set, and the largest clusters of findings

Usage:
    python3 tools/w3c_suite.py --fetch                       # once
    python3 tools/w3c_suite.py --out audit/w3c               # the whole suite
    python3 tools/w3c_suite.py --out audit/w3c-id --only IdConstr --samples 3
    python3 tools/w3c_suite.py --compare audit/before audit/after   # exit 1 on regressions

What it cannot see: anything the frontend does with the model (tree, diagram,
detail panel), and whether the model is *right* beyond what validation and
the sample generator make of it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path, PurePosixPath

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.parser.sample import SampleOptions, generate_sample_with_report  # noqa: E402
from app.parser.security import SecurityError  # noqa: E402
from app.parser.validation import ValidationSetupError, validate_xml  # noqa: E402
from app.parser.xsd_parser import parse_files_map  # noqa: E402

SUITE_URL = "https://github.com/w3c/xsdtests.git"
DEFAULT_SUITE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / (
    "xsd-viewer/xsdtests"
)
TS = "{http://www.w3.org/XML/2004/xml-schema-test-suite/}"
HREF = "{http://www.w3.org/1999/xlink}href"

# A document no schema of the suite declares: validating it only tells
# whether the schema itself compiles.
PROBE = b"<w3c-suite-probe-7f3a/>"
# Verdicts that are findings. ``not_checked`` is one too: the app could not
# say anything about a test the suite has an answer for.
FINDINGS = (
    "parser_crash",
    "parser_rejected",
    "rejected_valid",
    "accepted_invalid",
    "not_checked",
    "sample_invalid",
    "sample_crash",
    "timeout",
)


# ---------------------------------------------------------------------------
# Reading the suite
# ---------------------------------------------------------------------------


class _SuiteFiles(dict):
    """The suite directory as the name -> bytes map ``parse_files_map`` takes, read on demand."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _path(self, name: object) -> Path | None:
        if not isinstance(name, str) or not name or name.startswith(("/", "..")):
            return None
        path = self.root / name
        return path if path.is_file() else None

    def __contains__(self, name: object) -> bool:
        return self._path(name) is not None

    def __getitem__(self, name: str) -> bytes:
        path = self._path(name)
        if path is None:
            raise KeyError(name)
        return path.read_bytes()


def _versions(*elements: etree._Element | None) -> set[str]:
    """The ``version`` tokens in effect: the innermost element that has any."""
    for element in elements:
        if element is not None and element.get("version"):
            return set(element.get("version").split())
    return set()


def _expectations(test: etree._Element) -> dict[str, str]:
    """Expected validity by processor version; ``""`` is the one for every version."""
    out: dict[str, str] = {}
    for expected in test.findall(TS + "expected"):
        for token in (expected.get("version") or "").split() or [""]:
            out[token] = expected.get("validity") or ""
    return out


def _status(test: etree._Element) -> str:
    current = test.find(TS + "current")
    return (current.get("status") if current is not None else None) or "accepted"


def _href(element: etree._Element, base: PurePosixPath) -> str:
    """A document reference as a path relative to the suite root."""
    parts: list[str] = []
    for part in (base / element.get(HREF, "")).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def read_groups(suite: Path, only: list[str]) -> list[dict]:
    """Every test group of the suite as a plain dict a worker process can take."""
    groups: list[dict] = []
    index = etree.parse(str(suite / "suite.xml"))
    for ref in index.iter(TS + "testSetRef"):
        set_path = PurePosixPath(ref.get(HREF))
        if only and not any(o.lower() in str(set_path).lower() for o in only):
            continue
        test_set = etree.parse(str(suite / set_path)).getroot()
        base = set_path.parent
        for group in test_set.iter(TS + "testGroup"):
            schema_test = group.find(TS + "schemaTest")
            entry = {
                "set": test_set.get("name") or set_path.stem,
                "group": group.get("name"),
                "schema": None,
                "instances": [],
            }
            if schema_test is not None:
                entry["schema"] = {
                    "name": schema_test.get("name"),
                    "documents": [
                        _href(d, base) for d in schema_test.findall(TS + "schemaDocument")
                    ],
                    "expected": _expectations(schema_test),
                    "versions": sorted(_versions(schema_test, group, test_set)),
                    "status": _status(schema_test),
                }
            for instance in group.findall(TS + "instanceTest"):
                document = instance.find(TS + "instanceDocument")
                if document is None:
                    continue
                entry["instances"].append(
                    {
                        "name": instance.get("name"),
                        "document": _href(document, base),
                        "expected": _expectations(instance),
                        "versions": sorted(_versions(instance, group, test_set)),
                        "status": _status(instance),
                    }
                )
            if entry["schema"] or entry["instances"]:
                groups.append(entry)
    return groups


# ---------------------------------------------------------------------------
# Running one group
# ---------------------------------------------------------------------------


class _TimeoutError(Exception):
    pass


def _on_alarm(_signum, _frame):  # noqa: ANN001, ANN202
    raise _TimeoutError


_REFERENCE = re.compile(rb"""schemaLocation\s*=\s*["']([^"']+)["']""")


def _main_document(suite: Path, documents: list[str]) -> str:
    """The document the others hang off: the one that references most of them.

    A schema test may list several documents; the app loads one main file and
    follows its references, so the one that pulls in the rest is the main.
    """
    if len(documents) == 1:
        return documents[0]
    names = {PurePosixPath(d).name for d in documents}
    best, best_hits = documents[-1], -1
    for document in documents:
        try:
            content = (suite / document).read_bytes()
        except OSError:
            continue
        hits = sum(
            1
            for m in _REFERENCE.finditer(content)
            if PurePosixPath(m.group(1).decode("utf-8", "replace").replace("\\", "/")).name in names
        )
        if hits > best_hits:
            best, best_hits = document, hits
    return best


def _expected_for(expected: dict[str, str], mode: str) -> str | None:
    """The validity the suite expects from a processor of version ``mode``."""
    value = expected.get(mode, expected.get(""))
    return value if value in ("valid", "invalid") else None


def _mode_of_error(model, message: str) -> str:  # noqa: ANN001 - SchemaModel
    return "1.1" if model.xsd_version == "1.1" or "XSD 1.1" in message else "1.0"


def _shape(message: str) -> str:
    """``message`` without the names and numbers that differ from test to test."""
    message = re.sub(r"'[^']*'|\"[^\"]*\"|\{[^}]*\}[\w.-]*", "…", message)
    message = re.sub(r"\b[\w./-]+\.(?:xsd|xml)\b", "…", message)
    return re.sub(r"\d+", "N", message)[:160]


def _verdict(expected: str | None, valid: bool) -> str:
    if expected is None:
        return "skipped"
    if valid:
        return "ok" if expected == "valid" else "accepted_invalid"
    return "ok" if expected == "invalid" else "rejected_valid"


def _wrong_version(versions: list[str], mode: str) -> bool:
    """Whether the test is for the other XSD version than the validator that ran."""
    relevant = {v for v in versions if v in ("1.0", "1.1")}
    return bool(relevant) and mode not in relevant


def run_group(group: dict, suite_dir: str, samples: int, timeout: float) -> list[dict]:
    """Every test of one group, as result records."""
    signal.signal(signal.SIGALRM, _on_alarm)
    suite = Path(suite_dir)
    records: list[dict] = []
    base = {"set": group["set"], "group": group["group"]}
    model = None
    schema_ok = False

    def record(kind: str, test: dict, verdict: str, **extra: object) -> None:
        records.append({**base, "kind": kind, "test": test["name"], "verdict": verdict, **extra})

    schema = group["schema"]
    if schema is not None and schema["documents"]:
        main = _main_document(suite, schema["documents"])
        extra: dict[str, object] = {"document": main, "status": schema["status"]}
        if len(schema["documents"]) > 1:
            extra["documents"] = len(schema["documents"])
        signal.setitimer(signal.ITIMER_REAL, timeout)
        try:
            try:
                model = parse_files_map(_SuiteFiles(suite), main)
            except ValueError as exc:
                # The app's answer to a file it cannot read as a schema at all.
                expected = _expected_for(schema["expected"], "1.0") or _expected_for(
                    schema["expected"], "1.1"
                )
                record(
                    "schema",
                    schema,
                    "ok" if expected == "invalid" else "parser_rejected",
                    detail=str(exc)[:300],
                    **extra,
                )
            else:
                extra["detected"] = model.xsd_version
                warnings = [d.message for d in model.diagnostics]
                try:
                    result = validate_xml(model, PROBE)
                except ValidationSetupError as exc:
                    message = str(exc)
                    mode = _mode_of_error(model, message)
                    expected = _expected_for(schema["expected"], mode)
                    if message.startswith("the schema itself is not valid"):
                        verdict = _verdict(expected, valid=False)
                    else:
                        verdict = "skipped" if expected is None else "not_checked"
                    record("schema", schema, verdict, mode=mode, detail=message[:300], **extra)
                else:
                    mode = "1.1" if result.validator == "xmlschema" else "1.0"
                    expected = _expected_for(schema["expected"], mode)
                    verdict = _verdict(expected, valid=True)
                    schema_ok = True
                    if expected == "valid" and warnings:
                        # Not a wrong verdict, but the viewer complains about
                        # a schema there is nothing wrong with.
                        extra["warnings"] = warnings[:5]
                    record("schema", schema, verdict, mode=mode, **extra)
                if _wrong_version(schema["versions"], records[-1].get("mode", "1.0")):
                    records[-1]["wrong_version"] = True
        except _TimeoutError:
            record("schema", schema, "timeout", **extra)
        except Exception as exc:  # noqa: BLE001 - a crash is the finding
            record(
                "schema",
                schema,
                "parser_crash",
                detail=f"{type(exc).__name__}: {exc}"[:300],
                trace=traceback.format_exc()[-1500:],
                **extra,
            )
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    for instance in group["instances"]:
        extra = {"document": instance["document"], "status": instance["status"]}
        if model is None:
            # No schema in the group (it comes from xsi:schemaLocation), or
            # one the app could not load: nothing to validate against.
            record("instance", instance, "skipped", detail="no schema loaded", **extra)
            continue
        try:
            content = (suite / instance["document"]).read_bytes()
        except OSError:
            record("instance", instance, "skipped", detail="file missing from the suite", **extra)
            continue
        signal.setitimer(signal.ITIMER_REAL, timeout)
        try:
            try:
                result = validate_xml(model, content)
            except SecurityError as exc:
                # What the API answers with 400: a document with a DTD the
                # app refuses to read. A decision, but one that leaves the
                # test unanswered.
                record("instance", instance, "not_checked", detail=str(exc)[:300], **extra)
                continue
            except ValidationSetupError as exc:
                message = str(exc)
                mode = _mode_of_error(model, message)
                expected = _expected_for(instance["expected"], mode)
                record(
                    "instance",
                    instance,
                    "skipped" if expected is None else "not_checked",
                    mode=mode,
                    detail=message[:300],
                    **extra,
                )
            else:
                mode = "1.1" if result.validator == "xmlschema" else "1.0"
                expected = _expected_for(instance["expected"], mode)
                verdict = _verdict(expected, result.is_valid)
                if verdict == "rejected_valid":
                    extra["detail"] = "; ".join(e.message for e in result.errors[:3])[:300]
                record("instance", instance, verdict, mode=mode, **extra)
            if _wrong_version(instance["versions"], records[-1].get("mode", "1.0")):
                records[-1]["wrong_version"] = True
                # Nothing in such a schema says which version it is for; the
                # app lets its user say. The verdict when they do:
                declared = "1.1" if "1.1" in instance["versions"] else "1.0"
                try:
                    chosen = validate_xml(model, content, version=declared)
                except (SecurityError, ValidationSetupError):
                    records[-1]["as_declared"] = "not_checked"
                else:
                    records[-1]["as_declared"] = _verdict(
                        _expected_for(instance["expected"], declared), chosen.is_valid
                    )
        except _TimeoutError:
            record("instance", instance, "timeout", **extra)
        except Exception as exc:  # noqa: BLE001
            record(
                "instance",
                instance,
                "parser_crash",
                detail=f"{type(exc).__name__}: {exc}"[:300],
                trace=traceback.format_exc()[-1500:],
                **extra,
            )
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    if samples and model is not None and schema_ok and records and records[0]["verdict"] == "ok":
        elements = [e for e in model.elements if e.name and not e.abstract][:samples]
        for element in elements:
            test = {"name": f"{schema['name']}#{element.name}"}
            extra = {"document": records[0].get("document"), "status": schema["status"]}
            signal.setitimer(signal.ITIMER_REAL, timeout)
            try:
                xml, report = generate_sample_with_report(model, element, SampleOptions())
                try:
                    result = validate_xml(model, xml.encode("utf-8"))
                except ValidationSetupError as exc:
                    record("sample", test, "not_checked", detail=str(exc)[:300], **extra)
                else:
                    if result.is_valid:
                        record("sample", test, "ok", **extra)
                    else:
                        record(
                            "sample",
                            test,
                            "sample_invalid",
                            detail="; ".join(e.message for e in result.errors[:3])[:300],
                            # What the generator itself said it could not do.
                            report=report.counts,
                            **extra,
                        )
            except _TimeoutError:
                record("sample", test, "timeout", **extra)
            except Exception as exc:  # noqa: BLE001
                record(
                    "sample",
                    test,
                    "sample_crash",
                    detail=f"{type(exc).__name__}: {exc}"[:300],
                    trace=traceback.format_exc()[-1500:],
                    **extra,
                )
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
    return records


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def summarise(records: list[dict], suite_revision: str | None) -> dict:
    by_kind: dict[str, Counter] = defaultdict(Counter)
    by_set: dict[str, Counter] = defaultdict(Counter)
    clusters: dict[str, Counter] = defaultdict(Counter)
    examples: dict[tuple[str, str], str] = {}
    warnings: Counter = Counter()
    wrong_version = Counter()
    as_declared: Counter = Counter()
    unreported = 0
    for r in records:
        verdict = r["verdict"]
        if verdict == "sample_invalid" and not r.get("report"):
            unreported += 1
        by_kind[r["kind"]][verdict] += 1
        by_set[r["set"]][verdict] += 1
        if r.get("wrong_version") and verdict in FINDINGS:
            wrong_version[r["kind"]] += 1
        if r.get("as_declared") and (verdict in FINDINGS or r["as_declared"] in FINDINGS):
            as_declared[f"{verdict} -> {r['as_declared']}"] += 1
        if verdict in FINDINGS:
            shape = _shape(r.get("detail") or "(no message)")
            key = f"{r['kind']} {verdict}"
            clusters[key][shape] += 1
            examples.setdefault((key, shape), r.get("document") or r["test"])
        for message in r.get("warnings", ()):
            warnings[_shape(message)] += 1
    return {
        "suite_revision": suite_revision,
        "tests": len(records),
        "by_kind": {
            kind: {
                **dict(counts.most_common()),
                "agreement": _share(counts),
            }
            for kind, counts in sorted(by_kind.items())
        },
        "findings_on_tests_for_the_other_xsd_version": dict(wrong_version),
        # Instances of those tests again, validated as the version the test is for.
        "those_instances_with_the_version_chosen": dict(as_declared.most_common()),
        # The generator's report said nothing, so the sample claimed to be valid.
        "invalid_samples_the_generator_did_not_report": unreported,
        "sets_with_most_findings": [
            {"set": name, **{k: v for k, v in counts.items() if k in FINDINGS}}
            for name, counts in sorted(
                by_set.items(), key=lambda item: -sum(item[1][f] for f in FINDINGS)
            )[:25]
            if sum(counts[f] for f in FINDINGS)
        ],
        "clusters": {
            key: [
                {"count": count, "message": shape, "example": examples[(key, shape)]}
                for shape, count in counter.most_common(15)
            ]
            for key, counter in sorted(clusters.items())
        },
        "warnings_on_valid_schemas": [
            {"count": count, "message": shape} for shape, count in warnings.most_common(15)
        ],
    }


def _share(counts: Counter) -> str:
    """Tests the app agrees with the suite on, among those with an expectation."""
    decided = sum(v for k, v in counts.items() if k != "skipped")
    return f"{counts['ok'] / decided:.1%}" if decided else "n/a"


def print_summary(summary: dict) -> None:
    print(f"\n{summary['tests']} tests")
    for kind, counts in summary["by_kind"].items():
        rest = ", ".join(f"{k} {v}" for k, v in counts.items() if k != "agreement")
        print(f"  {kind:9} agreement {counts['agreement']:>6}   {rest}")
    print(
        "  invalid samples the generator did not report: "
        f"{summary['invalid_samples_the_generator_did_not_report']}"
    )
    for key, items in summary["clusters"].items():
        print(f"\n{key}")
        for item in items[:6]:
            print(f"  {item['count']:6}  {item['message']}   [{item['example']}]")
    if summary["warnings_on_valid_schemas"]:
        print("\nwarnings on schemas the suite calls valid")
        for item in summary["warnings_on_valid_schemas"][:6]:
            print(f"  {item['count']:6}  {item['message']}")


def _load(directory: Path) -> dict[tuple, dict]:
    path = directory / "results.jsonl"
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return {(r["set"], r["group"], r["kind"], r["test"]): r for r in rows}


def compare(before_dir: Path, after_dir: Path) -> int:
    before, after = _load(before_dir), _load(after_dir)
    fixed = [k for k, r in after.items() if r["verdict"] == "ok" and before.get(k, r)["verdict"] in FINDINGS]
    broken = [k for k, r in after.items() if r["verdict"] in FINDINGS and before.get(k, r)["verdict"] == "ok"]
    print(f"fixed: {len(fixed)}   regressions: {len(broken)}")
    for key in broken[:50]:
        print(f"  REGRESSION {key[0]}/{key[1]} {key[2]} {key[3]}: {after[key]['verdict']}"
              f" — {after[key].get('detail', '')[:120]}")
    return 1 if broken else 0


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _revision(suite: Path) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(suite), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return done.stdout.strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="checkout of w3c/xsdtests")
    parser.add_argument("--fetch", action="store_true", help="clone the suite into --suite and exit")
    parser.add_argument("--out", type=Path, help="directory for results.jsonl and summary.json")
    parser.add_argument(
        "--only", action="append", default=[], help="only test sets whose path contains this"
    )
    parser.add_argument("--limit", type=int, default=0, help="stop after this many test groups")
    parser.add_argument(
        "--samples", type=int, default=0, help="global elements per valid schema to sample"
    )
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds per test")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()

    if args.compare:
        return compare(*args.compare)
    if args.fetch:
        if (args.suite / "suite.xml").exists():
            print(f"already there: {args.suite}")
            return 0
        args.suite.parent.mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            ["git", "clone", "--depth", "1", SUITE_URL, str(args.suite)], check=False
        ).returncode
    if not (args.suite / "suite.xml").exists():
        parser.error(f"no suite at {args.suite}; run with --fetch first")
    if args.out is None:
        parser.error("--out is required")

    groups = read_groups(args.suite, args.only)
    if args.limit:
        groups = groups[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    records: list[dict] = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(run_group, group, str(args.suite), args.samples, args.timeout): group
            for group in groups
        }
        for done, future in enumerate(as_completed(futures), 1):
            group = futures[future]
            try:
                records.extend(future.result())
            except Exception as exc:  # noqa: BLE001 - the worker process itself died
                records.append(
                    {
                        "set": group["set"],
                        "group": group["group"],
                        "kind": "schema",
                        "test": group["group"],
                        "verdict": "parser_crash",
                        "detail": f"worker died: {type(exc).__name__}: {exc}"[:300],
                    }
                )
            if done % 500 == 0 or done == len(futures):
                elapsed = time.monotonic() - started
                print(f"  {done}/{len(futures)} groups, {elapsed:.0f} s", file=sys.stderr)

    records.sort(key=lambda r: (r["set"], r["group"] or "", r["kind"], r["test"] or ""))
    with (args.out / "results.jsonl").open("w", encoding="utf-8") as handle:
        for r in records:
            handle.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarise(records, _revision(args.suite))
    summary["seconds"] = int(time.monotonic() - started)
    summary["options"] = {"only": args.only, "limit": args.limit, "samples": args.samples}
    (args.out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print_summary(summary)
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
