import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HeaderActions, type HeaderAction } from "../src/components/HeaderActions";
import { countInlineActions } from "../src/lib/headerOverflow";

function actions(onAbout = vi.fn()): HeaderAction[] {
  return [
    { key: "github", label: "GitHub", title: "Source code on GitHub", ariaLabel: "Source code on GitHub", href: "https://example.com", external: true },
    { key: "sponsor", label: "♥ Support ↗", title: "Sponsor", ariaLabel: "Support this project", href: "https://example.com/sponsor", external: true },
    { key: "about", label: "ℹ️ About", title: "About this app", ariaLabel: "About this app", onClick: onAbout },
  ];
}

describe("countInlineActions", () => {
  it("keeps every action inline when they all fit without a menu", () => {
    expect(countInlineActions([100, 100, 100], 40, 8, 324)).toBe(3);
    expect(countInlineActions([], 40, 8, 0)).toBe(0);
  });

  it("folds the trailing actions into the menu and reserves room for its button", () => {
    // 3 × 108 = 324 does not fit; 2 × 108 + (40 + 8) = 264 does.
    expect(countInlineActions([100, 100, 100], 40, 8, 300)).toBe(2);
    // 1 × 108 + 48 = 156 fits, 2 × 108 + 48 = 264 does not.
    expect(countInlineActions([100, 100, 100], 40, 8, 200)).toBe(1);
  });

  it("never lets the menu button itself overflow", () => {
    expect(countInlineActions([100, 100, 100], 40, 8, 100)).toBe(0);
    expect(countInlineActions([100], 40, 8, 0)).toBe(0);
  });
});

/**
 * jsdom has no layout, so give it one: the header is `headerWidth` px wide,
 * every `.btn` in the measuring probe is 100 px, the menu button is 40 px,
 * gaps are 0 (jsdom reports no computed `column-gap`).
 */
function fakeLayout(headerWidth: number) {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const width = this.classList.contains("btn") ? (this.textContent === "⋯" ? 40 : 100) : 0;
    return { width, height: 0, x: 0, y: 0, top: 0, left: 0, right: width, bottom: 0, toJSON: () => ({}) } as DOMRect;
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get(this: HTMLElement) {
      return this.tagName === "HEADER" ? headerWidth : 0;
    },
  });
}

function renderInHeader(items: HeaderAction[]) {
  return render(
    <header>
      <div>
        <h1>Title</h1>
      </div>
      <div>
        <HeaderActions actions={items} />
      </div>
    </header>,
  );
}

describe("HeaderActions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    // @ts-expect-error restore jsdom's own (always 0) clientWidth
    delete HTMLElement.prototype.clientWidth;
  });

  it("renders every action inline when the header has room for all of them", () => {
    fakeLayout(300);
    renderInHeader(actions());
    expect(screen.getByRole("link", { name: "Source code on GitHub" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Support this project" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About this app" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More actions" })).not.toBeInTheDocument();
  });

  it("keeps as many leading actions inline as fit and folds only the rest into the menu", async () => {
    fakeLayout(260); // 2 × 100 + 40 fits, 3 × 100 does not
    renderInHeader(actions());
    expect(screen.getByRole("link", { name: "Source code on GitHub" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Support this project" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "About this app" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menuitem", { name: "About this app" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Source code on GitHub" })).not.toBeInTheDocument();
  });

  it("hides every action behind the More menu when nothing fits", () => {
    fakeLayout(100);
    renderInHeader(actions());
    expect(screen.getByRole("button", { name: "More actions" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Source code on GitHub" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "About this app" })).not.toBeInTheDocument();
  });

  it("opens the menu on click, runs the item and closes again", async () => {
    fakeLayout(100);
    const onAbout = vi.fn();
    renderInHeader(actions(onAbout));
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
    fakeLayout(100);
    renderInHeader(actions());
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("renders inline when there is no header to measure against (plain embedding)", () => {
    render(<HeaderActions actions={actions()} />);
    expect(screen.getByRole("button", { name: "About this app" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "More actions" })).not.toBeInTheDocument();
  });
});
