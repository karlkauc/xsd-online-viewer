import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import * as client from "../src/api/client";
import { Uploader } from "../src/components/Uploader";
import * as handoff from "../src/lib/xmlViewerHandoff";

describe("Uploader with pasted text", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("hands a pasted XML document to the XML viewer, content included", async () => {
    vi.spyOn(client, "uploadSchemaText").mockRejectedValue(
      new ApiError(
        "schema.xsd: root element is <games>, not <xs:schema> — this looks like an XML document, not an XML Schema",
        400,
      ),
    );
    vi.spyOn(handoff, "handoffSupported").mockReturnValue(true);
    const open = vi.spyOn(handoff, "openInXmlViewer").mockResolvedValue(true);

    render(<Uploader />);
    await userEvent.click(screen.getByRole("tab", { name: "Paste" }));
    fireEvent.change(screen.getByPlaceholderText("<xs:schema …>"), { target: { value: "<games/>" } });
    await userEvent.click(screen.getByRole("button", { name: "Parse" }));
    await userEvent.click(await screen.findByRole("button", { name: /Open in XML Viewer/ }));

    const sent = open.mock.calls[0][0];
    expect(sent.name).toBe("pasted.xml");
    await expect(sent.text()).resolves.toBe("<games/>");
  });
});
