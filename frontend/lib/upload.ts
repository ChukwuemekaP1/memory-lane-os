/** Browser upload flow: presign → PUT bytes → confirm → poll processing. */

import { confirmMedia, getMediaJob, presignMedia } from "./spaces";

export type UploadStatus =
  | { stage: "presigning" }
  | { stage: "uploading"; progress: number }
  | { stage: "confirming" }
  | { stage: "processing" }
  | { stage: "ready"; assetId: string }
  | { stage: "failed"; message: string };

export interface UploadHooks {
  onStatus: (status: UploadStatus) => void;
  pollIntervalMs?: number;
  pollAttempts?: number;
}

function kindFor(mime: string): string {
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  if (mime === "application/pdf") return "other";
  throw new Error(`Unsupported file type: ${mime}.`);
}

export async function uploadFile(
  spaceId: string,
  file: File,
  token: string | undefined,
  hooks: UploadHooks,
): Promise<string> {
  const { onStatus, pollIntervalMs = 2000, pollAttempts = 30 } = hooks;
  const kind = kindFor(file.type || "application/octet-stream");
  onStatus({ stage: "presigning" });
  const presigned = await presignMedia(spaceId, file.type, file.size, kind, token);
  if (!presigned.upload_url.startsWith("http")) {
    throw new Error("Uploads need object storage (run the compose stack).");
  }
  onStatus({ stage: "uploading", progress: 0 });
  const put = await fetch(presigned.upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!put.ok) {
    throw new Error("Upload interrupted. Please retry.");
  }
  onStatus({ stage: "confirming" });
  const confirmed = await confirmMedia(presigned.asset_id, token);
  onStatus({ stage: "processing" });
  for (let attempt = 0; attempt < pollAttempts; attempt += 1) {
    const job = await getMediaJob(confirmed.processing_job_id, token);
    if (job.status === "succeeded") {
      onStatus({ stage: "ready", assetId: presigned.asset_id });
      return presigned.asset_id;
    }
    if (job.status === "dead" || (job.status === "failed" && attempt > 2)) {
      throw new Error(job.last_error || "Processing failed. Please retry.");
    }
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }
  throw new Error("Processing is taking too long. It will finish in the background.");
}
