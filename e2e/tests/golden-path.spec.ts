import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SIMPLE_XSD = resolve(__dirname, "../../backend/tests/fixtures/simple.xsd");

test("upload XSD, switch tabs, and inspect the tree detail", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Online XSD Viewer" })).toBeVisible();

  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(SIMPLE_XSD);

  // Default tab is Diagram — the React Flow surface should appear immediately.
  await expect(page.locator(".react-flow")).toBeVisible();
  await expect(
    page.locator(".react-flow__node-element").filter({ hasText: "Person" }).first(),
  ).toBeVisible();

  // Switch to the Tree tab — sidebar appears with the element list.
  await page.getByRole("button", { name: "Tree" }).click();
  const person = page.getByRole("treeitem").filter({ hasText: "Person" }).first();
  await expect(person).toBeVisible();
  await person.click();

  await expect(page.getByRole("heading", { name: "Element" })).toBeVisible();
  await expect(page.getByText("tns:PersonType").first()).toBeVisible();

  // Text tab renders the XSD source with syntax highlighting.
  await page.getByRole("button", { name: "Text" }).click();
  await expect(page.locator(".cm-content")).toContainText("PersonType");
});

test("search palette opens with Ctrl-K", async ({ page }) => {
  await page.goto("/");
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(SIMPLE_XSD);
  await page.keyboard.press("Control+k");
  const searchInput = page.getByPlaceholder("Search names, documentation, enumeration values…");
  await expect(searchInput).toBeVisible();
  await searchInput.fill("Age");
  await expect(page.getByText("AgeType").first()).toBeVisible();
  // Sanity check that there is nothing strange about the fixture.
  const content = readFileSync(SIMPLE_XSD, "utf-8");
  expect(content).toContain("AgeType");
});

test("theme toggle persists across reloads", async ({ page }) => {
  await page.goto("/");
  const toggle = page.getByRole("button", { name: /Switch to (dark|light) theme/ });
  const before = await page.locator("html").evaluate((el) => el.classList.contains("dark"));
  await toggle.click();
  const after = await page.locator("html").evaluate((el) => el.classList.contains("dark"));
  expect(after).not.toBe(before);
  await page.reload();
  const afterReload = await page.locator("html").evaluate((el) => el.classList.contains("dark"));
  expect(afterReload).toBe(after);
});
