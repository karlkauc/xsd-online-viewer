+++
title = "pain.001 XSD: Customer Credit Transfer Initiation — structure and viewer"
heading = "pain.001 — Customer Credit Transfer Initiation"
description = "Structure of the ISO 20022 pain.001 (Customer Credit Transfer Initiation) XML Schema: root element, main blocks and how to view the XSD as a diagram and validate pain.001 files online."
lastmod = 2026-10-19
cta_label = "Open the XSD viewer"
cta_href = "/url"
+++

**pain.001** is the ISO 20022 message for the payment order a company sends to its bank: one or more batches of credit transfers, each with debtor, debtor account, execution date and the individual transactions.

## Structure

Every ISO 20022 message has a `Document` root in the message's own namespace
(`urn:iso:std:iso:20022:tech:xsd:pain.001.<variant>.<version>`), with exactly one child — here `CstmrCdtTrfInitn`:

- `GrpHdr` — message id (`MsgId`), creation time, number of transactions (`NbOfTxs`), control sum, initiating party
- `PmtInf` — one payment batch: payment method, requested execution date, debtor, debtor account and agent
- `CdtTrfTxInf` — each transfer: end-to-end id, amount, creditor, creditor account and agent, remittance information

The exact content differs between versions (`pain.001.001.03`, `.001.09`, …) and is usually restricted further by
your bank's or scheme's implementation guide (for example the EPC rulebooks for SEPA).

## View the schema

1. Download the pain.001 XSD for the version you need from the
   [ISO 20022 message catalogue](https://www.iso20022.org/catalogue-messages), or take the one from your bank's
   implementation guide.
2. Open it in the [XSD viewer](/): upload the file, or paste a public URL into the [URL tab](/url).
3. Explore `Document/CstmrCdtTrfInitn` as a diagram, search for element names (Ctrl/⌘ + K), and export the diagram or an
   HTML documentation for your team.

This site does not mirror ISO 20022 schemas; load them from the official source.

## Validate a pain.001 file

Load the XSD, then validate your XML document against it — in the browser or via the [REST API](/api-docs) from a
script. For a file-first workflow with an Excel list of all errors, use the [XML Viewer](/go/xml-viewer).
Schema validation checks structure, types, lengths and code lists; rules from bank-specific implementation
guides (MIGs) are outside an XSD and need your bank's own validator.

**Typical use:** SEPA credit transfers (with the EPC rulebook), payroll and supplier payment files, ERP payment runs.
