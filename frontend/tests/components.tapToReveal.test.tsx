import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TapToReveal } from "../src/components/TapToReveal";

describe("TapToReveal", () => {
  afterEach(() => cleanup());

  it("shows the summary and reveals the full text on click", async () => {
    render(<TapToReveal summary="First line" details={"First line\nSecond line"} />);
    const button = screen.getByRole("button", { name: /First line/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/Second line/)).not.toBeInTheDocument();
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Second line/)).toBeInTheDocument();
  });

  it("renders plain text when there is nothing more to reveal", () => {
    render(<TapToReveal summary="Only line" details="Only line" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Only line")).toBeInTheDocument();
  });

  it("keeps the click from bubbling to the row or node behind it", async () => {
    const onRowClick = vi.fn();
    render(
      <div onClick={onRowClick}>
        <TapToReveal summary="deeper sub-tree" details="a › b › c" />
      </div>,
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onRowClick).not.toHaveBeenCalled();
    expect(screen.getByText("a › b › c")).toBeInTheDocument();
  });
});
