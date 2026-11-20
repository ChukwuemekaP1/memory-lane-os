import { NextRequest, NextResponse } from "next/server";

import { getNeonAuthServer, isNeonAuthServerConfigured } from "@/lib/neon-auth-server";

export async function proxy(request: NextRequest) {
  if (
    process.env.NEXT_PUBLIC_AUTH_PROVIDER !== "neon" ||
    !isNeonAuthServerConfigured()
  ) {
    return NextResponse.next();
  }
  const handler = getNeonAuthServer().middleware({ loginUrl: "/login" });
  return handler(request);
}

export const config = {
  matcher: [
    "/app/:path*",
    "/create/:path*",
    "/dashboard/:path*",
    "/s/:spaceId/settings/:path*",
    "/s/:spaceId/studio/:path*",
  ],
};
