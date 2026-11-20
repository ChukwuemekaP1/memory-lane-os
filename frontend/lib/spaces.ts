/** Space + contribution API helpers (typed wrappers over lib/api). */

import { ApiError, apiListRequest, apiRequest } from "./api";

export { ApiError };

export interface ThemeTokens {
  accent?: string;
  background?: string;
  font?: string;
  layout?: string;
  cover_fit?: string;
  [key: string]: string | undefined;
}

export interface SpaceDetail {
  space: {
    id: string;
    title: string;
    description: string | null;
    kind: string;
    occasion: string;
    visibility: string;
    contribution_policy: string;
    event_date: string | null;
    publish_at: string | null;
    location_label: string | null;
    timezone: string;
    storage_quota_bytes: number;
    storage_used_bytes: number;
    allow_anonymous?: boolean;
    ai_opt_in?: boolean;
  };
  theme: { theme: { slug: string; name: string }; tokens: ThemeTokens; is_customized: boolean };
  stats: { contributions: number; media: number; contributors: number };
  my_role: string | null;
  my_permissions: string[];
  preview: boolean;
}

export interface ContributionCard {
  id: string;
  kind: string;
  body: string | null;
  display_name: string | null;
  is_anonymous: boolean;
  is_private_to_owner: boolean;
  status: string;
  taken_at: string | null;
  created_at: string;
  attachment_count: number;
  reaction_count: number;
  reply_count: number;
}

export interface ContributionDetail extends ContributionCard {
  attachments: Array<{
    asset_id: string;
    kind: string;
    mime: string;
    status: string;
    caption: string | null;
    urls: { derivatives: Record<string, string>; original?: string };
  }>;
  reactions: Array<{ emoji: string; count: number; mine: boolean }>;
  rejection_reason: string | null;
}

export interface FeedParams {
  kind?: string;
  status?: string;
  q?: string;
  taken_from?: string;
  taken_to?: string;
  author?: string;
  sort?: string;
  cursor?: string;
  limit?: number;
}

export interface FeedPage {
  items: ContributionCard[];
  next_cursor: string | null;
  has_more: boolean;
}

export function getSpace(spaceId: string, token?: string, signal?: AbortSignal) {
  return apiRequest<SpaceDetail>(`/v1/spaces/${spaceId}`, { token, signal });
}

export async function listContributions(
  spaceId: string,
  params: FeedParams,
  token?: string,
  signal?: AbortSignal,
): Promise<FeedPage> {
  const { items, page } = await apiListRequest<ContributionCard>(
    `/v1/spaces/${spaceId}/contributions`,
    params as Record<string, string | number | undefined | null>,
    { token, signal },
  );
  return { items, next_cursor: page.next_cursor, has_more: page.has_more };
}

export function getContribution(itemId: string, token?: string, signal?: AbortSignal) {
  return apiRequest<ContributionDetail>(`/v1/contributions/${itemId}`, { token, signal });
}

export interface ContributionPost {
  kind: string;
  body?: string;
  guest_name?: string;
  is_anonymous?: boolean;
  is_private_to_owner?: boolean;
  taken_at?: string;
  asset_ids?: string[];
}

export function postContribution(
  spaceId: string,
  post: ContributionPost,
  token?: string,
  idempotencyKey?: string,
) {
  return apiRequest<ContributionDetail>(`/v1/spaces/${spaceId}/contributions`, {
    method: "POST",
    body: post,
    token,
    idempotencyKey: idempotencyKey ?? crypto.randomUUID(),
  });
}

export function toggleReaction(itemId: string, emoji: string, on: boolean, token?: string) {
  if (!on) {
    return apiRequest<void>(`/v1/contributions/${itemId}/reactions/${encodeURIComponent(emoji)}`, {
      method: "DELETE",
      token,
    });
  }
  return apiRequest<{ reactions: ContributionDetail["reactions"] }>(
    `/v1/contributions/${itemId}/reactions`,
    { method: "POST", body: { emoji }, token },
  );
}

export function postReply(itemId: string, body: string, guest_name: string | undefined, token?: string) {
  return apiRequest<{ id: string }>(`/v1/contributions/${itemId}/replies`, {
    method: "POST",
    body: { body, guest_name },
    token,
  });
}

export interface PresignResult {
  id: string;
  asset_id: string;
  upload_url: string;
  kind: string;
  status: string;
}

export function presignMedia(
  spaceId: string,
  mime: string,
  bytes: number,
  kind: string,
  token?: string,
) {
  return apiRequest<PresignResult>("/v1/media/presign", {
    method: "POST",
    body: { space_id: spaceId, mime, bytes, kind },
    token,
  });
}

export function confirmMedia(assetId: string, token?: string) {
  return apiRequest<{ asset: { id: string; status: string }; processing_job_id: string }>(
    "/v1/media/confirm",
    { method: "POST", body: { asset_id: assetId }, token },
  );
}

export function getMediaJob(jobId: string, token?: string) {
  return apiRequest<{ status: string; attempts: number; last_error: string | null }>(
    `/v1/media/jobs/${jobId}`,
    { token },
  );
}

export interface OwnedSpace {
  space: SpaceDetail["space"];
  my_role: string;
}

export function listMySpaces(archived = false) {
  return apiRequest<OwnedSpace[]>(`/v1/spaces${archived ? "?archived=true" : ""}`);
}

export interface SpaceCreate {
  title: string;
  description?: string;
  kind?: string;
  occasion?: string;
  theme_id: string;
  visibility?: string;
  event_date?: string;
  location_label?: string;
  timezone?: string;
}

export function createSpace(body: SpaceCreate) {
  return apiRequest<{ space: SpaceDetail["space"]; guest_links: Array<{ url: string }> }>(
    "/v1/spaces",
    { method: "POST", body },
  );
}

export interface ThemeCatalogEntry {
  id: string;
  slug: string;
  name: string;
  occasions: string[];
  tokens: ThemeTokens;
  plan_required: string;
  entitled: boolean;
}

export function listThemes(occasion?: string) {
  const query = occasion ? `?occasion=${encodeURIComponent(occasion)}` : "";
  return apiRequest<ThemeCatalogEntry[]>(`/v1/themes${query}`);
}

export function patchSpace(spaceId: string, body: Record<string, unknown>, token?: string) {
  return apiRequest<SpaceDetail>(`/v1/spaces/${spaceId}`, { method: "PATCH", body, token });
}

export function previewTheme(
  spaceId: string,
  body: { theme_id?: string; overrides?: ThemeTokens },
  token?: string,
) {
  return apiRequest<{ theme: { slug: string; name: string }; tokens: ThemeTokens; is_customized: boolean }>(
    `/v1/spaces/${spaceId}/theme-preview`,
    { method: "POST", body, token },
  );
}

export function moderateContribution(
  itemId: string,
  action: "approve" | "hide" | "reject" | "restore",
  reason?: string,
  token?: string,
) {
  return apiRequest<ContributionDetail>(`/v1/contributions/${itemId}/moderate`, {
    method: "POST",
    body: { action, reason: reason || undefined },
    token,
  });
}

export interface GuestTokenInfo {
  id: string;
  role_cap: string;
  label: string;
  use_count: number;
  max_uses: number | null;
  expires_at: string | null;
  revoked_at: string | null;
}

export function listGuestTokens(spaceId: string, token?: string) {
  return apiRequest<GuestTokenInfo[]>(`/v1/spaces/${spaceId}/guest-tokens`, { token });
}

export function mintGuestToken(
  spaceId: string,
  body: { role_cap: "viewer" | "contributor"; label: string },
  token?: string,
) {
  return apiRequest<{ token: GuestTokenInfo; url: string; qr_payload: string; token_preview: string }>(
    `/v1/spaces/${spaceId}/guest-tokens`,
    { method: "POST", body, token },
  );
}
