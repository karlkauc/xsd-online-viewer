+++
title = "Free XMLSpy alternative for viewing XSD schemas (browser, Mac, Linux)"
heading = "A free alternative to XMLSpy's schema view"
description = "View XML Schemas as an XMLSpy-style diagram without a licence: in the browser on Windows, macOS and Linux, with multi-file schemas, documentation export and XML validation. Free and open source."
lastmod = 2026-10-19
cta_label = "Open a schema"
cta_href = "/"
+++

Altova XMLSpy is the reference tool for editing XML Schemas, and its schema diagram is what many people picture
when they think of an XSD. But not everyone who needs to *read* a schema has a licence, a Windows machine, or
the time to install one — business analysts checking an interface specification, developers on a Mac,
colleagues you want to send a link to.

The Online XSD Viewer covers the reading part:

| Task | Online XSD Viewer |
|---|---|
| Schema diagram with sequences, choices, cardinalities | yes, XMLSpy-style |
| Multi-file schemas (`xs:import`, `xs:include`, `xs:redefine`) | yes, from a ZIP or several files |
| Tree, search across names and documentation | yes |
| XSD 1.1 (assertions, alternatives, open content) | shown and validated |
| Validate XML against the schema | yes, in the browser and via REST API |
| Generate sample XML | yes |
| HTML documentation, PNG/SVG diagram | yes |
| Share a link to a node | yes |
| Edit the schema | no — it is a viewer |
| Platforms | any browser; Docker for self-hosting |
| Price | free, open source (MIT) |

## When you need to edit

For editing XSDs with a graphical editor, IntelliSense for instance documents, XSLT, Schematron and signing,
the same author's desktop app [FreeXmlToolkit](/go/freexmltoolkit) is free as well and runs on Windows, macOS
and Linux. XMLSpy remains the choice if your team relies on its other features.
