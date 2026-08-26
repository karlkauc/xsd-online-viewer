import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FeedbackDialog } from "../src/components/FeedbackDialog";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function open(detail?: object) {
  act(() => {
    window.dispatchEvent(new CustomEvent("xsdv:open-feedback", { detail }));
  });
}

describe("FeedbackDialog", () => {
  it("is closed until the open event fires", () => {
    render(<FeedbackDialog />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    open({ errorDetail: "boom" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Error attached: boom/)).toBeInTheDocument();
  });

  it("posts the message with context and shows success", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 204 });
    render(<FeedbackDialog />);
    open({ errorDetail: "boom", schemaName: "s.xsd" });
    await userEvent.type(screen.getByPlaceholderText(/What happened/), "The diagram is empty");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/feedback was sent/);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/feedback");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toMatchObject({ message: "The diagram is empty", schema_name: "s.xsd", error_detail: "boom", website: "" });
    expect(body.email).toBeUndefined();
  });

  it("shows the server error and keeps the text", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: "feedback is not configured on this server" }),
    });
    render(<FeedbackDialog />);
    open();
    await userEvent.type(screen.getByPlaceholderText(/What happened/), "hi");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not configured/);
    expect(screen.getByPlaceholderText(/What happened/)).toHaveValue("hi");
  });

  it("closes on Escape", async () => {
    render(<FeedbackDialog />);
    open();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
