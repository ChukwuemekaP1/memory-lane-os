import { afterEach, describe, expect, it, vi } from "vitest";

import { activeAuthProvider, clearCachedAuthToken, getAuthToken } from "./auth-provider";

afterEach(() => {
  clearCachedAuthToken();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("auth provider selection", () => {
  it("defaults to native and needs no bearer token", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "");
    expect(activeAuthProvider()).toBe("native");
    await expect(getAuthToken()).resolves.toBeUndefined();
  });

  it("selects neon explicitly, fetches /api/auth/token, and never fabricates a token", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "neon");
    expect(activeAuthProvider()).toBe("neon");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({}), { status: 401 })),
    );
    await expect(getAuthToken()).resolves.toBeUndefined();

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ token: "hdr.eyJleHAiOjk5OTk5OTk5OTl9.sig" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(getAuthToken()).resolves.toBe("hdr.eyJleHAiOjk5OTk5OTk5OTl9.sig");
  });
});
