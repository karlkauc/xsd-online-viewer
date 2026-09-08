import type { ReactNode } from "react";
import { render, screen, cleanup, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TreeView } from "../src/components/TreeView/TreeView";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";
import { constraintsModel, libraryElement } from "./fixtures/constraintsModel";

// react-virtuoso only renders the rows that fit an actually-measured
// viewport, which jsdom never provides — render every row unconditionally
// so the glyph assertions below can find them.
vi.mock("react-virtuoso", () => ({
  Virtuoso: ({
    totalCount,
    itemContent,
  }: {
    totalCount: number;
    itemContent: (index: number) => ReactNode;
  }) => (
    <div>
      {Array.from({ length: totalCount }, (_, i) => (
        <div key={i}>{itemContent(i)}</div>
      ))}
    </div>
  ),
}));

describe("TreeView identity-constraint glyph", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });
  afterEach(() => cleanup());

  it("shows a ⚿ glyph with an aria-label on a row whose element declares identity constraints", () => {
    act(() => {
      useSelection.getState().setSchema("constraints", constraintsModel);
    });
    render(<TreeView />);
    expect(screen.getByText(libraryElement.name!)).toBeInTheDocument();
    const glyph = screen.getByLabelText(
      "key bookKey, unique uniqueTitle, keyref loanBookRef, keyref danglingRef",
    );
    expect(glyph.textContent).toBe("⚿");
  });

  it("does not show the glyph for a model with no identity constraints", () => {
    act(() => {
      useSelection.getState().setSchema("small", smallModel);
    });
    render(<TreeView />);
    expect(screen.queryByText("⚿")).not.toBeInTheDocument();
  });
});
