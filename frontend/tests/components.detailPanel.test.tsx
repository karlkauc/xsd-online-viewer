import { render, screen, act } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { DetailPanel } from "../src/components/DetailPanel";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";

describe("DetailPanel", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("prompts when nothing is selected", () => {
    render(<DetailPanel />);
    expect(screen.getByText(/select a node/i)).toBeInTheDocument();
  });

  it("renders facets for a selected simpleType", () => {
    act(() => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection
        .getState()
        .setSelected("simpleType:{http://example.com/simple}AgeType");
    });
    render(<DetailPanel />);
    expect(screen.getByRole("heading", { name: "AgeType" })).toBeInTheDocument();
    expect(screen.getByText(/minInclusive/)).toBeInTheDocument();
    expect(screen.getByText(/maxInclusive/)).toBeInTheDocument();
  });
});
