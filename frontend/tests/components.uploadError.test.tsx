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

  it("explains binary .xsd uploads, including cross-stitch patterns", () => {
    render(
      <UploadError message="uyutnye_tykvy.xsd: not an XML file — it starts with binary data (b'\\x10\\x05'), not text" />,
    );
    expect(screen.getByText(/This is a binary file, not a schema/)).toBeInTheDocument();
    expect(screen.getByText(/cross-stitch patterns from/)).toBeInTheDocument();
  });

  it("names Pattern Maker cross-stitch patterns as their own kind", () => {
    render(
      <UploadError message="Idillia.xsd: not an XML file — it looks like a Pattern Maker cross-stitch pattern (the .xsd extension is shared, the format is unrelated to XML Schema), i.e. binary data, not text" />,
    );
    expect(screen.getByText(/This is a cross-stitch pattern, not an XML Schema/)).toBeInTheDocument();
    expect(screen.getByText(/Pattern Maker \(HobbyWare\)/)).toBeInTheDocument();
    expect(screen.queryByText(/This is a binary file, not a schema/)).not.toBeInTheDocument();
  });

  it("explains copies of the browser's rendered XML view", () => {
    render(
      <UploadError message="schema.xsd: this looks like a copy of the browser's rendered XML view (fold markers or the 'This XML file does not appear to have any style information' banner), not the file itself. Open the file with 'View page source' (Ctrl+U) or download it, then paste or upload the raw XML" />,
    );
    expect(screen.getByText(/This is the browser's rendered view, not the file/)).toBeInTheDocument();
    expect(screen.getByText(/download it \(Ctrl\+S\)/)).toBeInTheDocument();
    expect(screen.queryByText(/The file is not XML/)).not.toBeInTheDocument();
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
