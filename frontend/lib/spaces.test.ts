import { afterEach, describe, expect, it, vi } from "vitest";

import { listContributions, postContribution } from "./spaces";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("listContributions", () => {
  it("serializes only set params and unwraps the page", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ data: [{ id: "1" }], page: { next_cursor: "c", has_more: true } }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const page = await listContributions(
      "space-1",
      { q: "beach", kind: "", sort: "-created_at", limit: 20 },
      "tok",
    );
    expect(page).toEqual({ items: [{ id: "1" }], next_cursor: "c", has_more: true });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, { headers: Record<string, string> }];
    expect(url).toContain("/v1/spaces/space-1/contributions?");
    expect(url).toContain("q=beach");
    expect(url).not.toContain("kind=");
    expect(init.headers["Authorization"]).toBe("Bearer tok");
  });
});

describe("postContribution", () => {
  it("defaults idempotency keys and posts JSON", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 201,
      json: async () => ({ data: { id: "9" } }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "uuid-1" });
    await postContribution("space-1", { kind: "message", body: "hi" }, "tok");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, { headers: Record<string, string> }];
    expect(init.headers["Idempotency-Key"]).toBe("uuid-1");
  });
});
