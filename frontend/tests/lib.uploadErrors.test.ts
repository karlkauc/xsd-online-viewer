import { describe, expect, it } from "vitest";
import { classifyUploadError, looksLikeSchema, shouldSniff } from "../src/lib/uploadErrors";

describe("classifyUploadError", () => {
  it("detects XML documents from backend and client messages", () => {
    expect(classifyUploadError("db.xml: root element is <games>, not <xs:schema> — …").kind).toBe("xml-document");
    expect(classifyUploadError("a.xml: no <xs:schema> root found — this looks like an XML document").kind).toBe(
      "xml-document",
    );
  });
  it("maps the other backend messages", () => {
    expect(classifyUploadError("dim.xsd: not an XML file (it starts with b'PK')").kind).toBe("not-xml");
    expect(classifyUploadError("ZIP archive contains no .xsd file (found: a.stl)").kind).toBe("zip-no-xsd");
    expect(classifyUploadError("DTD constructs are not allowed in uploads").kind).toBe("dtd");
    expect(classifyUploadError("upload exceeds 20 MB limit").kind).toBe("too-large");
    expect(classifyUploadError("limit: 30 per 1 minute").kind).toBe("rate-limit");
    expect(classifyUploadError("something odd").kind).toBe("unknown");
  });
});

describe("client-side sniff", () => {
  it("only sniffs .xml names", () => {
    expect(shouldSniff("doc.xml")).toBe(true);
    expect(shouldSniff("schema.XSD")).toBe(false);
    expect(shouldSniff("bundle.zip")).toBe(false);
  });
  it("recognises schema roots with any prefix", () => {
    expect(looksLikeSchema('<?xml version="1.0"?>\n<xs:schema xmlns:xs="…">')).toBe(true);
    expect(looksLikeSchema('<schema xmlns="http://www.w3.org/2001/XMLSchema">')).toBe(true);
    expect(looksLikeSchema("<xsd:schema\n  targetNamespace=\"x\">")).toBe(true);
    expect(looksLikeSchema("<games><game/></games>")).toBe(false);
    expect(looksLikeSchema("<schemaLocation/>")).toBe(false);
  });
});
