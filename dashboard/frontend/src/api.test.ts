import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("builds query strings and unwraps responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.records({ status: "blocked", search: "", limit: 10 });
    expect(result).toEqual({ items: [], total: 0 });
    const url = new URL(fetchMock.mock.calls[0][0] as string, "http://localhost");
    expect(url.pathname).toBe("/api/requests");
    expect(url.searchParams.get("status")).toBe("blocked");
    expect(url.searchParams.get("search")).toBeNull();
    expect(url.searchParams.get("limit")).toBe("10");
  });

  it("throws ApiError with the server detail message", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "guardrails server unreachable" }), {
          status: 502,
          statusText: "Bad Gateway",
        })
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.status()).rejects.toThrow(ApiError);
    await expect(api.status()).rejects.toThrow("guardrails server unreachable");
  });

  it("sends JSON bodies for POST requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.adminReload("demo");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/commands/admin/reload");
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ config_id: "demo" });
  });
});
