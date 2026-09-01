import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SIMPLE_XSD = resolve(__dirname, "../../backend/tests/fixtures/simple.xsd");

// html-to-image deep-clones <svg> subtrees without inlining computed styles on
// their descendants, so the exported image carries no stylesheet — every edge
// stroke has to travel with the <path> as an inline style attribute.
test("exported SVG keeps the edge connector lines", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(SIMPLE_XSD);
  await expect(page.locator(".react-flow")).toBeVisible();

  await page.getByRole("button", { name: "Expand all" }).click();
  await expect(page.locator(".react-flow__edge-path").first()).toBeVisible();

  // Capture the data URL the download anchor would open instead of writing a file.
  const svg = await page.evaluate(async () => {
    const captured = new Promise<string>((resolve) => {
      const orig = HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click = function patched(this: HTMLAnchorElement) {
        if (this.download) {
          HTMLAnchorElement.prototype.click = orig;
          resolve(this.href);
          return;
        }
        return orig.call(this);
      };
    });
    const button = Array.from(document.querySelectorAll("button")).find((b) =>
      /export svg/i.test(b.textContent ?? ""),
    );
    button?.click();
    const href = await captured;
    return decodeURIComponent(href.replace(/^data:image\/svg\+xml;charset=utf-8,/, ""));
  });

  const edgePaths = svg.match(/<path[^>]*class="react-flow__edge-path"[^>]*>/g) ?? [];
  expect(edgePaths.length).toBeGreaterThan(0);
  for (const path of edgePaths) {
    expect(path).toMatch(/style="[^"]*stroke:\s*(?!none)[^;"]+/);
  }
});
