import { render, screen, act, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "../src/App";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";

describe('App "Load new…" header button', () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
    // Reset URL hash so prior selections don't bleed in.
    window.location.hash = "";
  });

  afterEach(() => {
    cleanup();
  });

  it("is hidden on the initial upload screen", () => {
    render(<App />);
    expect(
      screen.queryByRole("button", { name: /Load a different schema/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/Drop a file here/i)).toBeInTheDocument();
  });

  it("appears once a schema is loaded and clears the schema on click", async () => {
    render(<App />);
    act(() => {
      useSelection.getState().setSchema("test", smallModel);
    });
    const loadNew = await screen.findByRole("button", {
      name: /Load a different schema/i,
    });
    expect(loadNew).toBeInTheDocument();

    await userEvent.click(loadNew);
    // After click the Uploader is shown again and the button is gone.
    expect(screen.getByText(/Drop a file here/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Load a different schema/i }),
    ).not.toBeInTheDocument();
    expect(useSelection.getState().model).toBeNull();
  });
});
