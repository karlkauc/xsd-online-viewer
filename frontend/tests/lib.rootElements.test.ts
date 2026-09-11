import { describe, expect, it } from "vitest";
import { computeRootElements, sampleRootCandidates } from "../src/lib/rootElements";
import type { ElementDecl, SchemaModel, SourceFile } from "../src/types/schema";

const NS = "http://example.com/ns";

function globalElement(name: string, fileId: string): ElementDecl {
  return {
    id: `element:{${NS}}${name}`,
    name,
    qname: `{${NS}}${name}`,
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
    target_namespace: NS,
    is_global: true,
    annotation: null,
    source_ref: { file_id: fileId, line: 1 },
  };
}

function file(id: string, relationship: SourceFile["relationship"]): SourceFile {
  return {
    id,
    filename: `${id}.xsd`,
    target_namespace: NS,
    relationship,
    content: null,
  };
}

function model(elements: ElementDecl[], files: SourceFile[]): SchemaModel {
  return {
    schema_id: "test",
    target_namespace: NS,
    namespaces: { tns: NS, xs: "http://www.w3.org/2001/XMLSchema" },
    element_form_default: "qualified",
    attribute_form_default: "unqualified",
    elements,
    attributes: [],
    simple_types: [],
    complex_types: [],
    groups: [],
    attribute_groups: [],
    files,
    diagnostics: [],
  };
}

const MAIN = file("main", "main");
const INCLUDED = file("inc", "include");

describe("computeRootElements", () => {
  it("keeps only globals declared in the main file", () => {
    const root = globalElement("FundsXML4", "main");
    const inc1 = globalElement("Manifest", "inc");
    const inc2 = globalElement("SignatureProperties", "inc");

    const roots = computeRootElements(
      model([root, inc1, inc2], [MAIN, INCLUDED]),
    );

    expect(roots.map((e) => e.name)).toEqual(["FundsXML4"]);
  });

  it("keeps every main-file global regardless of references", () => {
    // "Main file only" ignores ref usage — a referenced main-file global is
    // still a root.
    const a = globalElement("A", "main");
    const b = globalElement("B", "main");

    const roots = computeRootElements(model([a, b], [MAIN]));

    expect(roots.map((e) => e.name)).toEqual(["A", "B"]);
  });

  it("falls back to the full list when the main file declares no globals", () => {
    // A pure include aggregator: every global comes from an included file.
    const inc1 = globalElement("Manifest", "inc");

    const roots = computeRootElements(model([inc1], [MAIN, INCLUDED]));

    expect(roots.map((e) => e.name)).toEqual(["Manifest"]);
  });

  it("falls back to the full list when no file is marked main", () => {
    const a = globalElement("A", "inc");

    const roots = computeRootElements(model([a], [INCLUDED]));

    expect(roots.map((e) => e.name)).toEqual(["A"]);
  });
});

function abstractElement(name: string, fileId = "main"): ElementDecl {
  return { ...globalElement(name, fileId), abstract: true };
}

function inGroup(element: ElementDecl, head: string): ElementDecl {
  return { ...element, substitution_group: `tns:${head}` };
}

const candidateNames = (m: SchemaModel) => sampleRootCandidates(m).map((e) => e.name);

describe("sampleRootCandidates", () => {
  it("leaves out abstract roots that nothing can substitute (KML: 113 of 269 roots)", () => {
    const kml = globalElement("kml", "main");
    const group = abstractElement("AbstractObjectGroup");

    expect(candidateNames(model([kml, group], [MAIN]))).toEqual(["kml"]);
  });

  it("keeps an abstract root with a concrete member, also one declared in another file", () => {
    const feature = abstractElement("AbstractFeatureGroup");
    const placemark = inGroup(globalElement("Placemark", "inc"), "AbstractFeatureGroup");

    expect(candidateNames(model([feature, placemark], [MAIN, INCLUDED]))).toEqual(["AbstractFeatureGroup"]);
  });

  it("follows the group through abstract members to a concrete one", () => {
    const feature = abstractElement("AbstractFeatureGroup");
    const container = inGroup(abstractElement("AbstractContainerGroup"), "AbstractFeatureGroup");
    const folder = inGroup(globalElement("Folder", "inc"), "AbstractContainerGroup");

    expect(candidateNames(model([feature, container, folder], [MAIN, INCLUDED]))).toEqual([
      "AbstractFeatureGroup",
      "AbstractContainerGroup",
    ]);
  });

  it("counts neither a chain of abstract members nor a cycle as substitutable", () => {
    const doc = globalElement("Doc", "main");
    const a = inGroup(abstractElement("A"), "B");
    const b = inGroup(abstractElement("B"), "A");

    expect(candidateNames(model([doc, a, b], [MAIN]))).toEqual(["Doc"]);
  });

  it("falls back to every root when all of them are abstract", () => {
    const a = abstractElement("A");
    const b = abstractElement("B");

    expect(candidateNames(model([a, b], [MAIN]))).toEqual(["A", "B"]);
  });
});
