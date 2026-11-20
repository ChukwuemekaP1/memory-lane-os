import { afterEach, describe, expect, it, vi } from "vitest";

import { cancelAIJob, cancelScheduledEvent, promoteAIAsset, runAIJob } from "./studio";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs?.();
});

function mockFetch(payload: unknown, status = 200) {
  return vi.fn(async () => ({ ok: status < 300, status, json: async () => payload }));
}

describe("studio helpers", () => {
  it("runs AI jobs with an idempotency key", async () => {
    const fetchMock = mockFetch({ data: { id: "job-1" } }, 202);
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => "uuid-9" });
    await runAIJob("space-1", "summary", {}, "tok");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit & { body: string }];
    expect(url).toContain("/v1/spaces/space-1/ai/jobs");
    expect(JSON.parse(init.body)).toMatchObject({ kind: "summary", idempotency_key: "uuid-9" });
  });

  it("cancels jobs and promotes assets", async () => {
    const fetchMock = mockFetch({ data: { id: "x" } });
    vi.stubGlobal("fetch", fetchMock);
    await cancelAIJob("job-1", "tok");
    await promoteAIAsset("asset-1", "tok");
    const urls = fetchMock.mock.calls.map((call) => (call as unknown as [string])[0]);
    expect(urls).toEqual(["/api/v1/ai/jobs/job-1/cancel", "/api/v1/ai/assets/asset-1/promote"]);
  });

  it("cancels scheduled events", async () => {
    const fetchMock = mockFetch({ data: { id: "e-1", status: "cancelled" } });
    vi.stubGlobal("fetch", fetchMock);
    const event = await cancelScheduledEvent("e-1", "tok");
    expect(event.status).toBe("cancelled");
  });
});
