// One-off Playwright script that records a walkthrough of the SPA against
// the local sandbox (http://127.0.0.1:8091) and writes a WebM video to
// docs/media/_raw/. A companion shell script converts that to GIF via ffmpeg.
//
// Run from the repo root:
//   node scripts/record_demo.mjs overview
//   node scripts/record_demo.mjs fundsxml
//
// Requires Playwright (already installed under e2e/node_modules).

import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
// Reuse the playwright install under e2e/ — avoids bloating the root with deps.
const { chromium } = require("../e2e/node_modules/playwright");
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { mkdirSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const OUT_DIR = resolve(ROOT, "docs/media/_raw");
mkdirSync(OUT_DIR, { recursive: true });

const BASE = process.env.VIEWER_URL ?? "http://127.0.0.1:8091";
const VIEWPORT = { width: 1280, height: 720 };

const scene = process.argv[2] ?? "overview";

async function pause(page, ms) {
  await page.waitForTimeout(ms);
}

async function moveTo(page, locator, opts = {}) {
  // Slow, visible mouse motion so the recorded GIF reads as a walkthrough.
  const box = await locator.boundingBox();
  if (!box) throw new Error("element has no bounding box");
  const target = {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  };
  await page.mouse.move(target.x, target.y, { steps: opts.steps ?? 18 });
  await pause(page, opts.hold ?? 250);
}

async function recordOverview(page) {
  await page.goto(BASE);
  await page.waitForLoadState("networkidle");
  await pause(page, 700);

  // Upload events.xsd via the file input.
  const sample = resolve(ROOT, "samples/xsd-1.1/events.xsd");
  await page.locator('input[type="file"]').setInputFiles(sample);
  await page.waitForSelector(".react-flow__node-element", { timeout: 15_000 });
  await pause(page, 1200);

  // Linger on Diagram — click a node so the right panel populates.
  const eventNode = page
    .locator(".react-flow__node-element")
    .filter({ hasText: "Event" })
    .first();
  await moveTo(page, eventNode);
  await eventNode.click();
  await pause(page, 1200);

  // Switch to Tree.
  const treeTab = page.getByRole("button", { name: "Tree", exact: true });
  await moveTo(page, treeTab);
  await treeTab.click();
  await pause(page, 800);

  const tiEvent = page.getByRole("treeitem").filter({ hasText: "Event" }).first();
  await moveTo(page, tiEvent);
  await tiEvent.click();
  await pause(page, 1000);

  // Switch to Text.
  const textTab = page.getByRole("button", { name: "Text", exact: true });
  await moveTo(page, textTab);
  await textTab.click();
  await pause(page, 1200);
  // Show a scroll, so source feels alive.
  await page.mouse.wheel(0, 300);
  await pause(page, 900);

  // Search palette.
  await page.keyboard.press("Control+k");
  await pause(page, 500);
  const search = page.getByPlaceholder("Search elements, types, attributes…");
  await search.type("Payload", { delay: 90 });
  await pause(page, 1200);
  await page.keyboard.press("Escape");
  await pause(page, 600);
}

async function recordFundsXml(page) {
  await page.goto(BASE);
  await page.waitForLoadState("networkidle");
  await pause(page, 600);

  const releasesTab = page.getByRole("tab", { name: "FundsXML Releases" });
  await moveTo(page, releasesTab);
  await releasesTab.click();

  // Wait for the releases table.
  await page
    .locator("table")
    .first()
    .waitFor({ state: "visible", timeout: 20_000 });
  await pause(page, 1500);

  const firstRow = page.locator("table tbody tr").first();
  await moveTo(page, firstRow);
  await firstRow.click();

  await page.waitForSelector(".react-flow__node-element", { timeout: 60_000 });
  await pause(page, 1500);
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: VIEWPORT,
  recordVideo: {
    dir: OUT_DIR,
    size: VIEWPORT,
  },
  deviceScaleFactor: 1,
});
const page = await context.newPage();

try {
  if (scene === "overview") {
    await recordOverview(page);
  } else if (scene === "fundsxml") {
    await recordFundsXml(page);
  } else {
    throw new Error(`Unknown scene: ${scene}`);
  }
} finally {
  await page.close();
  await context.close();
  await browser.close();
}

console.log(`done: ${scene}`);
