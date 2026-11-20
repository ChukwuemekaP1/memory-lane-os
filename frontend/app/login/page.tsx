"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Lock,
  Mail,
  MailCheck,
  Mic,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { AnimatePresence, FadeInUp, GlassCard, motion } from "@/components/ui/motion";
import { apiRequest } from "@/lib/api";
import { clearCachedAuthToken, getAuthToken } from "@/lib/auth-provider";
import { neonAuthClient } from "@/lib/neon-auth-client";

type AuthMode = "signin" | "signup" | "recover";
type AuthMethod = "password" | "otp";

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/app";
  return raw;
}

function friendlyAuthError(raw: string | undefined, fallback: string): string {
  if (!raw) return fallback;
  const lower = raw.toLowerCase();
  if (lower.includes("invalid origin")) {
    return "This domain is not yet trusted for sign-in. Please refresh or use the primary application URL.";
  }
  if (lower.includes("invalid email or password") || lower.includes("invalid credentials")) {
    return "That email and password combination didn't match our records.";
  }
  if (lower.includes("already exists") || lower.includes("user already")) {
    return "An account with this email already exists. Try signing in or using a 6-digit email code.";
  }
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

  // Passwordless 6-digit email OTP state + resend cooldown
  const [otpSent, setOtpSent] = useState(false);
  const [otp, setOtp] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const otpInputRef = useRef<HTMLInputElement | null>(null);

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

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setInterval(() => {
      setCooldown((prev) => (prev <= 1 ? 0 : prev - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldown]);

  useEffect(() => {
    if (method === "otp" && otpSent) {
      window.setTimeout(() => otpInputRef.current?.focus(), 60);
    }
  }, [method, otpSent]);

  function switchMode(next: AuthMode) {
    setMode(next);
    if (next === "recover") {
      setMethod("password");
    }
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
        throw new Error(
          friendlyAuthError(
            body?.message,
            "Could not send a verification code right now. Please try again.",
          ),
        );
      }
      setOtpSent(true);
      setCooldown(30);
      setNotice(`We sent a 6-digit verification code to ${trimmedEmail}.`);
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
          throw new Error(
            friendlyAuthError(
              body?.message,
              "We couldn't start password recovery right now. Please try again.",
            ),
          );
        }
        setNotice(
          "If an account exists for that email address, we've sent a password reset link. Check your inbox and spam folder.",
        );
        return;
      }

      if (method === "otp") {
        if (!otpSent) {
          setBusy(false);
          await sendEmailCode();
          return;
        }
        const cleanedOtp = otp.trim();
        if (cleanedOtp.length !== 6) {
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
          throw new Error(
            friendlyAuthError(
              body?.message,
              "That code is invalid or expired. Please request a fresh code.",
            ),
          );
        }
        await apiRequest("/v1/auth/me").catch(() => undefined);
        router.push(nextPath);
        return;
      }

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
          throw new Error(
            friendlyAuthError(signUpErr.message, "Could not create your account."),
          );
        }
      } else {
        const { error: signInErr } = await neonAuthClient.signIn.email({
          email: trimmedEmail,
          password,
        });
        if (signInErr) {
          throw new Error(
            friendlyAuthError(signInErr.message, "Incorrect email or password."),
          );
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
    <div className="min-h-screen lg:grid lg:grid-cols-12">
      {/* Left Panel (Desktop Editorial Showcase) */}
      <aside
        aria-label="Memory Lane keepsake showcase"
        className="relative hidden overflow-hidden bg-[var(--shadow-ink)] lg:col-span-5 lg:flex lg:flex-col lg:justify-between lg:p-10 xl:col-span-6 xl:p-14"
      >
        <motion.img
          src="/covers/wedding.jpg"
          alt="Warm candlelit celebration table"
          initial={{ scale: 1.06 }}
          animate={{ scale: 1 }}
          transition={{ duration: 12, ease: "easeOut" }}
          className="absolute inset-0 h-full w-full object-cover opacity-80"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/45 to-black/30" />

        <div className="relative z-10 flex items-center justify-between">
          <Link href="/" className="group inline-flex items-center">
            <BrandMark size="md" inverted />
          </Link>
          <span className="glass-dark eyebrow rounded-full px-3 py-1 text-[var(--gold)]">
            Heirloom Atelier
          </span>
        </div>

        <div className="relative z-10 my-auto max-w-lg py-10">
          <p className="eyebrow text-[var(--gold)]">Timeless Keepsakes</p>
          <blockquote className="mt-3 font-display text-3xl font-medium leading-[1.16] text-white xl:text-4xl">
            &ldquo;Every voice note, toast, and candid photograph — gathered quietly in one living
            album.&rdquo;
          </blockquote>

          {/* Floating Keepsake Preview Card */}
          <div className="glass-dark mt-8 rounded-2xl p-5">
            <div className="flex items-center justify-between text-xs text-white/80">
              <span className="inline-flex items-center gap-1.5 font-semibold text-[var(--gold)]">
                <Sparkles className="h-3.5 w-3.5" />
                Botanical Garden Celebration
              </span>
              <span>48 memories · 19 voices</span>
            </div>
            <p className="mt-2.5 text-sm leading-relaxed text-white/90">
              Guests share from a single link or QR code without ever creating an account, while
              you curate and reveal the album on your schedule.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-white/75">
              <span className="inline-flex items-center gap-1.5">
                <Mic className="h-3.5 w-3.5 text-[var(--gold)]" />
                Voice transcripts
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5 text-[var(--gold)]" />
                Encrypted private media
              </span>
            </div>
          </div>
        </div>

        <div className="relative z-10 flex items-center justify-between text-xs text-white/65">
          <span>Memory Lane · Crafted for life&apos;s milestones</span>
          <Link href="/how-it-works" className="underline hover:text-white">
            How privacy works
          </Link>
        </div>
      </aside>

      {/* Right Panel (Focused Auth Sheet — Desktop & Mobile) */}
      <div className="flex min-h-screen flex-col justify-between px-4 py-5 sm:px-8 sm:py-8 lg:col-span-7 xl:col-span-6">
        {/* Top Minimal Utility Bar */}
        <header className="mx-auto flex w-full max-w-md items-center justify-between lg:max-w-lg">
          <Link
            href="/"
            className="group inline-flex items-center gap-2 text-xs font-semibold text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          >
            <span className="lg:hidden">
              <BrandMark size="sm" />
            </span>
            <span className="hidden items-center gap-1.5 lg:inline-flex">
              <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
              Back to home
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
          </div>
        </header>

        {/* Centered Single-Focus Auth Card */}
        <main className="mx-auto my-auto w-full max-w-[420px] py-6">
          <FadeInUp>
            <GlassCard className="relative overflow-hidden p-6 sm:p-8">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={`${mode}-${method}-${otpSent ? "verify" : "entry"}`}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                  className="flex flex-col gap-5"
                >
                  {/* Heading */}
                  <div>
                    <p className="eyebrow text-[var(--bronze)]">
                      {mode === "signup"
                        ? "Host Registration"
                        : mode === "recover"
                          ? "Account Recovery"
                          : method === "otp"
                            ? "Passwordless Sign-In"
                            : "Host Sign-In"}
                    </p>
                    <h1 className="mt-1.5 font-display text-3xl font-medium tracking-tight text-[var(--foreground)]">
                      {mode === "signup"
                        ? "Create your account"
                        : mode === "recover"
                          ? "Reset your password"
                          : method === "otp"
                            ? otpSent
                              ? "Check your inbox"
                              : "Sign in with email code"
                            : "Welcome back"}
                    </h1>
                    <p className="mt-1.5 text-sm leading-relaxed text-[var(--muted-foreground)]">
                      {mode === "signup"
                        ? "Start curating keepsake albums in seconds. Guests never need an account."
                        : mode === "recover"
                          ? "Enter the email you registered with and we'll send a reset link."
                          : method === "otp"
                            ? otpSent
                              ? `Enter the 6-digit code sent to ${email.trim()}.`
                              : "We'll send a one-time 6-digit code straight to your email."
                            : "Enter your credentials to open your memory spaces and AI Studio."}
                    </p>
                  </div>

                  {/* Main Form */}
                  <form onSubmit={handleSubmit} method="POST" className="flex flex-col gap-4">
                    {mode === "signup" && method === "password" && (
                      <div className="field">
                        <label htmlFor="full-name">Your name</label>
                        <input
                          id="full-name"
                          name="full-name"
                          type="text"
                          required
                          autoComplete="name"
                          enterKeyHint="next"
                          value={name}
                          onChange={(event) => setName(event.target.value)}
                          placeholder="e.g., Ada Okafor"
                        />
                      </div>
                    )}

                    {/* Email Input (hidden once OTP is sent so focus stays on the 6-digit code) */}
                    {!(method === "otp" && otpSent) && (
                      <div className="field">
                        <label htmlFor="email">Email address</label>
                        <input
                          id="email"
                          name="email"
                          type="email"
                          required
                          spellCheck={false}
                          autoComplete="username"
                          enterKeyHint={method === "otp" || mode === "recover" ? "done" : "next"}
                          value={email}
                          onChange={(event) => setEmail(event.target.value)}
                          placeholder="you@example.com"
                        />
                      </div>
                    )}

                    {/* Password Input */}
                    {mode !== "recover" && method === "password" && (
                      <div className="field">
                        <div className="flex items-center justify-between">
                          <label htmlFor="auth-password">Password</label>
                          {mode === "signin" && (
                            <button
                              type="button"
                              onClick={() => switchMode("recover")}
                              className="text-xs font-medium text-[var(--primary)] transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                            >
                              Forgot password?
                            </button>
                          )}
                        </div>
                        <div className="relative">
                          <input
                            id="auth-password"
                            name="password"
                            type={showPassword ? "text" : "password"}
                            required
                            minLength={8}
                            autoComplete={mode === "signup" ? "new-password" : "current-password"}
                            enterKeyHint="done"
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            placeholder={
                              mode === "signup" ? "At least 8 characters" : "Enter your password"
                            }
                            className="pr-11"
                          />
                          <button
                            type="button"
                            onClick={() => setShowPassword((prev) => !prev)}
                            aria-label={showPassword ? "Hide password" : "Show password"}
                            aria-pressed={showPassword}
                            className="absolute right-2.5 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                          >
                            {showPassword ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Single-Input Visually Segmented 6-Digit OTP Control per `sms-otp-form` */}
                    {mode !== "recover" && method === "otp" && otpSent && (
                      <div className="flex flex-col gap-2">
                        <div className="flex items-center justify-between">
                          <label
                            htmlFor="otp-input"
                            className="text-sm font-semibold text-[var(--foreground)]"
                          >
                            Verification code
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
                        <p
                          id="otp-format-hint"
                          className="text-xs text-[var(--muted-foreground)]"
                        >
                          Enter or paste the 6-digit numeric code from your email.
                        </p>

                        {/* Visual 6-slot display backed by a single semantic <input> for native autofill & paste */}
                        <div className="relative mt-1">
                          <div
                            aria-hidden="true"
                            className="pointer-events-none grid grid-cols-6 gap-2"
                          >
                            {[0, 1, 2, 3, 4, 5].map((idx) => {
                              const char = otp[idx] ?? "";
                              const isCurrent = otp.length === idx || (otp.length === 6 && idx === 5);
                              return (
                                <div
                                  key={idx}
                                  className={`flex h-12 items-center justify-center rounded-[var(--radius)] border font-mono text-lg font-semibold transition-all ${
                                    char
                                      ? "border-[var(--primary)] bg-[var(--sage)]/35 text-[var(--foreground)]"
                                      : isCurrent
                                        ? "border-[var(--ring)] bg-[var(--card)] ring-2 ring-[var(--ring)]/20"
                                        : "border-[var(--border)] bg-[var(--card)]/70 text-[var(--muted-foreground)]"
                                  }`}
                                >
                                  {char || "·"}
                                </div>
                              );
                            })}
                          </div>
                          <input
                            ref={otpInputRef}
                            id="otp-input"
                            name="otp"
                            type="text"
                            inputMode="numeric"
                            autoComplete="one-time-code"
                            pattern="\d{6}"
                            maxLength={6}
                            aria-describedby="otp-format-hint"
                            enterKeyHint="done"
                            required
                            value={otp}
                            onChange={(event) => {
                              const cleaned = event.target.value.replace(/\D/g, "").slice(0, 6);
                              setOtp(cleaned);
                            }}
                            className="absolute inset-0 h-12 w-full cursor-text opacity-0"
                          />
                        </div>

                        <div className="mt-1 flex items-center justify-between text-xs text-[var(--muted-foreground)]">
                          <span>Didn&apos;t receive the email?</span>
                          <button
                            type="button"
                            disabled={busy || cooldown > 0}
                            onClick={sendEmailCode}
                            className="font-semibold text-[var(--primary)] disabled:opacity-50 hover:underline"
                          >
                            {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend code"}
                          </button>
                        </div>
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
                          <>
                            <CheckCircle2 className="h-4 w-4" />
                            Verify code
                          </>
                        ) : (
                          <>
                            <Mail className="h-4 w-4" />
                            Send 6-digit email code
                          </>
                        )
                      ) : mode === "signup" ? (
                        <>
                          Create account
                          <ArrowRight className="h-4 w-4" />
                        </>
                      ) : (
                        <>
                          Sign in
                          <ArrowRight className="h-4 w-4" />
                        </>
                      )}
                    </Button>
                  </form>

                  {/* Notice & Error Feedback */}
                  {notice && (
                    <div
                      role="status"
                      className="flex items-start gap-2.5 rounded-[var(--radius)] border border-[var(--primary)]/25 bg-[var(--sage)]/55 px-4 py-3 text-sm text-[var(--foreground)]"
                    >
                      <MailCheck className="mt-0.5 h-4 w-4 shrink-0 text-[var(--primary)]" />
                      <span>{notice}</span>
                    </div>
                  )}

                  {error && (
                    <p
                      role="alert"
                      className="rounded-[var(--radius)] border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700 dark:text-red-300"
                    >
                      {error}
                    </p>
                  )}

                  {/* Subtle Secondary Method Switcher (replaces the old stacked button rows) */}
                  {mode !== "recover" && (
                    <div className="flex flex-col gap-3 pt-1">
                      <div className="relative flex items-center justify-center">
                        <div className="w-full border-t border-[var(--border)]/80" />
                        <span className="bg-[var(--card)] px-3 text-[11px] font-medium uppercase tracking-widest text-[var(--muted-foreground)]">
                          or
                        </span>
                      </div>

                      <button
                        type="button"
                        onClick={() => switchMethod(method === "password" ? "otp" : "password")}
                        className="glass-pill inline-flex min-h-[42px] w-full items-center justify-center gap-2 rounded-full px-4 text-xs font-semibold text-[var(--foreground)] transition-all hover:border-[var(--ring)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
                      >
                        {method === "password" ? (
                          <>
                            <Mail className="h-3.5 w-3.5 text-[var(--primary)]" />
                            {mode === "signup"
                              ? "Continue with a 6-digit email code instead"
                              : "Sign in with a 6-digit email code"}
                          </>
                        ) : (
                          <>
                            <Lock className="h-3.5 w-3.5 text-[var(--primary)]" />
                            Use email &amp; password instead
                          </>
                        )}
                      </button>
                    </div>
                  )}

                  {/* Mode Switcher Footer Link */}
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
                </motion.div>
              </AnimatePresence>
            </GlassCard>

            <p className="mt-5 text-center text-xs text-[var(--muted-foreground)]">
              Invited to contribute to someone&apos;s album? Use their share link —{" "}
              <Link href="/how-it-works" className="underline hover:text-[var(--foreground)]">
                guests never need an account
              </Link>
              .
            </p>
          </FadeInUp>
        </main>

        <footer className="mx-auto flex w-full max-w-md items-center justify-between text-[11px] text-[var(--muted-foreground)] lg:max-w-lg">
          <span>&copy; {new Date().getFullYear()} Memory Lane</span>
          <Link href="/how-it-works" className="hover:underline">
            Privacy &amp; Curation
          </Link>
        </footer>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center text-sm text-[var(--muted-foreground)]">
          Loading…
        </div>
      }
    >
      <LoginInner />
    </Suspense>
  );
}
