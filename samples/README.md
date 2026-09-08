# Sample schemas

Curated schemas for trying out viewer features that a plain "hello world"
XSD doesn't exercise. Upload any of them through the **File / ZIP** tab.

| Folder | Feature mix |
|--------|-------------|
| [`xsd-1.1/`](xsd-1.1/) | XSD 1.1: `xs:assert`, `xs:alternative`, `xs:openContent`/`xs:defaultOpenContent`, `xs:override`, `@inheritable`, `vc:*`, new 1.1 built-in types |
| [`keys-and-ids/`](keys-and-ids/) | `xs:key`/`xs:keyref`/`xs:unique` (including a `.//` and a `\|` union selector), `xs:ID`/`xs:IDREF`/`xs:IDREFS` (element and attribute, direct and inline-restricted) |

Each folder has its own README with a feature table and what to look for in
the viewer. Unit-test fixtures under
[`backend/tests/fixtures/`](../backend/tests/fixtures) are smaller and more
focused — one construct (or edge case) at a time — but not meant as a
showcase; these samples combine several in one realistic-ish schema.

**FundsXML4** (`FundsXML4.xsd` at the repo root, opened from the **FundsXML
Releases** tab) exercises the identity-constraint and ID/IDREF features from
`keys-and-ids/` at production scale — a 98k-line real-world schema rather
than a hand-built demo.
