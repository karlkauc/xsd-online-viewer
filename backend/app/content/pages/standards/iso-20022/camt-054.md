+++
title = "camt.054 XSD: Bank To Customer Debit Credit Notification — structure and viewer"
heading = "camt.054 — Bank To Customer Debit Credit Notification"
description = "Structure of the ISO 20022 camt.054 (Bank To Customer Debit Credit Notification) XML Schema: root element, main blocks and how to view the XSD as a diagram and validate camt.054 files online."
lastmod = 2026-10-20
cta_label = "Open camt.054.001.12 in the viewer"
cta_href = "/iso20022?message=camt.054.001.12"
+++

**camt.054** is the ISO 20022 message for notifications of single debits or credits on an account — intraday or as a breakdown of batch bookings in camt.053.

## Structure

Every ISO 20022 message has a `Document` root in the message's own namespace
(`urn:iso:std:iso:20022:tech:xsd:camt.054.<variant>.<version>`), with exactly one child — here `BkToCstmrDbtCdtNtfctn`:

- `GrpHdr` — message id and creation time
- `Ntfctn` — one notification per account
- `Ntry` / `TxDtls` — the bookings with references, parties and remittance information

The exact content differs between versions (`camt.054.001.03`, `.001.09`, …) and is usually restricted further by
your bank's or scheme's implementation guide (for example the EPC rulebooks for SEPA).

## View the schema

Open [camt.054.001.12](/iso20022?message=camt.054.001.12), the latest version, directly in the viewer — or pick another version of
camt.054 in the [ISO 20022 tab](/iso20022?q=camt.054). Then explore `Document/BkToCstmrDbtCdtNtfctn` as a diagram, search for element names
(Ctrl/⌘ + K), and export the diagram or an HTML documentation for your team.

The schemas are loaded from a public mirror of the ISO 20022 catalogue, unchanged; the authoritative source is the
[ISO 20022 message catalogue](https://www.iso20022.org/catalogue-messages). Your bank's implementation guide may
require a specific version — the version is the last part of the file's namespace.

## Validate a camt.054 file

Load the XSD, then validate your XML document against it — in the browser or via the [REST API](/api-docs) from a
script. For a file-first workflow with an Excel list of all errors, use the [XML Viewer](/go/xml-viewer).
Schema validation checks structure, types, lengths and code lists; rules from bank-specific implementation
guides (MIGs) are outside an XSD and need your bank's own validator.

**Typical use:** Detailed reconciliation of batch bookings, incoming payment notifications.
