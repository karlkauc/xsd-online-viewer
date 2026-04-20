import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ContentModelView } from "../src/components/ContentModelView/ContentModelView";
import { useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";

function selectId(id: string) {
  act(() => {
    useSelection.getState().setSchema("id", smallModel);
    useSelection.getState().setSelected(id);
  });
}

describe("ContentModelView", () => {
  beforeEach(() => {
    useSelection.getState().clearSchema();
  });

  it("renders Children + Attributes for an element with a complex type", () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    expect(screen.getByRole("heading", { name: "Person" })).toBeInTheDocument();
    expect(screen.getByText("Children")).toBeInTheDocument();
    expect(screen.getByText("FirstName")).toBeInTheDocument();
    expect(screen.getByText("LastName")).toBeInTheDocument();
    expect(screen.getByText("Attributes")).toBeInTheDocument();
    expect(screen.getByText(/^@id$/)).toBeInTheDocument();
  });

  it("renders only the simple-type card for an element with a named simpleType", () => {
    selectId("element:{http://example.com/simple}PersonType/Age");
    render(<ContentModelView />);
    expect(screen.queryByText("Children")).not.toBeInTheDocument();
    expect(screen.queryByText("Attributes")).not.toBeInTheDocument();
    expect(screen.getByText("Range")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("130")).toBeInTheDocument();
  });

  it("renders enumeration values for a simpleType selection", () => {
    selectId("simpleType:{http://example.com/simple}ColorType");
    render(<ContentModelView />);
    expect(screen.getByText(/^Enumeration/)).toBeInTheDocument();
    expect(screen.getByText("red")).toBeInTheDocument();
    expect(screen.getByText("green")).toBeInTheDocument();
    expect(screen.getByText("blue")).toBeInTheDocument();
  });

  it("clicking a child element row updates the selection", async () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    const row = screen.getByText("FirstName").closest("tr");
    expect(row).not.toBeNull();
    await userEvent.click(row!);
    expect(useSelection.getState().selectedId).toBe(
      "element:{http://example.com/simple}PersonType/FirstName",
    );
  });

  it("clicking a Type cell with a resolvable QName selects the target", async () => {
    selectId("element:{http://example.com/simple}Person");
    render(<ContentModelView />);
    const button = screen.getByRole("button", { name: "tns:AgeType" });
    await userEvent.click(button);
    expect(useSelection.getState().selectedId).toBe(
      "simpleType:{http://example.com/simple}AgeType",
    );
  });

  it("returns nothing when no selection is active", () => {
    act(() => {
      useSelection.getState().setSchema("id", smallModel);
      useSelection.getState().setSelected(null);
    });
    const { container } = render(<ContentModelView />);
    expect(container.firstChild).toBeNull();
  });
});
