import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "../src/App";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";

describe("phone pane after a schema loads", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
    window.location.hash = "";
  });
  afterEach(() => cleanup());

  it("opens on the View pane so the diagram shows first", async () => {
    render(<App />);
    act(() => {
      useSelection.getState().setSchema("test", smallModel);
    });
    const nav = await screen.findByRole("navigation", { name: "Panes" });
    expect(nav.querySelector('button[aria-pressed="true"]')).toHaveTextContent("View");
  });

  it("returns to the View pane when a different schema is loaded", async () => {
    render(<App />);
    act(() => {
      useSelection.getState().setSchema("first", smallModel);
    });
    const nav = await screen.findByRole("navigation", { name: "Panes" });
    act(() => {
      (nav.querySelector('button[aria-pressed="false"]') as HTMLButtonElement).click();
    });
    expect(nav.querySelector('button[aria-pressed="true"]')).not.toHaveTextContent("View");
    act(() => {
      useSelection.getState().setSchema("second", smallModel);
    });
    expect(nav.querySelector('button[aria-pressed="true"]')).toHaveTextContent("View");
  });
});
