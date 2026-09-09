import { test, expect, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const IDENTITY_XSD = resolve(__dirname, "../../backend/tests/fixtures/identity_constraints.xsd");

// The React Flow camera is a CSS transform on the viewport layer; reading it
// is the cheapest way to tell whether the diagram moved.
async function viewportTransform(page: Page): Promise<string> {
  return page.locator(".react-flow__viewport").evaluate((el) => el.style.transform);
}

async function settledTransform(page: Page): Promise<string> {
  // fitView / setCenter animate for 250 ms; wait until two reads agree.
  let prev = await viewportTransform(page);
  for (let i = 0; i < 20; i++) {
    await page.waitForTimeout(150);
    const next = await viewportTransform(page);
    if (next === prev) return next;
    prev = next;
  }
  return prev;
}

test("diagram pans to a constraint step clicked in the detail pane", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(IDENTITY_XSD);

  // Diagram is the default tab; the tree (left column) stays visible on
  // desktop, so selecting Library there fills the detail pane while the
  // diagram is still mounted.
  const diagram = page.locator(".react-flow");
  await expect(diagram.locator(".react-flow__node-element").filter({ hasText: "Library" })).toBeVisible();
  await page.getByRole("treeitem").filter({ hasText: "Library" }).first().click();
  const detailPanel = page.locator("aside").filter({ hasText: "Generate sample XML" });
  const before = await settledTransform(page);

  // bookKey's selector "tns:Books/tns:Book": the second step points two
  // levels below Library, which is collapsed in the diagram right now.
  await detailPanel.getByRole("button", { name: "tns:Book", exact: true }).first().click();

  const bookNode = diagram
    .locator(".react-flow__node-element")
    .filter({ has: page.getByText("Book", { exact: true }) })
    .first();
  await expect(bookNode).toBeVisible();

  // The camera moved onto the revealed node…
  await expect.poll(() => settledTransform(page)).not.toBe(before);
  // …and the node sits fully inside the canvas.
  const canvas = (await diagram.boundingBox())!;
  const box = (await bookNode.boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(canvas.x);
  expect(box.y).toBeGreaterThanOrEqual(canvas.y);
  expect(box.x + box.width).toBeLessThanOrEqual(canvas.x + canvas.width);
  expect(box.y + box.height).toBeLessThanOrEqual(canvas.y + canvas.height);
});
