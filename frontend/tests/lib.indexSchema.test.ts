import { describe, expect, it } from "vitest";
import { buildIndex, overrideKey, resolveReference } from "../src/lib/indexSchema";
import type { SchemaModel } from "../src/types/schema";
import { smallModel } from "./fixtures/smallModel";
import {
  bookKeyConstraint,
  constraintsModel,
  danglingRefConstraint,
  libraryElement,
  loanBookRefConstraint,
  loanKeyConstraint,
  uniqueTitleConstraint,
} from "./fixtures/constraintsModel";
import { idRolesModel } from "./fixtures/idRolesModel";

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

  describe("identity constraints", () => {
    it("indexes every constraint carried by every element, keyed by constraint id", () => {
      const { constraintsById } = buildIndex(constraintsModel);
      expect(constraintsById.size).toBe(5);
      expect(constraintsById.get(bookKeyConstraint.id)?.constraint).toBe(bookKeyConstraint);
      expect(constraintsById.get(uniqueTitleConstraint.id)?.constraint).toBe(
        uniqueTitleConstraint,
      );
      expect(constraintsById.get(loanBookRefConstraint.id)?.constraint).toBe(
        loanBookRefConstraint,
      );
      expect(constraintsById.get(danglingRefConstraint.id)?.constraint).toBe(
        danglingRefConstraint,
      );
      expect(constraintsById.get(loanKeyConstraint.id)?.constraint).toBe(loanKeyConstraint);
    });

    it("records the host element id for each constraint", () => {
      const { constraintsById } = buildIndex(constraintsModel);
      expect(constraintsById.get(bookKeyConstraint.id)?.hostId).toBe(libraryElement.id);
      expect(constraintsById.get(loanKeyConstraint.id)?.hostId).not.toBe(libraryElement.id);
    });

    it("resolves a keyref's refer_id to the key it points at", () => {
      const { constraintsById } = buildIndex(constraintsModel);
      const loanBookRef = constraintsById.get(loanBookRefConstraint.id)?.constraint;
      const target = loanBookRef?.refer_id
        ? constraintsById.get(loanBookRef.refer_id)?.constraint
        : undefined;
      expect(target).toBe(bookKeyConstraint);
    });

    it("leaves a dangling keyref's refer_id unresolved", () => {
      const { constraintsById } = buildIndex(constraintsModel);
      const dangling = constraintsById.get(danglingRefConstraint.id)?.constraint;
      expect(dangling?.refer_id).toBeNull();
    });

    it("is empty for models without identity constraints", () => {
      const { constraintsById } = buildIndex(smallModel);
      expect(constraintsById.size).toBe(0);
    });
  });

  describe("ID/IDREF declarations", () => {
    it("collects elements and attributes with id_role 'id' into idDeclarations", () => {
      const { idDeclarations } = buildIndex(idRolesModel);
      const ids = idDeclarations.map((e) => e.id);
      expect(ids).toEqual(["element:{http://example.com/idroles}UniqueID"]);
    });

    it("collects elements and attributes with id_role 'idref'/'idrefs' into idrefDeclarations", () => {
      const { idrefDeclarations } = buildIndex(idRolesModel);
      const ids = new Set(idrefDeclarations.map((e) => e.id));
      expect(ids).toEqual(
        new Set([
          "element:{http://example.com/idroles}BenchmarkRef",
          "element:{http://example.com/idroles}RelatedRefs",
          "attribute:{http://example.com/idroles}refAttr",
        ]),
      );
    });

    it("does not list declarations without an id_role", () => {
      const { idDeclarations, idrefDeclarations } = buildIndex(idRolesModel);
      const allIds = [...idDeclarations, ...idrefDeclarations].map((e) => e.id);
      expect(allIds).not.toContain("element:{http://example.com/idroles}Plain");
      expect(allIds).not.toContain("attribute:{http://example.com/idroles}plainAttr");
    });

    it("is empty for models without ID/IDREF roles", () => {
      const { idDeclarations, idrefDeclarations } = buildIndex(smallModel);
      expect(idDeclarations).toEqual([]);
      expect(idrefDeclarations).toEqual([]);
    });
  });
});
