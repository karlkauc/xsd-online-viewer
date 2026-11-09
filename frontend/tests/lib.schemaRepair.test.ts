import { describe, expect, it } from "vitest";
import { repairSchemaText, XSD_NS } from "../src/lib/schemaRepair";

const UNDECLARED_XSD =
  'schema.xsd: Namespace prefix xsd on schema is not defined, line 1, column 167 — the prefix "xsd" is used';

describe("repairSchemaText", () => {
  it("declares an undeclared xs/xsd prefix on a schema root", () => {
    const text = '<?xml version="1.0"?>\n<!-- <a:b> -->\n<xsd:schema elementFormDefault="qualified"><xsd:element name="a"/></xsd:schema>';
    const repair = repairSchemaText(text, UNDECLARED_XSD);
    expect(repair?.text).toBe(
      `<?xml version="1.0"?>\n<!-- <a:b> -->\n<xsd:schema xmlns:xsd="${XSD_NS}" elementFormDefault="qualified"><xsd:element name="a"/></xsd:schema>`,
    );
    expect(repair?.label).toContain("xmlns:xsd");
  });

  it("wraps a snippet whose root is not a schema", () => {
    const text = '<?xml version="1.0"?>\n<xs:complexType name="T"/>\n';
    const repair = repairSchemaText(text, "schema.xsd: Namespace prefix xs on complexType is not defined, line 2");
    expect(repair?.text).toBe(`<?xml version="1.0"?>\n<xs:schema xmlns:xs="${XSD_NS}">\n<xs:complexType name="T"/>\n</xs:schema>\n`);
  });

  it("leaves foreign prefixes alone", () => {
    expect(repairSchemaText("<xs:schema><foo:x/></xs:schema>", "Namespace prefix foo on x is not defined")).toBeNull();
  });

  it("adds the default namespace to a bare <schema>", () => {
    const repair = repairSchemaText(
      "<schema><element name='a'/></schema>",
      "s.xsd: the root element <schema> declares no namespace — an XML Schema must declare xmlns=…",
    );
    expect(repair?.text).toBe(`<schema xmlns="${XSD_NS}"><element name='a'/></schema>`);
  });

  it("replaces a wrong or draft namespace on the root only", () => {
    const text = '<xs:schema xmlns:xs="http://w3.org" targetNamespace="http://w3.org"><xs:element name="a"/></xs:schema>';
    const repair = repairSchemaText(
      text,
      `s.xsd: the root element <schema> is in namespace http://w3.org, not the XML Schema namespace ${XSD_NS}`,
    );
    expect(repair?.text).toBe(`<xs:schema xmlns:xs="${XSD_NS}" targetNamespace="http://w3.org"><xs:element name="a"/></xs:schema>`);
    const draft = repairSchemaText(
      '<schema xmlns="http://www.w3.org/1999/XMLSchema"/>',
      "s.xsd: the root element <schema> uses the obsolete 1999 XML Schema draft namespace (http://www.w3.org/1999/XMLSchema) — replace it",
    );
    expect(draft?.text).toBe(`<schema xmlns="${XSD_NS}"/>`);
  });

  it("wraps a lone schema component", () => {
    const repair = repairSchemaText(
      `<xs:element xmlns:xs="${XSD_NS}" name="a"/>`,
      "s.xsd: the root element is <xs:element>, a part of an XML Schema rather than a whole one — wrap it",
    );
    expect(repair?.text.startsWith(`<xs:schema xmlns:xs="${XSD_NS}">`)).toBe(true);
  });

  it("offers nothing for other errors", () => {
    expect(repairSchemaText("<a/>", "Extra content at the end of the document")).toBeNull();
  });
});
