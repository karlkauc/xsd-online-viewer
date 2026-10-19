+++
title = "Generate sample XML from an XSD online"
heading = "Generate sample XML from an XSD"
description = "Create an example XML document from any element of an XML Schema: required content, optional parts on request, values that fit types, patterns and enumerations — checked against the schema before you get it."
lastmod = 2026-10-19
cta_label = "Load a schema"
cta_href = "/"

[[faq]]
q = "Is the generated XML valid?"
a = "The generator checks every sample against the schema. In rare cases — very unusual patterns or XSD 1.1 assertions — a value may not fit; the check tells you, and such cases are reported so the generator can be improved."
+++

Need a test file for an interface, an example for documentation, or a starting point for a message you have
to write by hand? Pick an element in the tree and choose **Sample XML**.

- **Required content first** — the minimal document that satisfies the schema, with the first branch of each
  `xs:choice` and the first enumeration value.
- **Everything optional** on request, and repeating elements shown up to three times.
- **Plausible values** — names suggest them (`Currency` → `EUR`, `Email` → an address, `ISIN` → a real ISIN),
  dates and numbers vary between occurrences, and patterns, lengths and ranges are respected.
- **Checked** against the schema, so you know whether the sample is valid as generated.
- **Copy, download, or open in the [XML Viewer](/go/xml-viewer)** to browse it as a tree.

## From the command line

The same validation is available through the [REST API](/api-docs): post a schema and an XML document and get a
JSON list of errors with line numbers — useful in CI pipelines that produce XML.
