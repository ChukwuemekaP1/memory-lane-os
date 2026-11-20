/** AI Studio + scheduling API helpers. */

import { apiRequest } from "./api";

export interface AIJob {
  id: string;
  kind: string;
  status: string;
  provider?: string;
  model?: string | null;
  attempts: number;
  quota_reserved: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cost_usd?: number | null;
  last_error: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at: string | null;
}

export interface AICapabilityStatus {
  available: boolean;
  model: string | null;
  reason: string | null;
}

export interface AICapabilities {
  provider: string;
  ai_opt_in: boolean;
  capabilities: Record<string, AICapabilityStatus>;
}

export interface AIAsset {
  id: string;
  job_id: string;
  kind: string;
  title: string | null;
  text_body: string | null;
  asset_id: string | null;
  edit_list: { clips?: Array<{ asset_id: string; start_s: number; end_s: number }> } | null;
  is_promoted: boolean;
  is_ai_labeled: boolean;
  created_at: string;
}

export interface AIQuota {
  plan: string;
  limit: number;
  used: number;
  reserved: number;
  resets_at: string;
}

export function runAIJob(spaceId: string, kind: string, inputs: Record<string, unknown>, token?: string) {
  return apiRequest<AIJob & { quota_reserved: number }>(`/v1/spaces/${spaceId}/ai/jobs`, {
    method: "POST",
    body: { kind, inputs, idempotency_key: crypto.randomUUID() },
    token,
  });
}

export function listAIJobs(spaceId: string, token?: string) {
  return apiRequest<AIJob[]>(`/v1/spaces/${spaceId}/ai/jobs`, { token });
}

export function cancelAIJob(jobId: string, token?: string) {
  return apiRequest<AIJob>(`/v1/ai/jobs/${jobId}/cancel`, { method: "POST", token });
}

export function listAIAssets(spaceId: string, token?: string) {
  return apiRequest<AIAsset[]>(`/v1/spaces/${spaceId}/ai/assets`, { token });
}

export function patchAIAsset(assetId: string, body: { title?: string; text_body?: string }, token?: string) {
  return apiRequest<AIAsset>(`/v1/ai/assets/${assetId}`, { method: "PATCH", body, token });
}

export function promoteAIAsset(assetId: string, token?: string) {
  return apiRequest<AIAsset>(`/v1/ai/assets/${assetId}/promote`, { method: "POST", token });
}

export function deleteAIAsset(assetId: string, token?: string) {
  return apiRequest<void>(`/v1/ai/assets/${assetId}`, { method: "DELETE", token });
}

export function getAIQuota(spaceId: string, token?: string) {
  return apiRequest<AIQuota>(`/v1/spaces/${spaceId}/ai/quota`, { token });
}

export function getAICapabilities(spaceId: string, token?: string) {
  return apiRequest<AICapabilities>(`/v1/spaces/${spaceId}/ai/capabilities`, { token });
}

export function createBookPdfArchive(spaceId: string, token?: string) {
  return apiRequest<{ id: string; kind: string; status: string }>(`/v1/spaces/${spaceId}/archives`, {
    method: "POST",
    body: { kind: "book_pdf" },
    token,
  });
}

export interface ScheduledEvent {
  id: string;
  space_id: string | null;
  kind: string;
  run_at: string;
  timezone: string;
  status: string;
  attempts: number;
  last_error: string | null;
}

export function listSchedule(spaceId: string, token?: string) {
  return apiRequest<ScheduledEvent[]>(`/v1/spaces/${spaceId}/schedule`, { token });
}

export function createScheduledEvent(
  spaceId: string,
  body: { kind: string; run_at: string; timezone?: string; payload?: Record<string, unknown> },
  token?: string,
) {
  return apiRequest<ScheduledEvent>(`/v1/spaces/${spaceId}/schedule`, {
    method: "POST",
    body,
    token,
  });
}

export function cancelScheduledEvent(eventId: string, token?: string) {
  return apiRequest<ScheduledEvent>(`/v1/schedule/${eventId}/cancel`, { method: "POST", token });
}

export function rescheduleEvent(eventId: string, run_at: string, token?: string) {
  return apiRequest<ScheduledEvent>(`/v1/schedule/${eventId}/reschedule`, {
    method: "POST",
    body: { run_at },
    token,
  });
}
