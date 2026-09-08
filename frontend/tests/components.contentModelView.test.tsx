import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ContentModelView } from "../src/components/ContentModelView/ContentModelView";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";
import { refModel, DOCUMENT_ID, SIGNATURE_REF_ID } from "./fixtures/refModel";
import {
  assertionsModel,
  codeAttribute,
  codeElement,
  measurementElement,
  measurementType,
  positiveCodeType,
} from "./fixtures/assertionsModel";
import {
  constraintsModel,
  libraryElement,
  bookElement,
  leafElement,
  archiveBookElement,
  inlineExtensionElement,
  NS as CONSTRAINTS_NS,
} from "./fixtures/constraintsModel";
import type { ElementDecl, SchemaModel } from "../src/types/schema";

function selectId(id: string) {
  act(() => {
    useSelection.getState().setSchema("id", smallModel);
    useSelection.getState().setSelected(id);
  });
}

describe("ContentModelView", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("renders Children + Attributes for an element with a complex type", () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    expect(screen.getByRole("heading", { name: "Person" })).toBeInTheDocument();
    expect(screen.getByText("Children")).toBeInTheDocument();
    expect(screen.getByText("FirstName")).toBeInTheDocument();
    expect(screen.getByText("LastName")).toBeInTheDocument();
    expect(screen.getByText("Attributes")).toBeInTheDocument();
    expect(screen.getByText(/^@id$/)).toBeInTheDocument();
  });

  it("renders only the simple-type card for an element with a named simpleType", () => {
    selectId("element:{http://example.com/simple}PersonType/Age");
    render(<ContentModelView />);
    expect(screen.queryByText("Children")).not.toBeInTheDocument();
    expect(screen.queryByText("Attributes")).not.toBeInTheDocument();
    expect(screen.getByText("Range")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("130")).toBeInTheDocument();
  });

  it("renders enumeration values for a simpleType selection", () => {
    selectId("simpleType:{http://example.com/simple}ColorType");
    render(<ContentModelView />);
    expect(screen.getByText(/^Enumeration/)).toBeInTheDocument();
    expect(screen.getByText("red")).toBeInTheDocument();
    expect(screen.getByText("green")).toBeInTheDocument();
    expect(screen.getByText("blue")).toBeInTheDocument();
  });

  it("clicking a child element row updates the selection", async () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    const row = screen.getByText("FirstName").closest("tr");
    expect(row).not.toBeNull();
    await userEvent.click(row!);
    expect(useSelection.getState().selectedId).toBe(
      "element:{http://example.com/simple}PersonType/FirstName",
    );
  });

  it("clicking a Type cell with a resolvable QName selects the target", async () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    const button = screen.getByRole("button", { name: "tns:AgeType" });
    await userEvent.click(button);
    expect(useSelection.getState().selectedId).toBe(
      "simpleType:{http://example.com/simple}AgeType",
    );
  });

  it("returns nothing when no selection is active", () => {
    act(() => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection.getState().setSelected(null);
    });
    const { container } = render(<ContentModelView />);
    expect(container.firstChild).toBeNull();
  });
});

describe("ContentModelView element references", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  function selectInRefModel(id: string) {
    act(() => {
      useSelection.getState().setSchema("ref", refModel);
      useSelection.getState().setSelected(id);
    });
  }

  it("shows the content model of the declaration a ref points at", () => {
    selectInRefModel(SIGNATURE_REF_ID);
    render(<ContentModelView />);
    expect(screen.getByText("Children")).toBeInTheDocument();
    expect(screen.getByText("ds:SignedInfo")).toBeInTheDocument();
    expect(screen.getByText(/^@Id$/)).toBeInTheDocument();
  });

  it("lists the referenced type in the children table", () => {
    selectInRefModel(DOCUMENT_ID);
    render(<ContentModelView />);
    const row = screen.getByText("ds:Signature").closest("tr");
    expect(row).not.toBeNull();
    expect(row!.textContent).toContain("ds:SignatureType");
  });
});

describe("ContentModelView assertions table", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  function selectInAssertionsModel(id: string) {
    act(() => {
      useSelection.getState().setSchema("assert", assertionsModel);
      useSelection.getState().setSelected(id);
    });
  }

  it("shows an assertions table for an element typed by a named complex type", () => {
    selectInAssertionsModel(measurementElement.id);
    render(<ContentModelView />);
    expect(screen.getByText("Assertions")).toBeInTheDocument();
    expect(screen.getByText("xs:date(@from) le xs:date(@to)")).toBeInTheDocument();
    expect(screen.getByText("count(Value) gt 0")).toBeInTheDocument();
  });

  it("shows an assertions table for a directly-selected complexType", () => {
    act(() => {
      useSelection.getState().setSchema("assert", assertionsModel);
      useSelection.getState().setSelected(measurementType.id);
    });
    render(<ContentModelView />);
    expect(screen.getByText("Assertions")).toBeInTheDocument();
    expect(screen.getByText("xs:date(@from) le xs:date(@to)")).toBeInTheDocument();
  });

  it("shows an assertions table for a directly-selected simpleType", () => {
    act(() => {
      useSelection.getState().setSchema("assert", assertionsModel);
      useSelection.getState().setSelected(positiveCodeType.id);
    });
    render(<ContentModelView />);
    expect(screen.getByText("Assertions")).toBeInTheDocument();
    expect(screen.getByText("string-length($value) gt 0")).toBeInTheDocument();
  });

  it("shows an assertions table for an element typed by a named simpleType", () => {
    selectInAssertionsModel(codeElement.id);
    render(<ContentModelView />);
    expect(screen.getByText("Assertions")).toBeInTheDocument();
    expect(screen.getByText("string-length($value) gt 0")).toBeInTheDocument();
  });

  it("shows an assertions table for an attribute typed by a named simpleType", () => {
    selectInAssertionsModel(codeAttribute.id);
    render(<ContentModelView />);
    expect(screen.getByText("Assertions")).toBeInTheDocument();
    expect(screen.getByText("string-length($value) gt 0")).toBeInTheDocument();
  });

  it("does not render an assertions table when there are no assertions", () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    expect(screen.queryByText("Assertions")).not.toBeInTheDocument();
  });
});

describe("ContentModelView identity constraints table", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("shows an identity-constraints table for an element with a complex type", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(libraryElement.id);
    });
    render(<ContentModelView />);
    expect(screen.getByText("Identity constraints")).toBeInTheDocument();
    expect(screen.getByText("bookKey")).toBeInTheDocument();
    expect(screen.getByText("uniqueTitle")).toBeInTheDocument();
    expect(screen.getByText("loanBookRef")).toBeInTheDocument();
    expect(screen.getByText("danglingRef")).toBeInTheDocument();
  });

  it("shows an identity-constraints table for an element with a simple type", () => {
    const keyedElement: ElementDecl = leafElement("Keyed", "", 200, {
      id: "element:{http://example.com/keyed-simple}Keyed",
      qname: "{http://example.com/keyed-simple}Keyed",
      is_global: true,
      type_name: null,
      type_inline_simple: {
        id: "simpleType:{http://example.com/keyed-simple}Keyed/anon",
        name: null,
        anonymous: true,
        derivation: "atomic",
        base: "xs:string",
        item_type: null,
        item_inline: null,
        member_types: [],
        member_inline: [],
        facets: [],
        annotation: null,
        source_ref: null,
      },
      identity_constraints: [
        {
          id: "identityConstraint:{http://example.com/keyed-simple}kc",
          kind: "unique",
          name: "kc",
          qname: "{http://example.com/keyed-simple}kc",
          selector: ".",
          fields: ["."],
          refer: null,
          refer_id: null,
          xpath_default_namespace: null,
          annotation: null,
          source_ref: null,
          version_constraints: null,
        },
      ],
    });
    const keyedModel: SchemaModel = { ...constraintsModel, elements: [keyedElement] };
    act(() => {
      useSelection.getState().setSchema("keyed-simple", keyedModel);
      useSelection.getState().setSelected(keyedElement.id);
    });
    render(<ContentModelView />);
    expect(screen.getByText("Identity constraints")).toBeInTheDocument();
    expect(screen.getByText("kc")).toBeInTheDocument();
  });

  it("does not render an identity-constraints table for an element without constraints", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(bookElement.id);
    });
    render(<ContentModelView />);
    expect(screen.queryByText("Identity constraints")).not.toBeInTheDocument();
  });

  it("does not render an identity-constraints table for a model without any constraints", () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    expect(screen.queryByText("Identity constraints")).not.toBeInTheDocument();
  });
});

describe("ContentModelView content inherited through xs:extension", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("shows the base's children/attributes and an inherited-from note for a named-type extension", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(archiveBookElement.id);
    });
    render(<ContentModelView />);
    expect(screen.getByText("Children")).toBeInTheDocument();
    expect(screen.getByText(/tns:BookCore/)).toBeInTheDocument();
    expect(screen.getByText("Edition")).toBeInTheDocument();
    expect(screen.getByText("Attributes")).toBeInTheDocument();
    expect(screen.getByText(/^@title$/)).toBeInTheDocument();
    expect(screen.getByText(/Content inherited from/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "BookType" })).toBeInTheDocument();
  });

  it("shows the base's content for an inline-complex extension too", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(inlineExtensionElement.id);
    });
    render(<ContentModelView />);
    expect(screen.getByText(/tns:BookCore/)).toBeInTheDocument();
    expect(screen.getByText("Edition")).toBeInTheDocument();
    expect(screen.getByText(/^@title$/)).toBeInTheDocument();
    expect(screen.getByText(/Content inherited from/)).toBeInTheDocument();
  });

  it("clicking the inherited-from link selects the base type", async () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(archiveBookElement.id);
    });
    render(<ContentModelView />);
    await userEvent.click(screen.getByRole("button", { name: "BookType" }));
    expect(useSelection.getState().selectedId).toBe(`complexType:{${CONSTRAINTS_NS}}BookType`);
  });

  it("does not render the inherited-from note for a plain (non-extension) type", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
      useSelection.getState().setSelected(bookElement.id);
    });
    render(<ContentModelView />);
    expect(screen.queryByText(/Content inherited from/)).not.toBeInTheDocument();
  });
});
