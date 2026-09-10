import { useCallback, useSyncExternalStore } from "react";

// Viewport tiers shared by the JS side of the layout. Keep in sync with the
// Tailwind screens used in App.tsx (`md` = 768, `lg` = 1024) so that the
// JS-driven pieces (header menu, diagram toolbar) flip at the same width as
// the CSS-driven grid.
export const SM_QUERY = "(min-width: 640px)";
export const MD_QUERY = "(min-width: 768px)";
export const LG_QUERY = "(min-width: 1024px)";
// Wide enough for every secondary header action inline next to the title
// (`2xl`). With a schema loaded they need about 1,350 px, more with wider
// system fonts; at `lg` they ran over the title up to that width.
export const HEADER_ACTIONS_QUERY = "(min-width: 1536px)";
export const COARSE_POINTER_QUERY = "(pointer: coarse)";

export function matchesMediaQuery(query: string): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(query).matches;
}

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
        return () => {};
      }
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    [query],
  );
  const getSnapshot = useCallback(() => matchesMediaQuery(query), [query]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
