/** Typed API client for the Memory Lane backend (API_SPECIFICATION envelopes). */

import { activeAuthProvider, getAuthToken } from "@/lib/auth-provider";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

export interface ApiErrorBody {
  code: string;
  message: string;
  retryable: boolean;
  details?: Record<string, unknown>;
  request_id?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

interface SuccessEnvelope<T> {
  data: T;
  request_id: string;
}

export interface PageInfo {
  next_cursor: string | null;
  has_more: boolean;
}

interface ListEnvelope<T> {
  data: T[];
  page: PageInfo;
  request_id: string;
}

function isErrorEnvelope(value: unknown): value is { error: ApiErrorBody } {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as { error: unknown }).error === "object"
  );
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  token?: string;
  idempotencyKey?: string;
  signal?: AbortSignal;
}

async function resolveBearerToken(explicitToken?: string): Promise<string | undefined> {
  if (explicitToken) return explicitToken;
  if (activeAuthProvider() === "neon") {
    return getAuthToken().catch(() => undefined);
  }
  return undefined;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const bearer = await resolveBearerToken(options.token);
  if (bearer) headers["Authorization"] = `Bearer ${bearer}`;
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    credentials: "include",
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok || isErrorEnvelope(payload)) {
    const body: ApiErrorBody = isErrorEnvelope(payload)
      ? payload.error
      : {
          code: "upstream_error",
          message: `Request failed with status ${response.status}.`,
          retryable: response.status >= 500,
        };
    throw new ApiError(response.status, body);
  }
  if (payload && typeof payload === "object" && "data" in payload) {
    return (payload as SuccessEnvelope<T>).data;
  }
  return payload as T;
}

export async function apiListRequest<T>(
  path: string,
  params: Record<string, string | number | undefined | null> = {},
  options: RequestOptions = {},
): Promise<{ items: T[]; page: PageInfo }> {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const query = search.size > 0 ? `?${search.toString()}` : "";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const bearer = await resolveBearerToken(options.token);
  if (bearer) headers["Authorization"] = `Bearer ${bearer}`;

  const response = await fetch(`${API_BASE_URL}${path}${query}`, {
    headers,
    credentials: "include",
    signal: options.signal,
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok || isErrorEnvelope(payload)) {
    const body: ApiErrorBody = isErrorEnvelope(payload)
      ? payload.error
      : {
          code: "upstream_error",
          message: `Request failed with status ${response.status}.`,
          retryable: response.status >= 500,
        };
    throw new ApiError(response.status, body);
  }
  const envelope = payload as ListEnvelope<T>;
  return { items: envelope.data, page: envelope.page };
}

export interface HealthStatus {
  status: string;
  version: string;
}

export interface ReadinessStatus {
  ready: boolean;
  version: string;
  components: Record<string, string>;
}

export function getHealth(signal?: AbortSignal): Promise<HealthStatus> {
  return apiRequest<HealthStatus>("/healthz", { signal });
}

export function getReadiness(signal?: AbortSignal): Promise<ReadinessStatus> {
  return apiRequest<ReadinessStatus>("/readyz", { signal });
}
