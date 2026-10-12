import { test, expect } from "@playwright/test";

// libxml2 compiles this schema; fractionDigits on an integer is not XSD.
const SCHEMA = `<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="Amount">
    <xs:restriction base="xs:integer">
      <xs:fractionDigits value="2"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:element name="Total" type="Amount"/>
</xs:schema>`;

test("a schema that breaks a rule of XSD is flagged, with a jump to the line", async ({ page }) => {
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles({
    name: "amount.xsd",
    mimeType: "application/xml",
    buffer: Buffer.from(SCHEMA),
  });
  await expect(page.locator(".react-flow")).toBeVisible();

  const check = page.getByTestId("schema-check");
  await expect(check).toContainText("breaks rules of XSD 1.0");
  await expect(check).toContainText("fractionDigits");

  await check.getByTitle("Open in the Text tab").click();
  await expect(page.locator(".cm-content")).toContainText("fractionDigits");
});
