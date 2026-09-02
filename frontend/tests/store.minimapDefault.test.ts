import { afterEach, describe, expect, it } from "vitest";
import { defaultMinimapVisible, useSelection } from "../src/stores/selectionStore";
import { smallModel } from "./fixtures/smallModel";

const original = window.matchMedia;
function mockWidthMatches(matches: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query === "(min-width: 768px)" ? matches : false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

describe("minimap default visibility", () => {
  afterEach(() => {
    window.matchMedia = original;
    useSelection.getState().clearSchema();
  });

  it("is off on viewports narrower than 768px", () => {
    mockWidthMatches(false);
    expect(defaultMinimapVisible()).toBe(false);
  });

  it("is on from 768px upwards", () => {
    mockWidthMatches(true);
    expect(defaultMinimapVisible()).toBe(true);
  });

  it("setSchema resets the minimap to the viewport default", () => {
    mockWidthMatches(false);
    useSelection.getState().setMinimapVisible(true);
    useSelection.getState().setSchema("s", smallModel);
    expect(useSelection.getState().minimapVisible).toBe(false);
  });
});
