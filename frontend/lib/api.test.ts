import { describe, expect, it, vi, afterEach } from "vitest";

import { ApiError, apiRequest, getHealth } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockFetch(status: number, payload: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: status >= 200 && status < 300,
      status,
      json: async () => payload,
    })),
  );
}

describe("apiRequest", () => {
  it("unwraps the success envelope", async () => {
    mockFetch(200, { data: { status: "ok", version: "0.1.0" }, request_id: "r1" });
    const health = await getHealth();
    expect(health).toEqual({ status: "ok", version: "0.1.0" });
  });

  it("throws ApiError with the server envelope on failure", async () => {
    mockFetch(404, {
      error: { code: "not_found", message: "Space not found.", retryable: false },
    });
    const failure = await apiRequest("/v1/spaces/x").then(
      () => null,
      (error: unknown) => error as ApiError,
    );
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure?.status).toBe(404);
    expect(failure?.body.code).toBe("not_found");
  });

  it("maps non-JSON failures to upstream_error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error("no json");
        },
      })),
    );
    const failure = await apiRequest("/healthz").then(
      () => null,
      (error: unknown) => error as ApiError,
    );
    expect(failure?.body.code).toBe("upstream_error");
    expect(failure?.body.retryable).toBe(true);
  });

  it("sends bearer token and idempotency key headers", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 201,
      json: async () => ({ data: { id: "1" }, request_id: "r" }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/v1/spaces/x/contributions", {
      method: "POST",
      body: { kind: "message" },
      token: "guest-token",
      idempotencyKey: "idem-1",
    });
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit & { headers: Record<string, string> }];
    expect(init.headers["Authorization"]).toBe("Bearer guest-token");
    expect(init.headers["Idempotency-Key"]).toBe("idem-1");
    expect(init.credentials).toBe("include");
  });
});
