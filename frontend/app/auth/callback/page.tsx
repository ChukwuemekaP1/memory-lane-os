"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

/** Landing target of the API's browser magic-link flow (?ok=1). */
function CallbackNotice() {
  const searchParams = useSearchParams();
  const ok = searchParams.get("ok") === "1";
  return (
    <main className="mx-auto flex w-full max-w-md flex-col gap-3 px-6 py-16">
      <h1 className="text-2xl font-bold">{ok ? "Signed in" : "Sign-in link"}</h1>
      <p className="text-sm opacity-70">
        {ok ? "Your magic link worked. Head to your dashboard." : "Continue to your dashboard."}
      </p>
      <Link href="/dashboard" className="text-sm font-medium underline">
        Go to dashboard
      </Link>
    </main>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense>
      <CallbackNotice />
    </Suspense>
  );
}
