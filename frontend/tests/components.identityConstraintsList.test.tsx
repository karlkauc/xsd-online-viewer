import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  IdentityConstraintsList,
  ConstraintPath,
} from "../src/components/IdentityConstraintsList";
import { useSelection } from "../src/stores/selectionStore";
import { buildIndex } from "../src/lib/indexSchema";
import type { IdentityConstraint } from "../src/types/schema";
import type { PathToken } from "../src/lib/constraintXPath";
import {
  constraintsModel,
  libraryElement,
  bookElement,
  bookKeyConstraint,
  uniqueTitleConstraint,
  loanBookRefConstraint,
  danglingRefConstraint,
} from "./fixtures/constraintsModel";

const { index, indexById, constraintsById } = buildIndex(constraintsModel);

function makeConstraint(overrides: Partial<IdentityConstraint> = {}): IdentityConstraint {
  return {
    id: "identityConstraint:test",
    kind: "unique",
    name: "testConstraint",
    qname: "{ns}testConstraint",
    selector: "tns:Book",
    fields: ["@title"],
    refer: null,
    refer_id: null,
    xpath_default_namespace: null,
    annotation: null,
    source_ref: null,
    version_constraints: null,
    ...overrides,
  };
}

describe("ConstraintPath", () => {
  it("renders resolved steps as buttons and calls setSelected on click", async () => {
    const setSelected = vi.fn();
    const tokens: PathToken[] = [
      { text: "tns:Book", kind: "step", targetId: "element:x", targetKind: "element" },
    ];
    render(<ConstraintPath tokens={tokens} setSelected={setSelected} />);
    const button = screen.getByRole("button", { name: "tns:Book" });
    expect(button).toHaveAttribute("title", "Go to tns:Book");
    await userEvent.click(button);
    expect(setSelected).toHaveBeenCalledWith("element:x");
  });

  it("renders unresolved steps as plain, unclickable text", () => {
    const tokens: PathToken[] = [
      { text: "tns:NoSuchThing", kind: "step", targetId: null },
    ];
    render(<ConstraintPath tokens={tokens} setSelected={vi.fn()} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("tns:NoSuchThing")).toBeInTheDocument();
  });

  it("renders separators verbatim", () => {
    const tokens: PathToken[] = [
      { text: "tns:Books", kind: "step", targetId: "x", targetKind: "element" },
      { text: "/", kind: "sep", targetId: null },
      { text: "tns:Book", kind: "step", targetId: "y", targetKind: "element" },
    ];
    const { container } = render(<ConstraintPath tokens={tokens} setSelected={vi.fn()} />);
    expect(container.textContent).toBe("tns:Books/tns:Book");
  });
});

describe("IdentityConstraintsList", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });
  afterEach(() => cleanup());

  it("renders nothing when there are no constraints", () => {
    const { container } = render(
      <IdentityConstraintsList
        constraints={[]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the section header with count and sub-label", () => {
    render(
      <IdentityConstraintsList
        constraints={libraryElement.identity_constraints ?? []}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    expect(screen.getByText("Identity constraints")).toBeInTheDocument();
    expect(
      screen.getByText(/4 · xs:key \/ xs:keyref \/ xs:unique · display-only/i),
    ).toBeInTheDocument();
  });

  it("shows a kind chip and the constraint name for every card", () => {
    render(
      <IdentityConstraintsList
        constraints={libraryElement.identity_constraints ?? []}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    expect(screen.getByText("key")).toBeInTheDocument();
    expect(screen.getByText("unique")).toBeInTheDocument();
    expect(screen.getAllByText("keyref")).toHaveLength(2);
    expect(screen.getByText("bookKey")).toBeInTheDocument();
    expect(screen.getByText("uniqueTitle")).toBeInTheDocument();
    expect(screen.getByText("loanBookRef")).toBeInTheDocument();
    expect(screen.getByText("danglingRef")).toBeInTheDocument();
  });

  it("renders the selector as clickable, resolved step buttons", async () => {
    const setSelected = vi.fn();
    render(
      <IdentityConstraintsList
        constraints={[bookKeyConstraint]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={setSelected}
      />,
    );
    // bookKeyConstraint.selector === "tns:Books/tns:Book"
    expect(screen.getByRole("button", { name: "tns:Books" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "tns:Book" }));
    expect(setSelected).toHaveBeenCalledWith(bookElement.id);
  });

  it("renders field steps as clickable, resolved buttons", () => {
    render(
      <IdentityConstraintsList
        constraints={[bookKeyConstraint]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    // fields: ["tns:ISBN"], resolved relative to Book
    expect(screen.getByRole("button", { name: "tns:ISBN" })).toBeInTheDocument();
  });

  it("leaves an unresolvable step as plain text", () => {
    const broken = makeConstraint({
      id: "identityConstraint:broken",
      kind: "unique",
      name: "broken",
      selector: "tns:NoSuchElement",
      fields: ["tns:Foo"],
    });
    render(
      <IdentityConstraintsList
        constraints={[broken]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    expect(screen.getByText("tns:NoSuchElement")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "tns:NoSuchElement" }),
    ).not.toBeInTheDocument();
  });

  it("resolves a keyref's 'refers to' via constraintsById to the key's host", async () => {
    const setSelected = vi.fn();
    render(
      <IdentityConstraintsList
        constraints={[loanBookRefConstraint]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={setSelected}
      />,
    );
    const referButton = screen.getByRole("button", { name: /bookKey/ });
    expect(referButton.textContent).toContain("⚿");
    await userEvent.click(referButton);
    expect(setSelected).toHaveBeenCalledWith(libraryElement.id);
  });

  it("falls back to a local-name match when refer_id is null but a same-named constraint exists", async () => {
    const setSelected = vi.fn();
    const aliasKeyref = makeConstraint({
      id: "identityConstraint:aliasRef",
      kind: "keyref",
      name: "aliasRef",
      refer: "other:bookKey",
      refer_id: null,
    });
    render(
      <IdentityConstraintsList
        constraints={[aliasKeyref]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={setSelected}
      />,
    );
    const referButton = screen.getByRole("button", { name: /bookKey/ });
    await userEvent.click(referButton);
    expect(setSelected).toHaveBeenCalledWith(libraryElement.id);
  });

  it("shows a plain, titled fallback for a dangling keyref that resolves nowhere", () => {
    render(
      <IdentityConstraintsList
        constraints={[danglingRefConstraint]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /noSuchKey/ }),
    ).not.toBeInTheDocument();
    const fallback = screen.getByText("tns:noSuchKey");
    expect(fallback).toHaveAttribute("title", "key not found in this schema");
  });

  it("shows an ns chip when xpath_default_namespace is set", () => {
    const withNs = makeConstraint({
      id: "identityConstraint:ns",
      name: "withNs",
      xpath_default_namespace: "http://example.com/keys",
    });
    render(
      <IdentityConstraintsList
        constraints={[withNs]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    expect(screen.getByText(/ns: http:\/\/example.com\/keys/)).toBeInTheDocument();
  });

  it("renders documentation in italics", () => {
    render(
      <IdentityConstraintsList
        constraints={[bookKeyConstraint]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Each ISBN must be unique among the library's books."),
    ).toBeInTheDocument();
  });

  it("renders a version badge when the constraint carries version constraints", () => {
    render(
      <IdentityConstraintsList
        constraints={[loanBookRefConstraint]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    expect(screen.getByText(/≥ 1\.1/)).toBeInTheDocument();
  });

  it("renders a source-line link that jumps to the constraint's source", async () => {
    render(
      <IdentityConstraintsList
        constraints={[bookKeyConstraint]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    const link = screen.getByRole("button", { name: /f1:61/ });
    await userEvent.click(link);
    const state = useSelection.getState();
    expect(state.activeTab).toBe("text");
    expect(state.sourceJump).toEqual({ file_id: "f1", line: 61 });
  });

  it("shows selector/field steps for a unique constraint using .// and @ steps", () => {
    render(
      <IdentityConstraintsList
        constraints={[uniqueTitleConstraint]}
        host={libraryElement}
        index={index}
        indexById={indexById}
        constraintsById={constraintsById}
        setSelected={vi.fn()}
      />,
    );
    // selector ".//tns:Book" resolves via BFS to Book
    expect(screen.getByRole("button", { name: "tns:Book" })).toBeInTheDocument();
    // fields: "@title" and "tns:Edition"
    expect(screen.getByRole("button", { name: "@title" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "tns:Edition" })).toBeInTheDocument();
  });
});
