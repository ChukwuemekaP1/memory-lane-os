/**
 * Auth provider selection (single active session model — never two).
 *
 * - "native" (default): passwordless OTP + magic links, session cookie.
 *   No bearer token is needed; API calls rely on the cookie.
 * - "neon": Neon Managed Better Auth (@neondatabase/auth). Proxied through
 *   /api/auth/*; bearer JWTs are fetched from /api/auth/token and sent to
 *   the FastAPI backend where they are verified against the Neon JWKS.
 */

export type AuthProviderName = "native" | "neon";

export function activeAuthProvider(): AuthProviderName {
  return process.env.NEXT_PUBLIC_AUTH_PROVIDER === "native" ? "native" : "neon";
}

let cachedToken: { value: string; expiresAtMs: number } | null = null;

export function clearCachedAuthToken(): void {
  cachedToken = null;
}

function decodeExpMs(jwt: string): number {
  try {
    const parts = jwt.split(".");
    if (parts.length !== 3) return Date.now() + 60_000;
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json =
      typeof atob === "function"
        ? atob(base64)
        : Buffer.from(base64, "base64").toString("utf8");
    const payload = JSON.parse(json) as { exp?: number };
    if (typeof payload.exp === "number") {
      return payload.exp * 1000;
    }
  } catch {
    // Fall back to short cache TTL if payload cannot be decoded.
  }
  return Date.now() + 60_000;
}

/**
 * Returns the bearer JWT for FastAPI calls when Neon Auth is active, or
 * undefined when native cookie auth is active (or no Neon session exists).
 * Never returns a fabricated token.
 */
export async function getAuthToken(): Promise<string | undefined> {
  if (activeAuthProvider() === "native") {
    return undefined;
  }
  const now = Date.now();
  if (cachedToken && cachedToken.expiresAtMs - 15_000 > now) {
    return cachedToken.value;
  }
  if (typeof fetch !== "function") {
    return undefined;
  }
  const response = await fetch("/api/auth/token", {
    method: "GET",
    credentials: "include",
  });
  if (response.status === 401 || response.status === 403) {
    cachedToken = null;
    return undefined;
  }
  if (!response.ok) {
    throw new Error(`Could not obtain Neon Auth session token (HTTP ${response.status}).`);
  }
  const data = (await response.json().catch(() => null)) as { token?: string } | null;
  const token = data?.token?.trim();
  if (!token) {
    cachedToken = null;
    return undefined;
  }
  cachedToken = { value: token, expiresAtMs: decodeExpMs(token) };
  return token;
}

/**
 * Signs out the active user using the single configured auth provider.
 */
export async function signOutCurrentUser(): Promise<void> {
  clearCachedAuthToken();
  if (activeAuthProvider() === "neon") {
    await fetch("/api/auth/sign-out", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }).catch(() => undefined);
    return;
  }
  await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api"}/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
  }).catch(() => undefined);
}
