import { describe, expect, it } from "vitest";
import { parseZipEntries, pickMainXsd, referencedLocations, xsdEntries } from "../src/lib/zipEntries";

// Built with Python's zipfile: a directory entry, two nested schemas, a text
// file and a UTF-8 flagged name.
const FIXTURE_B64 =
  "UEsDBBQAAAAIAFy3I10AAAAAAgAAAAAAAAAIAAAAc2NoZW1hcy8DAFBLAwQUAAAACABctyNdPBE9ll4AAABrAAAAEwAAAHNjaGVtYXMvbGlicmFyeS54c2SzqSi2Kk7OSM1NVKjIzckrtqootlXKKCkpsNLXLy8v1ys31ssvStc3MjAw1I/w9QkGK1WyswFqy8xLzilNSVWAaPfJT04syczPs1UqqSxILdarKE5R0rez0YebbwcAUEsDBBQAAAAIAFy3I11GbK/lNwAAADgAAAARAAAAc2NoZW1hcy90eXBlcy54c2SzqSi2Kk7OSM1NVKjIzckrtqootlXKKCkpsNLXLy8v1ys31ssvStc3MjAw1I/w9QkGK1XStwMAUEsDBBQAAAAIAFy3I12sKpPYBAAAAAIAAAAKAAAAUkVBRE1FLnR4dMvIBABQSwMEFAAACAgAXLcjXYVkpvYOAAAADAAAAA0AAADDvG7Dr2NvZGUueHNks6kotipOzkjNTdS3AwBQSwECFAMUAAAACABctyNdAAAAAAIAAAAAAAAACAAAAAAAAAAAABAA/UEAAAAAc2NoZW1hcy9QSwECFAMUAAAACABctyNdPBE9ll4AAABrAAAAEwAAAAAAAAAAAAAAgAEoAAAAc2NoZW1hcy9saWJyYXJ5LnhzZFBLAQIUAxQAAAAIAFy3I11GbK/lNwAAADgAAAARAAAAAAAAAAAAAACAAbcAAABzY2hlbWFzL3R5cGVzLnhzZFBLAQIUAxQAAAAIAFy3I12sKpPYBAAAAAIAAAAKAAAAAAAAAAAAAACAAR0BAABSRUFETUUudHh0UEsBAhQDFAAACAgAXLcjXYVkpvYOAAAADAAAAA0AAAAAAAAAAAAAAIABSQEAAMO8bsOvY29kZS54c2RQSwUGAAAAAAUABQApAQAAggEAAAAA";

function fixtureBytes(): Uint8Array {
  return Uint8Array.from(atob(FIXTURE_B64), (c) => c.charCodeAt(0));
}

describe("parseZipEntries", () => {
  it("lists file entries from the central directory, skipping directories", () => {
    expect(parseZipEntries(fixtureBytes())).toEqual([
      "schemas/library.xsd",
      "schemas/types.xsd",
      "README.txt",
      "ünïcode.xsd",
    ]);
  });

  it("returns nothing for data that is not a ZIP", () => {
    expect(parseZipEntries(new TextEncoder().encode("<xs:schema/>"))).toEqual([]);
    expect(parseZipEntries(new Uint8Array(0))).toEqual([]);
  });
});

describe("pickMainXsd", () => {
  it("keeps only .xsd names and prefers shallow, short paths", () => {
    const names = ["x/deep.xsd", "main-schema.xsd", "a.xsd", "readme.txt"];
    expect(xsdEntries(names)).toHaveLength(3);
    expect(pickMainXsd(names)).toBe("a.xsd");
    expect(pickMainXsd(["readme.txt"])).toBeUndefined();
  });

  it("prefers the schema nobody references when contents are known", () => {
    const contents = new Map([
      ["types.xsd", "<xs:schema/>"],
      ["library.xsd", '<xs:schema><xs:include schemaLocation="types.xsd"/></xs:schema>'],
    ]);
    expect(pickMainXsd([...contents.keys()], contents)).toBe("library.xsd");
  });

  it("resolves relative schemaLocations against the referencing file", () => {
    expect([...referencedLocations("schemas/main.xsd", 'schemaLocation="./common/types.xsd"')]).toEqual([
      "schemas/common/types.xsd",
      "types.xsd",
    ]);
    expect(referencedLocations("a.xsd", 'schemaLocation="https://example.com/x.xsd"').size).toBe(0);
  });
});
