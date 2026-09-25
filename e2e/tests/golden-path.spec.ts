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

test("the header title links back to a clean start page", async ({ page }) => {
  await page.goto("/fundsxml");
  await expect(page.getByRole("tab", { name: "FundsXML Releases" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // From an input tab: back to "/" with the default File tab.
  await page.getByRole("link", { name: "Online XSD Viewer" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("tab", { name: "File / ZIP" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // From a loaded schema with a selection hash: schema dropped, URL clean.
  await page.locator('input[type="file"]').setInputFiles(SIMPLE_XSD);
  await page.getByRole("button", { name: "Tree" }).click();
  await page.getByRole("treeitem").filter({ hasText: "Person" }).first().click();
  await expect(page).toHaveURL(/#\/id\//);

  await page.getByRole("link", { name: "Online XSD Viewer" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Load an XSD schema" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Load a different schema file" })).toHaveCount(0);
});

test("header shows the secondary actions inline while there is room for them", async ({ page }) => {
  // The split between inline buttons and the "More" menu is measured, not a
  // breakpoint: on the landing page at 1280 px only Search and the theme
  // toggle compete for space, so every secondary action — Sponsor included —
  // stays inline and there is no menu at all (it used to fold below 1536 px).
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  const banner = page.getByRole("banner");
  await expect(banner.getByRole("link", { name: "Support this project on GitHub Sponsors" })).toBeVisible();
  await expect(banner.getByRole("link", { name: "Source code on GitHub" })).toBeVisible();
  await expect(banner.getByRole("button", { name: "More actions" })).toHaveCount(0);
  const overflow = await banner.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

for (const width of [1024, 1280, 1440, 1600]) {
  test(`header actions never cover the title at ${width}px`, async ({ page }) => {
    // With a schema loaded every header action is present. Inline, they used
    // to run over the title from 1024 px up to about 1350 px, so a click on
    // "Online XSD Viewer" hit the "Load new" button instead (CI, 2026-09).
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/");
    await page.locator('input[type="file"]').setInputFiles(SIMPLE_XSD);
    const loadNew = page.getByRole("button", { name: "Load a different schema file" });
    await expect(loadNew).toBeVisible();
    const title = await page.getByRole("link", { name: "Online XSD Viewer" }).boundingBox();
    const actions = await loadNew.boundingBox();
    expect(title).not.toBeNull();
    expect(actions).not.toBeNull();
    expect(title!.x + title!.width).toBeLessThanOrEqual(actions!.x);
    const header = await page.getByRole("banner").evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(header).toBeLessThanOrEqual(0);
  });
}
