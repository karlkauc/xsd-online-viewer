import { describe, expect, it } from "vitest";
import { buildTreeRows } from "../src/components/TreeView/treeRows";
import { buildIndex } from "../src/lib/indexSchema";
import { smallModel } from "./fixtures/smallModel";
import { refModel, DOCUMENT_ID, SIGNATURE_REF_ID } from "./fixtures/refModel";
import {
  constraintsModel,
  libraryElement,
  archiveElement,
  archiveBookElement,
  inlineExtensionElement,
  specialBookType,
  extendedBookType,
  leafElement,
} from "./fixtures/constraintsModel";
import type {
  AttributeDecl,
  ComplexType,
  ElementDecl,
  SchemaModel,
  SchemaNodeKind,
} from "../src/types/schema";

const ALL: SchemaNodeKind[] = [
  "element",
  "attribute",
  "complexType",
  "simpleType",
  "group",
  "attributeGroup",
];

describe("buildTreeRows", () => {
  it("shows top-level globals when nothing is expanded", () => {
    const { indexById } = buildIndex(smallModel);
    const rows = buildTreeRows(smallModel, new Set(), new Set(ALL), indexById);
    const labels = rows.map((r) => r.label);
    expect(labels).toContain("Person");
    expect(labels).toContain("PersonType");
    expect(labels).toContain("AgeType");
  });

  it("drills into a Person's PersonType when expanded", () => {
    const { indexById } = buildIndex(smallModel);
    const expanded = new Set(["element:{http://example.com/simple}Person"]);
    const rows = buildTreeRows(smallModel, expanded, new Set(ALL), indexById);
    const labels = rows.map((r) => r.label);
    expect(labels).toContain("FirstName");
    expect(labels).toContain("@id");
  });

  it("respects the type-kind filter", () => {
    const { indexById } = buildIndex(smallModel);
    const rows = buildTreeRows(smallModel, new Set(), new Set(["simpleType"]), indexById);
    expect(rows.every((r) => r.kind === "simpleType")).toBe(true);
  });
});

describe("buildTreeRows element references", () => {
  it("follows an imported ref to the global declaration when expanded", () => {
    const { indexById } = buildIndex(refModel);
    const collapsed = buildTreeRows(refModel, new Set([DOCUMENT_ID]), new Set(ALL), indexById);
    const signature = collapsed.find((r) => r.label === "ds:Signature");
    expect(signature).toBeDefined();
    // The referenced global carries the type, so the row is drillable.
    expect(signature!.hasChildren).toBe(true);
    expect(signature!.typeHint).toBe("ds:SignatureType");

    const expanded = buildTreeRows(
      refModel,
      new Set([DOCUMENT_ID, SIGNATURE_REF_ID]),
      new Set(ALL),
      indexById,
    );
    const labels = expanded.map((r) => r.label);
    expect(labels).toContain("ds:SignedInfo");
    expect(labels).toContain("@Id");
  });
});

describe("buildTreeRows identity constraints", () => {
  it("carries the constraint count and title on the declaring element's row", () => {
    const { indexById } = buildIndex(constraintsModel);
    const rows = buildTreeRows(constraintsModel, new Set(), new Set(ALL), indexById);
    const library = rows.find((r) => r.id === libraryElement.id);
    expect(library).toBeDefined();
    expect(library!.constraintCount).toBe(4);
    expect(library!.constraintTitle).toBe(
      "key bookKey, unique uniqueTitle, keyref loanBookRef, keyref danglingRef",
    );
  });

  it("leaves constraintCount unset for elements without identity constraints", () => {
    const { indexById } = buildIndex(constraintsModel);
    const expanded = new Set([libraryElement.id]);
    const rows = buildTreeRows(constraintsModel, expanded, new Set(ALL), indexById);
    const books = rows.find((r) => r.label === "Books");
    expect(books).toBeDefined();
    expect(books!.constraintCount ?? 0).toBe(0);
  });
});

describe("buildTreeRows content inherited through xs:extension", () => {
  it("shows the extension base's rows for a named-type extension with no own particle", () => {
    const { indexById } = buildIndex(constraintsModel);
    const expanded = new Set([archiveElement.id, archiveBookElement.id]);
    const rows = buildTreeRows(constraintsModel, expanded, new Set(ALL), indexById);
    const labels = rows.map((r) => r.label);
    // BookType's own content: the BookCore group ref (holding ISBN), Edition,
    // and @title — none of which SpecialBookType (Book's actual type)
    // declares itself.
    expect(labels).toContain("tns:BookCore");
    expect(labels).toContain("Edition");
    expect(labels).toContain("@title");
  });

  it("shows the extension base's rows for an inline-complex extension with no own particle", () => {
    const { indexById } = buildIndex(constraintsModel);
    const expanded = new Set([inlineExtensionElement.id]);
    const rows = buildTreeRows(constraintsModel, expanded, new Set(ALL), indexById);
    const labels = rows.map((r) => r.label);
    expect(labels).toContain("tns:BookCore");
    expect(labels).toContain("Edition");
    expect(labels).toContain("@title");
  });

  it("marks a flat complexType-filter row for an extension with no own content as expandable, and shows the base's rows", () => {
    const { indexById } = buildIndex(constraintsModel);
    const expanded = new Set([specialBookType.id]);
    const rows = buildTreeRows(constraintsModel, expanded, new Set(ALL), indexById);
    const row = rows.find((r) => r.id === specialBookType.id);
    expect(row).toBeDefined();
    // Before the fix this was false (SpecialBookType's own particle/attributes
    // are both empty), so the row rendered as a non-expandable leaf even
    // though its extension base has content.
    expect(row!.hasChildren).toBe(true);
    const labels = rows.map((r) => r.label);
    expect(labels).toContain("tns:BookCore");
    expect(labels).toContain("Edition");
    expect(labels).toContain("@title");
  });

  it("interleaves base-then-own content for an extension that adds its own particle too", () => {
    const { indexById } = buildIndex(constraintsModel);
    const expanded = new Set([extendedBookType.id]);
    const rows = buildTreeRows(constraintsModel, expanded, new Set(ALL), indexById);
    const labels = rows.map((r) => r.label);
    // ExtendedBookType extends BookType and adds its own Publisher element —
    // exercises the synthetic sequence(base, own) branch end-to-end.
    expect(labels).toContain("tns:BookCore");
    expect(labels).toContain("Edition");
    expect(labels).toContain("@title");
    expect(labels).toContain("Publisher");
  });
});

describe("buildTreeRows leaf elements", () => {
  const personId = "element:{http://example.com/simple}Person";

  it("does not mark elements of a built-in or named simple type as expandable", () => {
    const { indexById } = buildIndex(smallModel);
    const rows = buildTreeRows(smallModel, new Set([personId]), new Set(ALL), indexById);
    const firstName = rows.find((r) => r.label === "FirstName");
    const age = rows.find((r) => r.label === "Age");
    const address = rows.find((r) => r.label === "Address");
    expect(firstName).toBeDefined();
    expect(age).toBeDefined();
    expect(address).toBeDefined();
    // xs:string / tns:AgeType have nothing to drill into — expanding them
    // would render no rows, so the row must not offer an expand toggle.
    expect(firstName!.hasChildren).toBe(false);
    expect(age!.hasChildren).toBe(false);
    // Inline complex type with a sequence stays drillable.
    expect(address!.hasChildren).toBe(true);
  });

  it("marks a simpleContent element as expandable only when it carries attributes", () => {
    const simpleContent = (id: string, attributes: AttributeDecl[]): ComplexType => ({
      id: `complexType:${id}/anon`,
      name: null,
      anonymous: true,
      abstract: false,
      mixed: false,
      content_kind: "simple",
      derivation: "extension",
      base: "xs:string",
      particle: null,
      attributes,
      attribute_group_refs: [],
      simple_content_base: "xs:string",
      simple_content_facets: [],
      annotation: null,
      source_ref: null,
    });
    const langAttr: AttributeDecl = {
      id: "attribute:Label/@lang",
      name: "lang",
      qname: null,
      ref: null,
      type_name: "xs:language",
      type_inline: null,
      use: "optional",
      default: null,
      fixed: null,
      form: null,
      target_namespace: null,
      is_global: false,
      annotation: null,
      source_ref: null,
    };
    const info: ElementDecl = {
      ...leafElement("Info", "", 1),
      type_name: null,
      type_inline_complex: simpleContent("Info", []),
    };
    const label: ElementDecl = {
      ...leafElement("Label", "", 2),
      type_name: null,
      type_inline_complex: simpleContent("Label", [langAttr]),
    };
    const model: SchemaModel = {
      ...constraintsModel,
      elements: [info, label],
      complex_types: [],
      simple_types: [],
      groups: [],
      attribute_groups: [],
      attributes: [],
    };
    const { indexById } = buildIndex(model);
    const rows = buildTreeRows(model, new Set(), new Set(ALL), indexById);
    // `<xs:simpleContent><xs:extension base="xs:string"/>` — text only, no
    // child rows to show (the OeNBCheck Infos/Info shape).
    expect(rows.find((r) => r.label === "Info")!.hasChildren).toBe(false);
    // …but an attribute on the extension is a child row.
    expect(rows.find((r) => r.label === "Label")!.hasChildren).toBe(true);
  });
});

describe("buildTreeRows wildcards, notations and redefined originals", () => {
  const wildcard = {
    namespace: "##other",
    not_namespace: null,
    not_qname: null,
    process_contents: "lax" as const,
    annotation: null,
  };
  const openType: ComplexType = {
    id: "complexType:Open",
    name: "Open",
    anonymous: false,
    abstract: false,
    mixed: false,
    content_kind: "complex",
    derivation: "none",
    base: null,
    particle: {
      kind: "sequence",
      min_occurs: 1,
      max_occurs: 1,
      element: null,
      group_ref: null,
      group_inline: null,
      children: [
        {
          kind: "any",
          min_occurs: 0,
          max_occurs: "unbounded",
          element: null,
          group_ref: null,
          group_inline: null,
          children: [],
          wildcard_namespace: "##targetNamespace",
          wildcard_process_contents: "strict",
          wildcard_not_qname: "t:Skip",
          annotation: null,
        },
      ],
      wildcard_namespace: null,
      wildcard_process_contents: null,
      annotation: null,
    },
    attributes: [],
    attribute_group_refs: [],
    any_attribute: wildcard,
    simple_content_base: null,
    simple_content_facets: [],
    annotation: null,
    source_ref: null,
  };
  const model: SchemaModel = {
    ...smallModel,
    elements: [],
    attributes: [],
    simple_types: [],
    groups: [],
    attribute_groups: [],
    complex_types: [
      openType,
      { ...openType, id: "complexType:Open~original", name: "Open~original", particle: null },
    ],
    notations: [
      {
        id: "notation:jpeg",
        name: "jpeg",
        qname: "jpeg",
        public: "image/jpeg",
        system: null,
        annotation: null,
        source_ref: null,
      },
    ],
    redefines: [
      {
        target_file_id: null,
        source_ref: null,
        redefinitions: [
          {
            kind: "complexType",
            qname: "Open",
            redefinition_id: "complexType:Open",
            original_id: "complexType:Open~original",
            source_ref: null,
          },
        ],
      },
    ],
  };
  const kinds = new Set<SchemaNodeKind>([...ALL, "notation"]);

  it("lists xs:any and xs:anyAttribute as rows that select their owner", () => {
    const { indexById } = buildIndex(model);
    const rows = buildTreeRows(model, new Set(["complexType:Open"]), kinds, indexById);
    const any = rows.find((r) => r.label === "any ##targetNamespace, not t:Skip");
    expect(any).toMatchObject({
      kind: "element",
      wildcard: true,
      occurs: "0..∞",
      typeHint: "strict",
      selectId: "complexType:Open",
    });
    const anyAttribute = rows.find((r) => r.label === "@any ##other");
    expect(anyAttribute).toMatchObject({
      kind: "attribute",
      wildcard: true,
      typeHint: "lax",
      selectId: "complexType:Open",
    });
    // A type with nothing but wildcards is still expandable.
    expect(rows.find((r) => r.id === "complexType:Open")?.hasChildren).toBe(true);
  });

  it("lists notations, and only when their kind is switched on", () => {
    const { indexById } = buildIndex(model);
    const rows = buildTreeRows(model, new Set(), kinds, indexById);
    expect(rows.find((r) => r.id === "notation:jpeg")).toMatchObject({
      kind: "notation",
      label: "jpeg",
      typeHint: "image/jpeg",
    });
    expect(indexById.get("notation:jpeg")?.kind).toBe("notation");
    const without = buildTreeRows(model, new Set(), new Set(ALL), indexById);
    expect(without.some((r) => r.kind === "notation")).toBe(false);
  });

  it("leaves out the definition an xs:redefine replaced", () => {
    const { indexById } = buildIndex(model);
    const rows = buildTreeRows(model, new Set(), kinds, indexById);
    expect(rows.map((r) => r.label)).toContain("Open");
    expect(rows.some((r) => r.label.includes("~original"))).toBe(false);
    // It stays in the index: the redefinition's base still resolves to it.
    expect(indexById.has("complexType:Open~original")).toBe(true);
  });
});
