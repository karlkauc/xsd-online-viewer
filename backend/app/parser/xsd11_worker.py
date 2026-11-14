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

Compiling a large schema is most of the work (FundsXML, 8 MB: about 7 s;
loading it pickled: 0.3 s). ``"compiled": path`` names a pickle of the schema
a previous worker wrote; ``"store": path`` asks for one, written after the
reply, so the caller has its answer before the pickling starts. Only workers
read these pickles, and only workers write them.

A request with ``"check": "1.0" | "1.1"`` and no ``xml`` asks what is wrong with
the schema itself, read as that version:

    {"status": "checked", "findings": [{"message", "file", "line"}, ...], "more": n}
"""

from __future__ import annotations

import contextlib
import json
import os
import pickle
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


_FINDINGS = 50


def _line_of(error, lines: dict) -> int | None:  # noqa: ANN001 - xmlschema.XMLSchemaParseError
    """The source line of the element an error is about.

    xmlschema reads schemas with ElementTree, which keeps no line numbers; the
    element's position in document order finds it again in an lxml parse.
    """
    from lxml import etree

    elem = getattr(error, "elem", None)
    schema = getattr(getattr(error, "validator", None), "schema", None)
    url = getattr(schema, "url", None)
    root = getattr(getattr(schema, "source", None), "root", None)
    if elem is None or root is None or not url or not url.startswith("file://"):
        return getattr(elem, "sourceline", None)
    if url not in lines:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        try:
            located = [e.sourceline for e in etree.parse(url[7:], parser).getroot().iter("*")]
        except (etree.LxmlError, OSError):
            located = []
        lines[url] = ([id(e) for e in root.iter()], located)
    ids, located = lines[url]
    try:
        index = ids.index(id(elem))
    except ValueError:
        return None
    return located[index] if len(located) == len(ids) else None


def check(request: dict) -> dict:
    """Every rule of XSD the schema breaks, as far as xmlschema finds them."""
    try:
        import xmlschema
        from lxml import etree
    except ImportError as exc:
        return {"status": "unavailable", "message": str(exc)}
    mapper = _UriMapper(request.get("urls") or {})
    reader = xmlschema.XMLSchema11 if request["check"] == "1.1" else xmlschema.XMLSchema10
    try:
        schema = reader(
            request["main"],
            locations=[tuple(pair) for pair in request.get("locations") or ()],
            base_url=request["root"],
            allow="sandbox",
            uri_mapper=mapper,
            validation="lax",
        )
        # Of every file read, not only the main one.
        errors = list(getattr(schema.maps, "all_errors", None) or schema.all_errors)
    except (xmlschema.XMLSchemaException, etree.LxmlError, OSError, ValueError, SyntaxError) as exc:
        # What stops the reading altogether, lax or not.
        errors = [exc]
    except (MemoryError, RecursionError):
        raise
    except Exception as exc:  # noqa: BLE001 - a defect in the validator
        return {"status": "validator-error", "message": f"{type(exc).__name__}: {exc}"[:300]}
    lines: dict = {}
    findings, seen = [], set()
    for error in errors:
        found = _schema_error(error)
        line = _line_of(error, lines)
        key = (found["message"], found["file"], line, id(getattr(error, "elem", None)))
        if key in seen:
            continue
        seen.add(key)
        # Without the dump of the component and its path that some messages carry.
        message = found["message"].split("\n\nSchema component", 1)[0].split("\n\nPath:", 1)[0]
        findings.append({"message": message.strip()[:500], "file": found["file"], "line": line})
    return {
        "status": "checked",
        "findings": findings[:_FINDINGS],
        "more": max(0, len(findings) - _FINDINGS),
    }


class _UriMapper:
    """An absolute schemaLocation names the URL the file was fetched from; the
    copy on disk is the only one this process may read. A class, not a closure:
    the compiled schema keeps it, and is pickled with it."""

    def __init__(self, urls: dict[str, str]) -> None:
        self.urls = urls

    def __call__(self, uri: str) -> str:
        return self.urls.get(_url_key(uri), uri) if "://" in uri and not uri.startswith("file:") else uri


# The schema this process compiled, for ``_store_compiled`` after the reply.
_COMPILED: list = []


def _load_compiled(path: str | None):  # noqa: ANN202 - an xmlschema.XMLSchema11
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            return pickle.load(fh)  # noqa: S301 - written by a worker like this one
    except Exception:  # noqa: BLE001 - any broken pickle: compile instead
        return None


def _store_compiled(path: str | None) -> None:
    if not path or not _COMPILED:
        return
    try:
        with open(path + ".part", "wb") as fh:
            pickle.dump(_COMPILED[0], fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(path + ".part", path)
    except Exception:  # noqa: BLE001 - only a missed speed-up; the reply is out
        pass


def run(request: dict) -> dict:
    _limit(request)
    if request.get("check"):
        return check(request)
    try:
        import xmlschema
        from lxml import etree
    except ImportError as exc:
        return {"status": "unavailable", "message": str(exc)}

    mapper = _UriMapper(request.get("urls") or {})
    schema = _load_compiled(request.get("compiled"))
    if schema is None:
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
        _COMPILED.append(schema)

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
    request = json.load(sys.stdin)
    reply = run(request)
    json.dump(reply, sys.stdout)
    if reply.get("status") == "ok":
        # Closing stdout hands the caller its answer; the pickle comes after.
        sys.stdout.close()
        with contextlib.suppress(OSError):
            os.close(1)  # the std streams leave their descriptor open
        _store_compiled(request.get("store"))
