import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AlternativesList } from "../src/components/AlternativesList";
import type { Alternative } from "../src/types/schema";

function alt(overrides: Partial<Alternative> = {}): Alternative {
  return {
    test: "@kind = 'x'",
    type_name: "tns:X",
    type_inline_simple: null,
    type_inline_complex: null,
    xpath_default_namespace: null,
    annotation: null,
    source_ref: null,
    ...overrides,
  };
}

const renderTypeRef = (typeName: string) => (
  <code data-testid={`type-ref-${typeName}`}>{typeName}</code>
);

describe("AlternativesList", () => {
  it("renders nothing when the list is empty", () => {
    const { container } = render(
      <AlternativesList alternatives={[]} renderTypeRef={renderTypeRef} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders an if-ladder for predicated alternatives", () => {
    render(
      <AlternativesList
        alternatives={[
          alt({ test: "@kind = 'dog'", type_name: "tns:Dog" }),
          alt({ test: "@kind = 'cat'", type_name: "tns:Cat" }),
        ]}
        renderTypeRef={renderTypeRef}
      />,
    );
    const ifs = screen.getAllByText("if");
    expect(ifs).toHaveLength(2);
    expect(screen.queryByText("else")).not.toBeInTheDocument();
    expect(screen.getByText("@kind = 'dog'")).toBeInTheDocument();
    expect(screen.getByText("@kind = 'cat'")).toBeInTheDocument();
    expect(screen.getByTestId("type-ref-tns:Dog")).toBeInTheDocument();
  });

  it("marks the default branch (test === null) as 'else'", () => {
    render(
      <AlternativesList
        alternatives={[
          alt({ test: "@kind = 'dog'", type_name: "tns:Dog" }),
          alt({ test: null, type_name: "tns:Animal" }),
        ]}
        renderTypeRef={renderTypeRef}
      />,
    );
    expect(screen.getByText("if")).toBeInTheDocument();
    expect(screen.getByText("else")).toBeInTheDocument();
    expect(screen.getByTestId("type-ref-tns:Animal")).toBeInTheDocument();
  });

  it("shows xpathDefaultNamespace chip when present", () => {
    render(
      <AlternativesList
        alternatives={[
          alt({
            test: "@kind = 'cat'",
            type_name: "tns:Cat",
            xpath_default_namespace: "http://example.com/alt",
          }),
        ]}
        renderTypeRef={renderTypeRef}
      />,
    );
    expect(screen.getByText(/ns: http:\/\/example.com\/alt/)).toBeInTheDocument();
  });

  it("renders 'inline complex' tag when an alternative has no named type", () => {
    render(
      <AlternativesList
        alternatives={[
          alt({
            test: "@kind = 'cat'",
            type_name: null,
            type_inline_complex: {
              id: "complexType:anon",
              name: null,
              anonymous: true,
              abstract: false,
              mixed: false,
              content_kind: "complex",
              derivation: "extension",
              base: "tns:Animal",
              particle: null,
              attributes: [],
              attribute_group_refs: [],
              simple_content_base: null,
              simple_content_facets: [],
              annotation: null,
              source_ref: null,
            },
          }),
        ]}
        renderTypeRef={renderTypeRef}
      />,
    );
    expect(screen.getByText("inline complex")).toBeInTheDocument();
  });
});
