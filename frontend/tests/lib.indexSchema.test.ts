import { describe, expect, it } from "vitest";
import { buildIndex, overrideKey, resolveReference } from "../src/lib/indexSchema";
import type { SchemaModel } from "../src/types/schema";
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

  it("builds override reverse maps for replacement and original lookups", () => {
    const overrideModel: SchemaModel = {
      ...smallModel,
      overrides: [
        {
          target_file_id: "f-base",
          source_ref: { file_id: "f-ovr", line: 5 },
          replacements: [
            {
              kind: "complexType",
              qname: "tns:ColorType",
              replacement_id: "override:f-ovr#complexType:tns:ColorType",
              source_ref: { file_id: "f-ovr", line: 7 },
            },
          ],
        },
      ],
    };
    const { overrideByReplacementId, overridesByOriginalKey } =
      buildIndex(overrideModel);
    const replacement = overrideByReplacementId.get(
      "override:f-ovr#complexType:tns:ColorType",
    );
    expect(replacement).toBeDefined();
    expect(replacement?.replacement.qname).toBe("tns:ColorType");

    const originalReplacements = overridesByOriginalKey.get(
      overrideKey("complexType", "tns:ColorType"),
    );
    expect(originalReplacements).toHaveLength(1);
    expect(originalReplacements?.[0].replacement_id).toBe(
      "override:f-ovr#complexType:tns:ColorType",
    );
  });
});
