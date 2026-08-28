import type { ReactNode } from "react";

/**
 * Public documentation for driving the validation API from the command line
 * (curl, PowerShell, Python). Rendered at /api-docs — see modeRoute.ts and
 * backend/app/spa.py, which must both know the route.
 *
 * Limits quoted here mirror backend/app/config.py, rate_limit.py, cache.py and
 * docs/DEPLOY_GCLOUD.md. Update both places when a limit changes.
 */

const API = "https://www.xsd-viewer.online/api";

function Code({ children }: { children: ReactNode }) {
  return (
    <code className="font-mono text-[0.88em] px-1 py-px rounded bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200">
      {children}
    </code>
  );
}

function Pre({ children }: { children: string }) {
  return (
    <pre className="my-3 p-4 rounded-md border border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-200 font-mono text-[13px] leading-relaxed overflow-x-auto">
      {children}
    </pre>
  );
}

function H2({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="mt-10 mb-3 text-xl font-semibold scroll-mt-4">
      {children}
    </h2>
  );
}

function H3({ children }: { children: ReactNode }) {
  return <h3 className="mt-6 mb-2 text-base font-semibold">{children}</h3>;
}

function Note({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="my-4 pl-4 pr-4 py-3 border-l-[3px] border-accent dark:border-accent-dark bg-white dark:bg-slate-900 rounded-r-md text-sm">
      <strong className="text-accent dark:text-accent-dark">{title}</strong> {children}
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto my-3">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            {head.map((h) => (
              <th
                key={h}
                className="text-left py-2 px-2 border-b border-slate-200 dark:border-slate-800 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((cells, i) => (
            <tr key={i}>
              {cells.map((c, j) => (
                <td key={j} className="py-2 px-2 border-b border-slate-200 dark:border-slate-800 align-top">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const TOC: { id: string; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "step-1", label: "1 · Load the XSD" },
  { id: "step-2", label: "2 · Validate the XML" },
  { id: "report", label: "The error report" },
  { id: "report-files", label: "Saving the report" },
  { id: "examples", label: "curl · PowerShell · Python" },
  { id: "limits", label: "Limits" },
  { id: "errors", label: "Error codes" },
];

export function ApiDocsPage() {
  return (
    <div className="h-full overflow-auto">
      <article className="max-w-3xl mx-auto px-4 py-8 text-[15px] leading-relaxed text-slate-800 dark:text-slate-200">
        <p className="font-mono text-xs uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-1">
          xsd-viewer.online · REST API
        </p>
        <h1 className="text-3xl font-semibold leading-tight [text-wrap:balance]">
          XML validation from the command line
        </h1>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Check well-formedness and validate XML against an XSD with <Code>curl</Code>, PowerShell or
          Python — and keep the error report as a file. No account, no API key.
        </p>

        <nav aria-label="On this page" className="mt-6 flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {TOC.map((t) => (
            <a key={t.id} href={`#${t.id}`} className="text-blue-600 dark:text-blue-400 hover:underline">
              {t.label}
            </a>
          ))}
        </nav>

        <H2 id="overview">Overview</H2>
        <p>
          Everything the web UI does is available as an HTTP API at <Code>{API}/</Code>. Validation is
          a two-step flow:
        </p>
        <ol className="my-3 space-y-2 list-decimal pl-6">
          <li>
            Upload the XSD (single file, zip bundle or URL). The response contains a <Code>schema_id</Code>.
          </li>
          <li>
            Validate the XML against that <Code>schema_id</Code>. The response is the complete error
            report as JSON.
          </li>
        </ol>
        <p>
          One call covers both checks: first <strong>well-formedness</strong> (is it valid XML at all?),
          then — if well-formed — <strong>schema validation</strong> against the XSD.
        </p>

        <H2 id="step-1">Step 1: Load the XSD and get a <Code>schema_id</Code></H2>
        <H3>Single XSD file</H3>
        <Pre>{`SCHEMA_ID=$(curl -s -F "file=@schema.xsd" \\
  ${API}/schema/upload | jq -r .schema_id)`}</Pre>
        <H3>Zip with several XSD files (includes / imports)</H3>
        <p>
          Name the root schema inside the zip with <Code>main_filename</Code>:
        </p>
        <Pre>{`SCHEMA_ID=$(curl -s -F "file=@schema-bundle.zip" -F "main_filename=Root.xsd" \\
  ${API}/schema/upload | jq -r .schema_id)`}</Pre>
        <H3>XSD from a URL</H3>
        <Pre>{`SCHEMA_ID=$(curl -s -H "Content-Type: application/json" \\
  -d '{"url":"https://example.com/schema.xsd"}' \\
  ${API}/schema/url | jq -r .schema_id)`}</Pre>
        <p>
          The response is <Code>{`{"schema_id": "…", "model": {…}}`}</Code>; <Code>model</Code> is the
          parsed schema structure and can be ignored here.
        </p>
        <Note title="Important:">
          the <Code>schema_id</Code> points to a server-side cache and expires after 60 minutes (see{" "}
          <a href="#limits" className="text-blue-600 dark:text-blue-400 hover:underline">
            Limits
          </a>
          ). A <Code>404 schema not found or expired</Code> during validation simply means: repeat step 1.
        </Note>

        <H2 id="step-2">Step 2: Validate the XML</H2>
        <H3>Upload an XML file</H3>
        <Pre>{`curl -s -F "file=@document.xml" \\
  ${API}/schema/$SCHEMA_ID/validate/upload \\
  -o report.json`}</Pre>
        <H3>XML from a URL</H3>
        <Pre>{`curl -s -H "Content-Type: application/json" \\
  -d '{"url":"https://example.com/document.xml"}' \\
  ${API}/schema/$SCHEMA_ID/validate/url \\
  -o report.json`}</Pre>
        <H3>XML as text in the JSON body</H3>
        <Pre>{`jq -Rs '{content: ., filename: "document.xml"}' document.xml \\
  | curl -s -H "Content-Type: application/json" -d @- \\
    ${API}/schema/$SCHEMA_ID/validate/text \\
    -o report.json`}</Pre>

        <H2 id="report">The error report</H2>
        <p>
          Validation always answers with <strong>HTTP 200</strong> — even when there are errors. The
          outcome is in the JSON body. That body <em>is</em> the error report; there is no separate
          download endpoint, so save it directly with <Code>-o report.json</Code>.
        </p>
        <Pre>{`{
  "schema_id": "…",
  "is_valid": false,
  "reformatted_xml": "<?xml version=…>\\n<Person xmlns=…>\\n  …",
  "errors": [
    {
      "line": 4,
      "column": null,
      "message": "Element '{http://example.com/simple}Age': This element is not expected. Expected is ( {http://example.com/simple}LastName ).",
      "severity": "error",
      "kind": "schema-validation",
      "path": "/*/*[2]",
      "type_name": null,
      "domain": "SCHEMASV"
    }
  ]
}`}</Pre>
        <Table
          head={["Field", "Meaning"]}
          rows={[
            [
              <Code>is_valid</Code>,
              <>
                <span className="text-green-700 dark:text-green-400 font-medium">true</span> = well-formed
                and schema-conformant.{" "}
                <span className="text-red-700 dark:text-red-400 font-medium">false</span> = at least one
                entry in <Code>errors</Code>.
              </>,
            ],
            [
              <Code>reformatted_xml</Code>,
              <>
                The submitted XML, pretty-printed. <strong>All line numbers refer to this text</strong>,
                not to the original file. <Code>null</Code> when the XML is not well-formed.
              </>,
            ],
            [
              <Code>errors[].kind</Code>,
              <>
                <Code>not-well-formed</Code> — XML syntax error, the parser stopped (exactly one entry,
                no schema check).
                <br />
                <Code>schema-validation</Code> — the XML is well-formed but violates the XSD.
              </>,
            ],
            [
              <Code>errors[].line / column</Code>,
              <>
                Position inside <Code>reformatted_xml</Code>. <Code>column</Code> is usually{" "}
                <Code>null</Code> (libxml2 reports no column for schema errors); for syntax errors the
                column is part of the message text.
              </>,
            ],
            [
              <Code>errors[].message</Code>,
              <>
                Validator message (libxml2), e.g. missing mandatory element, wrong data type, pattern
                mismatch.
              </>,
            ],
            [
              <Code>errors[].path</Code>,
              <>
                Positional XPath to the offending element, e.g. <Code>/*/*[2]</Code> (second child of the
                root element); element names are in the <Code>message</Code>.
              </>,
            ],
            [
              <Code>errors[].severity</Code>,
              <>
                <Code>fatal</Code>, <Code>error</Code> or <Code>warning</Code>.
              </>,
            ],
          ]}
        />
        <H3>Only checking well-formedness?</H3>
        <p>
          There is no dedicated "well-formed only" endpoint, but the distinction is unambiguous: if{" "}
          <Code>is_valid</Code> is false and the first error has <Code>kind: "not-well-formed"</Code>,
          the file is not valid XML. Every other error already implies well-formedness.
        </p>
        <Pre>{`jq -r 'if .is_valid then "well-formed + valid"
       elif .errors[0].kind == "not-well-formed" then "NOT well-formed: " + .errors[0].message
       else "well-formed, but \\(.errors|length) schema error(s)" end' report.json`}</Pre>

        <H2 id="report-files">Saving and processing the report</H2>
        <H3>Readable text file</H3>
        <Pre>{`jq -r '.errors[] | "\\(.kind)\\tL\\(.line)\\t\\(.path // "-")\\t\\(.message)"' \\
  report.json > errors.txt`}</Pre>
        <H3>CSV</H3>
        <Pre>{`jq -r '["line","column","kind","severity","path","message"],
       (.errors[] | [.line,.column,.kind,.severity,.path,.message]) | @csv' \\
  report.json > errors.csv`}</Pre>
        <H3>Pretty-printed XML with matching line numbers</H3>
        <Pre>{`jq -r '.reformatted_xml // empty' report.json > document.pretty.xml
jq -r '.errors[] | "\\(.line): \\(.message)"' report.json`}</Pre>

        <H2 id="examples">Examples: curl, PowerShell, Python</H2>
        <p>
          All variants do the same thing: upload the XSD, validate the XML, save{" "}
          <Code>report.json</Code>, print the errors. Exit code 0 = valid, 1 = errors.
        </p>
        <H3>Bash + curl (with automatic reload on 404)</H3>
        <Pre>{`#!/usr/bin/env bash
set -euo pipefail
API=${API}
XSD=$1; XML=$2

SCHEMA_ID=$(curl -sf -F "file=@$XSD" "$API/schema/upload" | jq -r .schema_id)

code=$(curl -s -o report.json -w '%{http_code}' -F "file=@$XML" \\
       "$API/schema/$SCHEMA_ID/validate/upload")
if [ "$code" = 404 ]; then   # schema expired → reload once
  SCHEMA_ID=$(curl -sf -F "file=@$XSD" "$API/schema/upload" | jq -r .schema_id)
  code=$(curl -s -o report.json -w '%{http_code}' -F "file=@$XML" \\
         "$API/schema/$SCHEMA_ID/validate/upload")
fi
[ "$code" = 200 ] || { echo "HTTP $code: $(jq -r .detail report.json)" >&2; exit 2; }

if jq -e .is_valid report.json >/dev/null; then
  echo "OK: $XML is valid"
else
  jq -r '.errors[] | "  L\\(.line) [\\(.kind)] \\(.message)"' report.json >&2
  exit 1
fi`}</Pre>
        <p>
          Without <Code>jq</Code>: extract the id with{" "}
          <Code>{`sed -E 's/.*"schema_id":"([^"]+)".*/\\1/'`}</Code>, check validity with{" "}
          <Code>{`grep -q '"is_valid":true' report.json`}</Code>, pretty-print with{" "}
          <Code>python3 -m json.tool report.json</Code>.
        </p>

        <H3>PowerShell 7+</H3>
        <Pre>{`$Api = "${API}"

$schema = Invoke-RestMethod -Method Post -Uri "$Api/schema/upload" \`
            -Form @{ file = Get-Item .\\schema.xsd }
$schemaId = $schema.schema_id

$report = Invoke-RestMethod -Method Post -Uri "$Api/schema/$schemaId/validate/upload" \`
            -Form @{ file = Get-Item .\\document.xml }

$report | ConvertTo-Json -Depth 5 | Set-Content report.json -Encoding utf8

if ($report.is_valid) {
    Write-Host "VALID" -ForegroundColor Green
} else {
    $report.errors | Format-Table line, kind, message -AutoSize
    $report.errors | Select-Object line, column, kind, severity, path, message |
        Export-Csv errors.csv -NoTypeInformation -Encoding utf8
    exit 1
}`}</Pre>
        <Note title="Windows PowerShell 5.1:">
          has no <Code>-Form</Code>. Either use <Code>curl.exe</Code> (bundled since Windows 10 1803 —
          not the <Code>curl</Code> alias) with the Bash examples, or post JSON to{" "}
          <Code>/api/schema/text</Code> and <Code>/validate/text</Code> with{" "}
          <Code>Invoke-RestMethod -ContentType "application/json" -Body (… | ConvertTo-Json)</Code>.
        </Note>

        <H3>Python 3 (standard library only)</H3>
        <p>
          Uses the JSON endpoints <Code>/schema/text</Code> and <Code>/validate/text</Code>, so no
          multipart handling is needed. Reloads the schema once on <Code>404</Code>.
        </p>
        <Pre>{`#!/usr/bin/env python3
import json, sys, urllib.request, urllib.error
from pathlib import Path

API = "${API}"

def post_json(path, payload):
    req = urllib.request.Request(
        API + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def load_schema(xsd: Path) -> str:
    return post_json("/schema/text", {"filename": xsd.name,
                                      "content": xsd.read_text("utf-8")})["schema_id"]

def validate(schema_id: str, xml: Path, xsd: Path) -> dict:
    payload = {"filename": xml.name, "content": xml.read_text("utf-8")}
    try:
        return post_json(f"/schema/{schema_id}/validate/text", payload)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise SystemExit(f"HTTP {e.code}: {e.read().decode()}")
        schema_id = load_schema(xsd)          # expired → reload once
        return post_json(f"/schema/{schema_id}/validate/text", payload)

if __name__ == "__main__":
    xsd, xml = Path(sys.argv[1]), Path(sys.argv[2])
    report = validate(load_schema(xsd), xml, xsd)
    Path("report.json").write_text(json.dumps(report, indent=2), "utf-8")
    if report["is_valid"]:
        print("VALID")
    else:
        for e in report["errors"]:
            print(f"L{e['line']} [{e['kind']}] {e['message']}")
        sys.exit(1)`}</Pre>

        <H3>Python 3 with <Code>requests</Code></H3>
        <Pre>{`import json, sys, requests

API = "${API}"

with open("schema-bundle.zip", "rb") as f:
    r = requests.post(f"{API}/schema/upload", files={"file": f},
                      data={"main_filename": "Root.xsd"}, timeout=60)
r.raise_for_status()
schema_id = r.json()["schema_id"]

with open("document.xml", "rb") as f:
    r = requests.post(f"{API}/schema/{schema_id}/validate/upload",
                      files={"file": f}, timeout=60)
r.raise_for_status()
report = r.json()

with open("report.json", "w", encoding="utf-8") as out:
    json.dump(report, out, indent=2)

print("VALID" if report["is_valid"] else
      "\\n".join(f"L{e['line']}: {e['message']}" for e in report["errors"]))
sys.exit(0 if report["is_valid"] else 1)`}</Pre>
        <p>
          Several files against one schema: fetch the <Code>schema_id</Code> once and reuse it in a
          loop — fewer uploads and friendlier to the rate limit.
        </p>

        <H2 id="limits">Limits</H2>
        <p>
          These values apply to the public instance. Self-hosted installations can change them via
          environment variables (in parentheses).
        </p>
        <Table
          head={["Limit", "Value", "Details"]}
          rows={[
            [
              "Upload size (XSD, zip, XML)",
              <span className="font-mono tabular-nums whitespace-nowrap">32 MB</span>,
              <>
                Per request, including the JSON body of <Code>/validate/text</Code>. Larger uploads are
                rejected with <Code>413</Code>. (<Code>MAX_UPLOAD_MB</Code>)
              </>,
            ],
            [
              "Fetch by URL",
              <span className="font-mono tabular-nums whitespace-nowrap">10 MB · 10 s · 3 redirects</span>,
              <>
                For <Code>/schema/url</Code> and <Code>/validate/url</Code>. Only <Code>http</Code>/
                <Code>https</Code>, no private or loopback addresses. Exceeding any of these →{" "}
                <Code>400</Code>. (<Code>FETCH_MAX_RESPONSE_MB</Code>, <Code>FETCH_TIMEOUT_SECONDS</Code>,{" "}
                <Code>FETCH_MAX_REDIRECTS</Code>)
              </>,
            ],
            [
              "Request timeout",
              <span className="font-mono tabular-nums whitespace-nowrap">60 s</span>,
              <>
                Requests are aborted after 60 s (<Code>504</Code>). Parsing and validation typically take
                well under a second; the first request after a period of inactivity adds a 1–3 s cold
                start.
              </>,
            ],
            [
              "Rate limit",
              <span className="font-mono tabular-nums whitespace-nowrap">30 requests / min</span>,
              <>
                Per client IP, shared by all write endpoints (<Code>/schema/upload|url|text</Code> and
                every <Code>/validate/*</Code>). Beyond that: <Code>429</Code>. Reuse the{" "}
                <Code>schema_id</Code> for batch runs.
              </>,
            ],
            [
              <>
                <Code>schema_id</Code> lifetime
              </>,
              <span className="font-mono tabular-nums whitespace-nowrap">60 min · 32 entries</span>,
              <>
                In-memory LRU cache per server instance: entries expire 60 minutes after loading, and the
                oldest is evicted once more than 32 schemas are cached. The service runs on several
                instances under load, so an id may also be unknown on another instance. Scripts should
                react to <Code>404</Code> by re-uploading the XSD once (see examples). (
                <Code>SCHEMA_CACHE_TTL_MIN</Code>, <Code>SCHEMA_CACHE_MAX_ENTRIES</Code>)
              </>,
            ],
            [
              "DTD / entities in the XML",
              <span className="font-mono tabular-nums whitespace-nowrap">≤ 32 declarations</span>,
              <>
                Only simple internal <Code>{"<!ENTITY>"}</Code>/<Code>{"<!ATTLIST>"}</Code> declarations
                with literal values (≤ 512 characters) are accepted; external entities, parameter entities
                and nested references yield <Code>400</Code>. Fix: drop the DOCTYPE and inline the values.
              </>,
            ],
            [
              "Privacy",
              "—",
              <>
                Schemas and documents are processed in memory and never stored; only anonymous usage
                statistics (no IP address, no content) are recorded.
              </>,
            ],
          ]}
        />

        <H2 id="errors">Error codes</H2>
        <Table
          head={["HTTP", "Cause", "Fix"]}
          rows={[
            [
              <span className="font-mono">200</span>,
              <>
                Validation ran (result in <Code>is_valid</Code>)
              </>,
              "—",
            ],
            [
              <span className="font-mono">400</span>,
              <>
                URL rejected (not http/https, private address, &gt; 3 redirects, &gt; 10 MB, &gt; 10 s) or
                unsafe XML (external entities)
              </>,
              "Upload the file instead / remove the DOCTYPE",
            ],
            [
              <span className="font-mono">404</span>,
              <>
                <Code>schema_id</Code> unknown or expired
              </>,
              "Repeat step 1",
            ],
            [<span className="font-mono">413</span>, "File too large (> 32 MB)", "Reduce or split the file"],
            [
              <span className="font-mono">422</span>,
              "XSD could not be compiled into a validator (e.g. missing imports)",
              "Upload a complete zip with all imports",
            ],
            [
              <span className="font-mono">429</span>,
              "Rate limit hit (30 requests/min per IP)",
              <>
                Wait briefly, reuse the <Code>schema_id</Code>
              </>,
            ],
            [<span className="font-mono">504</span>, "Request timeout (60 s) exceeded", "Shrink the schema, retry"],
          ]}
        />
        <p>
          Error responses (≠ 200) have the shape <Code>{`{"detail": "…"}`}</Code>.
        </p>

        <p className="mt-10 pt-4 border-t border-slate-200 dark:border-slate-800 text-sm text-slate-500 dark:text-slate-400">
          <a href="/" className="text-blue-600 dark:text-blue-400 hover:underline">
            ← Back to the viewer
          </a>
        </p>
      </article>
    </div>
  );
}
