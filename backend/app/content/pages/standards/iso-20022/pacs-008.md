+++
title = "pacs.008 XSD: FI To FI Customer Credit Transfer — structure and viewer"
heading = "pacs.008 — FI To FI Customer Credit Transfer"
description = "Structure of the ISO 20022 pacs.008 (FI To FI Customer Credit Transfer) XML Schema: root element, main blocks and how to view the XSD as a diagram and validate pacs.008 files online."
lastmod = 2026-10-20
cta_label = "Open pacs.008.001.13 in the viewer"
cta_href = "/iso20022?message=pacs.008.001.13"
+++

**pacs.008** is the ISO 20022 message for the interbank message that carries a customer credit transfer between banks — the core message of SEPA, of the ISO 20022 migration of cross-border payments (CBPR+) and of many instant payment schemes.

## Structure

Every ISO 20022 message has a `Document` root in the message's own namespace
(`urn:iso:std:iso:20022:tech:xsd:pacs.008.<variant>.<version>`), with exactly one child — here `FIToFICstmrCdtTrf`:

- `GrpHdr` — message id, settlement information, number of transactions
- `CdtTrfTxInf` — each transfer: payment ids (incl. UETR), settlement amount and date, debtor and creditor with their agents, remittance information

The exact content differs between versions (`pacs.008.001.03`, `.001.09`, …) and is usually restricted further by
your bank's or scheme's implementation guide (for example the EPC rulebooks for SEPA).

## View the schema

Open [pacs.008.001.13](/iso20022?message=pacs.008.001.13), the latest version, directly in the viewer — or pick another version of
pacs.008 in the [ISO 20022 tab](/iso20022?q=pacs.008). Then explore `Document/FIToFICstmrCdtTrf` as a diagram, search for element names
(Ctrl/⌘ + K), and export the diagram or an HTML documentation for your team.

The schemas are loaded from a public mirror of the ISO 20022 catalogue, unchanged; the authoritative source is the
[ISO 20022 message catalogue](https://www.iso20022.org/catalogue-messages). Your bank's implementation guide may
require a specific version — the version is the last part of the file's namespace.

## Validate a pacs.008 file

Load the XSD, then validate your XML document against it — in the browser or via the [REST API](/api-docs) from a
script. For a file-first workflow with an Excel list of all errors, use the [XML Viewer](/go/xml-viewer).
Schema validation checks structure, types, lengths and code lists; rules from bank-specific implementation
guides (MIGs) are outside an XSD and need your bank's own validator.

**Typical use:** Bank back offices, payment hubs, scheme and CBPR+ testing.
