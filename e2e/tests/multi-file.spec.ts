import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES = resolve(__dirname, "../../backend/tests/fixtures");

// Built with Python's zipfile: schemas/library.xsd (includes types.xsd) and
// schemas/types.xsd, plus a README and a stray UTF-8 named schema.
const BUNDLE_B64 =
  "UEsDBBQAAAAIAFy3I10AAAAAAgAAAAAAAAAIAAAAc2NoZW1hcy8DAFBLAwQUAAAACABctyNdPBE9ll4AAABrAAAAEwAAAHNjaGVtYXMvbGlicmFyeS54c2SzqSi2Kk7OSM1NVKjIzckrtqootlXKKCkpsNLXLy8v1ys31ssvStc3MjAw1I/w9QkGK1WyswFqy8xLzilNSVWAaPfJT04syczPs1UqqSxILdarKE5R0rez0YebbwcAUEsDBBQAAAAIAFy3I11GbK/lNwAAADgAAAARAAAAc2NoZW1hcy90eXBlcy54c2SzqSi2Kk7OSM1NVKjIzckrtqootlXKKCkpsNLXLy8v1ys31ssvStc3MjAw1I/w9QkGK1XStwMAUEsDBBQAAAAIAFy3I12sKpPYBAAAAAIAAAAKAAAAUkVBRE1FLnR4dMvIBABQSwMEFAAACAgAXLcjXYVkpvYOAAAADAAAAA0AAADDvG7Dr2NvZGUueHNks6kotipOzkjNTdS3AwBQSwECFAMUAAAACABctyNdAAAAAAIAAAAAAAAACAAAAAAAAAAAABAA/UEAAAAAc2NoZW1hcy9QSwECFAMUAAAACABctyNdPBE9ll4AAABrAAAAEwAAAAAAAAAAAAAAgAEoAAAAc2NoZW1hcy9saWJyYXJ5LnhzZFBLAQIUAxQAAAAIAFy3I11GbK/lNwAAADgAAAARAAAAAAAAAAAAAACAAbcAAABzY2hlbWFzL3R5cGVzLnhzZFBLAQIUAxQAAAAIAFy3I12sKpPYBAAAAAIAAAAKAAAAAAAAAAAAAACAAR0BAABSRUFETUUudHh0UEsBAhQDFAAACAgAXLcjXYVkpvYOAAAADAAAAA0AAAAAAAAAAAAAAIABSQEAAMO8bsOvY29kZS54c2RQSwUGAAAAAAUABQApAQAAggEAAAAA";

test("two loose files: pick the main schema, then load", async ({ page }) => {
  await page.goto("/");
  await page
    .locator('input[type="file"]')
    .setInputFiles([resolve(FIXTURES, "types.xsd"), resolve(FIXTURES, "library.xsd")]);

  const select = page.getByLabel("Main schema");
  await expect(select).toHaveValue("library.xsd");
  await page.getByRole("button", { name: "Load" }).click();

  await expect(page.locator(".react-flow__node-element").filter({ hasText: "Library" }).first()).toBeVisible();
  // Both files are part of the model: the Text tab offers one button per file.
  await page.getByRole("button", { name: "Text" }).click();
  await expect(page.getByRole("button", { name: "types.xsd" })).toBeVisible();
});

test("ZIP with several schemas: the picker lists the entries", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles({
    name: "bundle.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(BUNDLE_B64, "base64"),
  });

  const select = page.getByLabel("Main schema");
  await expect(select).toHaveValue("ünïcode.xsd");
  await expect(select.locator("option")).toHaveText(["schemas/library.xsd", "schemas/types.xsd", "ünïcode.xsd"]);
  await select.selectOption("schemas/library.xsd");
  await page.getByRole("button", { name: "Load" }).click();

  await expect(page.getByRole("button", { name: "Load a different schema file" })).toBeVisible();
});
