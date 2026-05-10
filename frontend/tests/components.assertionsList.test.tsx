import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssertionsList } from "../src/components/AssertionsList";
import type { Assertion } from "../src/types/schema";

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
});
