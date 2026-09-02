import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Uploader } from "../src/components/Uploader";

const original = window.matchMedia;
function mockCoarsePointer(coarse: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query === "(pointer: coarse)" ? coarse : false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

describe("Uploader on touch devices", () => {
  afterEach(() => {
    window.matchMedia = original;
    cleanup();
    window.history.replaceState(null, "", "/");
  });

  it("drops the drag-and-drop wording when the pointer is coarse", () => {
    mockCoarsePointer(true);
    render(<Uploader />);
    expect(screen.getByText(/Choose a file to load/i)).toBeInTheDocument();
    expect(screen.queryByText(/Drop a file here/i)).not.toBeInTheDocument();
  });

  it("keeps the drop-zone wording for mouse users", () => {
    mockCoarsePointer(false);
    render(<Uploader />);
    expect(screen.getByText(/Drop a file here/i)).toBeInTheDocument();
  });
});
