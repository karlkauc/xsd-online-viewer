# Identity constraints / ID-IDREF sample

A single showcase schema for the viewer's identity-constraint (`xs:key` /
`xs:keyref` / `xs:unique`) and `xs:ID`/`xs:IDREF`/`xs:IDREFS` features. Upload
[`order-registry.xsd`](order-registry.xsd) directly as `.xsd` through the
**File / ZIP** tab.

## Feature mix

| Feature | Where |
|---------|-------|
| `xs:key` | `productKey` on `Registry` — `Product/@sku` is a compound business key |
| `xs:keyref` | `orderItemRef` — every `Order/Items/Item/@sku` must name a known product |
| `xs:unique` with `.//` and a `\|` union selector | `emailUnique` — checks `Customer/@email` and `Order/Contact/@email` for uniqueness in one constraint |
| `xs:ID` on an element | `Order/OrderNumber` |
| `xs:ID` on an attribute | `Customer/@id` |
| `xs:IDREF` (direct, built-in) | `Customer/@favoriteOrderRef` |
| `xs:IDREF` (inline restriction) | `Order/@relatedOrderRef` — the shape FundsXML4 actually uses: a restriction with `base="xs:IDREF"` plus a facet, not the built-in type directly |
| `xs:IDREFS` | `Order/@customerRefs` |
| `xs:assert` on a named type | `OrderType` — a discount can never exceed the order total |

## What to look for in the viewer

* Select `Registry` (Tree tab) — the detail panel's **Identity constraints**
  section lists all three constraints as teal cards; the selector/field XPath
  steps that resolve to a concrete declaration are clickable, and
  `orderItemRef`'s "refers to" jumps to `productKey`'s host element
  (`Registry`).
* The centre pane on the Tree tab shows the same three constraints in a
  table, plus an **Assertions** table for `OrderType`.
* Select `OrderNumber` (Tree tab) to see the indigo **ID role** chip (`ID`)
  on the element itself. `Customer` and `Order` are typed by named complex
  types (`CustomerType`/`OrderType`), so the elements carry no chip — their
  ID/IDREF roles sit on the attributes instead. Select `Customer/@id` in the
  tree or attributes table to see the `ID` chip and the **ID reference**
  section, or `Customer/@favoriteOrderRef` to see the `IDREF` chip and the
  **Referenced by IDREF** section — XSD never binds an IDREF to one specific
  ID, so both sides list every candidate/usage in the schema instead of a
  resolved target.
* The Diagram tab shows the teal `⚿ N` badge on `Registry`, the indigo `ID`
  badge on `OrderNumber` (the only node whose element itself is ID/IDREF
  typed — attribute-level roles on `Customer`/`Order` don't render as
  attribute rows on the diagram, since those two are typed by named complex
  types, not inline ones), and the amber `⚖ 1` badge on `Order` (inherited
  from `OrderType`'s assertion).

`Product/@sku` and `Item/@sku` are deliberately **not** typed `xs:ID`/
`xs:IDREF` — `xs:key`/`xs:keyref` and `xs:ID`/`xs:IDREF` are independent XSD
mechanisms, and real-world schemas often use the former for structured,
scoped keys while reserving the latter for flat, document-wide identifiers.

Everything is display-only: the viewer parses and shows these constructs but
never evaluates XPath or validates instance documents against them.

**FundsXML4** (open it from the **FundsXML Releases** tab) exercises the same
features at production scale: key `benchmarkID` + keyref `benchmarkDynamicRef`
on `Fund`, key `transactionID` on `Transactions`, two `xs:ID` declarations,
and ten `xs:IDREF`-classified attributes — most of them, like
`Order/@relatedOrderRef` above, inline restrictions rather than the built-in
type used directly.
