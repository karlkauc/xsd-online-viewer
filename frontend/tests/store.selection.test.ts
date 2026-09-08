import { beforeEach, describe, expect, it } from "vitest";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";
import { constraintsModel } from "./fixtures/constraintsModel";
import { idRolesModel } from "./fixtures/idRolesModel";

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

  it("defaults to the diagram tab", () => {
    expect(useSelection.getState().activeTab).toBe("diagram");
  });

  it("replaces the entire expanded set via setExpandedIds", () => {
    useSelection.getState().setSchema("id", smallModel);
    useSelection.getState().toggleExpanded("a");
    useSelection.getState().toggleExpanded("b");
    useSelection.getState().setExpandedIds(new Set(["x", "y", "z"]));
    const state = useSelection.getState();
    expect(state.expandedIds.has("a")).toBe(false);
    expect(state.expandedIds.has("x")).toBe(true);
    expect(state.expandedIds.size).toBe(3);
  });

  it("indexes identity constraints and ID/IDREF declarations when the schema is set", () => {
    useSelection.getState().setSchema("id", constraintsModel);
    const state = useSelection.getState();
    expect(state.constraintsById.size).toBe(5);
    useSelection.getState().setSchema("id2", idRolesModel);
    const state2 = useSelection.getState();
    expect(state2.idDeclarations.length).toBe(1);
    expect(state2.idrefDeclarations.length).toBe(3);
  });

  it("clearSchema resets the constraint/id maps", () => {
    useSelection.getState().setSchema("id", constraintsModel);
    useSelection.getState().clearSchema();
    const state = useSelection.getState();
    expect(state.constraintsById.size).toBe(0);
    expect(state.idDeclarations).toEqual([]);
    expect(state.idrefDeclarations).toEqual([]);
  });

  describe("sourceJump", () => {
    it("defaults to null", () => {
      expect(useSelection.getState().sourceJump).toBeNull();
    });

    it("jumpToSource sets the active tab to text and stores the ref", () => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection.getState().setActiveTab("tree");
      const ref = { file_id: "f1", line: 42 };
      useSelection.getState().jumpToSource(ref);
      const state = useSelection.getState();
      expect(state.activeTab).toBe("text");
      expect(state.sourceJump).toBe(ref);
    });

    it("setSelected clears a pending source jump", () => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection.getState().jumpToSource({ file_id: "f1", line: 42 });
      useSelection.getState().setSelected("element:{http://example.com/simple}Person");
      expect(useSelection.getState().sourceJump).toBeNull();
    });

    it("setSchema resets a pending source jump", () => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection.getState().jumpToSource({ file_id: "f1", line: 42 });
      useSelection.getState().setSchema("id2", smallModel);
      expect(useSelection.getState().sourceJump).toBeNull();
    });

    it("clearSchema resets a pending source jump", () => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection.getState().jumpToSource({ file_id: "f1", line: 42 });
      useSelection.getState().clearSchema();
      expect(useSelection.getState().sourceJump).toBeNull();
    });
  });
});
