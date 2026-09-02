import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DiagramToolbar } from "../src/components/DiagramView/DiagramToolbar";

function renderToolbar(compact: boolean, onExport = vi.fn()) {
  render(
    <DiagramToolbar
      compact={compact}
      minimapVisible
      canExpand
      canCollapse={false}
      onExpandAll={vi.fn()}
      onCollapseAll={vi.fn()}
      onToggleMinimap={vi.fn()}
      onExport={onExport}
    />,
  );
  return onExport;
}

describe("DiagramToolbar", () => {
  afterEach(() => cleanup());

  it("shows the full text buttons on desktop", () => {
    renderToolbar(false);
    expect(screen.getByRole("button", { name: "Expand all" })).toHaveTextContent("Expand all");
    expect(screen.getByRole("button", { name: "Export SVG" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export PNG" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export" })).not.toBeInTheDocument();
  });

  it("keeps the accessible names but folds export into a menu when compact", async () => {
    const onExport = renderToolbar(true);
    expect(screen.getByRole("button", { name: "Expand all" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Collapse all" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hide minimap" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("menuitem", { name: "Export SVG" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Export PNG" }));
    expect(onExport).toHaveBeenCalledWith("png");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
