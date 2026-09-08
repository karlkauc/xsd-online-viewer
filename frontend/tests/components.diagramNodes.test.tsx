import { cleanup, render } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import { afterEach, describe, expect, it } from "vitest";
import { ElementNode } from "../src/components/DiagramView/ElementNode";
import { CompositorNode } from "../src/components/DiagramView/CompositorNode";

function renderElement(data: Record<string, unknown>) {
  const { container } = render(
    <ReactFlowProvider>
      <ElementNode data={{ schemaId: "element:x", label: "x", ...data }} />
    </ReactFlowProvider>,
  );
  return container.firstElementChild as HTMLElement;
}

function renderCompositor(data: Record<string, unknown>) {
  const { container } = render(
    <ReactFlowProvider>
      <CompositorNode data={{ kind: "sequence", label: "sequence", ...data }} />
    </ReactFlowProvider>,
  );
  return container.firstElementChild as HTMLElement;
}

describe("ElementNode border encodes cardinality", () => {
  afterEach(() => cleanup());

  it("draws a thin solid border for mandatory single elements", () => {
    const box = renderElement({});
    expect(box.className).toMatch(/\bborder\b/);
    expect(box.className).toContain("border-solid");
    expect(box.className).not.toContain("border-dashed");
    expect(box.className).not.toContain("border-2");
  });

  it("draws a dashed border for optional elements", () => {
    const box = renderElement({ optional: true });
    expect(box.className).toContain("border-dashed");
    expect(box.className).not.toContain("border-2");
  });

  it("draws a thick solid border for repeating mandatory elements", () => {
    const box = renderElement({ repeating: true });
    expect(box.className).toContain("border-2");
    expect(box.className).toContain("border-solid");
  });

  it("draws a thick dashed border for repeating optional elements", () => {
    const box = renderElement({ optional: true, repeating: true });
    expect(box.className).toContain("border-2");
    expect(box.className).toContain("border-dashed");
  });

  it("keeps the selection ring on top of the cardinality style", () => {
    const box = renderElement({ optional: true, repeating: true, selected: true });
    expect(box.className).toContain("border-accent");
    expect(box.className).toContain("border-2");
    expect(box.className).toContain("border-dashed");
  });

  it("still shows the textual occurs label", () => {
    const box = renderElement({ optional: true, repeating: true, occurs: "[0..∞]" });
    expect(box.textContent).toContain("[0..∞]");
  });
});

describe("ElementNode identity-constraint badge", () => {
  afterEach(() => cleanup());

  it("shows the ⚿ badge with the count and title when constraints exist", () => {
    const box = renderElement({
      identityConstraintCount: 4,
      identityConstraintTitle: "key bookKey, unique uniqueTitle, keyref loanBookRef, keyref danglingRef",
    });
    expect(box.textContent).toContain("⚿ 4");
    const badge = box.querySelector("[aria-label]");
    expect(badge).not.toBeNull();
    expect(badge).toHaveAttribute(
      "title",
      "key bookKey, unique uniqueTitle, keyref loanBookRef, keyref danglingRef",
    );
    expect(badge).toHaveAttribute(
      "aria-label",
      "key bookKey, unique uniqueTitle, keyref loanBookRef, keyref danglingRef",
    );
  });

  it("does not show the badge when there are no identity constraints", () => {
    const box = renderElement({ identityConstraintCount: 0 });
    expect(box.textContent).not.toContain("⚿");
  });

  it("renders the ⚿ badge before the ≷ alternatives badge", () => {
    const box = renderElement({
      identityConstraintCount: 1,
      identityConstraintTitle: "key k",
      alternativesCount: 2,
    });
    const text = box.textContent ?? "";
    expect(text.indexOf("⚿")).toBeLessThan(text.indexOf("≷"));
  });
});

describe("ElementNode ID/IDREF badge", () => {
  afterEach(() => cleanup());

  it("shows the ID badge with an xs:ID title when idRole is 'id'", () => {
    const box = renderElement({ idRole: "id" });
    const badge = box.querySelector("[aria-label='xs:ID']");
    expect(badge).not.toBeNull();
    expect(badge).toHaveAttribute("title", "xs:ID");
    expect(badge?.textContent).toBe("ID");
  });

  it("shows the ⇢ ID badge with an xs:IDREF title when idRole is 'idref'", () => {
    const box = renderElement({ idRole: "idref" });
    const badge = box.querySelector("[aria-label='xs:IDREF']");
    expect(badge).not.toBeNull();
    expect(badge?.textContent).toBe("⇢ ID");
  });

  it("shows the ⇢ ID badge with an xs:IDREFS title when idRole is 'idrefs'", () => {
    const box = renderElement({ idRole: "idrefs" });
    const badge = box.querySelector("[aria-label='xs:IDREFS']");
    expect(badge).not.toBeNull();
    expect(badge?.textContent).toBe("⇢ ID");
  });

  it("shows no ID/IDREF badge when idRole is absent", () => {
    const box = renderElement({});
    expect(box.querySelector("[aria-label='xs:ID']")).toBeNull();
    expect(box.querySelector("[aria-label='xs:IDREF']")).toBeNull();
    expect(box.querySelector("[aria-label='xs:IDREFS']")).toBeNull();
  });

  it("renders the ID/IDREF badge before the ⚿ identity-constraint badge", () => {
    const box = renderElement({
      idRole: "id",
      identityConstraintCount: 1,
      identityConstraintTitle: "key k",
    });
    const text = box.textContent ?? "";
    expect(text.indexOf("ID")).toBeLessThan(text.indexOf("⚿"));
  });
});

describe("ElementNode attribute ID/IDREF marker", () => {
  afterEach(() => cleanup());

  it("shows a marker on an attribute row typed xs:IDREF", () => {
    const box = renderElement({
      attributes: [{ id: "a1", name: "ref", type_name: "xs:IDREF", id_role: "idref" }],
    });
    const marker = box.querySelector("[aria-label='xs:IDREF']");
    expect(marker).not.toBeNull();
  });

  it("shows no marker on an attribute row without an id_role", () => {
    const box = renderElement({
      attributes: [{ id: "a1", name: "plain", type_name: "xs:string" }],
    });
    expect(box.querySelector("[aria-label='xs:ID']")).toBeNull();
    expect(box.querySelector("[aria-label='xs:IDREF']")).toBeNull();
    expect(box.querySelector("[aria-label='xs:IDREFS']")).toBeNull();
  });
});

describe("CompositorNode border encodes cardinality", () => {
  afterEach(() => cleanup());

  it("draws a thin solid border for a mandatory single compositor", () => {
    const box = renderCompositor({});
    expect(box.className).toMatch(/\bborder\b/);
    expect(box.className).toContain("border-solid");
    expect(box.className).not.toContain("border-2");
  });

  it("draws dashed / thick per flags", () => {
    expect(renderCompositor({ optional: true }).className).toContain("border-dashed");
    cleanup();
    expect(renderCompositor({ repeating: true }).className).toContain("border-2");
    cleanup();
    const both = renderCompositor({ optional: true, repeating: true }).className;
    expect(both).toContain("border-2");
    expect(both).toContain("border-dashed");
  });

  it("lets the open-content cue win over the cardinality border", () => {
    const box = renderCompositor({ repeating: false, optional: false, openContentMode: "interleave" });
    expect(box.className).toContain("border-2");
    expect(box.className).toContain("border-dashed");
    expect(box.className).toContain("border-sky-500/70");
  });
});
