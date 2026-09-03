import { describe, expect, it } from "vitest";
import { isShareable, shareLink, sourceFromLocation, sourcePath } from "../src/lib/schemaSource";

function loc(pathname: string, search = "", hash = ""): Location {
  return { origin: "https://www.xsd-viewer.online", pathname, search, hash } as Location;
}

describe("schemaSource", () => {
  it("encodes URL and release sources as paths and reads them back", () => {
    const url = { kind: "url" as const, url: "https://example.com/a b.xsd?v=1" };
    const path = sourcePath(url)!;
    expect(path.startsWith("/url?src=")).toBe(true);
    const [pathname, search] = path.split("?");
    expect(sourceFromLocation(loc(pathname, `?${search}`))).toEqual(url);

    const release = { kind: "release" as const, tag: "4.2.11", filename: "FundsXML4.xsd" };
    const rp = sourcePath(release)!;
    const [rpath, rsearch] = rp.split("?");
    expect(sourceFromLocation(loc(rpath, `?${rsearch}`))).toEqual(release);
  });

  it("has no path for local input and ignores bogus parameters", () => {
    expect(sourcePath({ kind: "text", content: "<xs:schema/>" })).toBeNull();
    expect(sourcePath({ kind: "upload", files: [] })).toBeNull();
    expect(sourceFromLocation(loc("/url", "?src=javascript:alert(1)"))).toBeNull();
    expect(sourceFromLocation(loc("/fundsxml", "?release=4.2.11"))).toBeNull();
    expect(sourceFromLocation(loc("/", "?src=https://example.com/x.xsd"))).toBeNull();
  });

  it("builds a share link that keeps the selection hash", () => {
    const hash = "#/id/element%3APerson";
    expect(shareLink({ kind: "url", url: "https://example.com/x.xsd" }, loc("/", "", hash))).toBe(
      "https://www.xsd-viewer.online/url?src=https%3A%2F%2Fexample.com%2Fx.xsd#/id/element%3APerson",
    );
    expect(shareLink({ kind: "text", content: "" }, loc("/paste", "", hash))).toBe(
      "https://www.xsd-viewer.online/paste#/id/element%3APerson",
    );
    expect(isShareable({ kind: "release", tag: "t", filename: "f" })).toBe(true);
    expect(isShareable({ kind: "upload", files: [] })).toBe(false);
    expect(isShareable(null)).toBe(false);
  });
});
