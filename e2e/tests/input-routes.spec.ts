import { test, expect } from "@playwright/test";

test("/fundsxml opens the FundsXML Releases tab", async ({ page }) => {
  await page.goto("/fundsxml");

  await expect(page.getByRole("tab", { name: "FundsXML Releases" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  // The releases panel, not the file dropzone, is shown.
  await expect(
    page.getByRole("link", { name: "fundsxml/schema" }),
  ).toBeVisible();
});

test("clicking an input tab updates the URL, and back/forward switches tabs", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("tab", { name: "File / ZIP" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.getByRole("tab", { name: "FundsXML Releases" }).click();
  await expect(page).toHaveURL(/\/fundsxml$/);

  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("tab", { name: "File / ZIP" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});
