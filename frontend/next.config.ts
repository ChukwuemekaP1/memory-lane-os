import type { NextConfig } from "next";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api",
    NEXT_PUBLIC_AUTH_PROVIDER: process.env.NEXT_PUBLIC_AUTH_PROVIDER ?? "neon",
  },
  // Same-origin API proxy: fallback runs after Next.js App Router route
  // handlers (so /api/auth/* hits Neon Auth's route handler while /api/v1/*,
  // /api/healthz, and /api/readyz proxy to the FastAPI backend).
  rewrites: async () => ({
    fallback: [{ source: "/api/:path*", destination: `${API_INTERNAL_URL}/:path*` }],
  }),
};

export default nextConfig;
