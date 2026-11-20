"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArrowLeft, Eye, EyeOff, KeyRound, Lock, Mail, MailCheck } from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { SiteHeader } from "@/components/site-header";
import { Button } from "@/components/ui/button";
import { AnimatedTabs, FadeInUp, GlassCard } from "@/components/ui/motion";
import { apiRequest } from "@/lib/api";
import { clearCachedAuthToken, getAuthToken } from "@/lib/auth-provider";
import { neonAuthClient } from "@/lib/neon-auth-client";

type AuthMode = "signin" | "signup" | "recover";
type AuthMethod = "password" | "otp";

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/app";
  return raw;
}

function LoginInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const initialModeParam = searchParams.get("mode");
  const initialMode: AuthMode =
    initialModeParam === "signup" || initialModeParam === "recover" ? initialModeParam : "signin";
  const initialMethodParam = searchParams.get("method");
  const initialMethod: AuthMethod = initialMethodParam === "otp" ? "otp" : "password";
  const nextPath = safeNextPath(searchParams.get("next"));

  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [method, setMethod] = useState<AuthMethod>(initialMethod);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Passwordless 6-digit email OTP state
  const [otpSent, setOtpSent] = useState(false);
  const [otp, setOtp] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    let active = true;
    getAuthToken()
      .then((tok) => {
        if (active && tok) router.replace(nextPath);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [router, nextPath]);

  function switchMode(next: AuthMode) {
    setMode(next);
    setOtpSent(false);
    setOtp("");
    setError(null);
    setNotice(null);
  }

  function switchMethod(next: AuthMethod) {
    setMethod(next);
    setOtpSent(false);
    setOtp("");
    setError(null);
    setNotice(null);
  }

  async function sendEmailCode() {
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError("Please enter your email address first.");
      return;
    }
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const res = await fetch("/api/auth/email-otp/send-verification-otp", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: trimmedEmail,
          type: "sign-in",
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { message?: string } | null;
        throw new Error(body?.message || "Could not send a sign-in code right now. Please try again.");
      }
      setOtpSent(true);
      setNotice(`We sent a 6-digit code to ${trimmedEmail}. Enter it below to continue.`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not send code.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      clearCachedAuthToken();
      const trimmedEmail = email.trim();

      if (mode === "recover") {
        const res = await fetch("/api/auth/request-password-reset", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: trimmedEmail,
            redirectTo: `${window.location.origin}/login?mode=signin`,
          }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => null)) as { message?: string } | null;
          throw new Error(body?.message || "We couldn't start password recovery right now. Please try again.");
        }
        setNotice(
          "If an account exists for that email address, we've sent a password reset link. Check your inbox and spam folder.",
        );
        return;
      }

      // Passwordless Email Code (works for both Sign in and Create account)
      if (method === "otp") {
        if (!otpSent) {
          setBusy(false);
          await sendEmailCode();
          return;
        }
        const cleanedOtp = otp.trim();
        if (cleanedOtp.length < 6) {
          throw new Error("Please enter the 6-digit code from your email.");
        }
        const res = await fetch("/api/auth/sign-in/email-otp", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: trimmedEmail,
            otp: cleanedOtp,
          }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => null)) as { message?: string } | null;
          throw new Error(body?.message || "That code is invalid or expired. Please try again.");
        }
        await apiRequest("/v1/auth/me").catch(() => undefined);
        router.push(nextPath);
        return;
      }

      // Email + Password
      if (mode === "signup") {
        if (password.length < 8) {
          throw new Error("Please choose a password with at least 8 characters.");
        }
        const { error: signUpErr } = await neonAuthClient.signUp.email({
          email: trimmedEmail,
          password,
          name: name.trim() || trimmedEmail.split("@")[0] || "Host",
        });
        if (signUpErr) {
          throw new Error(signUpErr.message || "Could not create your account.");
        }
      } else {
        const { error: signInErr } = await neonAuthClient.signIn.email({
          email: trimmedEmail,
          password,
        });
        if (signInErr) {
          throw new Error(signInErr.message || "Incorrect email or password.");
        }
      }

      await apiRequest("/v1/auth/me").catch(() => undefined);
      router.push(nextPath);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="site-frame flex justify-center py-10 sm:py-16">
        <FadeInUp className="w-full max-w-[440px]">
          <GlassCard className="flex flex-col gap-5 p-6 sm:p-8">
            <div className="flex flex-col items-center text-center">
              <BrandMark size="md" showWordmark={false} />
              <h1 className="mt-4 font-display text-3xl font-medium tracking-tight">
                {mode === "signup"
                  ? "Create your account"
                  : mode === "recover"
                    ? "Reset your password"
                    : "Welcome back"}
              </h1>
              <p className="mt-1.5 max-w-xs text-sm text-[var(--muted-foreground)]">
                {mode === "signup"
                  ? "Use a password or a one-time email code. Guests never need an account."
                  : mode === "recover"
                    ? "Enter the email you used to register and we'll send you a reset link."
                    : "Sign in with your password or a quick passwordless email code."}
              </p>
            </div>

            <AnimatedTabs
              layoutId="login-mode"
              value={mode}
              onChange={switchMode}
              items={[
                { value: "signin", label: "Sign in" },
                { value: "signup", label: "Create account" },
                { value: "recover", label: "Forgot" },
              ]}
            />

            {/* Method Toggle: Email + Password vs Passwordless Email Code */}
            {mode !== "recover" && (
              <div
                role="group"
                aria-label="Authentication method"
                className="grid grid-cols-2 gap-1.5 rounded-full border border-[var(--border)] bg-white/60 p-1"
              >
                <button
                  type="button"
                  onClick={() => switchMethod("password")}
                  className={`inline-flex min-h-[36px] items-center justify-center gap-1.5 rounded-full text-xs font-semibold transition-all ${
                    method === "password"
                      ? "bg-[var(--secondary)] text-[var(--foreground)] shadow-sm"
                      : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  <Lock className="h-3.5 w-3.5" />
                  With password
                </button>
                <button
                  type="button"
                  onClick={() => switchMethod("otp")}
                  className={`inline-flex min-h-[36px] items-center justify-center gap-1.5 rounded-full text-xs font-semibold transition-all ${
                    method === "otp"
                      ? "bg-[var(--secondary)] text-[var(--foreground)] shadow-sm"
                      : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
                  }`}
                >
                  <Mail className="h-3.5 w-3.5" />
                  Email code
                </button>
              </div>
            )}

            <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
              {mode === "signup" && method === "password" && (
                <label className="field">
                  Your name
                  <input
                    type="text"
                    required
                    autoComplete="name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="e.g., Ada Okafor"
                  />
                </label>
              )}

              <label className="field">
                Email address
                <input
                  type="email"
                  required
                  autoComplete="email"
                  disabled={method === "otp" && otpSent}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                />
              </label>

              {/* Password field */}
              {mode !== "recover" && method === "password" && (
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label htmlFor="auth-password" className="text-sm font-medium text-[var(--foreground)]">
                      Password
                    </label>
                    {mode === "signin" && (
                      <button
                        type="button"
                        onClick={() => switchMode("recover")}
                        className="text-xs font-medium text-[var(--primary)] hover:underline"
                      >
                        Forgot password?
                      </button>
                    )}
                  </div>
                  <div className="relative">
                    <input
                      id="auth-password"
                      type={showPassword ? "text" : "password"}
                      required
                      minLength={8}
                      autoComplete={mode === "signup" ? "new-password" : "current-password"}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder={mode === "signup" ? "At least 8 characters" : "Enter your password"}
                      className="w-full rounded-[calc(var(--radius)-2px)] border border-[var(--border)] bg-white/80 px-3.5 py-2.5 pr-10 text-sm text-[var(--foreground)] outline-none transition-all focus:border-[var(--primary)] focus:ring-2 focus:ring-[var(--ring)]/25"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((prev) => !prev)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
              )}

              {/* Passwordless 6-digit OTP code input */}
              {mode !== "recover" && method === "otp" && otpSent && (
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label htmlFor="auth-otp" className="text-sm font-medium text-[var(--foreground)]">
                      6-digit email code
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        setOtpSent(false);
                        setOtp("");
                        setNotice(null);
                      }}
                      className="text-xs font-medium text-[var(--primary)] hover:underline"
                    >
                      Change email
                    </button>
                  </div>
                  <input
                    id="auth-otp"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    required
                    value={otp}
                    onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="123456"
                    className="w-full rounded-[calc(var(--radius)-2px)] border border-[var(--border)] bg-white/80 px-3.5 py-2.5 text-center text-lg font-semibold tracking-[0.35em] text-[var(--foreground)] outline-none transition-all focus:border-[var(--primary)] focus:ring-2 focus:ring-[var(--ring)]/25"
                  />
                </div>
              )}

              <Button type="submit" disabled={busy} className="mt-1 w-full">
                {busy ? (
                  "Please wait…"
                ) : mode === "recover" ? (
                  <>
                    <KeyRound className="h-4 w-4" />
                    Send reset link
                  </>
                ) : method === "otp" ? (
                  otpSent ? (
                    "Verify code & continue"
                  ) : (
                    <>
                      <Mail className="h-4 w-4" />
                      Send 6-digit email code
                    </>
                  )
                ) : mode === "signup" ? (
                  "Create account"
                ) : (
                  "Sign in"
                )}
              </Button>

              {mode !== "recover" && method === "otp" && otpSent && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={sendEmailCode}
                  className="text-center text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:underline"
                >
                  Didn&apos;t receive a code? Resend
                </button>
              )}
            </form>

            {notice && (
              <div
                role="status"
                className="flex items-start gap-2.5 rounded-[var(--radius)] bg-[var(--sage)]/60 px-4 py-3 text-sm text-[var(--primary)]"
              >
                <MailCheck className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{notice}</span>
              </div>
            )}

            {error && (
              <p role="alert" className="rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
                {error}
              </p>
            )}

            <div className="border-t border-[var(--border)]/70 pt-4 text-center text-xs text-[var(--muted-foreground)]">
              {mode === "signin" ? (
                <>
                  New to Memory Lane?{" "}
                  <button
                    type="button"
                    onClick={() => switchMode("signup")}
                    className="font-semibold text-[var(--primary)] hover:underline"
                  >
                    Create an account
                  </button>
                </>
              ) : mode === "signup" ? (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => switchMode("signin")}
                    className="font-semibold text-[var(--primary)] hover:underline"
                  >
                    Sign in
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => switchMode("signin")}
                  className="inline-flex items-center gap-1 font-semibold text-[var(--primary)] hover:underline"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Back to sign in
                </button>
              )}
            </div>
          </GlassCard>

          <p className="mt-5 text-center text-xs text-[var(--muted-foreground)]">
            Invited as a guest? Use the share link your host sent you —{" "}
            <Link href="/how-it-works" className="underline">
              no account needed
            </Link>
            .
          </p>
        </FadeInUp>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen">
          <SiteHeader />
        </div>
      }
    >
      <LoginInner />
    </Suspense>
  );
}
