# XSD 1.1 sample schemas

Curated showcase schemas for trying out the viewer's XSD 1.1 features.
Unlike the focused unit-test fixtures under
[`backend/tests/fixtures/`](../../backend/tests/fixtures), these are
realistic-ish schemas that combine **multiple** 1.1 constructs in one
file. Upload them through the **File / ZIP** tab and explore the
diagram, detail panel, and text view.

## Single-file samples

Upload each one directly as `.xsd`.

| File | Feature mix |
|------|-------------|
| [`measurement.xsd`](measurement.xsd) | `xs:assert`, `xs:alternative`, `@inheritable`, `vc:typeAvailable`, `xpathDefaultNamespace` |
| [`api-envelope.xsd`](api-envelope.xsd) | `xs:defaultOpenContent`, per-type `xs:openContent` (suffix + none), `xs:alternative`, `xs:assert`, `vc:typeAvailable` |
| [`chess-game.xsd`](chess-game.xsd) | `xs:all` with `maxOccurs > 1`, `xs:any` inside `xs:all`, `xs:alternative`, `xs:assert`, `@inheritable` |
| [`events.xsd`](events.xsd) | new 1.1 built-ins (`xs:dateTimeStamp`, `xs:yearMonthDuration`, `xs:dayTimeDuration`, `xs:precisionDecimal`), `explicitTimezone` facet, simple-type `xs:assertion` |

## Override pair

`xs:override` is multi-file. Zip these two together before uploading,
and set the main file to `plugin-config-strict.xsd` in the upload
dialog:

```bash
cd samples/xsd-1.1
zip plugin-config.zip plugin-config-strict.xsd plugin-config-base.xsd
```

| File | Role |
|------|------|
| [`plugin-config-base.xsd`](plugin-config-base.xsd) | Permissive base schema with `defaultAttributes` and `@inheritable` |
| [`plugin-config-strict.xsd`](plugin-config-strict.xsd) | `xs:override` block that replaces `SecurityPolicy` and adds `Quotas` |

After upload, select `ColorType`-style declarations from the tree to see
the **"overrides …"** / **"overridden by"** badges in the detail panel,
and switch tabs to see how the override file is listed in the text view.

## What to look for in the viewer

* **XSD-version pill** — every sample is detected as `XSD 1.1` (top
  right of the schema overview + next to the source-file tabs in the
  Text view).
* **`vc:*` badges** — declarations gated by version constraints carry a
  small `vc` chip; hover for the full attribute set.
* **Diagram chips** — `⚖ N` for assertions on the resolved type,
  `≷ N` for type alternatives on the element, dashed compositor border
  with corner `+` for open content, and `all+` label when an `xs:all`
  exercises 1.1 relaxations.
* **Assertion blocks** — XPath text is rendered verbatim with the
  `xpathDefaultNamespace` chip when it differs from the schema default.
* **Type-alternative ladder** — `if (test) → type`, `else → type`,
  clickable to jump to the matching named type.

Everything is display-only — the viewer parses these constructs and
shows them, but never evaluates XPath or validates instance documents.
