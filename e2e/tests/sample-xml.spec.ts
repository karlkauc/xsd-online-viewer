import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SIMPLE_XSD = resolve(__dirname, "../../backend/tests/fixtures/simple.xsd");

test("generate a sample XML document for the selected element", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(SIMPLE_XSD);

  await page.getByRole("button", { name: "Tree" }).click();
  await page.getByRole("treeitem").filter({ hasText: "Person" }).first().click();
  await page.getByRole("button", { name: "Generate sample XML" }).click();

  const dialog = page.getByRole("dialog", { name: "Sample XML for <Person>" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("pre")).toContainText("<tns:FirstName>string</tns:FirstName>");
  await expect(dialog.locator("pre")).not.toContainText("<tns:Age>");

  await dialog.getByRole("checkbox", { name: /Include optional/ }).check();
  await expect(dialog.locator("pre")).toContainText("<tns:Age>0</tns:Age>");

  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
});
