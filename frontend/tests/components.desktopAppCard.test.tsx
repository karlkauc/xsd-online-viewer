import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DesktopAppCard } from "../src/components/DesktopAppCard";
import { FREEXMLTOOLKIT_DOWNLOAD_GO, FREEXMLTOOLKIT_GO } from "../src/lib/links";

afterEach(cleanup);

describe("DesktopAppCard", () => {
  it("renders the landing card with counted, new-tab links", () => {
    render(<DesktopAppCard bullets={["One", "Two", "Three"]} />);
    expect(screen.getByRole("complementary", { name: /FreeXmlToolkit/ })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    const download = screen.getByRole("link", { name: "Download" });
    expect(download).toHaveAttribute("href", FREEXMLTOOLKIT_DOWNLOAD_GO);
    expect(download).toHaveAttribute("target", "_blank");
    expect(download).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: /Learn more/ })).toHaveAttribute("href", FREEXMLTOOLKIT_GO);
    expect(screen.getByText(/Apache 2.0/)).toBeInTheDocument();
  });

  it("renders the inline tip as one sentence with a link", () => {
    render(<DesktopAppCard variant="inline">Do more with</DesktopAppCard>);
    expect(screen.getByText(/Do more with/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "FreeXmlToolkit ↗" })).toHaveAttribute("href", FREEXMLTOOLKIT_GO);
    expect(screen.queryByRole("link", { name: "Download" })).not.toBeInTheDocument();
  });
});
