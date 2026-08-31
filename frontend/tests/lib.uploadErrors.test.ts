import { describe, expect, it } from "vitest";
import { classifyUploadError, looksLikeSchema, shouldSniff } from "../src/lib/uploadErrors";

describe("classifyUploadError", () => {
  it("detects XML documents from backend and client messages", () => {
    expect(classifyUploadError("db.xml: root element is <games>, not <xs:schema> — …").kind).toBe("xml-document");
    expect(classifyUploadError("a.xml: no <xs:schema> root found — this looks like an XML document").kind).toBe(
      "xml-document",
    );
  });
  it("keeps a <schema> root with a bad namespace out of the xml-document bucket", () => {
    expect(
      classifyUploadError(
        'HU_LABEL_E.xsd: the root element <schema> declares no namespace — an XML Schema must declare xmlns="http://www.w3.org/2001/XMLSchema" (the prefix itself does not matter, <schema> is as valid as <xs:schema>)',
      ).kind,
    ).toBe("schema-namespace");
    expect(
      classifyUploadError(
        "old.xsd: the root element <schema> uses the obsolete 1999 XML Schema draft namespace (http://www.w3.org/1999/XMLSchema) — replace it with http://www.w3.org/2001/XMLSchema",
      ).kind,
    ).toBe("schema-namespace");
    expect(
      classifyUploadError(
        "weird.xsd: the root element <schema> is in namespace urn:acme, not the XML Schema namespace http://www.w3.org/2001/XMLSchema",
      ).kind,
    ).toBe("schema-namespace");
  });
  it("maps the other backend messages", () => {
    expect(classifyUploadError("dim.xsd: not an XML file (it starts with b'name;value')").kind).toBe("not-xml");
    expect(classifyUploadError("p.xsd: not an XML file — it looks like a PDF document, i.e. binary data, not text").kind).toBe(
      "binary-file",
    );
    expect(
      classifyUploadError("uyutnye_tykvy.xsd: not an XML file — it starts with binary data (b'\\x10\\x05'), not text").kind,
    ).toBe("binary-file");
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
