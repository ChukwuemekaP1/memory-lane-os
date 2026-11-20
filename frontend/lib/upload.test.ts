import { afterEach, describe, expect, it, vi } from "vitest";

import { uploadFile } from "./upload";

afterEach(() => {
  vi.unstubAllGlobals();
});

function fileOf(size: number, type: string): File {
  return new File([new Uint8Array(size)], "photo.jpg", { type });
}

describe("uploadFile", () => {
  it("rejects unsupported types before any request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      uploadFile("space-1", fileOf(10, "application/x-evil"), "tok", { onStatus: () => {} }),
    ).rejects.toThrow("Unsupported file type");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("runs presign → PUT → confirm → poll to ready", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? "GET"} ${url}`);
        if (String(url).includes("/v1/media/presign")) {
          return {
            ok: true,
            status: 201,
            json: async () => ({
              data: { id: "asset-1", asset_id: "asset-1", upload_url: "http://minio/put" },
            }),
          };
        }
        if (url === "http://minio/put") {
          return { ok: true, status: 200, json: async () => ({}) };
        }
        if (String(url).includes("/v1/media/confirm")) {
          return {
            ok: true,
            status: 202,
            json: async () => ({ data: { asset: { id: "asset-1" }, processing_job_id: "job-1" } }),
          };
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ data: { status: "succeeded", attempts: 1, last_error: null } }),
        };
      }),
    );
    const statuses: string[] = [];
    const assetId = await uploadFile("space-1", fileOf(100, "image/jpeg"), "tok", {
      onStatus: (status) => statuses.push(status.stage),
      pollIntervalMs: 1,
    });
    expect(assetId).toBe("asset-1");
    expect(statuses).toEqual(["presigning", "uploading", "confirming", "processing", "ready"]);
    expect(calls.some((call) => call.startsWith("PUT http://minio/put"))).toBe(true);
  });

  it("surfaces interrupted uploads as retryable errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (String(url).includes("/v1/media/presign")) {
          return {
            ok: true,
            status: 201,
            json: async () => ({
              data: { id: "asset-1", asset_id: "asset-1", upload_url: "http://minio/put" },
            }),
          };
        }
        return { ok: false, status: 500, json: async () => ({}) };
      }),
    );
    await expect(
      uploadFile("space-1", fileOf(100, "image/jpeg"), "tok", {
        onStatus: () => {},
        pollIntervalMs: 1,
      }),
    ).rejects.toThrow("Upload interrupted");
  });
});
