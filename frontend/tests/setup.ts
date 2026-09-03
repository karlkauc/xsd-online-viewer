import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// jsdom is missing a handful of browser globals that the production code
// reads at render time. Stub them so any component-under-test can render
// without a per-file polyfill dance.

if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// jsdom's Blob lacks the promise-based readers the uploader uses to sniff
// files; route them through FileReader.
function readBlob(blob: Blob, as: "text" | "arrayBuffer"): Promise<string | ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string | ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    if (as === "text") reader.readAsText(blob);
    else reader.readAsArrayBuffer(blob);
  });
}
if (typeof Blob.prototype.text !== "function") {
  Blob.prototype.text = function text() {
    return readBlob(this, "text") as Promise<string>;
  };
}
if (typeof Blob.prototype.arrayBuffer !== "function") {
  Blob.prototype.arrayBuffer = function arrayBuffer() {
    return readBlob(this, "arrayBuffer") as Promise<ArrayBuffer>;
  };
}
