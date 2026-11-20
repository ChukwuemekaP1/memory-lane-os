import { afterEach, describe, expect, it, vi } from "vitest";

import { activeAuthProvider, clearCachedAuthToken, getAuthToken } from "./auth-provider";

afterEach(() => {
  clearCachedAuthToken();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("auth provider selection", () => {
  it("selects native explicitly and needs no bearer token", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "native");
    expect(activeAuthProvider()).toBe("native");
    await expect(getAuthToken()).resolves.toBeUndefined();
  });

  it("defaults to neon, fetches /api/auth/token, and never fabricates a token", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "");
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
