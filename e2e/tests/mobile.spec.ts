import { test, expect, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SIMPLE_XSD = resolve(__dirname, "../../backend/tests/fixtures/simple.xsd");

async function expectNoHorizontalOverflow(page: Page) {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth, "page must not scroll horizontally").toBeLessThanOrEqual(clientWidth);
}

async function loadSimpleSchema(page: Page) {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(SIMPLE_XSD);
  await expect(page.getByRole("button", { name: "Load a different schema file" })).toBeVisible();
}

test.describe("phone", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== "phone", "phone project only");
  });

  test("landing page fits the viewport and folds secondary header actions into a menu", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Online XSD Viewer" })).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await expect(page.getByRole("button", { name: "More actions" })).toBeVisible();
    await expect(page.getByRole("button", { name: "About this app" })).toBeHidden();
    await page.getByRole("button", { name: "More actions" }).click();
    await expect(page.getByRole("menuitem", { name: "About this app" })).toBeVisible();
  });

  test("bottom nav walks structure → view → details without overflow", async ({ page }) => {
    await loadSimpleSchema(page);
    await expectNoHorizontalOverflow(page);

    const nav = page.getByRole("navigation", { name: "Panes" });
    await expect(nav).toBeVisible();

    // The View pane (diagram) shows first; the structure tree is one tap away.
    await expect(page.locator(".react-flow")).toBeVisible();
    await nav.getByRole("button", { name: "Structure" }).click();
    await expect(page.locator(".react-flow")).toBeHidden();
    const person = page.getByRole("treeitem").filter({ hasText: "Person" }).first();
    await expect(person).toBeVisible();
    await person.click();

    // Selecting jumps back to the View pane; the compact toolbar keeps export behind a menu.
    await expect(page.locator(".react-flow")).toBeVisible();
    await expect(page.getByRole("button", { name: "Export SVG" })).toBeHidden();
    await page.getByRole("button", { name: "Export" }).click();
    await expect(page.getByRole("menuitem", { name: "Export SVG" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expectNoHorizontalOverflow(page);

    await nav.getByRole("button", { name: "Details" }).click();
    const details = page
      .getByRole("complementary")
      .filter({ has: page.getByRole("heading", { name: "Element" }) });
    await expect(details.getByRole("heading", { name: "Element" })).toBeVisible();
    await expect(details.getByText("tns:PersonType").first()).toBeVisible();
  });
});

test.describe("tablet", () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== "tablet", "tablet project only");
  });

  test("shows structure and view side by side with details in a drawer", async ({ page }) => {
    await loadSimpleSchema(page);
    await expectNoHorizontalOverflow(page);

    // Two columns: tree and diagram visible at once, no bottom nav.
    await expect(page.getByRole("navigation", { name: "Panes" })).toBeHidden();
    await page.getByRole("button", { name: "Tree" }).click();
    const person = page.getByRole("treeitem").filter({ hasText: "Person" }).first();
    await expect(person).toBeVisible();
    await person.click();
    await expect(page.getByRole("heading", { name: "Element" })).toBeHidden();

    await page.getByRole("button", { name: "Show details" }).click();
    const drawer = page
      .getByRole("complementary")
      .filter({ has: page.getByRole("heading", { name: "Element" }) });
    await expect(drawer.getByRole("heading", { name: "Element" })).toBeVisible();
    await expect(drawer.getByText("tns:PersonType").first()).toBeVisible();
    await page.getByRole("button", { name: "Close details" }).click();
    await expect(page.getByRole("heading", { name: "Element" })).toBeHidden();
    await expectNoHorizontalOverflow(page);
  });
});
