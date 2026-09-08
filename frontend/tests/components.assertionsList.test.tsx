import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, beforeEach } from "vitest";
import { AssertionsList } from "../src/components/AssertionsList";
import { useSelection } from "../src/stores/selectionStore";
import type { AssertionGroup } from "../src/lib/assertions";
import type { Assertion, VersionConstraints } from "../src/types/schema";

function makeAssertion(overrides: Partial<Assertion> = {}): Assertion {
  return {
    test: "true()",
    xpath_default_namespace: null,
    annotation: null,
    source_ref: null,
    ...overrides,
  };
}

describe("AssertionsList", () => {
  it("renders nothing when the list is empty", () => {
    const { container } = render(<AssertionsList assertions={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders raw XPath verbatim", () => {
    const assertions: Assertion[] = [
      makeAssertion({ test: "$value mod 2 eq 0" }),
      makeAssertion({ test: "xs:date(From) le xs:date(To)" }),
    ];
    render(<AssertionsList assertions={assertions} />);
    expect(screen.getByText("$value mod 2 eq 0")).toBeInTheDocument();
    expect(
      screen.getByText("xs:date(From) le xs:date(To)"),
    ).toBeInTheDocument();
  });

  it("shows the section header with assertion count and display-only marker", () => {
    render(<AssertionsList assertions={[makeAssertion()]} />);
    expect(screen.getByText("Assertions")).toBeInTheDocument();
    expect(screen.getByText(/1 · XPath 2.0 · display-only/i)).toBeInTheDocument();
  });

  it("surfaces xpathDefaultNamespace as a chip", () => {
    render(
      <AssertionsList
        assertions={[
          makeAssertion({
            test: "$value gt 0",
            xpath_default_namespace: "http://example.com/x",
          }),
        ]}
      />,
    );
    expect(screen.getByText(/ns: http:\/\/example.com\/x/)).toBeInTheDocument();
  });

  describe("groups", () => {
    beforeEach(() => {
      useSelection.getState().clearSchema();
    });

    it("renders nothing when every group is empty", () => {
      const { container } = render(<AssertionsList groups={[]} />);
      expect(container.firstChild).toBeNull();
    });

    it("sums assertions across groups in the header count", () => {
      const groups: AssertionGroup[] = [
        { assertions: [makeAssertion({ test: "a" })], from: null, typeId: "t1" },
        {
          assertions: [makeAssertion({ test: "b" }), makeAssertion({ test: "c" })],
          from: "BaseType",
          typeId: "t2",
        },
      ];
      render(<AssertionsList groups={groups} />);
      expect(screen.getByText(/3 · XPath 2.0 · display-only/i)).toBeInTheDocument();
      expect(screen.getByText("a")).toBeInTheDocument();
      expect(screen.getByText("b")).toBeInTheDocument();
      expect(screen.getByText("c")).toBeInTheDocument();
    });

    it("shows a 'from <Type>' sub-label for a group with a non-null from", () => {
      const groups: AssertionGroup[] = [
        { assertions: [makeAssertion({ test: "@x = 1" })], from: "MeasurementType", typeId: "t1" },
      ];
      render(<AssertionsList groups={groups} />);
      expect(screen.getByText("MeasurementType")).toBeInTheDocument();
    });

    it("shows no 'from' sub-label when from is null", () => {
      const groups: AssertionGroup[] = [
        { assertions: [makeAssertion({ test: "@x = 1" })], from: null, typeId: "t1" },
      ];
      render(<AssertionsList groups={groups} />);
      expect(screen.queryByText(/^from /)).not.toBeInTheDocument();
    });

    it("renders a source-line link that jumps to the assertion's source", async () => {
      const groups: AssertionGroup[] = [
        {
          assertions: [
            makeAssertion({ test: "@x = 1", source_ref: { file_id: "f1", line: 41 } }),
          ],
          from: "MeasurementType",
          typeId: "t1",
        },
      ];
      render(<AssertionsList groups={groups} />);
      const link = screen.getByRole("button", { name: /f1:41/ });
      await userEvent.click(link);
      const state = useSelection.getState();
      expect(state.activeTab).toBe("text");
      expect(state.sourceJump).toEqual({ file_id: "f1", line: 41 });
    });

    it("renders a version badge when the assertion carries version constraints", () => {
      const vc: VersionConstraints = {
        min_version: "1.1",
        max_version: null,
        type_available: null,
        type_unavailable: null,
        facet_available: null,
        facet_unavailable: null,
      };
      const groups: AssertionGroup[] = [
        {
          assertions: [makeAssertion({ test: "@x = 1", version_constraints: vc })],
          from: null,
          typeId: "t1",
        },
      ];
      render(<AssertionsList groups={groups} />);
      expect(screen.getByText(/≥ 1\.1/)).toBeInTheDocument();
    });
  });
});
