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

// Windows archivers store a name in the OEM code page — here CP866 for
// "Сервис1/General_1.40.xsd" — without the UTF-8 flag, and may add its UTF-8
// form in an Info-ZIP unicode path field (0x7075).
const CP866_NAME = new Uint8Array([
  0x91, 0xa5, 0xe0, 0xa2, 0xa8, 0xe1, 0x31, 0x2f, 0x47, 0x65, 0x6e, 0x65, 0x72, 0x61, 0x6c, 0x5f, 0x31, 0x2e, 0x34,
  0x30, 0x2e, 0x78, 0x73, 0x64,
]);
const CP866_NAME_CRC = 0x0586b622;

/** A one-entry central directory and its end record: all parseZipEntries reads. */
function legacyArchive(extra: Uint8Array = new Uint8Array(0)): Uint8Array {
  const central = new Uint8Array(46 + CP866_NAME.length + extra.length);
  const entry = new DataView(central.buffer);
  entry.setUint32(0, 0x02014b50, true); // flags stay 0: no UTF-8 flag
  entry.setUint16(28, CP866_NAME.length, true);
  entry.setUint16(30, extra.length, true);
  central.set(CP866_NAME, 46);
  central.set(extra, 46 + CP866_NAME.length);
  const archive = new Uint8Array(central.length + 22);
  archive.set(central);
  const end = new DataView(archive.buffer, central.length);
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, 1, true);
  end.setUint16(10, 1, true);
  end.setUint32(12, central.length, true);
  end.setUint32(16, 0, true);
  return archive;
}

function unicodePathField(nameCrc: number): Uint8Array {
  const utf8 = new TextEncoder().encode("Сервис1/General_1.40.xsd");
  const field = new Uint8Array(9 + utf8.length);
  const view = new DataView(field.buffer);
  view.setUint16(0, 0x7075, true);
  view.setUint16(2, 5 + utf8.length, true);
  field[4] = 1; // version
  view.setUint32(5, nameCrc, true);
  field.set(utf8, 9);
  return field;
}

// The backend (Python 3.12's zipfile) reads names this way. Reading them
// differently here sent a main schema name the backend did not know: "main
// schema '‘¥à¢¨á1 …' is not among the uploaded files" (2026-09-11).
describe("parseZipEntries with names in a legacy code page", () => {
  it("uses the UTF-8 name from an Info-ZIP unicode path field", () => {
    expect(parseZipEntries(legacyArchive(unicodePathField(CP866_NAME_CRC)))).toEqual(["Сервис1/General_1.40.xsd"]);
  });

  it("ignores a unicode path field written for a different name", () => {
    expect(parseZipEntries(legacyArchive(unicodePathField(CP866_NAME_CRC ^ 1)))).toEqual([
      "æÑαó¿ß1/General_1.40.xsd",
    ]);
  });

  it("decodes a legacy name without that field as code page 437", () => {
    expect(parseZipEntries(legacyArchive())).toEqual(["æÑαó¿ß1/General_1.40.xsd"]);
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
