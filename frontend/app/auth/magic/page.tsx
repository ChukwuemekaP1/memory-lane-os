"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

function MagicExchange() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setError("This magic link is missing its token.");
      return;
    }
    fetch(`/api/v1/auth/magic?token=${encodeURIComponent(token)}`, {
      headers: { Accept: "application/json" },
      credentials: "include",
    }).then(
      async (response) => {
        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as {
            error?: { message?: string };
          } | null;
          setError(payload?.error?.message ?? "This link has expired or was already used.");
          return;
        }
        router.replace("/dashboard");
      },
      () => setError("Could not reach the server. Please retry."),
    );
  }, [searchParams, router]);

  if (error) {
    return (
      <main className="mx-auto w-full max-w-md px-6 py-16">
        <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-900">
          {error}
        </p>
      </main>
    );
  }
  return (
    <main className="mx-auto w-full max-w-md px-6 py-16">
      <p role="status" className="text-sm opacity-70">
        Signing you in…
      </p>
    </main>
  );
}

export default function MagicPage() {
  return (
    <Suspense>
      <MagicExchange />
    </Suspense>
  );
}
