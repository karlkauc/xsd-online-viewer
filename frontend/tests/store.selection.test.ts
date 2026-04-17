import { beforeEach, describe, expect, it } from "vitest";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";

describe("selectionStore", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("indexes the model when set", () => {
    useSelection.getState().setSchema("id", smallModel);
    const state = useSelection.getState();
    expect(state.schemaId).toBe("id");
    expect(state.index.length).toBeGreaterThan(0);
  });

  it("sets selection without touching expansion state", () => {
    useSelection.getState().setSchema("id", smallModel);
    useSelection.getState().setSelected("complexType:{http://example.com/simple}PersonType");
    const state = useSelection.getState();
    expect(state.selectedId).toBe("complexType:{http://example.com/simple}PersonType");
    expect(state.expandedIds.size).toBe(0);
  });

  it("toggles expansion", () => {
    useSelection.getState().setSchema("id", smallModel);
    useSelection.getState().toggleExpanded("x");
    expect(useSelection.getState().expandedIds.has("x")).toBe(true);
    useSelection.getState().toggleExpanded("x");
    expect(useSelection.getState().expandedIds.has("x")).toBe(false);
  });
});
