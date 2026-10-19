import { test, expect } from "@playwright/test";

const XSD = `<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="Order"><xs:complexType><xs:sequence>
    <xs:element name="Id" type="xs:string"/>
    <xs:element name="Line" maxOccurs="unbounded" type="xs:string"/>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>`;

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("a FundsXML release page lists its changes and opens the viewer", async ({ page }) => {
    await page.goto("/fundsxml/releases");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("FundsXML schema releases");
    await page.getByRole("link", { name: "FundsXML 4.2.11" }).click();
    await expect(page.getByRole("heading", { name: /Changes since FundsXML 4\.2\.10/ })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open FundsXML 4.2.11 in the viewer" })).toHaveAttribute(
      "href",
      "/fundsxml?release=4.2.11&file=FundsXML.xsd",
    );
  });

  test("the home shell carries the FAQ and the family links", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Can it read schemas that import or include other files?")).toBeVisible();
    await expect(page.getByRole("link", { name: "Online OData Viewer" })).toBeVisible();
  });
});

test("the embed view can be framed and shows the diagram", async ({ page, request, baseURL }) => {
  // Parse a schema through the real backend, then answer the iframe's URL load with it (offline).
  const parsed = await (await request.post("/api/schema/text", { data: { content: XSD, filename: "order.xsd" } })).json();
  await page.route("**/api/schema/url", (route) => route.fulfill({ json: parsed }));
  // A documentation page that frames the embed. Chromium's local-network checks refuse a
  // cross-origin frame of a loopback address in tests, so the host page shares the origin —
  // still enough to prove that neither X-Frame-Options DENY nor frame-ancestors 'none' is sent
  // (both block same-origin framing too); the headers themselves are covered in the backend tests.
  const host = new URL("/docs-host-page", baseURL ?? "http://127.0.0.1:8080");
  await page.route(host.href, (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<iframe id="e" src="${baseURL}/embed?src=https://example.com/order.xsd" width="900" height="500"></iframe>`,
    }),
  );
  await page.goto(host.href);
  const frame = page.frameLocator("#e");
  await expect(frame.getByText("order.xsd")).toBeVisible();
  await expect(frame.getByRole("link", { name: "Open in XSD Viewer ↗" })).toHaveAttribute("href", /\/url\?src=https%3A%2F%2Fexample\.com%2Forder\.xsd/);
  await expect(frame.locator(".react-flow__node").first()).toBeVisible({ timeout: 30_000 });
});

test("a blocked request explains itself instead of a bare HTTP 403", async ({ page }) => {
  await page.route("**/api/schema/text", (route) => route.fulfill({ status: 403, body: "<html>Access denied</html>", contentType: "text/html" }));
  await page.goto("/paste");
  await page.locator("textarea").first().fill(XSD);
  await page.getByRole("button", { name: /^(Parse|Load|View|Show)/ }).first().click();
  await expect(page.getByText(/blocked before it reached the XSD Viewer/)).toBeVisible();
});

test("the FundsXML releases tab and the landing page link to the release pages", async ({ page }) => {
  await page.route("**/api/fundsxml/releases", (route) =>
    route.fulfill({
      json: {
        releases: [
          { tag_name: "4.2.11", name: "4.2.11", published_at: "2026-06-23T00:00:00Z", prerelease: false, html_url: "", assets: [{ filename: "FundsXML.xsd", download_url: "", size: 1, content_type: null }] },
          { tag_name: "9.9.9", name: "9.9.9", published_at: "2026-10-01T00:00:00Z", prerelease: false, html_url: "", assets: [{ filename: "FundsXML.xsd", download_url: "", size: 1, content_type: null }] },
        ],
        cached_at: "2026-10-19T00:00:00Z",
        ttl_seconds: 600,
      },
    }),
  );
  await page.goto("/fundsxml");
  await expect(page.getByRole("link", { name: "What changed in each release →" })).toHaveAttribute("href", "/fundsxml/releases");
  // A release with a generated page gets a link; one newer than the last page build does not.
  await expect(page.getByRole("link", { name: "changes" })).toHaveCount(1);
  await expect(page.getByRole("link", { name: "changes" })).toHaveAttribute("href", "/fundsxml/4.2.11");
  await page.goto("/");
  await page.getByRole("link", { name: "All guides and resources →" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Guides and resources" })).toBeVisible();
  await expect(page.getByRole("link", { name: /FundsXML schema releases/ })).toBeVisible();
});
