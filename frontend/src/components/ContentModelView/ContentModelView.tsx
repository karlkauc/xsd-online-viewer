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
      const selectedElement = entry.node as ElementDecl;
      // An `<xs:element ref="…">` particle has no content model of its own —
      // show the one of the global declaration it references.
      const e = resolveElementRef(selectedElement, indexById) ?? selectedElement;
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
  }, [entry, index, indexById]);

  if (!entry) return null;

  return (
    <div className="h-full overflow-auto">
      <Header entry={entry} onSelectBase={onSelectBase} />
      {body}
    </div>
  );
}
