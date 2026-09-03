import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Uploader } from "../src/components/Uploader";
import * as client from "../src/api/client";

const LIBRARY = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="types.xsd"/></xs:schema>';
const TYPES = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>';

function chooseFiles(files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files } });
}

describe("Uploader with several loose files", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("asks for the main schema, pre-selecting the one nobody includes", async () => {
    const spy = vi.spyOn(client, "uploadSchemaFiles").mockResolvedValue({
      schema_id: "x",
      model: {} as never,
    });
    render(<Uploader />);
    chooseFiles([
      new File([TYPES], "types.xsd", { type: "application/xml" }),
      new File([LIBRARY], "library.xsd", { type: "application/xml" }),
    ]);

    const select = (await screen.findByLabelText(/Main schema/i)) as HTMLSelectElement;
    expect(select.value).toBe("library.xsd");
    expect(screen.getByText(/2 files chosen, 2 of them schemas/i)).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();

    fireEvent.change(select, { target: { value: "types.xsd" } });
    fireEvent.click(screen.getByRole("button", { name: "Load" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(spy.mock.calls[0][0].map((f) => f.name)).toEqual(["types.xsd", "library.xsd"]);
    expect(spy.mock.calls[0][1]).toBe("types.xsd");
  });

  it("uploads a single schema straight away", async () => {
    const spy = vi.spyOn(client, "uploadSchemaFiles").mockResolvedValue({
      schema_id: "x",
      model: {} as never,
    });
    render(<Uploader />);
    chooseFiles([new File([TYPES], "types.xsd", { type: "application/xml" })]);
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(spy.mock.calls[0][1]).toBeUndefined();
    expect(screen.queryByLabelText(/Main schema/i)).not.toBeInTheDocument();
  });

  it("explains when none of the files is a schema", async () => {
    render(<Uploader />);
    chooseFiles([
      new File(["a"], "a.txt", { type: "text/plain" }),
      new File(["b"], "b.txt", { type: "text/plain" }),
    ]);
    expect(await screen.findByText(/none of the 2 files is an \.xsd schema/i)).toBeInTheDocument();
  });
});
