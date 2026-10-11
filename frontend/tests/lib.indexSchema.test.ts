import { describe, expect, it } from "vitest";
import {
  buildIndex,
  findRedefineLink,
  resolveReference,
} from "../src/lib/indexSchema";
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

  it("maps an override replacement's id to its directive", () => {
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
              replacement_id: "complexType:tns:ColorType",
              source_ref: { file_id: "f-ovr", line: 7 },
              original_source_ref: { file_id: "f-base", line: 4 },
            },
          ],
        },
      ],
    };
    const { overrideByReplacementId } = buildIndex(overrideModel);
    const hit = overrideByReplacementId.get("complexType:tns:ColorType");
    expect(hit?.directive.target_file_id).toBe("f-base");
    expect(hit?.replacement.original_source_ref).toEqual({ file_id: "f-base", line: 4 });
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

describe("findRedefineLink", () => {
  const model: SchemaModel = {
    ...smallModel,
    redefines: [
      {
        target_file_id: "f1",
        source_ref: null,
        redefinitions: [
          {
            kind: "complexType",
            qname: "{urn:t}Base",
            redefinition_id: "complexType:{urn:t}Base",
            original_id: "complexType:{urn:t}Base~original",
            source_ref: null,
          },
          {
            kind: "group",
            qname: "{urn:t}G",
            redefinition_id: "group:{urn:t}G",
            original_id: null,
            source_ref: null,
          },
        ],
      },
    ],
  };

  it("links a redefinition and its original in both directions", () => {
    expect(findRedefineLink(model, "complexType:{urn:t}Base")).toEqual({
      role: "redefinition",
      otherId: "complexType:{urn:t}Base~original",
    });
    expect(findRedefineLink(model, "complexType:{urn:t}Base~original")).toEqual({
      role: "original",
      otherId: "complexType:{urn:t}Base",
    });
  });

  it("knows a redefinition whose original is missing, and nothing else", () => {
    expect(findRedefineLink(model, "group:{urn:t}G")).toEqual({
      role: "redefinition",
      otherId: null,
    });
    expect(findRedefineLink(model, "complexType:{urn:t}Other")).toBeNull();
    expect(findRedefineLink(smallModel, "complexType:{urn:t}Base")).toBeNull();
    expect(findRedefineLink(null, "x")).toBeNull();
  });
});
