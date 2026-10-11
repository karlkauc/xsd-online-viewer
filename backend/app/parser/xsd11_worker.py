"""Validate one document against an XSD 1.1 schema, in a process of its own.

Run as a script by :mod:`app.parser.validation`, never imported by the app.
``xmlschema`` is pure Python: it compiles a large schema in seconds rather
than milliseconds, its patterns run on the backtracking ``re`` engine, and an
``xs:assert`` is an XPath expression the schema author chose. None of that can
be interrupted inside a worker thread, so it runs here, where the parent can
kill it and the limits below hold whatever the schema does.

Protocol: a JSON request on stdin, a JSON reply on stdout.

    {"root": dir, "main": path, "locations": [[namespace, path], ...],
     "urls": {url-without-scheme: path}, "xml": text, "cpu_seconds": n, "memory_mb": n}

    {"status": "ok", "errors": [{"line", "message", "path", "type_name", "declaration"}, ...]}
    {"status": "schema-error", "message": text, "file": path | null, "line": n | null}
    {"status": "unavailable", "message": text}
    {"status": "validator-error", "message": text}   (xmlschema itself failed)
"""

from __future__ import annotations

import json
import resource
import sys
from io import BytesIO


def _limit(request: dict) -> None:
    cpu = int(request.get("cpu_seconds") or 0)
    if cpu:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    memory = int(request.get("memory_mb") or 0) * 1024 * 1024
    if memory:
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))


def _url_key(url: str) -> str:
    rest = url.split("://", 1)[1]
    return rest.split("#", 1)[0].split("?", 1)[0]


def _schema_error(exc: Exception) -> dict:
    """Where and why the schema does not compile, without xmlschema's multi-line dump."""
    message = getattr(exc, "message", None) or str(exc)
    elem = getattr(exc, "elem", None)
    validator = getattr(exc, "validator", None)
    schema = getattr(validator, "schema", None) or validator
    return {
        "status": "schema-error",
        "message": str(message).strip(),
        "file": getattr(schema, "url", None),
        "line": getattr(elem, "sourceline", None),
    }


def _error(error) -> dict:  # noqa: ANN001 - xmlschema.XMLSchemaValidationError
    validator = error.validator
    message = str(error.reason or error.message)
    test = getattr(validator, "path", None)
    if test and type(validator).__name__ == "XsdAssert":
        # "assertion test is false" does not say which of several it was.
        message = f"{message}: {test}"
    # A content-model error is reported on the parent; the child is what to look at.
    at = getattr(error, "invalid_child", None)
    if at is None:
        at = error.elem
    name = getattr(validator, "name", None)
    return {
        "line": getattr(at, "sourceline", None),
        "message": message,
        "path": error.path,
        "type_name": type(validator).__name__,
        "declaration": name if isinstance(name, str) else None,
    }


def run(request: dict) -> dict:
    _limit(request)
    try:
        import xmlschema
        from lxml import etree
    except ImportError as exc:
        return {"status": "unavailable", "message": str(exc)}

    urls: dict[str, str] = request.get("urls") or {}

    def mapper(uri: str) -> str:
        # An absolute schemaLocation names the URL the file was fetched from;
        # the copy on disk is the only one this process may read.
        return urls.get(_url_key(uri), uri) if "://" in uri and not uri.startswith("file:") else uri

    try:
        schema = xmlschema.XMLSchema11(
            request["main"],
            locations=[tuple(pair) for pair in request.get("locations") or ()],
            base_url=request["root"],
            allow="sandbox",
            uri_mapper=mapper,
        )
    except (xmlschema.XMLSchemaException, etree.LxmlError, OSError, ValueError, SyntaxError) as exc:
        return _schema_error(exc)

    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
    tree = etree.parse(BytesIO(request["xml"].encode("utf-8")), parser)
    try:
        return {"status": "ok", "errors": [_error(e) for e in schema.iter_errors(tree)]}
    except (MemoryError, RecursionError):
        raise  # a limit, which the caller reports as such
    except Exception as exc:  # noqa: BLE001 - a defect in the validator, whatever it raises
        # E.g. a KeyError for an xs:keyref used by reference (xmlschema 4.1).
        return {"status": "validator-error", "message": f"{type(exc).__name__}: {exc}"[:300]}


if __name__ == "__main__":
    json.dump(run(json.load(sys.stdin)), sys.stdout)
