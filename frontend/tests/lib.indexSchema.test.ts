import { describe, expect, it } from "vitest";
import { buildIndex, resolveReference } from "../src/lib/indexSchema";
import { smallModel } from "./fixtures/smallModel";

describe("buildIndex", () => {
  it("catalogs every named global declaration", () => {
    const { index } = buildIndex(smallModel);
    const labels = new Set(index.map((e) => e.label));
    expect(labels).toContain("Person");
    expect(labels).toContain("PersonType");
    expect(labels).toContain("AgeType");
  });

  it("captures usage of types via references", () => {
    const { usagesByTarget } = buildIndex(smallModel);
    const users = usagesByTarget.get("tns:PersonType") ?? [];
    expect(users.map((u) => u.label)).toContain("Person");
  });

  it("resolves local-name references when no exact qname match", () => {
    const { index } = buildIndex(smallModel);
    const resolved = resolveReference("tns:PersonType", index, ["complexType"]);
    expect(resolved?.label).toBe("PersonType");
  });
});
