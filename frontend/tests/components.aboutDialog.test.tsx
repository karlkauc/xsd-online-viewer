import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AboutDialog, GITHUB_REPO_URL, openAbout } from "../src/components/AboutDialog";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AboutDialog", () => {
  it("is closed until openAbout() fires and shows the backend version", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "ok", version: "0.2.0" }) });
    render(<AboutDialog />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    act(() => openAbout());
    expect(screen.getByRole("dialog", { name: "Online XSD Viewer" })).toBeInTheDocument();
    expect(await screen.findByText("Version 0.2.0")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/health");
    const repo = screen.getByRole("link", { name: /Source code on GitHub/ });
    expect(repo).toHaveAttribute("href", GITHUB_REPO_URL);
    expect(repo).toHaveAttribute("target", "_blank");
  });

  it("degrades gracefully when the health endpoint fails and closes on Escape", async () => {
    fetchMock.mockRejectedValue(new Error("offline"));
    render(<AboutDialog />);
    act(() => openAbout());
    expect(await screen.findByText("Version unavailable")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("links to the FreeXmlToolkit desktop app", () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "ok", version: "x" }) });
    render(<AboutDialog />);
    act(() => openAbout());
    expect(screen.getByRole("link", { name: "FreeXmlToolkit" })).toHaveAttribute("href", "/go/freexmltoolkit");
  });

  it("explains the kind badges with a legend", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "ok", version: "x" }) });
    render(<AboutDialog />);
    act(() => openAbout());
    const legend = screen.getByRole("list", { name: "Kind badges" });
    expect(legend).toHaveTextContent("complexType");
    expect(legend).toHaveTextContent("attributeGroup");
  });

  it("hands over to the feedback dialog", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "ok", version: "x" }) });
    const onFeedback = vi.fn();
    window.addEventListener("xsdv:open-feedback", onFeedback);
    render(<AboutDialog />);
    act(() => openAbout());
    await userEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    expect(onFeedback).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    window.removeEventListener("xsdv:open-feedback", onFeedback);
  });
});
