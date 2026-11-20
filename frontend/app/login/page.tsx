"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Lock } from "lucide-react";

import { SiteHeader } from "@/components/site-header";
import { Button } from "@/components/ui/button";
import { AnimatedTabs, FadeInUp, GlassCard } from "@/components/ui/motion";
import { ApiError, apiRequest } from "@/lib/api";
import { activeAuthProvider, clearCachedAuthToken, getAuthToken } from "@/lib/auth-provider";
import { neonAuthClient } from "@/lib/neon-auth-client";

type NeonMode = "signin" | "signup" | "recover";

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/app";
  return raw;
}

function LoginInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const provider = activeAuthProvider();

  const initialModeParam = searchParams.get("mode");
  const initialMode: NeonMode =
    initialModeParam === "signup" || initialModeParam === "recover" ? initialModeParam : "signin";
  const nextPath = safeNextPath(searchParams.get("next"));

  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);

  const [mode, setMode] = useState<NeonMode>(initialMode);
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    if (provider !== "neon") return;
    let active = true;
    getAuthToken()
      .then((tok) => {
        if (active && tok) router.replace(nextPath);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [provider, router, nextPath]);

  async function requestCode(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiRequest("/v1/auth/request-code", { method: "POST", body: { email } });
      setSent(true);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Could not send a code.");
    } finally {
      setBusy(false);
    }
  }

  async function verify(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiRequest("/v1/auth/verify", { method: "POST", body: { email, code } });
      router.push(nextPath);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function submitNeonAuth(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      clearCachedAuthToken();
      if (mode === "recover") {
        const res = await fetch("/api/auth/request-password-reset", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: email.trim(),
            redirectTo: `${window.location.origin}/login`,
          }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => null)) as { message?: string } | null;
          throw new Error(body?.message || "Could not start account recovery.");
        }
        setNotice("If an account exists for this email, recovery instructions have been sent.");
        return;
      }

      if (mode === "signup") {
        const { error: signUpErr } = await neonAuthClient.signUp.email({
          email: email.trim(),
          password,
          name: name.trim() || email.split("@")[0] || "Member",
        });
        if (signUpErr) {
          throw new Error(signUpErr.message || "Could not create your account.");
        }
      } else {
        const { error: signInErr } = await neonAuthClient.signIn.email({
          email: email.trim(),
          password,
        });
        if (signInErr) {
          throw new Error(signInErr.message || "Invalid email or password.");
        }
      }

      await apiRequest("/v1/auth/me");
      router.push(nextPath);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="site-frame flex justify-center py-14 sm:py-20">
        <FadeInUp className="w-full max-w-md">
          <GlassCard className="flex flex-col gap-5 p-7 sm:p-8">
            <div>
              <span className="eyebrow inline-flex items-center gap-1.5 text-[var(--bronze)]">
                <Lock className="h-3.5 w-3.5" />
                {provider === "neon" ? "Neon Managed Auth" : "Passwordless sign-in"}
              </span>
              <h1 className="mt-2 font-display text-3xl font-medium">
                {provider === "neon"
                  ? mode === "signup"
                    ? "Create your account"
                    : mode === "recover"
                      ? "Reset password"
                      : "Welcome back"
                  : "Sign in"}
              </h1>
              <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                {provider === "neon"
                  ? "Hosts sign in to enter Memory Lane, curate albums, and run AI Memory Studio. Guests never need an account."
                  : "Password-free: we email you a 6-digit code and a magic link."}
              </p>
            </div>

            {provider === "neon" ? (
              <>
                <AnimatedTabs
                  layoutId="login-mode"
                  value={mode}
                  onChange={(next) => {
                    setMode(next);
                    setError(null);
                    setNotice(null);
                  }}
                  items={[
                    { value: "signin", label: "Sign in" },
                    { value: "signup", label: "Register" },
                    { value: "recover", label: "Recover" },
                  ]}
                />
                <form onSubmit={submitNeonAuth} className="flex flex-col gap-3.5">
                  {mode === "signup" && (
                    <label className="field">
                      Display name
                      <input
                        type="text"
                        required
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        placeholder="Ada Lovelace"
                      />
                    </label>
                  )}
                  <label className="field">
                    Email
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="you@example.com"
                    />
                  </label>
                  {mode !== "recover" && (
                    <label className="field">
                      Password
                      <input
                        type="password"
                        required
                        minLength={8}
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        placeholder="At least 8 characters"
                      />
                    </label>
                  )}
                  <Button type="submit" disabled={busy} className="mt-1 w-full">
                    {busy
                      ? "Please wait…"
                      : mode === "signup"
                        ? "Create account & enter app"
                        : mode === "recover"
                          ? "Send recovery email"
                          : "Sign in & enter app"}
                  </Button>
                </form>
              </>
            ) : !sent ? (
              <form onSubmit={requestCode} className="flex flex-col gap-3.5">
                <label className="field">
                  Email
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                  />
                </label>
                <Button type="submit" disabled={busy} className="w-full">
                  {busy ? "Sending…" : "Email me a code"}
                </Button>
              </form>
            ) : (
              <form onSubmit={verify} className="flex flex-col gap-3.5">
                <p className="text-sm text-[var(--muted-foreground)]">
                  Code sent to {email}. It expires in 10 minutes.
                </p>
                <label className="field">
                  6-digit code
                  <input
                    inputMode="numeric"
                    required
                    value={code}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="123456"
                    className="tracking-widest"
                  />
                </label>
                <Button type="submit" disabled={busy || code.length !== 6} className="w-full">
                  {busy ? "Signing in…" : "Sign in"}
                </Button>
              </form>
            )}

            {notice && (
              <p role="status" className="rounded-[var(--radius)] bg-[var(--sage)]/60 px-4 py-3 text-sm text-[var(--primary)]">
                {notice}
              </p>
            )}
            {error && (
              <p role="alert" className="rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
                {error}
              </p>
            )}
          </GlassCard>
        </FadeInUp>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen"><SiteHeader /></div>}>
      <LoginInner />
    </Suspense>
  );
}
