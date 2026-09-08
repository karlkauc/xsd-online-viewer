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
import { resolveElementRef, resolveReference } from "../../lib/indexSchema";
import {
  collectAttributeAssertions,
  collectComplexAssertions,
  collectElementAssertions,
  collectSimpleAssertions,
  makeIndexResolver,
  type AssertionGroup,
} from "../../lib/assertions";
import {
  effectiveAttributes,
  effectiveParticle,
  makeIndexComplexResolver,
} from "../../lib/effectiveContent";
import type { IdentityConstraint } from "../../types/schema";
import { Header } from "./Header";
import { ChildrenTable } from "./ChildrenTable";
import { AttributesTable } from "./AttributesTable";
import { AssertionsTable } from "./AssertionsTable";
import { IdentityConstraintsTable } from "./IdentityConstraintsTable";
import { SimpleTypeCard } from "./SimpleTypeCard";

// Small muted note rendered above the Children/Attributes tables when some
// (or all) of a complex type's content comes from an `xs:extension` base
// chain — mirrors SimpleTypeCard's "inherited from" styling. Each base name
// is a clickable link (`onSelectBase`) so the base type is one click away.
function InheritedFromNote({
  names,
  onSelectBase,
}: {
  names: string[];
  onSelectBase: (qname: string) => void;
}) {
  if (!names.length) return null;
  return (
    <p className="px-4 md:px-6 pt-4 text-xs text-slate-500 dark:text-slate-400">
      Content inherited from{" "}
      {names.map((name, i) => (
        <span key={name}>
          {i > 0 && ", "}
          <button
            type="button"
            className="text-accent hover:underline"
            onClick={() => onSelectBase(name)}
          >
            {name}
          </button>
        </span>
      ))}
    </p>
  );
}

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
  const constraintsById = useSelection((s) => s.constraintsById);
  const setSelected = useSelection((s) => s.setSelected);

  const entry = selectedId ? indexById.get(selectedId) : undefined;

  const complexResolver = useMemo(() => makeIndexComplexResolver(index), [index]);

  const onSelectBase = (qname: string) => {
    const baseEntry =
      resolveReference(qname, index, ["complexType"]) ??
      resolveReference(qname, index, ["simpleType"]);
    if (baseEntry) setSelected(baseEntry.id);
  };

  const body = useMemo(() => {
    if (!entry) return null;

    if (entry.kind === "element") {
      const selectedElement = entry.node as ElementDecl;
      // An `<xs:element ref="…">` particle has no content model of its own —
      // show the one of the global declaration it references.
      const e = resolveElementRef(selectedElement, indexById) ?? selectedElement;
      const inlineComplex = e.type_inline_complex;
      const namedComplex = !inlineComplex ? resolveComplex(e.type_name, index) : undefined;
      const complex = inlineComplex ?? namedComplex;
      if (complex) {
        const particleResult = effectiveParticle(complex, complexResolver);
        const attrsResult = effectiveAttributes(complex, complexResolver);
        return (
          <>
            <InheritedFromNote
              names={particleResult.inheritedFrom}
              onSelectBase={onSelectBase}
            />
            <ChildrenTable particle={particleResult.particle} />
            <AttributesTable
              attributes={attrsResult.attributes}
              attributeGroupRefs={attrsResult.attributeGroupRefs}
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
      const particleResult = effectiveParticle(c, complexResolver);
      const attrsResult = effectiveAttributes(c, complexResolver);
      return (
        <>
          <InheritedFromNote
            names={particleResult.inheritedFrom}
            onSelectBase={onSelectBase}
          />
          {particleResult.particle && <ChildrenTable particle={particleResult.particle} />}
          <AttributesTable
            attributes={attrsResult.attributes}
            attributeGroupRefs={attrsResult.attributeGroupRefs}
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onSelectBase is
    // a stable closure over setSelected/index, not worth memoising separately.
  }, [entry, index, indexById, complexResolver]);

  const assertionGroups = useMemo<AssertionGroup[]>(() => {
    if (!entry) return [];
    const resolver = makeIndexResolver(index);
    if (entry.kind === "element") {
      const selectedElement = entry.node as ElementDecl;
      const e = resolveElementRef(selectedElement, indexById) ?? selectedElement;
      return collectElementAssertions(e, resolver);
    }
    if (entry.kind === "complexType") {
      return collectComplexAssertions(entry.node as ComplexType, resolver);
    }
    if (entry.kind === "simpleType") {
      return collectSimpleAssertions(entry.node as SimpleType, resolver);
    }
    if (entry.kind === "attribute") {
      return collectAttributeAssertions(entry.node as AttributeDecl, resolver);
    }
    return [];
  }, [entry, index, indexById]);

  // Identity constraints (xs:key/xs:keyref/xs:unique) only ever apply to
  // elements — unlike assertions, there's no complexType/simpleType/
  // attribute variant to fold in.
  const identityConstraints = useMemo<{
    constraints: IdentityConstraint[];
    host: ElementDecl;
  } | null>(() => {
    if (!entry || entry.kind !== "element") return null;
    const selectedElement = entry.node as ElementDecl;
    const e = resolveElementRef(selectedElement, indexById) ?? selectedElement;
    return { constraints: e.identity_constraints ?? [], host: e };
  }, [entry, indexById]);

  if (!entry) return null;

  return (
    <div className="h-full overflow-auto">
      <Header entry={entry} onSelectBase={onSelectBase} />
      {body}
      <AssertionsTable groups={assertionGroups} />
      {identityConstraints && (
        <IdentityConstraintsTable
          constraints={identityConstraints.constraints}
          host={identityConstraints.host}
          index={index}
          indexById={indexById}
          constraintsById={constraintsById}
        />
      )}
    </div>
  );
}
