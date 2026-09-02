import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMediaQuery } from "../src/lib/useMediaQuery";

type Listener = (event: { matches: boolean }) => void;

function installMatchMedia(initial: Record<string, boolean>) {
  const listeners = new Map<string, Set<Listener>>();
  const state = { ...initial };
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    get matches() {
      return state[query] ?? false;
    },
    media: query,
    onchange: null,
    addEventListener: (_type: string, cb: Listener) => {
      if (!listeners.has(query)) listeners.set(query, new Set());
      listeners.get(query)!.add(cb);
    },
    removeEventListener: (_type: string, cb: Listener) => {
      listeners.get(query)?.delete(cb);
    },
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
  return {
    set(query: string, matches: boolean) {
      state[query] = matches;
      listeners.get(query)?.forEach((cb) => cb({ matches }));
    },
    listenerCount(query: string) {
      return listeners.get(query)?.size ?? 0;
    },
    restore() {
      window.matchMedia = original;
    },
  };
}

describe("useMediaQuery", () => {
  let mm: ReturnType<typeof installMatchMedia> | null = null;
  afterEach(() => {
    mm?.restore();
    mm = null;
  });

  it("returns the current match state of the query", () => {
    mm = installMatchMedia({ "(min-width: 1024px)": true });
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(true);
  });

  it("re-renders when the media query list fires a change event", () => {
    mm = installMatchMedia({ "(min-width: 1024px)": false });
    const { result } = renderHook(() => useMediaQuery("(min-width: 1024px)"));
    expect(result.current).toBe(false);
    act(() => mm!.set("(min-width: 1024px)", true));
    expect(result.current).toBe(true);
  });

  it("unsubscribes on unmount", () => {
    mm = installMatchMedia({ "(pointer: coarse)": false });
    const { unmount } = renderHook(() => useMediaQuery("(pointer: coarse)"));
    expect(mm.listenerCount("(pointer: coarse)")).toBe(1);
    unmount();
    expect(mm.listenerCount("(pointer: coarse)")).toBe(0);
  });
});
