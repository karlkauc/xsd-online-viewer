# Content Model View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static "Schema Overview" placeholder in the Tree-tab center with a selection-driven Content Model Table that shows the children, attributes and facets of the selected node.

**Architecture:** A pure helper (`flattenParticle`) produces an indentation-aware row list from XSD particles. A top-level `ContentModelView` dispatches by selected node kind to small focused sub-components (`Header`, `ChildrenTable`, `AttributesTable`, `SimpleTypeCard`). `FacetGroups` is extracted from `DetailPanel.tsx` so both views can share it.

**Tech Stack:** React 18, TypeScript, Vite, Vitest + @testing-library/react, Tailwind, Zustand store (existing `useSelection`).

**Spec:** `docs/superpowers/specs/2026-04-20-content-model-view-design.md`

---

## File Structure

### New
- `frontend/src/lib/particles.ts` — `flattenParticle` + `FlatRow` type
- `frontend/src/components/FacetGroups.tsx` — extracted from `DetailPanel.tsx`
- `frontend/src/components/ContentModelView/ContentModelView.tsx` — top-level dispatcher
- `frontend/src/components/ContentModelView/Header.tsx`
- `frontend/src/components/ContentModelView/ChildrenTable.tsx`
- `frontend/src/components/ContentModelView/AttributesTable.tsx`
- `frontend/src/components/ContentModelView/SimpleTypeCard.tsx`
- `frontend/src/components/ContentModelView/symbols.ts` — compositor glyph map (small shared constant)
- `frontend/tests/lib.particles.test.ts`
- `frontend/tests/components.contentModelView.test.tsx`

### Modified
- `frontend/src/components/DetailPanel.tsx` — drop the local `FacetGroups` definition; import from `../FacetGroups`
- `frontend/src/App.tsx` — replace `<EmptyOverview />` with conditional render: `selectedId ? <ContentModelView /> : <EmptyOverview />`
- `frontend/tests/components.detailPanel.test.tsx` — update import path for `FacetGroups`

---

## Conventions & verification commands

- Tests run from `frontend/`: `npm run test -- <file>` (Vitest CLI).
- Type check: `npm run build` (`tsc -b`). Run after each task to catch ts errors early.
- Commit after each task. Use Conventional Commits: `feat:`, `refactor:`, `test:`.

---

## Task 1: Extract `FacetGroups` into its own module (mechanical refactor)

**Why first:** `SimpleTypeCard` (Task 4) needs `FacetGroups` without dragging in the entire `DetailPanel`. Mechanical move with no behaviour change — verified by the existing `DetailPanel` tests staying green.

**Files:**
- Create: `frontend/src/components/FacetGroups.tsx`
- Modify: `frontend/src/components/DetailPanel.tsx`
- Modify: `frontend/tests/components.detailPanel.test.tsx`

- [ ] **Step 1.1: Create `FacetGroups.tsx` containing the extracted code**

Move lines 329-612 of `frontend/src/components/DetailPanel.tsx` (everything from the `// ============== FacetGroups` banner to the end of `OtherGroup`) into a new file. Add the imports `FacetGroups` needs.

```tsx
// frontend/src/components/FacetGroups.tsx
import { Fragment } from "react";
import type { Facet, FacetKind, SimpleType } from "../types/schema";

// ============================================================================
// FacetGroups — structured rendering of <xs:restriction>/<xs:list> facets.
// ============================================================================

type GroupId =
  | "restriction"
  | "enumeration"
  | "range"
  | "precision"
  | "length"
  | "pattern"
  | "whitespace"
  | "other";

const FACET_GROUP: Partial<Record<FacetKind, GroupId>> = {
  enumeration: "enumeration",
  minInclusive: "range",
  maxInclusive: "range",
  minExclusive: "range",
  maxExclusive: "range",
  totalDigits: "precision",
  fractionDigits: "precision",
  length: "length",
  minLength: "length",
  maxLength: "length",
  pattern: "pattern",
  whiteSpace: "whitespace",
};

export interface FacetGroupsProps {
  facets: Facet[];
  restriction?:
    | Pick<SimpleType, "base" | "derivation" | "item_type" | "member_types">
    | null;
  inheritedFrom?: string | null;
}

export function FacetGroups({ facets, restriction, inheritedFrom }: FacetGroupsProps) {
  if (!facets.length && !restriction) return null;

  const byGroup = new Map<GroupId, Facet[]>();
  for (const f of facets) {
    const g = FACET_GROUP[f.kind] ?? "other";
    const arr = byGroup.get(g) ?? [];
    arr.push(f);
    byGroup.set(g, arr);
  }

  const order: GroupId[] = [
    "restriction",
    "enumeration",
    "range",
    "precision",
    "length",
    "pattern",
    "whitespace",
    "other",
  ];

  return (
    <section className="mt-3">
      <h3 className="font-semibold mb-3 flex items-baseline gap-2">
        <span>Facets &amp; Restrictions</span>
        {inheritedFrom && (
          <span className="text-xs font-normal text-slate-400">
            · inherited from <code>{inheritedFrom}</code>
          </span>
        )}
      </h3>
      <div className="space-y-4">
        {order.map((gid) => {
          if (gid === "restriction") {
            return restriction ? (
              <RestrictionGroup key={gid} restriction={restriction} />
            ) : null;
          }
          const list = byGroup.get(gid);
          if (!list || !list.length) return null;
          switch (gid) {
            case "enumeration":
              return <EnumerationGroup key={gid} facets={list} />;
            case "range":
              return (
                <RangeGroup
                  key={gid}
                  facets={list}
                  digits={byGroup.get("precision") ?? []}
                />
              );
            case "precision":
              return byGroup.has("range") ? null : (
                <PrecisionGroup key={gid} facets={list} />
              );
            case "length":
              return <LengthGroup key={gid} facets={list} />;
            case "pattern":
              return <PatternGroup key={gid} facets={list} />;
            case "whitespace":
              return <WhitespaceGroup key={gid} facets={list} />;
            case "other":
              return <OtherGroup key={gid} facets={list} />;
            default:
              return null;
          }
        })}
      </div>
    </section>
  );
}

function GroupHead({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="text-[10.5px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1.5">
      {title}
      {meta && <span className="font-normal text-slate-400 ml-1">· {meta}</span>}
    </div>
  );
}

function RestrictionGroup({
  restriction: r,
}: {
  restriction: NonNullable<FacetGroupsProps["restriction"]>;
}) {
  const rows: [string, string][] = [];
  if (r.base) rows.push(["Base", r.base]);
  if (r.derivation) rows.push(["Derivation", r.derivation]);
  if (r.item_type) rows.push(["Item type", r.item_type]);
  if (r.member_types.length) rows.push(["Members", r.member_types.join(" ")]);
  if (!rows.length) return null;
  return (
    <div>
      <GroupHead title="Restriction" />
      <table className="w-full text-xs">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k}>
              <th className="text-left font-normal text-slate-500 py-0.5 pr-3 w-1/3">{k}</th>
              <td className="font-mono py-0.5 break-all">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EnumerationGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Enumeration" meta={`${facets.length} values`} />
      <div className="flex flex-wrap gap-1">
        {facets.map((f, i) => (
          <span
            key={i}
            className="font-mono text-[11px] px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-200 dark:border-emerald-800/50"
            title={f.fixed ? "fixed" : undefined}
          >
            {f.value}
          </span>
        ))}
      </div>
    </div>
  );
}

function RangeGroup({ facets, digits }: { facets: Facet[]; digits: Facet[] }) {
  const find = (k: FacetKind) => facets.find((f) => f.kind === k)?.value;
  const minI = find("minInclusive");
  const minE = find("minExclusive");
  const maxI = find("maxInclusive");
  const maxE = find("maxExclusive");
  const minVal = minI ?? minE ?? "−∞";
  const maxVal = maxI ?? maxE ?? "+∞";
  const minOp = minI ? "≥" : minE ? ">" : "";
  const maxOp = maxI ? "≤" : maxE ? "<" : "";
  return (
    <div>
      <GroupHead title="Range" />
      <div className="flex items-center gap-2 rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 px-3 py-1.5 font-mono text-xs">
        <span className="text-slate-400 text-[10px]">{minOp}</span>
        <span className="font-semibold text-emerald-700 dark:text-emerald-300">{minVal}</span>
        <span className="flex-1 h-[3px] rounded bg-gradient-to-r from-slate-300 via-slate-500 to-slate-300 dark:from-slate-700 dark:via-slate-500 dark:to-slate-700" />
        <span className="font-semibold text-emerald-700 dark:text-emerald-300">{maxVal}</span>
        <span className="text-slate-400 text-[10px]">{maxOp}</span>
      </div>
      {digits.length > 0 && (
        <div className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-xs">
          {digits.map((d) => (
            <Fragment key={d.kind}>
              <span className="text-slate-500">{d.kind}</span>
              <span>{d.value}</span>
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
}

function PrecisionGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Precision" />
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-xs">
        {facets.map((f) => (
          <Fragment key={f.kind}>
            <span className="text-slate-500">{f.kind}</span>
            <span>{f.value}</span>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function LengthGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Length" />
      <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 font-mono text-xs">
        {facets.map((f) => (
          <Fragment key={f.kind}>
            <span className="text-slate-500">{f.kind}</span>
            <span>{f.value} chars</span>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function PatternGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead
        title="Pattern"
        meta={facets.length > 1 ? `${facets.length} alternatives` : undefined}
      />
      <div className="space-y-1">
        {facets.map((f, i) => (
          <div
            key={i}
            className="font-mono text-xs rounded border border-slate-200 dark:border-slate-700 border-l-2 border-l-accent bg-slate-50 dark:bg-slate-900/60 px-3 py-1.5 whitespace-pre-wrap break-all"
            title="Regular expression"
          >
            {f.value}
          </div>
        ))}
      </div>
    </div>
  );
}

function WhitespaceGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Whitespace" />
      <span className="inline-block font-mono text-xs px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
        {facets[0].value}
      </span>
    </div>
  );
}

function OtherGroup({ facets }: { facets: Facet[] }) {
  return (
    <div>
      <GroupHead title="Other" />
      <ul className="space-y-0.5">
        {facets.map((f, i) => (
          <li key={`${f.kind}-${i}`} className="font-mono text-xs">
            <span className="text-slate-500">{f.kind}</span> ={" "}
            <span className="text-emerald-700 dark:text-emerald-300">{f.value}</span>
            {f.fixed && <span className="text-slate-500 ml-1">(fixed)</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 1.2: Update `DetailPanel.tsx` to import from the new module**

Delete the entire `// ====== FacetGroups` block (lines 329-612) from `DetailPanel.tsx` and replace the existing local `import { Fragment, useMemo } from "react";` at line 1 with `import { useMemo } from "react";` (Fragment no longer needed). Add this import near the top:

```tsx
import { FacetGroups } from "./FacetGroups";
```

Re-export it for downstream callers (the existing test imports it from `DetailPanel`):

```tsx
// at the bottom of DetailPanel.tsx, after the function definitions:
export { FacetGroups } from "./FacetGroups";
```

- [ ] **Step 1.3: Verify import path in the existing test still works**

The test at `frontend/tests/components.detailPanel.test.tsx:3` does
`import { DetailPanel, FacetGroups } from "../src/components/DetailPanel";` — the re-export in step 1.2 keeps this working. No test edits needed yet.

- [ ] **Step 1.4: Run the existing tests**

```
cd frontend && npm run test -- tests/components.detailPanel.test.tsx
```

Expected: all 5 tests in the existing file PASS, no behaviour change.

- [ ] **Step 1.5: Run typecheck**

```
cd frontend && npm run build
```

Expected: clean build (no TS errors).

- [ ] **Step 1.6: Commit**

```
git add frontend/src/components/FacetGroups.tsx frontend/src/components/DetailPanel.tsx
git commit -m "refactor(detail-panel): extract FacetGroups to its own module"
```

---

## Task 2: `flattenParticle` helper + tests

**Why:** Pure data transformation. Drives the Children table. Test it in isolation before any UI lands on top.

**Files:**
- Create: `frontend/src/lib/particles.ts`
- Test: `frontend/tests/lib.particles.test.ts`

- [ ] **Step 2.1: Write the failing tests**

```ts
// frontend/tests/lib.particles.test.ts
import { describe, expect, it } from "vitest";
import { flattenParticle } from "../src/lib/particles";
import type { ElementDecl, Particle } from "../src/types/schema";

function leaf(name: string): ElementDecl {
  return {
    id: `element:test/${name}`,
    name,
    qname: null,
    ref: null,
    type_name: "xs:string",
    type_inline_simple: null,
    type_inline_complex: null,
    min_occurs: 1,
    max_occurs: 1,
    default: null,
    fixed: null,
    nillable: false,
    abstract: false,
    substitution_group: null,
    form: null,
    target_namespace: null,
    is_global: false,
    annotation: null,
    source_ref: null,
  };
}

function elementParticle(element: ElementDecl, min = 1, max: number | "unbounded" = 1): Particle {
  return {
    kind: "element",
    min_occurs: min,
    max_occurs: max,
    element,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

function compositor(
  kind: "sequence" | "choice" | "all",
  children: Particle[],
  min = 1,
  max: number | "unbounded" = 1,
): Particle {
  return {
    kind,
    min_occurs: min,
    max_occurs: max,
    element: null,
    group_ref: null,
    group_inline: null,
    children,
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

describe("flattenParticle", () => {
  it("returns [] for null input", () => {
    expect(flattenParticle(null)).toEqual([]);
  });

  it("unwraps the outer compositor and emits children at depth 0", () => {
    const root = compositor("sequence", [
      elementParticle(leaf("A")),
      elementParticle(leaf("B")),
      elementParticle(leaf("C")),
    ]);
    const rows = flattenParticle(root);
    expect(rows).toHaveLength(3);
    expect(rows.every((r) => r.depth === 0)).toBe(true);
    expect(rows.map((r) => r.element?.name)).toEqual(["A", "B", "C"]);
    expect(rows.every((r) => r.compositor === undefined)).toBe(true);
  });

  it("emits a header row for nested compositors and their children at depth+1", () => {
    const inner = compositor("choice", [
      elementParticle(leaf("X")),
      elementParticle(leaf("Y")),
    ]);
    const root = compositor("sequence", [
      elementParticle(leaf("A")),
      inner,
      elementParticle(leaf("B")),
    ]);
    const rows = flattenParticle(root);
    expect(rows.map((r) => ({
      depth: r.depth,
      label: r.element?.name ?? r.compositor ?? r.ellipsis,
    }))).toEqual([
      { depth: 0, label: "A" },
      { depth: 0, label: "choice" },
      { depth: 1, label: "X" },
      { depth: 1, label: "Y" },
      { depth: 0, label: "B" },
    ]);
  });

  it("renders group-ref as a single non-expanded row", () => {
    const groupRef: Particle = {
      kind: "group-ref",
      min_occurs: 1,
      max_occurs: "unbounded",
      element: null,
      group_ref: "tns:NameGroup",
      group_inline: null,
      children: [],
      wildcard_namespace: null,
      wildcard_process_contents: null,
      annotation: null,
    };
    const root = compositor("sequence", [
      elementParticle(leaf("A")),
      groupRef,
    ]);
    const rows = flattenParticle(root);
    expect(rows).toHaveLength(2);
    expect(rows[1]).toMatchObject({
      depth: 0,
      groupRef: "tns:NameGroup",
      occurs: "1..*",
    });
  });

  it("renders any (wildcard) as a single row with namespace and processContents", () => {
    const wildcard: Particle = {
      kind: "any",
      min_occurs: 0,
      max_occurs: "unbounded",
      element: null,
      group_ref: null,
      group_inline: null,
      children: [],
      wildcard_namespace: "##other",
      wildcard_process_contents: "lax",
      annotation: null,
    };
    const root = compositor("sequence", [wildcard]);
    const rows = flattenParticle(root);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      depth: 0,
      any: { namespace: "##other", processContents: "lax" },
      occurs: "0..*",
    });
  });

  it("collapses depth >2 into a single ellipsis row at the deeper level", () => {
    // sequence > choice > sequence > element ("DeepLeaf")
    // depth-0 choice header, depth-1 sequence header, depth-2 sequence header,
    // its child would be at depth 3 → collapsed.
    const deepLeaf = elementParticle(leaf("DeepLeaf"));
    const lvl3 = compositor("sequence", [deepLeaf]);
    const lvl2 = compositor("sequence", [lvl3]);
    const lvl1 = compositor("choice", [lvl2]);
    const root = compositor("sequence", [lvl1]);

    const rows = flattenParticle(root);
    // rows: choice@0, sequence@1, sequence@2, ellipsis@3 (one)
    expect(rows.map((r) => ({
      depth: r.depth,
      label: r.compositor ?? (r.ellipsis ? "…" : r.element?.name),
    }))).toEqual([
      { depth: 0, label: "choice" },
      { depth: 1, label: "sequence" },
      { depth: 2, label: "sequence" },
      { depth: 3, label: "…" },
    ]);
    // The ellipsis tooltip should mention the elided element by name.
    const ellipsis = rows[3];
    expect(ellipsis.ellipsis).toContain("DeepLeaf");
  });

  it("formats occurs as min..max with * for unbounded", () => {
    const root = compositor("sequence", [
      elementParticle(leaf("Once"), 1, 1),
      elementParticle(leaf("Optional"), 0, 1),
      elementParticle(leaf("ZeroToMany"), 0, "unbounded"),
      elementParticle(leaf("OneToMany"), 1, "unbounded"),
    ]);
    const rows = flattenParticle(root);
    expect(rows.map((r) => r.occurs)).toEqual([
      "1..1",
      "0..1",
      "0..*",
      "1..*",
    ]);
  });

  it("walks a non-compositor root particle (single-element top) without unwrapping", () => {
    const root = elementParticle(leaf("Solo"), 0, 1);
    const rows = flattenParticle(root);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ depth: 0, occurs: "0..1" });
    expect(rows[0].element?.name).toBe("Solo");
  });
});
```

- [ ] **Step 2.2: Run the failing tests**

```
cd frontend && npm run test -- tests/lib.particles.test.ts
```

Expected: FAIL — `Cannot find module '../src/lib/particles'`.

- [ ] **Step 2.3: Implement `flattenParticle`**

```ts
// frontend/src/lib/particles.ts
// Flattens an XSD particle tree into an indentation-aware row list for the
// Content Model table. The outer compositor is unwrapped; nested compositors
// emit their own header row. Recursion is capped at MAX_DEPTH; deeper subtrees
// collapse to a single ellipsis row whose `ellipsis` text serialises the
// elided sub-tree for a tooltip.

import type { ElementDecl, Particle, QName } from "../types/schema";

export const MAX_DEPTH = 2;

export type CompositorKind = "sequence" | "choice" | "all";

export interface FlatRow {
  /** Stable React key. */
  key: string;
  /** Indentation level. 0 = direct child of the unwrapped outer compositor. */
  depth: number;
  /** Formatted "min..max" string (e.g. "1..1", "0..*"). */
  occurs: string;
  /** When this row IS a nested compositor header. */
  compositor?: CompositorKind;
  /** When this row is an element leaf. */
  element?: ElementDecl;
  /** When this row is a group-ref leaf — the QName of the referenced group. */
  groupRef?: QName;
  /** When this row is a wildcard. */
  any?: { namespace: string | null; processContents: string | null };
  /** When this row is the collapse marker for an elided deep sub-tree. */
  ellipsis?: string;
}

export function flattenParticle(particle: Particle | null): FlatRow[] {
  const rows: FlatRow[] = [];
  if (!particle) return rows;

  if (particle.kind === "sequence" || particle.kind === "choice" || particle.kind === "all") {
    // Unwrap the outer compositor; its children become the depth-0 rows.
    let counter = 0;
    for (const child of particle.children) {
      walk(child, 0, `r${counter++}`, rows);
    }
    return rows;
  }

  walk(particle, 0, "r0", rows);
  return rows;
}

function walk(
  particle: Particle,
  depth: number,
  keyPrefix: string,
  rows: FlatRow[],
): void {
  const occurs = formatOccurs(particle.min_occurs, particle.max_occurs);

  if (particle.kind === "element" && particle.element) {
    rows.push({
      key: `${keyPrefix}-el`,
      depth,
      occurs,
      element: particle.element,
    });
    return;
  }

  if (particle.kind === "group-ref") {
    rows.push({
      key: `${keyPrefix}-gr`,
      depth,
      occurs,
      groupRef: particle.group_ref ?? "(group)",
    });
    return;
  }

  if (particle.kind === "any") {
    rows.push({
      key: `${keyPrefix}-any`,
      depth,
      occurs,
      any: {
        namespace: particle.wildcard_namespace,
        processContents: particle.wildcard_process_contents,
      },
    });
    return;
  }

  // sequence | choice | all  → emit a header row, then walk children.
  rows.push({
    key: `${keyPrefix}-c`,
    depth,
    occurs,
    compositor: particle.kind as CompositorKind,
  });

  if (depth >= MAX_DEPTH) {
    rows.push({
      key: `${keyPrefix}-…`,
      depth: depth + 1,
      occurs: "",
      ellipsis: serialiseSubtree(particle, ""),
    });
    return;
  }

  let counter = 0;
  for (const child of particle.children) {
    walk(child, depth + 1, `${keyPrefix}-${counter++}`, rows);
  }
}

function formatOccurs(min: number, max: number | "unbounded"): string {
  const maxStr = max === "unbounded" ? "*" : String(max);
  return `${min}..${maxStr}`;
}

// Recursive, indented text rendering used for the ellipsis-row tooltip so
// the user can still see what was collapsed.
function serialiseSubtree(particle: Particle, indent: string): string {
  const occ = formatOccurs(particle.min_occurs, particle.max_occurs);
  const head = (() => {
    if (particle.kind === "element" && particle.element) {
      return `${particle.element.name ?? particle.element.ref ?? "?"} [${occ}]`;
    }
    if (particle.kind === "group-ref") {
      return `«group ${particle.group_ref ?? "?"}» [${occ}]`;
    }
    if (particle.kind === "any") {
      return `any [${occ}]`;
    }
    return `${particle.kind} [${occ}]`;
  })();
  const lines = [indent + head];
  for (const child of particle.children) {
    lines.push(serialiseSubtree(child, indent + "  "));
  }
  return lines.join("\n");
}
```

- [ ] **Step 2.4: Run tests until they pass**

```
cd frontend && npm run test -- tests/lib.particles.test.ts
```

Expected: all 8 tests PASS.

- [ ] **Step 2.5: Typecheck**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 2.6: Commit**

```
git add frontend/src/lib/particles.ts frontend/tests/lib.particles.test.ts
git commit -m "feat(particles): add flattenParticle helper for content-model rows"
```

---

## Task 3: `Header` component

**Why:** Top of the Content Model panel. Pure presentational, no data resolution. Needed by `ContentModelView`.

**Files:**
- Create: `frontend/src/components/ContentModelView/Header.tsx`
- Create: `frontend/src/components/ContentModelView/symbols.ts`

- [ ] **Step 3.1: Create the symbols module**

```ts
// frontend/src/components/ContentModelView/symbols.ts
import type { CompositorKind } from "../../lib/particles";

export const COMPOSITOR_GLYPH: Record<CompositorKind, string> = {
  sequence: "▦",
  choice: "◇",
  all: "≡",
};

export const GROUP_REF_GLYPH = "★";
export const WILDCARD_GLYPH = "*";
```

- [ ] **Step 3.2: Implement the Header component**

The Header receives the resolved `NodeIndexEntry` for the selection plus an optional callback for clicking the "extends" base link. It renders the kind badge, label, qname, type-line and (for `extension`-derived complex types) a one-line `extends <Base>` link.

```tsx
// frontend/src/components/ContentModelView/Header.tsx
import type { NodeIndexEntry, ComplexType, ElementDecl, SimpleType } from "../../types/schema";
import { KindBadge } from "../TreeView/KindBadge";

interface HeaderProps {
  entry: NodeIndexEntry;
  onSelectBase?: (qname: string) => void;
}

function typeLine(entry: NodeIndexEntry): string {
  const node = entry.node;
  if (entry.kind === "element") {
    const e = node as ElementDecl;
    if (e.type_name) return `→ ${e.type_name}`;
    if (e.type_inline_complex) return "→ (inline complex type)";
    if (e.type_inline_simple) return "→ (inline simple type)";
    return "→ (anyType)";
  }
  if (entry.kind === "complexType") {
    const c = node as ComplexType;
    return `complexType · ${c.content_kind} content`;
  }
  if (entry.kind === "simpleType") {
    const s = node as SimpleType;
    return `simpleType · ${s.derivation}${s.base ? ` of ${s.base}` : ""}`;
  }
  if (entry.kind === "group") return "model group";
  if (entry.kind === "attributeGroup") return "attribute group";
  if (entry.kind === "attribute") return "attribute";
  return "";
}

function extendsBase(entry: NodeIndexEntry): string | null {
  if (entry.kind !== "complexType") return null;
  const c = entry.node as ComplexType;
  if (c.derivation === "extension" && c.base) return c.base;
  return null;
}

export function Header({ entry, onSelectBase }: HeaderProps) {
  const base = extendsBase(entry);
  return (
    <header className="px-6 pt-6 pb-4 border-b border-slate-200 dark:border-slate-800">
      <div className="flex items-center gap-2">
        <KindBadge kind={entry.kind} />
        <h2 className="font-mono text-lg">{entry.label}</h2>
      </div>
      {entry.qname && (
        <p className="mt-1 text-xs font-mono text-slate-500 dark:text-slate-400 break-all">
          {entry.qname}
        </p>
      )}
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-300 font-mono">{typeLine(entry)}</p>
      {base && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          extends{" "}
          <button
            type="button"
            className="font-mono text-accent hover:underline"
            onClick={() => onSelectBase?.(base)}
          >
            {base}
          </button>
          {" "}— see base for inherited members.
        </p>
      )}
    </header>
  );
}
```

- [ ] **Step 3.3: Typecheck**

```
cd frontend && npm run build
```

Expected: clean (component is unused so far; TS will warn only if there are syntax/type errors — not unused-export errors with the project's settings).

- [ ] **Step 3.4: Commit**

```
git add frontend/src/components/ContentModelView/Header.tsx frontend/src/components/ContentModelView/symbols.ts
git commit -m "feat(content-model): header component + compositor glyph map"
```

---

## Task 4: `SimpleTypeCard` component

**Why:** Encapsulates the "this is a simple type" rendering used for `simpleType`, simple-content `complexType`, simple-typed `element`, and `attribute` selections. Wraps `FacetGroups`.

**Files:**
- Create: `frontend/src/components/ContentModelView/SimpleTypeCard.tsx`

- [ ] **Step 4.1: Implement the component**

```tsx
// frontend/src/components/ContentModelView/SimpleTypeCard.tsx
import type { Facet, SimpleType } from "../../types/schema";
import { FacetGroups } from "../FacetGroups";

interface SimpleTypeCardProps {
  /** The owning simple type, when one is available (may be inline or named). */
  simple?: SimpleType | null;
  /** Optional standalone facet list — used by complexType simple-content where
   *  there is no full SimpleType node (just facets + a base QName). */
  standaloneFacets?: Facet[];
  standaloneBase?: string | null;
  /** When facets come from a separate named type, label the source. */
  inheritedFrom?: string | null;
  /** Empty-state text when neither simple nor standaloneFacets are useful. */
  emptyText?: string;
}

export function SimpleTypeCard({
  simple,
  standaloneFacets,
  standaloneBase,
  inheritedFrom,
  emptyText = "No constraints — accepts any value of the base type.",
}: SimpleTypeCardProps) {
  if (simple) {
    const restriction = {
      base: simple.base,
      derivation: simple.derivation,
      item_type: simple.item_type,
      member_types: simple.member_types,
    };
    if (!simple.facets.length && !simple.base && !simple.item_type && !simple.member_types.length) {
      return (
        <section className="px-6 py-4 text-sm text-slate-500 dark:text-slate-400">
          {emptyText}
        </section>
      );
    }
    return (
      <section className="px-6 py-4">
        <FacetGroups
          facets={simple.facets}
          restriction={restriction}
          inheritedFrom={inheritedFrom ?? null}
        />
      </section>
    );
  }

  if (standaloneFacets && (standaloneFacets.length > 0 || standaloneBase)) {
    return (
      <section className="px-6 py-4">
        <FacetGroups
          facets={standaloneFacets}
          restriction={
            standaloneBase
              ? { base: standaloneBase, derivation: "restriction", item_type: null, member_types: [] }
              : null
          }
          inheritedFrom={inheritedFrom ?? null}
        />
      </section>
    );
  }

  return (
    <section className="px-6 py-4 text-sm text-slate-500 dark:text-slate-400">
      {emptyText}
    </section>
  );
}
```

- [ ] **Step 4.2: Typecheck**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 4.3: Commit**

```
git add frontend/src/components/ContentModelView/SimpleTypeCard.tsx
git commit -m "feat(content-model): SimpleTypeCard wrapping FacetGroups"
```

---

## Task 5: `AttributesTable` component (with attribute-group resolution)

**Why:** Lists attributes for the selected node with a flat schema. Resolves `attribute_group_refs` transitively via the existing index.

**Files:**
- Create: `frontend/src/components/ContentModelView/AttributesTable.tsx`

- [ ] **Step 5.1: Implement the component**

```tsx
// frontend/src/components/ContentModelView/AttributesTable.tsx
import { useMemo } from "react";
import type { AttributeDecl, AttributeGroup, NodeIndexEntry } from "../../types/schema";
import { useSelection } from "../../stores/selectionStore";
import { resolveReference } from "../../lib/indexSchema";

interface AttributesTableProps {
  /** Attributes declared directly on the node. */
  attributes: AttributeDecl[];
  /** Attribute-group QNames to resolve and inline. */
  attributeGroupRefs: string[];
}

interface ResolvedAttribute {
  attr: AttributeDecl;
  /** Origin label when the attribute was pulled in via a referenced group. */
  origin: string | null;
}

function collectFromGroup(
  ref: string,
  index: NodeIndexEntry[],
  seen: Set<string>,
  out: ResolvedAttribute[],
): void {
  const entry = resolveReference(ref, index, ["attributeGroup"]);
  if (!entry) return;
  if (seen.has(entry.id)) return;
  seen.add(entry.id);
  const ag = entry.node as AttributeGroup;
  for (const a of ag.attributes) out.push({ attr: a, origin: entry.label });
  for (const nested of ag.attribute_group_refs) {
    collectFromGroup(nested, index, seen, out);
  }
}

function firstDocLine(attr: AttributeDecl): string {
  const text = attr.annotation?.documentation?.[0]?.text?.trim() ?? "";
  if (!text) return "";
  return text.split(/\r?\n/)[0];
}

function defOrFix(attr: AttributeDecl): string {
  if (attr.fixed != null) return `[fixed] ${attr.fixed}`;
  if (attr.default != null) return attr.default;
  return "—";
}

export function AttributesTable({ attributes, attributeGroupRefs }: AttributesTableProps) {
  const index = useSelection((s) => s.index);
  const setSelected = useSelection((s) => s.setSelected);

  const rows = useMemo<ResolvedAttribute[]>(() => {
    const out: ResolvedAttribute[] = attributes.map((a) => ({ attr: a, origin: null }));
    const seen = new Set<string>();
    for (const ref of attributeGroupRefs) {
      collectFromGroup(ref, index, seen, out);
    }
    return out;
  }, [attributes, attributeGroupRefs, index]);

  if (!rows.length) return null;

  const onTypeClick = (typeName: string | null) => {
    if (!typeName) return;
    const entry = resolveReference(typeName, index, ["simpleType"]);
    if (entry) setSelected(entry.id);
  };

  return (
    <section className="px-6 py-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
        Attributes
      </h3>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-[10.5px] uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
            <th className="py-1.5 pr-3 font-semibold">Name</th>
            <th className="py-1.5 pr-3 font-semibold">Type</th>
            <th className="py-1.5 pr-3 font-semibold">Use</th>
            <th className="py-1.5 pr-3 font-semibold">Default / Fixed</th>
            <th className="py-1.5 pr-3 font-semibold">Doc</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ attr, origin }, i) => {
            const doc = firstDocLine(attr);
            return (
              <tr
                key={`${attr.id}-${i}`}
                className="border-b border-slate-100 dark:border-slate-900 hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer"
                onClick={() => setSelected(attr.id)}
              >
                <td className="py-1.5 pr-3 font-mono">
                  @{attr.name ?? attr.ref ?? "?"}
                  {origin && (
                    <span className="ml-1 text-[10px] text-slate-400">from {origin}</span>
                  )}
                </td>
                <td className="py-1.5 pr-3 font-mono">
                  {attr.type_name ? (
                    <button
                      type="button"
                      className="text-accent hover:underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onTypeClick(attr.type_name);
                      }}
                    >
                      {attr.type_name}
                    </button>
                  ) : attr.type_inline ? (
                    <span className="text-slate-500">(inline simple)</span>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </td>
                <td className="py-1.5 pr-3">{attr.use}</td>
                <td className="py-1.5 pr-3 font-mono">{defOrFix(attr)}</td>
                <td
                  className="py-1.5 pr-3 text-slate-600 dark:text-slate-400 text-xs truncate max-w-[260px]"
                  title={attr.annotation?.documentation?.[0]?.text ?? undefined}
                >
                  {doc || ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
```

- [ ] **Step 5.2: Typecheck**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 5.3: Commit**

```
git add frontend/src/components/ContentModelView/AttributesTable.tsx
git commit -m "feat(content-model): AttributesTable resolves attribute_group_refs"
```

---

## Task 6: `ChildrenTable` component

**Why:** Renders the flat row list from `flattenParticle`. Compositor symbols, indentation guides, type click-through.

**Files:**
- Create: `frontend/src/components/ContentModelView/ChildrenTable.tsx`

- [ ] **Step 6.1: Implement the component**

```tsx
// frontend/src/components/ContentModelView/ChildrenTable.tsx
import type { Particle } from "../../types/schema";
import { flattenParticle } from "../../lib/particles";
import { useSelection } from "../../stores/selectionStore";
import { resolveReference } from "../../lib/indexSchema";
import { COMPOSITOR_GLYPH, GROUP_REF_GLYPH, WILDCARD_GLYPH } from "./symbols";
import { KindBadge } from "../TreeView/KindBadge";

interface ChildrenTableProps {
  particle: Particle | null;
}

const INDENT_PX = 16;

export function ChildrenTable({ particle }: ChildrenTableProps) {
  const index = useSelection((s) => s.index);
  const setSelected = useSelection((s) => s.setSelected);
  const rows = flattenParticle(particle);

  if (!rows.length) {
    return (
      <section className="px-6 py-4 text-sm text-slate-500 dark:text-slate-400">
        No child elements declared.
      </section>
    );
  }

  const onTypeClick = (typeName: string | null) => {
    if (!typeName) return;
    const entry =
      resolveReference(typeName, index, ["complexType"]) ??
      resolveReference(typeName, index, ["simpleType"]) ??
      resolveReference(typeName, index, ["element"]);
    if (entry) setSelected(entry.id);
  };

  const onGroupClick = (groupRef: string) => {
    const entry = resolveReference(groupRef, index, ["group"]);
    if (entry) setSelected(entry.id);
  };

  return (
    <section className="px-6 py-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
        Children
      </h3>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-[10.5px] uppercase tracking-wide text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
            <th className="py-1.5 pr-2 w-6"></th>
            <th className="py-1.5 pr-3 font-semibold">Name</th>
            <th className="py-1.5 pr-3 font-semibold">Kind</th>
            <th className="py-1.5 pr-3 font-semibold">Type</th>
            <th className="py-1.5 pr-3 font-semibold">Card.</th>
            <th className="py-1.5 pr-3 font-semibold">Default / Fixed</th>
            <th className="py-1.5 pr-3 font-semibold">Doc</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const padLeft = row.depth * INDENT_PX;

            // Compositor header row
            if (row.compositor) {
              return (
                <tr
                  key={row.key}
                  className="border-b border-slate-100 dark:border-slate-900 bg-slate-50/40 dark:bg-slate-900/30"
                >
                  <td className="py-1 pr-2 text-center text-slate-500" style={{ paddingLeft: padLeft }}>
                    {COMPOSITOR_GLYPH[row.compositor]}
                  </td>
                  <td className="py-1 pr-3 font-mono text-xs uppercase tracking-wide text-slate-500">
                    {row.compositor}
                  </td>
                  <td className="py-1 pr-3" />
                  <td className="py-1 pr-3" />
                  <td className="py-1 pr-3 font-mono text-xs text-slate-500">{row.occurs}</td>
                  <td className="py-1 pr-3" />
                  <td className="py-1 pr-3" />
                </tr>
              );
            }

            // Ellipsis row
            if (row.ellipsis !== undefined) {
              return (
                <tr key={row.key} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="py-1 pr-2 text-center text-slate-400" style={{ paddingLeft: padLeft }}>
                    …
                  </td>
                  <td
                    colSpan={6}
                    className="py-1 pr-3 text-xs text-slate-500 italic"
                    title={row.ellipsis}
                  >
                    deeper sub-tree (hover for details)
                  </td>
                </tr>
              );
            }

            // group-ref row
            if (row.groupRef) {
              return (
                <tr
                  key={row.key}
                  className="border-b border-slate-100 dark:border-slate-900 hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer"
                  onClick={() => onGroupClick(row.groupRef!)}
                >
                  <td className="py-1.5 pr-2 text-center text-slate-500" style={{ paddingLeft: padLeft }}>
                    {GROUP_REF_GLYPH}
                  </td>
                  <td className="py-1.5 pr-3 font-mono">
                    «{row.groupRef}»
                  </td>
                  <td className="py-1.5 pr-3"><KindBadge kind="group" /></td>
                  <td className="py-1.5 pr-3"></td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{row.occurs}</td>
                  <td className="py-1.5 pr-3"></td>
                  <td className="py-1.5 pr-3"></td>
                </tr>
              );
            }

            // any (wildcard) row
            if (row.any) {
              return (
                <tr key={row.key} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="py-1.5 pr-2 text-center text-slate-500" style={{ paddingLeft: padLeft }}>
                    {WILDCARD_GLYPH}
                  </td>
                  <td className="py-1.5 pr-3 font-mono italic text-slate-500">any</td>
                  <td className="py-1.5 pr-3 text-xs text-slate-500">wildcard</td>
                  <td className="py-1.5 pr-3 font-mono text-xs text-slate-500">
                    ns={row.any.namespace ?? "##any"} · {row.any.processContents ?? "strict"}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{row.occurs}</td>
                  <td className="py-1.5 pr-3"></td>
                  <td className="py-1.5 pr-3"></td>
                </tr>
              );
            }

            // element row
            if (row.element) {
              const e = row.element;
              const docFull = e.annotation?.documentation?.[0]?.text ?? null;
              const docFirst = docFull ? docFull.split(/\r?\n/)[0] : "";
              const typeName = e.type_name;
              const defOrFix =
                e.fixed != null ? `[fixed] ${e.fixed}` : e.default ?? "—";
              return (
                <tr
                  key={row.key}
                  className="border-b border-slate-100 dark:border-slate-900 hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer"
                  onClick={() => setSelected(e.id)}
                >
                  <td className="py-1.5 pr-2" style={{ paddingLeft: padLeft }} />
                  <td className="py-1.5 pr-3 font-mono">{e.name ?? e.ref ?? "?"}</td>
                  <td className="py-1.5 pr-3"><KindBadge kind="element" /></td>
                  <td className="py-1.5 pr-3 font-mono">
                    {typeName ? (
                      <button
                        type="button"
                        className="text-accent hover:underline"
                        onClick={(ev) => {
                          ev.stopPropagation();
                          onTypeClick(typeName);
                        }}
                      >
                        {typeName}
                      </button>
                    ) : e.type_inline_complex ? (
                      <span className="text-slate-500">(inline complex)</span>
                    ) : e.type_inline_simple ? (
                      <span className="text-slate-500">(inline simple)</span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{row.occurs}</td>
                  <td className="py-1.5 pr-3 font-mono text-xs">{defOrFix}</td>
                  <td
                    className="py-1.5 pr-3 text-slate-600 dark:text-slate-400 text-xs truncate max-w-[260px]"
                    title={docFull ?? undefined}
                  >
                    {docFirst}
                  </td>
                </tr>
              );
            }

            return null;
          })}
        </tbody>
      </table>
    </section>
  );
}
```

- [ ] **Step 6.2: Typecheck**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 6.3: Commit**

```
git add frontend/src/components/ContentModelView/ChildrenTable.tsx
git commit -m "feat(content-model): ChildrenTable renders flattened particles"
```

---

## Task 7: `ContentModelView` top-level dispatcher + integration tests

**Why:** Picks the right sub-view per selected node kind. This is the component `App.tsx` will render.

**Files:**
- Create: `frontend/src/components/ContentModelView/ContentModelView.tsx`
- Test: `frontend/tests/components.contentModelView.test.tsx`

- [ ] **Step 7.1: Write the failing tests**

```tsx
// frontend/tests/components.contentModelView.test.tsx
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ContentModelView } from "../src/components/ContentModelView/ContentModelView";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";

function selectId(id: string) {
  act(() => {
    useSelection.getState().setSchema("id", smallModel);
    useSelection.getState().setSelected(id);
  });
}

describe("ContentModelView", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("renders Children + Attributes for an element with a complex type", () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    expect(screen.getByRole("heading", { name: "Person" })).toBeInTheDocument();
    expect(screen.getByText("Children")).toBeInTheDocument();
    expect(screen.getByText("FirstName")).toBeInTheDocument();
    expect(screen.getByText("LastName")).toBeInTheDocument();
    expect(screen.getByText("Attributes")).toBeInTheDocument();
    expect(screen.getByText("@id")).toBeInTheDocument();
  });

  it("renders only the simple-type card for an element with a named simpleType", () => {
    selectId("element:{http://example.com/simple}PersonType/Age");
    render(<ContentModelView />);
    expect(screen.queryByText("Children")).not.toBeInTheDocument();
    expect(screen.queryByText("Attributes")).not.toBeInTheDocument();
    expect(screen.getByText("Range")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("130")).toBeInTheDocument();
  });

  it("renders enumeration values for a simpleType selection", () => {
    selectId("simpleType:{http://example.com/simple}ColorType");
    render(<ContentModelView />);
    expect(screen.getByText("Enumeration")).toBeInTheDocument();
    expect(screen.getByText("red")).toBeInTheDocument();
    expect(screen.getByText("green")).toBeInTheDocument();
    expect(screen.getByText("blue")).toBeInTheDocument();
  });

  it("clicking a child element row updates the selection", async () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    const row = screen.getByText("FirstName").closest("tr");
    expect(row).not.toBeNull();
    await userEvent.click(row!);
    expect(useSelection.getState().selectedId).toBe(
      "element:{http://example.com/simple}PersonType/FirstName",
    );
  });

  it("clicking a Type cell with a resolvable QName selects the target", async () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    // PersonType.Age has type tns:AgeType — find the Type-cell button.
    const button = screen.getByRole("button", { name: "tns:AgeType" });
    await userEvent.click(button);
    expect(useSelection.getState().selectedId).toBe(
      "simpleType:{http://example.com/simple}AgeType",
    );
  });

  it("returns nothing when no selection is active", () => {
    act(() => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection.getState().setSelected(null);
    });
    const { container } = render(<ContentModelView />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 7.2: Run failing tests**

```
cd frontend && npm run test -- tests/components.contentModelView.test.tsx
```

Expected: FAIL — `Cannot find module '../src/components/ContentModelView/ContentModelView'`.

- [ ] **Step 7.3: Implement the dispatcher**

```tsx
// frontend/src/components/ContentModelView/ContentModelView.tsx
import { useMemo } from "react";
import type {
  AttributeDecl,
  ComplexType,
  ElementDecl,
  Group,
  AttributeGroup,
  NodeIndexEntry,
  SimpleType,
} from "../../types/schema";
import { useSelection } from "../../stores/selectionStore";
import { resolveReference } from "../../lib/indexSchema";
import { Header } from "./Header";
import { ChildrenTable } from "./ChildrenTable";
import { AttributesTable } from "./AttributesTable";
import { SimpleTypeCard } from "./SimpleTypeCard";

function resolveComplex(typeName: string | null, index: NodeIndexEntry[]): ComplexType | undefined {
  if (!typeName) return undefined;
  const entry = resolveReference(typeName, index, ["complexType"]);
  if (!entry) return undefined;
  return entry.node as ComplexType;
}

function resolveSimple(typeName: string | null, index: NodeIndexEntry[]): {
  type: SimpleType;
  label: string;
} | undefined {
  if (!typeName) return undefined;
  const entry = resolveReference(typeName, index, ["simpleType"]);
  if (!entry) return undefined;
  return { type: entry.node as SimpleType, label: entry.label };
}

export function ContentModelView() {
  const selectedId = useSelection((s) => s.selectedId);
  const indexById = useSelection((s) => s.indexById);
  const index = useSelection((s) => s.index);
  const setSelected = useSelection((s) => s.setSelected);

  const entry = selectedId ? indexById.get(selectedId) : undefined;

  const onSelectBase = (qname: string) => {
    const baseEntry =
      resolveReference(qname, index, ["complexType"]) ??
      resolveReference(qname, index, ["simpleType"]);
    if (baseEntry) setSelected(baseEntry.id);
  };

  const body = useMemo(() => {
    if (!entry) return null;

    if (entry.kind === "element") {
      const e = entry.node as ElementDecl;
      const inlineComplex = e.type_inline_complex;
      const namedComplex = !inlineComplex ? resolveComplex(e.type_name, index) : undefined;
      const complex = inlineComplex ?? namedComplex;
      if (complex) {
        return (
          <>
            <ChildrenTable particle={complex.particle} />
            <AttributesTable
              attributes={complex.attributes}
              attributeGroupRefs={complex.attribute_group_refs}
            />
            {complex.content_kind === "simple" && (
              <SimpleTypeCard
                standaloneFacets={complex.simple_content_facets}
                standaloneBase={complex.simple_content_base}
              />
            )}
          </>
        );
      }
      const inlineSimple = e.type_inline_simple;
      if (inlineSimple) return <SimpleTypeCard simple={inlineSimple} />;
      const namedSimple = resolveSimple(e.type_name, index);
      if (namedSimple) {
        return <SimpleTypeCard simple={namedSimple.type} inheritedFrom={namedSimple.label} />;
      }
      return <SimpleTypeCard emptyText="No type information available." />;
    }

    if (entry.kind === "complexType") {
      const c = entry.node as ComplexType;
      return (
        <>
          {c.particle && <ChildrenTable particle={c.particle} />}
          <AttributesTable
            attributes={c.attributes}
            attributeGroupRefs={c.attribute_group_refs}
          />
          {c.content_kind === "simple" && (
            <SimpleTypeCard
              standaloneFacets={c.simple_content_facets}
              standaloneBase={c.simple_content_base}
            />
          )}
        </>
      );
    }

    if (entry.kind === "simpleType") {
      const s = entry.node as SimpleType;
      return <SimpleTypeCard simple={s} />;
    }

    if (entry.kind === "group") {
      const g = entry.node as Group;
      return <ChildrenTable particle={g.particle} />;
    }

    if (entry.kind === "attributeGroup") {
      const ag = entry.node as AttributeGroup;
      return (
        <AttributesTable
          attributes={ag.attributes}
          attributeGroupRefs={ag.attribute_group_refs}
        />
      );
    }

    if (entry.kind === "attribute") {
      const a = entry.node as AttributeDecl;
      if (a.type_inline) return <SimpleTypeCard simple={a.type_inline} />;
      const namedSimple = resolveSimple(a.type_name, index);
      if (namedSimple) {
        return <SimpleTypeCard simple={namedSimple.type} inheritedFrom={namedSimple.label} />;
      }
      return <SimpleTypeCard emptyText="No simple-type metadata available for this attribute." />;
    }

    return null;
  }, [entry, index]);

  if (!entry) return null;

  return (
    <div className="h-full overflow-auto">
      <Header entry={entry} onSelectBase={onSelectBase} />
      {body}
    </div>
  );
}
```

- [ ] **Step 7.4: Run tests until they pass**

```
cd frontend && npm run test -- tests/components.contentModelView.test.tsx
```

Expected: all 6 tests PASS.

- [ ] **Step 7.5: Run the full frontend test suite**

```
cd frontend && npm run test
```

Expected: all tests pass — the existing `DetailPanel`, tree, diagram and other suites stay green because no public APIs changed.

- [ ] **Step 7.6: Typecheck**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 7.7: Commit**

```
git add frontend/src/components/ContentModelView/ContentModelView.tsx frontend/tests/components.contentModelView.test.tsx
git commit -m "feat(content-model): top-level dispatcher + integration tests"
```

---

## Task 8: Wire `ContentModelView` into the Tree tab

**Why:** Final hookup — replaces `<EmptyOverview />` in the Tree tab's center with `ContentModelView` when something is selected. `EmptyOverview` stays as the empty state.

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 8.1: Add the import and update the conditional render**

In `frontend/src/App.tsx`:

Add to the imports near the top (with the other component imports):

```tsx
import { ContentModelView } from "./components/ContentModelView/ContentModelView";
```

Replace this block (currently at App.tsx:200-206):

```tsx
            {/* CENTER — active view; tree tab shows an overview placeholder */}
            <section className="min-h-0 overflow-hidden flex flex-col">
              <div className="flex-1 min-h-0">
                {activeTab === "tree" && <EmptyOverview />}
                {activeTab === "diagram" && <DiagramView />}
                {activeTab === "text" && <TextView />}
              </div>
            </section>
```

with:

```tsx
            {/* CENTER — active view; Tree tab shows ContentModelView for the
                selected node, or the Schema Overview when nothing is selected. */}
            <section className="min-h-0 overflow-hidden flex flex-col">
              <div className="flex-1 min-h-0">
                {activeTab === "tree" && (selectedId ? <ContentModelView /> : <EmptyOverview />)}
                {activeTab === "diagram" && <DiagramView />}
                {activeTab === "text" && <TextView />}
              </div>
            </section>
```

(`selectedId` is already declared at App.tsx:73 — no other changes needed.)

- [ ] **Step 8.2: Run the full frontend test suite**

```
cd frontend && npm run test
```

Expected: all tests pass.

- [ ] **Step 8.3: Typecheck**

```
cd frontend && npm run build
```

Expected: clean build.

- [ ] **Step 8.4: Manual smoke test in the dev server**

```
cd frontend && npm run dev
```

Then in another terminal, also run the backend (per `CLAUDE.md`):

```
cd backend && uvicorn app.main:app --reload
```

In the browser:
1. Upload a real XSD (e.g. one of the FundsXML samples in `frontend/public` or the user's local samples).
2. Switch to the **Tree** tab — verify Schema Overview is shown initially.
3. Click any element in the Structure tree → Content Model table appears with children + attributes.
4. Click a row in the Children table → Detail panel and Tree highlight update.
5. Click a Type-cell button (e.g. a complex type name) → selection jumps to that type and its content model renders.
6. Select a `simpleType` from the tree → Facets render.
7. Deselect (collapse the tree, click on whitespace, or pick a `group` with no particle) → the panel still renders sensibly.

Stop both dev servers when done.

- [ ] **Step 8.5: Commit**

```
git add frontend/src/App.tsx
git commit -m "feat(app): render ContentModelView in Tree tab on selection"
```

---

## Self-Review (executed during plan writing)

**1. Spec coverage:**
- Layout / Header — Task 3 ✓
- Children table columns + click behaviour — Task 6 ✓
- Attributes table + group resolution — Task 5 ✓
- SimpleTypeCard + reuse of FacetGroups — Tasks 1, 4 ✓
- Per-kind behaviour table — Task 7 (dispatcher + tests cover element/simple, simpleType, complex element) ✓
- Particle flattening rules (1-6) — Task 2 (tests cover unwrap, nested compositor, group-ref, wildcard, depth collapse) ✓
- App.tsx wiring + EmptyOverview fallback — Task 8 ✓
- File structure list — matches the file list at the top of this plan ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows full code; every test step shows full test; commit messages provided.

**3. Type consistency:**
- `flattenParticle` returns `FlatRow[]`, used in `ChildrenTable` ✓
- `FlatRow` field names (`element`, `groupRef`, `any`, `compositor`, `ellipsis`, `occurs`, `depth`, `key`) consistent across particles.ts and ChildrenTable ✓
- `CompositorKind` used in both `particles.ts` and `symbols.ts` ✓
- `resolveReference(ref, index, kinds[])` signature from indexSchema.ts matches all call sites ✓
- `SimpleTypeCard` props referenced consistently from ContentModelView ✓

**4. Ambiguity:** depth-collapse semantics fixed in Task 2 step 2.6 test — ellipsis row appears at `depth + 1` of the deepest visible compositor; matches spec.

---

## Out of scope (per spec — possible follow-ups)

- Sortable / filterable columns
- Sample XML generation
- Inline expansion of inherited members from `extension`
- Recursive "show all leaves" toggle
