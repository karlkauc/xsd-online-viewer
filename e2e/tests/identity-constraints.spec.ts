import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES = resolve(__dirname, "../../backend/tests/fixtures");
const IDENTITY_XSD = resolve(FIXTURES, "identity_constraints.xsd");
const ID_IDREF_XSD = resolve(FIXTURES, "id_idref.xsd");

test("identity constraints: detail cards, tree glyph, centre table, and step navigation", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(IDENTITY_XSD);

  await page.getByRole("button", { name: "Tree" }).click();
  await page.getByRole("treeitem").filter({ hasText: "Library" }).first().click();

  // Detail panel (right column) — identified by the "Generate sample XML"
  // button that only DetailPanel renders, since IdentityConstraintsList's
  // heading/chips/step buttons are duplicated verbatim in the centre-pane
  // table (ConstraintPath/ReferButton are shared between both).
  const detailPanel = page.locator("aside").filter({ hasText: "Generate sample XML" });

  await expect(
    detailPanel.getByText("4 · xs:key / xs:keyref / xs:unique · display-only"),
  ).toBeVisible();
  await expect(detailPanel.getByText("key", { exact: true })).toHaveCount(1);
  await expect(detailPanel.getByText("keyref", { exact: true })).toHaveCount(2);
  await expect(detailPanel.getByText("unique", { exact: true })).toHaveCount(1);

  // Tree row glyph: a teal "⚿" span next to the label, aria-label lists the
  // constraints ("kind name, kind name, ...").
  const libraryRow = page.getByRole("treeitem").filter({ hasText: "Library" }).first();
  const glyph = libraryRow.locator(
    '[aria-label="key bookKey, unique uniqueTitle, keyref loanBookRef, keyref danglingRef"]',
  );
  await expect(glyph).toHaveText("⚿");

  // Centre pane (ContentModelView, Tree tab): "Identity constraints" table.
  await expect(page.getByRole("columnheader", { name: "Selector" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Field(s)" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Refers to" })).toBeVisible();
  await expect(page.getByRole("row", { name: /danglingRef/ })).toBeVisible();

  // Selector step navigation: "tns:Book" (bookKey's selector second step) is
  // a clickable button, titled "Go to <step>" — clicking it selects the Book
  // element. (The button's accessible name is its own visible step text, not
  // the tooltip title — a title only stands in for the accessible name when
  // there is no text content.)
  const goToBook = detailPanel.getByRole("button", { name: "tns:Book", exact: true }).first();
  await expect(goToBook).toHaveAttribute("title", "Go to tns:Book");
  await goToBook.click();
  await expect(detailPanel.getByText("tns:BookType")).toBeVisible();
  await expect(detailPanel.getByText("Identity constraints")).toHaveCount(0);

  // Back to Library: the resolved keyref "refers to" control selects the
  // key's host element (here, Library itself — bookKey is declared directly
  // on Library); the dangling one falls back to plain, titled text.
  await page.getByRole("treeitem").filter({ hasText: "Library" }).first().click();
  await expect(detailPanel.getByText("tns:noSuchKey")).toHaveAttribute(
    "title",
    "key not found in this schema",
  );
  await detailPanel.getByRole("button", { name: "⚿ bookKey →" }).click();
  await expect(page.getByRole("treeitem").filter({ hasText: "Library" }).first()).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // Diagram badge: teal "⚿ N" with a title listing every constraint.
  await page.getByRole("button", { name: "Diagram" }).click();
  const libraryNode = page.locator(".react-flow__node-element").filter({ hasText: "Library" }).first();
  const badge = libraryNode.locator(
    '[title="key bookKey, unique uniqueTitle, keyref loanBookRef, keyref danglingRef"]',
  );
  await expect(badge).toHaveText("⚿ 4");
});

test("ID/IDREF: role chip, candidate/usage sections, and diagram badges", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles(ID_IDREF_XSD);

  await page.getByRole("button", { name: "Tree" }).click();
  const detailPanel = page.locator("aside").filter({ hasText: "Generate sample XML" });

  // "DirectId" is a literal text prefix of "DirectIdref"/"DirectIdrefs", and
  // tree/diagram labels sit flush against sibling badge text in the DOM (no
  // whitespace node between them) — a \b-anchored regex can't tell them
  // apart, so match on the label's own exact text instead.
  const treeLabel = (name: string) =>
    page.getByRole("treeitem").filter({ has: page.getByText(name, { exact: true }) });
  const diagramNode = (name: string) =>
    page.locator(".react-flow__node-element").filter({ has: page.getByText(name, { exact: true }) });

  // xs:ID side: chip "ID", "Referenced by IDREF" usage list (12 IDREF/IDREFS
  // declarations anywhere in the schema — XSD never binds an IDREF to one ID).
  await treeLabel("DirectId").click();
  await expect(detailPanel.locator('span[title="xs:ID"]')).toHaveText("ID");
  await expect(
    detailPanel.getByRole("heading", { name: "Referenced by IDREF" }),
  ).toBeVisible();
  await expect(detailPanel.getByText("12 xs:IDREF/IDREFS declaration")).toBeVisible();
  await expect(detailPanel.getByText("DirectIdrefs")).toBeVisible();

  // xs:IDREF side: chip "IDREF", "ID reference" candidate cards (5 xs:ID
  // declarations total, under the 8-candidate cap so no "Show all" button).
  await treeLabel("DirectIdref").click();
  await expect(detailPanel.locator('span[title="xs:IDREF"]')).toHaveText("IDREF");
  await expect(detailPanel.getByRole("heading", { name: "ID reference" })).toBeVisible();
  await expect(detailPanel.getByText("5 xs:ID candidates")).toBeVisible();
  await expect(
    detailPanel.getByText("XML Schema does not bind an IDREF to a specific ID"),
  ).toBeVisible();
  await expect(detailPanel.getByRole("button", { name: "globalIdAttr" })).toBeVisible();
  await expect(detailPanel.getByRole("button", { name: /Show all/ })).toHaveCount(0);

  // Diagram badges: indigo "ID" (title xs:ID) / "⇢ ID" (title xs:IDREF).
  await page.getByRole("button", { name: "Diagram" }).click();
  await expect(diagramNode("DirectId").locator('[title="xs:ID"]')).toHaveText("ID");
  await expect(diagramNode("DirectIdref").locator('[title="xs:IDREF"]')).toHaveText("⇢ ID");
});
