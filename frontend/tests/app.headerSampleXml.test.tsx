import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { useSelection } from "../src/stores/selectionStore";
import { computeRootElements } from "../src/lib/rootElements";
import { smallModel } from "./fixtures/smallModel";

describe('App "Sample XML" header button', () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
    window.location.hash = "";
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("is absent without a schema and opens the dialog for the document root", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, text: async () => "<Root/>" });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(screen.queryByRole("button", { name: "Generate sample XML for the root element" })).not.toBeInTheDocument();

    act(() => useSelection.getState().setSchema("test", smallModel));
    const roots = computeRootElements(smallModel);
    expect(roots.length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: "Generate sample XML for the root element" }));
    expect(
      screen.getByRole("dialog", { name: `Sample XML for <${roots[0].name}>` }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(decodeURIComponent(String(fetchMock.mock.calls[0][0]))).toContain(`element=${roots[0].id}`);
  });
});
