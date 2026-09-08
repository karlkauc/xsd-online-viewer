import { describe, expect, it } from "vitest";
import { buildIndex } from "../src/lib/indexSchema";
import {
  collectAttributeAssertions,
  collectComplexAssertions,
  collectElementAssertions,
  collectSimpleAssertions,
  countAssertions,
  makeIndexResolver,
  makeModelResolver,
  type AssertionGroup,
} from "../src/lib/assertions";
import {
  amountType,
  assertionsModel,
  codeAttribute,
  codeElement,
  cyclicType,
  cyclicElement,
  derivedAssertType,
  derivedElement,
  inlineCodedElement,
  measurementElement,
  measurementType,
  paymentElement,
  positiveCodeType,
  restrictedAssertType,
  restrictedElement,
} from "./fixtures/assertionsModel";

describe("countAssertions", () => {
  it("sums assertions across every group", () => {
    const groups: AssertionGroup[] = [
      { assertions: measurementType.assertions!, from: null, typeId: "a" },
      { assertions: [positiveCodeType.assertions![0]], from: "PositiveCode", typeId: "b" },
    ];
    expect(countAssertions(groups)).toBe(3);
  });

  it("is 0 for an empty list", () => {
    expect(countAssertions([])).toBe(0);
  });
});

describe.each([
  ["makeIndexResolver", () => makeIndexResolver(buildIndex(assertionsModel).index)],
  ["makeModelResolver", () => makeModelResolver(assertionsModel)],
])("%s", (_name, makeResolver) => {
  describe("collectComplexAssertions", () => {
    it("returns the type's own assertions with a null 'from' by default", () => {
      const resolver = makeResolver();
      const groups = collectComplexAssertions(measurementType, resolver);
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBeNull();
      expect(groups[0].assertions).toHaveLength(2);
      expect(groups[0].typeId).toBe(measurementType.id);
    });

    it("uses the supplied ownLabel for the type's own group", () => {
      const resolver = makeResolver();
      const groups = collectComplexAssertions(measurementType, resolver, "MeasurementType");
      expect(groups[0].from).toBe("MeasurementType");
    });

    it("walks the extension-base chain, labelling each group by its declaring type", () => {
      const resolver = makeResolver();
      const groups = collectComplexAssertions(derivedAssertType, resolver, "DerivedAssertType");
      expect(groups).toHaveLength(2);
      expect(groups[0]).toMatchObject({ from: "DerivedAssertType" });
      expect(groups[0].assertions[0].test).toBe("@derived-flag = 'ok'");
      expect(groups[1]).toMatchObject({ from: "BaseAssertType" });
      expect(groups[1].assertions[0].test).toBe("@base-flag = 'ok'");
    });

    it("walks the restriction-base chain, labelling each group by its declaring type", () => {
      const resolver = makeResolver();
      const groups = collectComplexAssertions(
        restrictedAssertType,
        resolver,
        "RestrictedAssertType",
      );
      expect(groups).toHaveLength(2);
      expect(groups[0]).toMatchObject({ from: "RestrictedAssertType" });
      expect(groups[0].assertions[0].test).toBe("@restricted-flag = 'ok'");
      expect(groups[1]).toMatchObject({ from: "BaseAssertType" });
      expect(groups[1].assertions[0].test).toBe("@base-flag = 'ok'");
    });

    it("folds in the simpleContent base simple type's assertions", () => {
      const resolver = makeResolver();
      const groups = collectComplexAssertions(amountType, resolver, "AmountType");
      // AmountType itself has no assertions; only the simpleContent base does.
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBe("AmountValue");
      expect(groups[0].assertions[0].test).toBe("$value ge 0");
    });

    it("does not infinite-loop on a self-referential extension", () => {
      const resolver = makeResolver();
      const groups = collectComplexAssertions(cyclicType, resolver, "CyclicType");
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBe("CyclicType");
    });
  });

  describe("collectSimpleAssertions", () => {
    it("returns the type's own assertions", () => {
      const resolver = makeResolver();
      const groups = collectSimpleAssertions(positiveCodeType, resolver, "PositiveCode");
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBe("PositiveCode");
      expect(groups[0].assertions[0].test).toBe("string-length($value) gt 0");
    });
  });

  describe("collectElementAssertions", () => {
    it("labels a named complex type's assertions with the type name", () => {
      const resolver = makeResolver();
      const groups = collectElementAssertions(measurementElement, resolver);
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBe("MeasurementType");
      expect(groups[0].assertions).toHaveLength(2);
    });

    it("labels a named simple type's assertions with the type name", () => {
      const resolver = makeResolver();
      const groups = collectElementAssertions(codeElement, resolver);
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBe("PositiveCode");
    });

    it("labels an inline simple type's assertions with a null 'from'", () => {
      const resolver = makeResolver();
      const groups = collectElementAssertions(inlineCodedElement, resolver);
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBeNull();
      expect(groups[0].assertions[0].test).toBe("matches($value, '^[A-Z]+$')");
    });

    it("walks the extension-base chain for a named complex type", () => {
      const resolver = makeResolver();
      const groups = collectElementAssertions(derivedElement, resolver);
      expect(groups.map((g) => g.from)).toEqual(["DerivedAssertType", "BaseAssertType"]);
    });

    it("walks the restriction-base chain for a named complex type", () => {
      const resolver = makeResolver();
      const groups = collectElementAssertions(restrictedElement, resolver);
      expect(groups.map((g) => g.from)).toEqual(["RestrictedAssertType", "BaseAssertType"]);
    });

    it("includes the simpleContent base simple type's assertions", () => {
      const resolver = makeResolver();
      const groups = collectElementAssertions(paymentElement, resolver);
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBe("AmountValue");
    });

    it("does not infinite-loop on a self-referential extension", () => {
      const resolver = makeResolver();
      const groups = collectElementAssertions(cyclicElement, resolver);
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBe("CyclicType");
    });
  });

  describe("collectAttributeAssertions", () => {
    it("labels a named simple type's assertions with the type name", () => {
      const resolver = makeResolver();
      const groups = collectAttributeAssertions(codeAttribute, resolver);
      expect(groups).toHaveLength(1);
      expect(groups[0].from).toBe("PositiveCode");
      expect(groups[0].assertions[0].test).toBe("string-length($value) gt 0");
    });
  });
});
