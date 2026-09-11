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
    const fetchMock = vi.fn().mockImplementation(async (url: string) =>
      String(url).includes("/validate/")
        ? { ok: true, status: 200, json: async () => ({ is_valid: true, errors: [], reformatted_xml: "" }) }
        : { ok: true, status: 200, text: async () => "<Root/>" },
    );
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
    const sampleCall = fetchMock.mock.calls.find((c) => String(c[0]).includes("/sample?"));
    expect(decodeURIComponent(String(sampleCall?.[0]))).toContain(`element=${roots[0].id}`);
  });

  it("does not offer abstract roots that nothing can substitute", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (url: string) =>
        String(url).includes("/validate/")
          ? { ok: true, status: 200, json: async () => ({ is_valid: true, errors: [], reformatted_xml: "" }) }
          : { ok: true, status: 200, text: async () => "<Root/>", headers: new Headers() },
      ),
    );
    const person = computeRootElements(smallModel)[0];
    // A main-file global that can never be a document element on its own.
    const orphan = {
      ...person,
      id: "element:{http://example.com/simple}AbstractPart",
      name: "AbstractPart",
      qname: "{http://example.com/simple}AbstractPart",
      abstract: true,
    };
    render(<App />);
    act(() => useSelection.getState().setSchema("test", { ...smallModel, elements: [...smallModel.elements, orphan] }));

    await userEvent.click(screen.getByRole("button", { name: "Generate sample XML for the root element" }));
    expect(screen.getByRole("dialog", { name: `Sample XML for <${person.name}>` })).toBeInTheDocument();
    const select = screen.queryByRole("combobox", { name: /Root element/ }) as HTMLSelectElement | null;
    const offered = select ? Array.from(select.options).map((o) => o.textContent) : [person.name];
    expect(offered).not.toContain("AbstractPart");
  });
});
