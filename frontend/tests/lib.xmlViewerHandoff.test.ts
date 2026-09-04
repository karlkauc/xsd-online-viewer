import { afterEach, describe, expect, it, vi } from "vitest";
import { handoffSupported, handoffUrl, openInXmlViewer } from "../src/lib/xmlViewerHandoff";

const TARGET = "https://www.xml-viewer.online/?from=xsd-viewer";

// jsdom's File has no arrayBuffer(); every real browser does.
if (typeof File.prototype.arrayBuffer !== "function") {
  File.prototype.arrayBuffer = function (this: File) {
    return new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(this);
    });
  };
}

// jsdom drops MessageEvent.source unless it is a real Window, so the "popup"
// is the test window itself with postMessage spied.
function fakePopup() {
  vi.spyOn(window, "postMessage").mockImplementation(() => {});
  return window;
}

function ready(source: Window, origin: string, data: unknown = { type: "xml-viewer:ready" }) {
  window.dispatchEvent(new MessageEvent("message", { data, origin, source: source as unknown as MessageEventSource }));
}

afterEach(() => vi.restoreAllMocks());

describe("handoffUrl", () => {
  it("adds the from=xsd-viewer marker", () => {
    expect(handoffUrl("https://www.xml-viewer.online/")).toBe(TARGET);
  });
});

describe("openInXmlViewer", () => {
  it("posts the file once the popup reports ready", async () => {
    const popup = fakePopup();
    const open = vi.spyOn(window, "open").mockReturnValue(popup);
    const file = new File(["<a/>"], "doc.xml");

    const result = openInXmlViewer(file, { target: TARGET, timeoutMs: 1000 });
    await vi.waitFor(() => expect(open).toHaveBeenCalled()); // file read + listener installed
    ready(popup, "https://www.xml-viewer.online");

    await expect(result).resolves.toBe(true);
    const [msg, origin, transfer] = (popup.postMessage as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(msg.type).toBe("xml-viewer:file");
    expect(msg.name).toBe("doc.xml");
    expect(new TextDecoder().decode(msg.content)).toBe("<a/>");
    expect(origin).toBe("https://www.xml-viewer.online");
    expect(transfer).toEqual([msg.content]);
  });

  it("attaches the schema when a loader is given and transfers both buffers", async () => {
    const popup = fakePopup();
    const open = vi.spyOn(window, "open").mockReturnValue(popup);
    const schemaContent = new TextEncoder().encode("<xs:schema/>").buffer;
    const schema = vi.fn().mockResolvedValue({ name: "simple.xsd", content: schemaContent });

    const result = openInXmlViewer(new File(["<a/>"], "doc.xml"), { target: TARGET, timeoutMs: 1000, schema });
    await vi.waitFor(() => expect(open).toHaveBeenCalled());
    expect(schema).toHaveBeenCalledTimes(1);
    ready(popup, "https://www.xml-viewer.online");

    await expect(result).resolves.toBe(true);
    const [msg, , transfer] = (popup.postMessage as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(msg.schema).toEqual({ name: "simple.xsd", content: schemaContent });
    expect(transfer).toEqual([msg.content, schemaContent]);
  });

  it("still sends the document when the schema loader fails", async () => {
    const popup = fakePopup();
    const open = vi.spyOn(window, "open").mockReturnValue(popup);
    const result = openInXmlViewer(new File(["<a/>"], "doc.xml"), {
      target: TARGET,
      timeoutMs: 1000,
      schema: () => Promise.reject(new Error("expired")),
    });
    await vi.waitFor(() => expect(open).toHaveBeenCalled());
    ready(popup, "https://www.xml-viewer.online");
    await expect(result).resolves.toBe(true);
    const [msg] = (popup.postMessage as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(msg.schema).toBeUndefined();
  });

  it("ignores ready messages from foreign origins or other windows", async () => {
    const popup = fakePopup();
    const open = vi.spyOn(window, "open").mockReturnValue(popup);
    const result = openInXmlViewer(new File(["x"], "a.xml"), { target: TARGET, timeoutMs: 300 });
    await vi.waitFor(() => expect(open).toHaveBeenCalled());
    ready(popup, "https://evil.example");
    ready({} as Window, "https://www.xml-viewer.online");
    await expect(result).resolves.toBe(false);
    expect(popup.postMessage).not.toHaveBeenCalled();
  });

  it("returns false when the popup is blocked", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    await expect(openInXmlViewer(new File(["x"], "a.xml"), { target: TARGET })).resolves.toBe(false);
  });
});

describe("handoffSupported", () => {
  it("accepts the public site, the self-hosted instance and dev hosts only", () => {
    expect(handoffSupported("https://www.xsd-viewer.online")).toBe(true);
    expect(handoffSupported("https://viewer.status20.net")).toBe(true);
    expect(handoffSupported("http://127.0.0.1:8180")).toBe(import.meta.env.DEV);
    expect(handoffSupported("https://example.com")).toBe(false);
  });
});
