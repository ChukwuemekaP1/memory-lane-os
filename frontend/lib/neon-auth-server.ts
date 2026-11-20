import { createNeonAuth } from "@neondatabase/auth/next/server";

export function isNeonAuthServerConfigured(): boolean {
  return Boolean(
    process.env.NEON_AUTH_BASE_URL &&
      process.env.NEON_AUTH_COOKIE_SECRET &&
      process.env.NEON_AUTH_COOKIE_SECRET.length >= 32,
  );
}

let cached: ReturnType<typeof createNeonAuth> | null = null;

export function getNeonAuthServer() {
  if (!cached) {
    const baseUrl = process.env.NEON_AUTH_BASE_URL;
    const secret = process.env.NEON_AUTH_COOKIE_SECRET;
    if (!baseUrl || !secret || secret.length < 32) {
      throw new Error(
        "Neon Auth server is not configured (set NEON_AUTH_BASE_URL and a 32+ char NEON_AUTH_COOKIE_SECRET).",
      );
    }
    cached = createNeonAuth({
      baseUrl,
      cookies: { secret },
    });
  }
  return cached;
}
