import { getNeonAuthServer, isNeonAuthServerConfigured } from "@/lib/neon-auth-server";

type Context = { params: Promise<{ path: string[] }> };

function unconfiguredResponse() {
  return Response.json(
    {
      error: {
        code: "not_configured",
        message: "Neon Auth is not configured on this server.",
        retryable: false,
      },
    },
    { status: 503 },
  );
}

export async function GET(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  return getNeonAuthServer().handler().GET(request, context);
}

export async function POST(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  return getNeonAuthServer().handler().POST(request, context);
}

export async function PUT(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  return getNeonAuthServer().handler().PUT(request, context);
}

export async function PATCH(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  return getNeonAuthServer().handler().PATCH(request, context);
}

export async function DELETE(request: Request, context: Context) {
  if (!isNeonAuthServerConfigured()) return unconfiguredResponse();
  return getNeonAuthServer().handler().DELETE(request, context);
}
