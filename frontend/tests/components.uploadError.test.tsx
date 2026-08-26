import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UploadError } from "../src/components/UploadError";

afterEach(() => cleanup());

describe("UploadError", () => {
  it("links XML documents to the sister project", () => {
    render(<UploadError message="db.xml: root element is <games>, not <xs:schema>" />);
    expect(screen.getByText(/This is an XML document/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Open XML Viewer/ });
    expect(link).toHaveAttribute("href", "https://www.xml-viewer.online/");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("offers 'Upload anyway' only for client-side rejections", async () => {
    const anyway = vi.fn();
    const { rerender } = render(<UploadError message="x.xml: looks like an XML document" onUploadAnyway={anyway} />);
    await userEvent.click(screen.getByRole("button", { name: /Upload anyway/ }));
    expect(anyway).toHaveBeenCalledOnce();
    rerender(<UploadError message="x.xsd: not an XML file" />);
    expect(screen.queryByRole("button", { name: /Upload anyway/ })).not.toBeInTheDocument();
  });

  it("opens the feedback dialog with the error attached", async () => {
    const listener = vi.fn();
    window.addEventListener("xsdv:open-feedback", listener);
    render(<UploadError message="boom" schemaName="s.xsd" />);
    await userEvent.click(screen.getByRole("button", { name: /Send feedback/ }));
    expect(listener).toHaveBeenCalledOnce();
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual({ errorDetail: "boom", schemaName: "s.xsd" });
    window.removeEventListener("xsdv:open-feedback", listener);
  });
});
