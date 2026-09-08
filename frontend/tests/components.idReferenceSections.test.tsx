import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  IdReferenceSection,
  ReferencedByIdrefSection,
} from "../src/components/IdReferenceSections";
import { buildIndex } from "../src/lib/indexSchema";
import { idRolesModel, uniqueIdElement, relatedRefsElement } from "./fixtures/idRolesModel";
import type { ElementDecl, NodeIndexEntry } from "../src/types/schema";

const { idDeclarations, idrefDeclarations, indexById, parentById } = buildIndex(idRolesModel);

describe("IdReferenceSection", () => {
  afterEach(() => cleanup());

  it("shows the section heading and hint text", () => {
    render(
      <IdReferenceSection
        idDeclarations={idDeclarations}
        indexById={indexById}
        parentById={parentById}
        setSelected={vi.fn()}
      />,
    );
    expect(screen.getByText("ID reference")).toBeInTheDocument();
    expect(
      screen.getByText(
        /XML Schema does not bind an IDREF to a specific ID: any element or attribute typed xs:ID in the document is a valid target\. Declarations typed xs:ID in this schema:/,
      ),
    ).toBeInTheDocument();
  });

  it("renders a card per xs:ID candidate with kind badge, name button and path", async () => {
    const setSelected = vi.fn();
    render(
      <IdReferenceSection
        idDeclarations={idDeclarations}
        indexById={indexById}
        parentById={parentById}
        setSelected={setSelected}
      />,
    );
    expect(screen.getByText("UniqueID")).toBeInTheDocument();
    expect(screen.getByText("/Holder/UniqueID")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "UniqueID" }));
    expect(setSelected).toHaveBeenCalledWith(uniqueIdElement.id);
  });

  it("shows the empty state when there are no xs:ID declarations", () => {
    render(
      <IdReferenceSection
        idDeclarations={[]}
        indexById={indexById}
        parentById={parentById}
        setSelected={vi.fn()}
      />,
    );
    expect(screen.getByText("No xs:ID declarations in this schema.")).toBeInTheDocument();
  });

  it("caps candidates at 8 and reveals the rest via 'Show all (N)'", async () => {
    const manyIdEntries: NodeIndexEntry[] = Array.from({ length: 9 }, (_, i) => ({
      id: `element:id-${i}`,
      kind: "element",
      label: `Id${i}`,
      qname: `{ns}Id${i}`,
      source_ref: null,
      node: {
        ...uniqueIdElement,
        id: `element:id-${i}`,
        name: `Id${i}`,
        qname: `{ns}Id${i}`,
      } as ElementDecl,
    }));
    render(
      <IdReferenceSection
        idDeclarations={manyIdEntries}
        indexById={indexById}
        parentById={parentById}
        setSelected={vi.fn()}
      />,
    );
    for (let i = 0; i < 8; i++) {
      expect(screen.getByText(`Id${i}`)).toBeInTheDocument();
    }
    expect(screen.queryByText("Id8")).not.toBeInTheDocument();
    const showAll = screen.getByRole("button", { name: "Show all (9)" });
    await userEvent.click(showAll);
    expect(screen.getByText("Id8")).toBeInTheDocument();
  });
});

describe("ReferencedByIdrefSection", () => {
  afterEach(() => cleanup());

  it("shows the section heading with the IDREF/IDREFS count", () => {
    render(
      <ReferencedByIdrefSection idrefDeclarations={idrefDeclarations} setSelected={vi.fn()} />,
    );
    expect(screen.getByText("Referenced by IDREF")).toBeInTheDocument();
    expect(screen.getByText(/3 xs:IDREF\/IDREFS declarations/)).toBeInTheDocument();
  });

  it("renders a UsageRow per IDREF/IDREFS declaration and calls setSelected on click", async () => {
    const setSelected = vi.fn();
    render(
      <ReferencedByIdrefSection idrefDeclarations={idrefDeclarations} setSelected={setSelected} />,
    );
    expect(screen.getByText("BenchmarkRef")).toBeInTheDocument();
    expect(screen.getByText("RelatedRefs")).toBeInTheDocument();
    expect(screen.getByText("refAttr")).toBeInTheDocument();
    await userEvent.click(screen.getByText("RelatedRefs"));
    expect(setSelected).toHaveBeenCalledWith(relatedRefsElement.id);
  });

  it("shows an IDREFS chip only next to idrefs declarations", () => {
    render(
      <ReferencedByIdrefSection idrefDeclarations={idrefDeclarations} setSelected={vi.fn()} />,
    );
    expect(screen.getAllByText("IDREFS")).toHaveLength(1);
  });

  it("shows the empty state when nothing references this ID", () => {
    render(<ReferencedByIdrefSection idrefDeclarations={[]} setSelected={vi.fn()} />);
    expect(
      screen.getByText("No xs:IDREF/IDREFS declarations in this schema."),
    ).toBeInTheDocument();
  });
});
