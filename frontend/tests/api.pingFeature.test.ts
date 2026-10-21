import { afterEach, describe, expect, it, vi } from "vitest";
import { pingFeature } from "../src/api/client";

describe("pingFeature", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts the feature name with keepalive", () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    pingFeature("diagram_png");
    expect(fetchMock).toHaveBeenCalledWith("/api/usage/feature?name=diagram_png", { method: "POST", keepalive: true });
  });

  it("pings a once-feature only on its first use", () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    pingFeature("search_open", { once: true });
    pingFeature("search_open", { once: true });
    pingFeature("search_open", { once: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    pingFeature("diagram_svg");
    pingFeature("diagram_svg");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("never throws, whether the request fails or fetch itself does", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    expect(() => pingFeature("diagram_png")).not.toThrow();
    await Promise.resolve();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        throw new TypeError("no fetch");
      }),
    );
    expect(() => pingFeature("diagram_svg")).not.toThrow();
  });
});
