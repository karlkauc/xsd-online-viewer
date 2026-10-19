+++
title = "pain.002 XSD: Customer Payment Status Report — structure and viewer"
heading = "pain.002 — Customer Payment Status Report"
description = "Structure of the ISO 20022 pain.002 (Customer Payment Status Report) XML Schema: root element, main blocks and how to view the XSD as a diagram and validate pain.002 files online."
lastmod = 2026-10-19
cta_label = "Open the XSD viewer"
cta_href = "/url"
+++

**pain.002** is the ISO 20022 message for the bank's answer to a pain.001 or pain.008: whether the file, a batch or a single transaction was accepted or rejected, and why.

## Structure

Every ISO 20022 message has a `Document` root in the message's own namespace
(`urn:iso:std:iso:20022:tech:xsd:pain.002.<variant>.<version>`), with exactly one child — here `CstmrPmtStsRpt`:

- `GrpHdr` — id and time of the status report
- `OrgnlGrpInfAndSts` — status of the original message as a whole
- `OrgnlPmtInfAndSts` / `TxInfAndSts` — status per batch and per transaction, with reason codes

The exact content differs between versions (`pain.002.001.03`, `.001.09`, …) and is usually restricted further by
your bank's or scheme's implementation guide (for example the EPC rulebooks for SEPA).

## View the schema

1. Download the pain.002 XSD for the version you need from the
   [ISO 20022 message catalogue](https://www.iso20022.org/catalogue-messages), or take the one from your bank's
   implementation guide.
2. Open it in the [XSD viewer](/): upload the file, or paste a public URL into the [URL tab](/url).
3. Explore `Document/CstmrPmtStsRpt` as a diagram, search for element names (Ctrl/⌘ + K), and export the diagram or an
   HTML documentation for your team.

This site does not mirror ISO 20022 schemas; load them from the official source.

## Validate a pain.002 file

Load the XSD, then validate your XML document against it — in the browser or via the [REST API](/api-docs) from a
script. For a file-first workflow with an Excel list of all errors, use the [XML Viewer](/go/xml-viewer).
Schema validation checks structure, types, lengths and code lists; rules from bank-specific implementation
guides (MIGs) are outside an XSD and need your bank's own validator.

**Typical use:** Reconciling rejected payments, automated handling of reason codes in ERP systems.
