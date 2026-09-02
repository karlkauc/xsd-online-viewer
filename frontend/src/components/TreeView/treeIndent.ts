const INDENT_PX = 14;
const COMPACT_INDENT_PX = 10;
const BASE_PX = 6;

/** Left padding of a tree row. Compact viewports (phones) indent less so deep
 *  nesting leaves room for the node name. */
export function treeIndentPx(depth: number, compact: boolean): number {
  return depth * (compact ? COMPACT_INDENT_PX : INDENT_PX) + BASE_PX;
}
