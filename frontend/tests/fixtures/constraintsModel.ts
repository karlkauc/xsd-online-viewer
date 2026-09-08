import type {
  AttributeDecl,
  AttributeGroup,
  ComplexType,
  ElementDecl,
  Group,
  IdentityConstraint,
  Particle,
  SchemaModel,
} from "../../src/types/schema";

// Mirrors backend/tests/fixtures/identity_constraints.xsd — used by Task 3
// (index/store plumbing) and reused by Task 5 (XPath resolution against
// selector/field steps). Namespace/prefix/ids follow the Clark-form scheme
// the backend emits (see backend/tests/test_parser.py::TestIdentityConstraints).

export const NS = "http://example.com/keys";

export function elementParticle(element: ElementDecl): Particle {
  return {
    kind: "element",
    min_occurs: element.min_occurs,
    max_occurs: element.max_occurs,
    element,
    group_ref: null,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

export function groupRefParticle(ref: string): Particle {
  return {
    kind: "group-ref",
    min_occurs: 1,
    max_occurs: 1,
    element: null,
    group_ref: ref,
    group_inline: null,
    children: [],
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

export function sequence(children: Particle[]): Particle {
  return {
    kind: "sequence",
    min_occurs: 1,
    max_occurs: 1,
    element: null,
    group_ref: null,
    group_inline: null,
    children,
    wildcard_namespace: null,
    wildcard_process_contents: null,
    annotation: null,
  };
}

export function leafElement(name: string, typeName: string, line: number, opts?: Partial<ElementDecl>): ElementDecl {
  return {
    id: `element:{${NS}}${name}`,
    name,
    qname: `{${NS}}${name}`,
    ref: null,
    type_name: typeName,
    type_inline_simple: null,
    type_inline_complex: null,
    min_occurs: 1,
    max_occurs: 1,
    default: null,
    fixed: null,
    nillable: false,
    abstract: false,
    substitution_group: null,
    form: "qualified",
    target_namespace: NS,
    is_global: false,
    annotation: null,
    source_ref: { file_id: "f1", line },
    ...opts,
  };
}

// xs:group name="BookCore" { sequence { element ISBN } }
export const isbnElement = leafElement("ISBN", "xs:string", 10);
export const bookCoreGroup: Group = {
  id: `group:{${NS}}BookCore`,
  name: "BookCore",
  ref: null,
  particle: sequence([elementParticle(isbnElement)]),
  annotation: null,
  source_ref: { file_id: "f1", line: 8 },
};

export const titleAttr: AttributeDecl = {
  id: `attribute:{${NS}}BookType/@title`,
  name: "title",
  qname: null,
  ref: null,
  type_name: "xs:string",
  type_inline: null,
  use: "optional",
  default: null,
  fixed: null,
  form: null,
  target_namespace: null,
  is_global: false,
  annotation: null,
  source_ref: { file_id: "f1", line: 19 },
};

export const editionElement = leafElement("Edition", "xs:string", 17, { min_occurs: 0 });

// xs:complexType name="BookType" — group ref + own element + attribute.
export const bookType: ComplexType = {
  id: `complexType:{${NS}}BookType`,
  name: "BookType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([groupRefParticle("tns:BookCore"), elementParticle(editionElement)]),
  attributes: [titleAttr],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 14 },
};

// xs:complexType name="SpecialBookType" — extension of BookType, no particle
// of its own (mirrors the FundsXML4 "Benchmark" shape).
export const specialBookType: ComplexType = {
  id: `complexType:{${NS}}SpecialBookType`,
  name: "SpecialBookType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "extension",
  base: "tns:BookType",
  particle: null,
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 24 },
};

const loanIdElement = leafElement("LoanID", "xs:string", 32);
const bookIsbnElement = leafElement("BookISBN", "xs:string", 33);

export const loanType: ComplexType = {
  id: `complexType:{${NS}}LoanType`,
  name: "LoanType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([elementParticle(loanIdElement), elementParticle(bookIsbnElement)]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 30 },
};

export const bookElement = leafElement("Book", "tns:BookType", 43, { max_occurs: "unbounded" });
export const loanElement = leafElement("Loan", "tns:LoanType", 50, { max_occurs: "unbounded" });

// Nested xs:key on the inline "Loans" complex type — exercises a
// non-top-level element carrying its own constraint list.
export const loanKeyConstraint: IdentityConstraint = {
  id: `identityConstraint:{${NS}}loanKey`,
  kind: "key",
  name: "loanKey",
  qname: `{${NS}}loanKey`,
  selector: "tns:Loan",
  fields: ["tns:LoanID"],
  refer: null,
  refer_id: null,
  xpath_default_namespace: null,
  annotation: null,
  source_ref: { file_id: "f1", line: 53 },
  version_constraints: null,
};

const loansInlineType: ComplexType = {
  id: `complexType:{${NS}}Library/Loans/anon`,
  name: null,
  anonymous: true,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([elementParticle(loanElement)]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 48 },
};

const loansElement: ElementDecl = {
  ...leafElement("Loans", "", 47),
  type_name: null,
  type_inline_complex: loansInlineType,
  identity_constraints: [loanKeyConstraint],
};

const booksInlineType: ComplexType = {
  id: `complexType:{${NS}}Library/Books/anon`,
  name: null,
  anonymous: true,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([elementParticle(bookElement)]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 40 },
};

const booksElement: ElementDecl = {
  ...leafElement("Books", "", 39),
  type_name: null,
  type_inline_complex: booksInlineType,
};

const libraryInlineType: ComplexType = {
  id: `complexType:{${NS}}Library/anon`,
  name: null,
  anonymous: true,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([elementParticle(booksElement), elementParticle(loansElement)]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 38 },
};

export const bookKeyConstraint: IdentityConstraint = {
  id: `identityConstraint:{${NS}}bookKey`,
  kind: "key",
  name: "bookKey",
  qname: `{${NS}}bookKey`,
  selector: "tns:Books/tns:Book",
  fields: ["tns:ISBN"],
  refer: null,
  refer_id: null,
  xpath_default_namespace: null,
  annotation: {
    documentation: [
      {
        lang: null,
        text: "Each ISBN must be unique among the library's books.",
        source: "documentation",
      },
    ],
    appinfo: [],
    comments: [],
  },
  source_ref: { file_id: "f1", line: 61 },
  version_constraints: null,
};

export const uniqueTitleConstraint: IdentityConstraint = {
  id: `identityConstraint:{${NS}}uniqueTitle`,
  kind: "unique",
  name: "uniqueTitle",
  qname: `{${NS}}uniqueTitle`,
  selector: ".//tns:Book",
  fields: ["@title", "tns:Edition"],
  refer: null,
  refer_id: null,
  xpath_default_namespace: null,
  annotation: null,
  source_ref: { file_id: "f1", line: 69 },
  version_constraints: null,
};

export const loanBookRefConstraint: IdentityConstraint = {
  id: `identityConstraint:{${NS}}loanBookRef`,
  kind: "keyref",
  name: "loanBookRef",
  qname: `{${NS}}loanBookRef`,
  selector: "tns:Loans/tns:Loan",
  fields: ["tns:BookISBN"],
  refer: "tns:bookKey",
  refer_id: bookKeyConstraint.id,
  xpath_default_namespace: null,
  annotation: null,
  source_ref: { file_id: "f1", line: 75 },
  version_constraints: {
    min_version: "1.1",
    max_version: null,
    type_available: null,
    type_unavailable: null,
    facet_available: null,
    facet_unavailable: null,
  },
};

// Dangling keyref — `refer` points at a constraint that doesn't exist, so
// the backend leaves `refer_id` null (and emits a warning diagnostic).
export const danglingRefConstraint: IdentityConstraint = {
  id: `identityConstraint:{${NS}}danglingRef`,
  kind: "keyref",
  name: "danglingRef",
  qname: `{${NS}}danglingRef`,
  selector: "tns:Loans/tns:Loan",
  fields: ["tns:BookISBN"],
  refer: "tns:noSuchKey",
  refer_id: null,
  xpath_default_namespace: null,
  annotation: null,
  source_ref: { file_id: "f1", line: 80 },
  version_constraints: null,
};

export const libraryElement: ElementDecl = {
  ...leafElement("Library", "", 37),
  is_global: true,
  type_name: null,
  type_inline_complex: libraryInlineType,
  identity_constraints: [
    bookKeyConstraint,
    uniqueTitleConstraint,
    loanBookRefConstraint,
    danglingRefConstraint,
  ],
};

// --- Additional fixtures for Task 5 (lib/constraintXPath.ts) --------------
// These are not wired into the Library particle tree; tests construct ad-hoc
// `start` elements typed against them directly (the resolver only needs the
// type to be reachable via the model's complex_types/groups/attribute_groups
// lists, not to be part of any element's actual content model).

// xs:complexType name="ExtendedBookType" — extension of BookType that *also*
// adds its own element, so flattening must interleave base-then-own content:
// base's [ISBN, Edition] followed by this type's own [Publisher].
export const publisherElement = leafElement("Publisher", "xs:string", 95, { min_occurs: 0 });
export const extendedBookType: ComplexType = {
  id: `complexType:{${NS}}ExtendedBookType`,
  name: "ExtendedBookType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "extension",
  base: "tns:BookType",
  particle: sequence([elementParticle(publisherElement)]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 94 },
};

// `<xs:element ref="tns:Book"/>` particle — exercises collectChildElements
// following resolveElementRef to reach BookType's children through the ref,
// rather than the ref particle's own (name === null) declaration. The ref
// particle keeps its own id distinct from the target's, matching the
// convention used elsewhere (treeRows.ts, ChildrenTable.tsx): selection
// targets the local particle, resolution follows the ref for content.
export const bookRefParticleElement: ElementDecl = {
  ...leafElement("Book", "", 100),
  id: `element:tns:Book`,
  name: null,
  qname: null,
  ref: "tns:Book",
  ref_id: bookElement.id,
  type_name: null,
};
export const refHolderType: ComplexType = {
  id: `complexType:{${NS}}RefHolderType`,
  name: "RefHolderType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([elementParticle(bookRefParticleElement)]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 99 },
};
export const refHolderElement = leafElement("RefHolder", "tns:RefHolderType", 98);

// Self-referencing xs:group — exercises the visited-set recursion guard in
// collectChildElements (group_ref -> group whose own particle refs itself).
export const recursiveMarkerElement = leafElement("Marker", "xs:string", 105);
export const recursiveGroup: Group = {
  id: `group:{${NS}}RecursiveGroup`,
  name: "RecursiveGroup",
  ref: null,
  particle: sequence([elementParticle(recursiveMarkerElement), groupRefParticle("tns:RecursiveGroup")]),
  annotation: null,
  source_ref: { file_id: "f1", line: 104 },
};
export const recursiveHolderType: ComplexType = {
  id: `complexType:{${NS}}RecursiveHolderType`,
  name: "RecursiveHolderType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([groupRefParticle("tns:RecursiveGroup")]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 103 },
};
export const recursiveHolderElement = leafElement("RecursiveHolder", "tns:RecursiveHolderType", 102);

// Self-recursive element type (Node contains Child of type NodeType again) —
// exercises the `.//` BFS recursion/depth cap: an unmatched search must
// terminate rather than loop forever.
export const nodeValueElement = leafElement("Value", "xs:string", 110);
const nodeChildElement = leafElement("Child", "tns:NodeType", 111, {
  max_occurs: "unbounded",
  min_occurs: 0,
});
export const nodeType: ComplexType = {
  id: `complexType:{${NS}}NodeType`,
  name: "NodeType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([elementParticle(nodeValueElement), elementParticle(nodeChildElement)]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 109 },
};
export const nodeRootElement = leafElement("Node", "tns:NodeType", 108);

// xs:attributeGroup name="ContactGroup" — exercises collectAttributes
// flattening attribute-group refs via attributeGroups.collectFromGroup.
export const phoneAttribute: AttributeDecl = {
  id: `attribute:{${NS}}ContactGroup/@phone`,
  name: "phone",
  qname: null,
  ref: null,
  type_name: "xs:string",
  type_inline: null,
  use: "optional",
  default: null,
  fixed: null,
  form: null,
  target_namespace: null,
  is_global: false,
  annotation: null,
  source_ref: { file_id: "f1", line: 115 },
};
export const contactAttributeGroup: AttributeGroup = {
  id: `attributeGroup:{${NS}}ContactGroup`,
  name: "ContactGroup",
  ref: null,
  attributes: [phoneAttribute],
  attribute_group_refs: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 114 },
};
export const contactHolderType: ComplexType = {
  id: `complexType:{${NS}}ContactHolderType`,
  name: "ContactHolderType",
  anonymous: false,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: null,
  attributes: [],
  attribute_group_refs: ["tns:ContactGroup"],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 113 },
};
export const contactHolderElement = leafElement("Contact", "tns:ContactHolderType", 112);

// --- Fixtures for the effectiveContent.ts base-chain fix -------------------
// xs:element name="Archive" — mirrors backend/tests/fixtures/identity_constraints.xsd's
// Archive/Book, whose Book is typed SpecialBookType (an extension with no
// particle of its own). Expanding it must show BookType's inherited
// ISBN/Edition/@title content, not an empty children table.
export const archiveBookElement = leafElement("Book", "tns:SpecialBookType", 121, {
  id: `element:{${NS}}Archive/Book`,
  max_occurs: "unbounded",
});
const archiveInlineType: ComplexType = {
  id: `complexType:{${NS}}Archive/anon`,
  name: null,
  anonymous: true,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "none",
  base: null,
  particle: sequence([elementParticle(archiveBookElement)]),
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 120 },
};
export const archiveElement: ElementDecl = {
  ...leafElement("Archive", "", 119),
  is_global: true,
  type_name: null,
  type_inline_complex: archiveInlineType,
};

// An element whose *inline* complex type (not a named one) is itself an
// extension with no particle of its own — exercises the inline-complex path
// of effectiveParticle/effectiveAttributes (as opposed to Archive/Book,
// which goes through a named type).
export const inlineExtensionType: ComplexType = {
  id: `complexType:{${NS}}InlineExtensionItem/anon`,
  name: null,
  anonymous: true,
  abstract: false,
  mixed: false,
  content_kind: "complex",
  derivation: "extension",
  base: "tns:BookType",
  particle: null,
  attributes: [],
  attribute_group_refs: [],
  simple_content_base: null,
  simple_content_facets: [],
  annotation: null,
  source_ref: { file_id: "f1", line: 125 },
};
export const inlineExtensionElement: ElementDecl = {
  ...leafElement("InlineExtensionItem", "", 124),
  is_global: true,
  type_name: null,
  type_inline_complex: inlineExtensionType,
};

export const constraintsModel: SchemaModel = {
  schema_id: "test-constraints",
  target_namespace: NS,
  namespaces: {
    xs: "http://www.w3.org/2001/XMLSchema",
    vc: "http://www.w3.org/2007/XMLSchema-versioning",
    tns: NS,
  },
  element_form_default: "qualified",
  attribute_form_default: "unqualified",
  elements: [libraryElement, archiveElement, inlineExtensionElement],
  attributes: [],
  simple_types: [],
  complex_types: [
    bookType,
    specialBookType,
    loanType,
    extendedBookType,
    refHolderType,
    recursiveHolderType,
    nodeType,
    contactHolderType,
  ],
  groups: [bookCoreGroup, recursiveGroup],
  attribute_groups: [contactAttributeGroup],
  files: [
    {
      id: "f1",
      filename: "identity_constraints.xsd",
      target_namespace: NS,
      relationship: "main",
      content: "<xs:schema/>",
    },
  ],
  diagnostics: [],
};
