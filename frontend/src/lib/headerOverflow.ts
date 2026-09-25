/**
 * How many leading actions fit inline. Every inline control costs its own
 * width plus one flex gap; when not everything fits, the "More" button must
 * fit too, so its width (plus a gap) is reserved before the actions are
 * counted.
 */
export function countInlineActions(
  widths: number[],
  menuWidth: number,
  gap: number,
  available: number,
): number {
  const all = widths.reduce((sum, w) => sum + w + gap, 0);
  if (all <= available) return widths.length;
  let used = menuWidth + gap;
  let count = 0;
  for (const w of widths) {
    if (used + w + gap > available) break;
    used += w + gap;
    count += 1;
  }
  return count;
}
