import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HeaderActions, type HeaderAction } from "../src/components/HeaderActions";

function actions(onAbout = vi.fn()): HeaderAction[] {
  return [
    { key: "github", label: "GitHub", title: "Source code on GitHub", ariaLabel: "Source code on GitHub", href: "https://example.com", external: true },
    { key: "about", label: "ℹ️ About", title: "About this app", ariaLabel: "About this app", onClick: onAbout },
  ];
}

describe("HeaderActions", () => {
  afterEach(() => cleanup());

  it("renders every action inline when inline=true and shows no menu button", () => {
    render(<HeaderActions actions={actions()} inline />);
    expect(screen.getByRole("link", { name: "Source code on GitHub" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About this app" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More actions" })).not.toBeInTheDocument();
  });

  it("hides the actions behind a More menu when inline=false", () => {
    render(<HeaderActions actions={actions()} inline={false} />);
    expect(screen.getByRole("button", { name: "More actions" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.queryByText("About this app")).not.toBeInTheDocument();
  });

  it("opens the menu on click, runs the item and closes again", async () => {
    const onAbout = vi.fn();
    render(<HeaderActions actions={actions(onAbout)} inline={false} />);
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    const menu = screen.getByRole("menu");
    expect(menu).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Source code on GitHub" })).toHaveAttribute("href", "https://example.com");
    await userEvent.click(screen.getByRole("menuitem", { name: "About this app" }));
    expect(onAbout).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "More actions" })).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the menu with Escape", async () => {
    render(<HeaderActions actions={actions()} inline={false} />);
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("HeaderActions menu-only entries", () => {
  it("keeps menuOnly actions in a More menu even when inline", async () => {
    const { render, screen, cleanup } = await import("@testing-library/react");
    const { default: userEvent } = await import("@testing-library/user-event");
    const { HeaderActions } = await import("../src/components/HeaderActions");
    render(
      <HeaderActions
        inline
        actions={[
          { key: "a", label: "Inline one", title: "Inline one", href: "/a" },
          { key: "b", label: "Menu only", title: "Menu only", href: "/b", menuOnly: true },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "Inline one" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Menu only" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menuitem", { name: "Menu only" })).toHaveAttribute("href", "/b");
    cleanup();
  });
});
