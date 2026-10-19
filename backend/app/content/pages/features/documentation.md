+++
title = "XSD documentation generator online: XML Schema to HTML"
heading = "Generate HTML documentation from an XSD"
description = "Create standalone HTML documentation from an XML Schema in the browser: every element, type and attribute with its documentation, facets, cardinality and source location. Free, no install."
lastmod = 2026-10-19
cta_label = "Load a schema"
cta_href = "/"
+++

Interface specifications often ship as an XSD plus a PDF that no longer matches it. Generate the
documentation from the schema itself instead:

1. Load the schema — upload, paste, URL or a ZIP with all its files.
2. Choose **Export → HTML** in the header.
3. You get one self-contained HTML file: no server, no external scripts, ready for a wiki, an e-mail or a
   ticket attachment.

## What the documentation contains

- The files of the bundle with their target namespaces and how they are connected (`import`, `include`,
  `redefine`).
- Every global element, complex type and simple type with its `xs:documentation` and `xs:appinfo`.
- The facets of simple types: patterns, lengths, enumerations, ranges.
- Anything the parser noticed about the schema itself (diagnostics), so the reader knows about loose ends.

For the structure of the content models, add the [diagram](/features/diagram) as PNG or SVG.

## Other exports

- **Diagram as PNG/SVG** for the parts you want to show visually ([XSD diagram](/features/diagram)).
- **Sample XML** for any element ([generate sample XML from an XSD](/features/sample-xml)).
- **Pretty-printed XSD** of every file in the bundle.

For larger documentation projects with templates and Word or PDF output, the desktop app
[FreeXmlToolkit](/go/freexmltoolkit) has a full XSD documentation generator.
