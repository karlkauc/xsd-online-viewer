import { render, screen, act } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { SourceLineLink } from "../src/components/SourceLineLink";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";

describe("SourceLineLink", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("renders 'file:line ->' text", () => {
    render(<SourceLineLink sourceRef={{ file_id: "f1", line: 42 }} />);
    expect(screen.getByRole("button")).toHaveTextContent("f1:42");
    expect(screen.getByRole("button")).toHaveTextContent("→");
  });

  it("has a title hinting at the Text tab", () => {
    render(<SourceLineLink sourceRef={{ file_id: "f1", line: 42 }} />);
    expect(screen.getByRole("button")).toHaveAttribute(
      "title",
      "Open in the Text tab",
    );
  });

  it("clicking it calls jumpToSource with the given ref", () => {
    act(() => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection.getState().setActiveTab("tree");
    });
    const ref = { file_id: "f1", line: 42 };
    render(<SourceLineLink sourceRef={ref} />);
    act(() => screen.getByRole("button").click());
    const state = useSelection.getState();
    expect(state.activeTab).toBe("text");
    expect(state.sourceJump).toBe(ref);
  });

  it("accepts a className", () => {
    render(<SourceLineLink sourceRef={{ file_id: "f1", line: 1 }} className="my-class" />);
    expect(screen.getByRole("button").className).toContain("my-class");
  });
});
