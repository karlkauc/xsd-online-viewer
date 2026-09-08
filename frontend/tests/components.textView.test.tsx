import { render, screen, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TextView } from "../src/components/TextView/TextView";
import { useSelection } from "../src/stores/selectionStore";
import type { SchemaModel } from "../src/types/schema";
import { smallModel } from "./fixtures/smallModel";

const twoFileModel: SchemaModel = {
  ...smallModel,
  files: [
    { id: "f1", filename: "main.xsd", target_namespace: null, relationship: "main", content: "<a/>" },
    { id: "f2", filename: "other.xsd", target_namespace: null, relationship: "include", content: "<b/>" },
  ],
};

describe("TextView", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("switches to the file named by a pending sourceJump, ignoring the selection's own file", () => {
    act(() => {
      useSelection.getState().setSchema("id", twoFileModel);
      // Person's source_ref points at f1.
      useSelection.getState().setSelected("element:{http://example.com/simple}Person");
    });
    render(<TextView />);
    expect(screen.getByTitle("main.xsd")).toHaveClass("bg-accent");

    act(() => {
      useSelection.getState().jumpToSource({ file_id: "f2", line: 3 });
    });
    expect(screen.getByTitle("other.xsd")).toHaveClass("bg-accent");
  });

  it("clears the active tab file switch back to selection once sourceJump is reset by a new selection", () => {
    act(() => {
      useSelection.getState().setSchema("id", twoFileModel);
      useSelection.getState().jumpToSource({ file_id: "f2", line: 3 });
    });
    render(<TextView />);
    expect(screen.getByTitle("other.xsd")).toHaveClass("bg-accent");

    act(() => {
      useSelection.getState().setSelected("element:{http://example.com/simple}Person");
    });
    expect(screen.getByTitle("main.xsd")).toHaveClass("bg-accent");
  });

  it("re-runs the scroll/highlight effect on a second jumpToSource click to the same line", () => {
    // A fresh ref object per click (same file+line) must still trigger the
    // scroll effect — regression test for including `sourceJump` (not just
    // the derived `targetLine` number) in the effect's dependency array.
    // Spying on requestAnimationFrame (rather than letting jsdom actually
    // run CodeMirror's internal measurement pass, which jsdom doesn't fully
    // support) is enough to prove the effect fired again.
    const rafSpy = vi.spyOn(window, "requestAnimationFrame");
    act(() => {
      useSelection.getState().setSchema("id", twoFileModel);
    });
    render(<TextView />);
    rafSpy.mockClear();

    act(() => {
      useSelection.getState().jumpToSource({ file_id: "f1", line: 1 });
    });
    expect(rafSpy).toHaveBeenCalledTimes(1);

    // Same file+line, but a brand-new object — must still schedule a fresh
    // scroll/highlight dispatch.
    act(() => {
      useSelection.getState().jumpToSource({ file_id: "f1", line: 1 });
    });
    expect(rafSpy).toHaveBeenCalledTimes(2);

    rafSpy.mockRestore();
  });
});
