import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SIMPLE_XSD = resolve(__dirname, "../../backend/tests/fixtures/simple.xsd");

test("upload XSD, navigate tree, switch tabs", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Online XSD Viewer" })).toBeVisible();

  // Upload the sample file.
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(SIMPLE_XSD);

  // Tree view shows Person (from the fixture).
  const person = page.getByRole("treeitem").filter({ hasText: "Person" }).first();
  await expect(person).toBeVisible();
  await person.click();

  // Detail panel shows Element info with the referenced type.
  await expect(page.getByRole("heading", { name: "Element" })).toBeVisible();
  await expect(page.getByText("tns:PersonType").first()).toBeVisible();

  // Diagram tab renders.
  await page.getByRole("button", { name: "Diagram" }).click();
  await expect(page.locator(".react-flow")).toBeVisible();

  // Text tab renders with the XSD source.
  await page.getByRole("button", { name: "Text" }).click();
  await expect(page.locator(".cm-content")).toContainText("PersonType");
});

test("search palette opens with Ctrl-K", async ({ page }) => {
  await page.goto("/");
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(SIMPLE_XSD);
  await page.keyboard.press("Control+k");
  const searchInput = page.getByPlaceholder("Search elements, types, attributes…");
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
