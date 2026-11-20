import { getNeonAuthServer, isNeonAuthServerConfigured } from "@/lib/neon-auth-server";

type Context = { params: Promise<{ path: string[] }> };

function unconfiguredResponse() {
  return Response.json(
    {
      error: {
        code: "not_configured",
        message: "Authentication service is not configured on this server.",
        retryable: false,
      },
    },
    { status: 503 },
  );
}

/**
 * Verifies same-origin CSRF on incoming state-changing auth requests, then
 * normalizes the upstream Origin/Referer header to a domain registered in
 * Neon Auth Trusted Domains (`https://memory-lane-os.vercel.app` or
 * `http://localhost:3000`) so Vercel preview URLs and 127.0.0.1 never fail
 * upstream origin validation.
 */
function normalizeTrustedSameOriginRequest(request: Request): Request | Response {
  const reqUrl = new URL(request.url);
  const forwardedHost = request.headers.get("x-forwarded-host") || request.headers.get("host") || reqUrl.host;
  const originHeader = request.headers.get("origin");

  if (originHeader && request.method !== "GET" && request.method !== "HEAD") {
    try {
      const originUrl = new URL(originHeader);
      const isLocalLoopback =
        (originUrl.hostname === "localhost" || originUrl.hostname === "127.0.0.1") &&
        (forwardedHost.startsWith("localhost") || forwardedHost.startsWith("127.0.0.1"));
      if (originUrl.host !== forwardedHost && !isLocalLoopback) {
        return Response.json(
          { message: "Cross-origin authentication request refused." },
          { status: 403 },
        );
      }
    } catch {
      return Response.json(
        { message: "Invalid request origin header." },
        { status: 403 },
      );
    }
  }

  const isLocal =
    forwardedHost.startsWith("localhost") || forwardedHost.startsWith("127.0.0.1");
  const trustedOrigin =
    process.env.NEON_AUTH_TRUSTED_ORIGIN?.trim() ||
    (isLocal ? "http://localhost:3000" : "https://memory-lane-os.vercel.app");

  const headers = new Headers(request.headers);
  headers.set("origin", trustedOrigin);
  headers.set("referer", `${trustedOrigin}/login`);

  return new Request(request.url, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    // @ts-expect-error Node fetch duplex option required when streaming request.body
    duplex: "half",
  });
}

export async function GET(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  const normalized = normalizeTrustedSameOriginRequest(request);
  if (normalized instanceof Response) return normalized;
  return getNeonAuthServer().handler().GET(normalized, context);
}

export async function POST(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  const normalized = normalizeTrustedSameOriginRequest(request);
  if (normalized instanceof Response) return normalized;
  return getNeonAuthServer().handler().POST(normalized, context);
}

export async function PUT(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  const normalized = normalizeTrustedSameOriginRequest(request);
  if (normalized instanceof Response) return normalized;
  return getNeonAuthServer().handler().PUT(normalized, context);
}

export async function PATCH(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  const normalized = normalizeTrustedSameOriginRequest(request);
  if (normalized instanceof Response) return normalized;
  return getNeonAuthServer().handler().PATCH(normalized, context);
}

export async function DELETE(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  const normalized = normalizeTrustedSameOriginRequest(request);
  if (normalized instanceof Response) return normalized;
  return getNeonAuthServer().handler().DELETE(normalized, context);
}
