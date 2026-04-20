import type { CompositorKind } from "../../lib/particles";

export const COMPOSITOR_GLYPH: Record<CompositorKind, string> = {
  sequence: "▦",
  choice: "◇",
  all: "≡",
};

export const GROUP_REF_GLYPH = "★";
export const WILDCARD_GLYPH = "*";
