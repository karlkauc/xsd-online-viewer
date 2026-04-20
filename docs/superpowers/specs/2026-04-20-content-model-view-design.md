# Content Model View — Design Spec

**Date:** 2026-04-20
**Status:** Approved (brainstorming)
**Scope:** Tree tab — center panel

## Problem

The Tree tab's center panel currently renders `EmptyOverview` (a static
"Schema Overview" with global declaration counts). It does not react to
selection in the Structure tree on the left, so the panel is dead weight
during navigation. The Detail panel on the right is narrow (~26 % width)
and already crowded with metadata, facets, documentation and "Used by".

There is no view today that gives a flat, scannable answer to the question
*"what fields does this complex object have, with type and cardinality?"*.
The Tree shows hierarchy, the Detail panel shows metadata, the Diagram
shows a graph — none of them is a content-model summary table.

## Goal

Replace `EmptyOverview` (when something is selected) with a **Content
Model Table** that is selection-driven, complementary to Tree and Detail,
and built from the existing `SchemaModel` without backend changes.

When nothing is selected, the existing `EmptyOverview` (Schema Overview)
remains as the empty state.

## Non-goals

- Replacing or restyling the Detail panel (right) or the Diagram tab.
- Backend / parser changes — `SchemaModel` already carries everything.
- Generating sample XML, sortable columns, filtering inside the table,
  or recursive type expansion. (Possible follow-ups.)
- Showing inherited members inline for `extension`-derived complex types
  (V1 only links to the base type).

## Layout

```
┌────────────────────────────────────────────────────────────────────┐
│  [badge] UniqueDocumentID                                          │
│  → TestIDType  (complexType, simple content)                       │
│  ───────────────────────────────────────────────────────────────── │
│                                                                    │
│  Children                                                          │
│  ┌──┬───────────────┬──────┬──────────┬────────┬──────────┬─────┐ │
│  │▸ │ Name          │ Kind │ Type     │ Card.  │ Def/Fix  │ Doc │ │
│  ├──┼───────────────┼──────┼──────────┼────────┼──────────┼─────┤ │
│  │▦ │ Identifier    │ elem │ ISIN     │ 1..1   │ —        │ ... │ │
│  │▦ │ ListedExch.   │ elem │ MIC      │ 0..1   │ —        │ ... │ │
│  └──┴───────────────┴──────┴──────────┴────────┴──────────┴─────┘ │
│                                                                    │
│  Attributes                                                        │
│  ┌──┬───────────────┬──────────┬──────────┬──────────┬──────────┐ │
│  │  │ Name          │ Type     │ Use      │ Def/Fix  │ Doc      │ │
│  ├──┼───────────────┼──────────┼──────────┼──────────┼──────────┤ │
│  │@ │ Currency      │ ISO4217  │ optional │ —        │ ...      │ │
│  └──┴───────────────┴──────────┴──────────┴──────────┴──────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

### Header

- Kind badge + label (mono font), qname underneath in muted small font.
- Type line: `→ <type-qname> (<kind>, <content_kind?>)`.
  - For elements: type referenced or `(inline complex)` / `(inline simple)`.
  - For complexTypes: `(complexType, content_kind=mixed)` etc.
  - For simpleTypes: `(simpleType, derivation=restriction, base=xs:string)`.
- For `extension`-derived complex types: small line
  `extends <Base>` — Base is a clickable link that selects the base type.

### Children table

Columns:

| Col | Source | Notes |
|---|---|---|
| ▸ | Particle context | `▦` sequence, `◇` choice, `≡` all, `★` group-ref, `*` any. Empty for top-level rows when the outer compositor is the only one. |
| Name | element name / `«groupName»` / `any` | Mono. |
| Kind | `element` / `group-ref` / `any` | Reuse `KindBadge` palette. |
| Type | `type_name` or `(inline complex)` / `(inline simple)` | Rendered as a button when the QName resolves to an indexed declaration via `resolveReference`; otherwise plain mono text. |
| Card. | `min..max` (`*` for unbounded) | Same formatting as the tree's occurs pill. |
| Def/Fix | `default` or `[fixed] value` | `—` if neither. |
| Doc | `documentation[0].text`, single-line truncated via CSS | Tooltip (`title`) = full text. Empty cell when no documentation. |

Row click → `setSelected(row.id)` (synchronises Tree, Diagram, Detail).
Hover row → subtle highlight (matches Tree hover style).

### Attributes table

Same row component, simpler columns: Name (`@name`), Type, Use, Def/Fix,
Doc. Type cell behaves the same (clickable). Includes attributes from
`attribute_group_refs` resolved transitively (with a small inline tag
`from <groupName>` so the origin is visible).

## Behaviour per node kind

| Selected kind | Children table | Attributes table | Simple-type card |
|---|---|---|---|
| `element` (complex type, named or inline) | yes | yes | — |
| `element` (simple type, named or inline) | — | — | yes |
| `complexType` (complex content) | yes | yes | — |
| `complexType` (simple content) | — | yes | yes (resolved from `simple_content_base` + `simple_content_facets`) |
| `simpleType` | — | — | yes |
| `group` | yes | — | — |
| `attributeGroup` | — | yes | — |
| `attribute` | — | — | yes (resolved from `type_name` or `type_inline`); empty placeholder card with the use/default if neither is present |
| nothing selected | — | — | — → `EmptyOverview` |

The **simple-type card** reuses the existing `FacetGroups` component from
`DetailPanel.tsx` (currently rendered on the right). The card lives in
the center, sized for readability — the right-panel rendering stays
unchanged.

## Particle flattening rules

Implemented as a pure helper:

```ts
// frontend/src/lib/particles.ts
export interface FlatRow {
  id: string;            // stable for React key + selection
  depth: number;         // 0 = top-level child of the root particle
  compositor?:           // when this row IS a nested compositor header
    | "sequence" | "choice" | "all";
  compositorOccurs?: string;
  element?: ElementDecl; // when this row is an element leaf
  groupRef?: QName;      // when this row is a group-ref leaf
  any?: { namespace: string | null; processContents: string | null };
}
export function flattenParticle(p: Particle | null): FlatRow[];
```

Rules:

1. **Outer particle is unwrapped.** Its direct children become depth-0
   rows. The outer compositor itself does not get a header row.
2. **Nested compositors emit a header row** (with `▦`/`◇`/`≡` symbol and
   their own occurs pill). Their children render at `depth+1`.
3. **Indentation is rendered visually** (left padding + a faint vertical
   guide), not by adding a column.
4. **Max visible depth: 2.** Depths 0, 1 and 2 render normally; any
   particle at depth ≥ 3 collapses to a single `…` row at depth 2 whose
   tooltip lists the full sub-tree as indented text. (Avoids a wall of
   indentation. Diagram tab is the place for deep visualisation.)
5. **`group-ref` is a single row, never inline-expanded.** Click =
   `setSelected(<groupId>)` — the group then becomes its own Content
   Model view.
6. **`any` (wildcard)** renders as one row with namespace and
   processContents in the Type column.

Inherited content from `derivation = extension` is **not** flattened
into the table in V1. The header's "extends *Base*" link is the bridge.
A future iteration may merge inherited rows with a "(from Base)" tag.

## Reuse / new code

### New
- `frontend/src/lib/particles.ts` — `flattenParticle` + `FlatRow` type.
- `frontend/src/components/ContentModelView/ContentModelView.tsx` —
  top-level component, picks the right sub-view per kind.
- `frontend/src/components/ContentModelView/ChildrenTable.tsx`
- `frontend/src/components/ContentModelView/AttributesTable.tsx`
- `frontend/src/components/ContentModelView/SimpleTypeCard.tsx` — wraps
  `FacetGroups` in a centered, comfortably sized container.
- `frontend/src/components/ContentModelView/Header.tsx`

### Modified
- `frontend/src/App.tsx` — replace
  `{activeTab === "tree" && <EmptyOverview />}` with a switch:
  `selectedId ? <ContentModelView /> : <EmptyOverview />`.
- Extract `FacetGroups` (today at the bottom of `DetailPanel.tsx`) into
  its own file `frontend/src/components/FacetGroups.tsx` so both
  `DetailPanel` and `SimpleTypeCard` can import it without dragging the
  whole detail panel into the new view. `DetailPanel.tsx` becomes a
  re-export consumer; no behaviour change there.

### Helpers reused (read-only)
- `useSelection` store — `selectedId`, `indexById`, `setSelected`,
  `model`.
- `resolveReference` from `frontend/src/lib/indexSchema.ts` — for the
  clickable Type cell.
- `KindBadge` — for Kind column.

## Tests

- Unit (`frontend/tests/lib.particles.test.ts`):
  - sequence of 3 elements → 3 depth-0 rows, no header.
  - sequence containing a choice → choice header at depth 0, its
    children at depth 1.
  - group-ref → single row, no expansion.
  - depth-4 nesting → collapse to `…` at depth 3.
  - wildcard → one row with namespace/processContents.
- Component (`frontend/tests/components.contentModelView.test.tsx`):
  - element with named complex type → renders Children + Attributes.
  - element with simple type → renders simple-type card only.
  - simpleType with enumeration → enumeration chips visible.
  - group selected → Children only, no Attributes.
  - clicking a Type cell with resolvable QName calls `setSelected` with
    the target id.
  - row click calls `setSelected` with the row's id.
  - empty selection → `EmptyOverview` still rendered (covered by an
    existing/added integration test in `App.test.tsx`).
- Existing tests stay green (no API or store changes).

## Out of scope (possible follow-ups)

- Sortable / filterable columns.
- Sample XML generation in the same panel.
- Inline expansion of inherited members from `extension`.
- "Show all leaves recursively" toggle.
- Sortable group-ref expansion.
