"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Check,
  Globe,
  KeyRound,
  Lock,
  LogOut,
  Palette,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from "lucide-react";

import { ThemePreferencePicker } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { FadeInUp, GlassCard } from "@/components/ui/motion";
import { apiRequest } from "@/lib/api";
import { signOutCurrentUser } from "@/lib/auth-provider";
import { EDITORIAL_THEMES } from "@/lib/covers";
import {
  DEFAULT_PREFERENCES,
  loadUserPreferences,
  saveUserPreferences,
  type UserPreferences,
} from "@/lib/preferences";

type MeUser = {
  id: string;
  email: string;
  display_name: string;
  email_verified_at: string | null;
  role_global: string;
};

export default function AppAccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<MeUser | null>(null);
  const [prefs, setPrefs] = useState<UserPreferences>(DEFAULT_PREFERENCES);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  useEffect(() => {
    setPrefs(loadUserPreferences());
    apiRequest<{ actor: { user?: MeUser } | null }>("/v1/auth/me")
      .then((res) => setUser(res.actor?.user ?? null))
      .catch(() => undefined);
  }, []);

  function updatePref<K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) {
    setPrefs((curr) => {
      const next = { ...curr, [key]: value };
      saveUserPreferences(next);
      return next;
    });
    setSavedNotice("Preferences saved — new spaces will use these defaults.");
    window.setTimeout(() => setSavedNotice(null), 2600);
  }

  async function handleSignOut() {
    await signOutCurrentUser();
    router.push("/");
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <FadeInUp>
        <p className="eyebrow text-[var(--bronze)]">Account &amp; Settings</p>
        <h1 className="mt-1 font-display text-4xl font-medium">Your profile &amp; preferences</h1>
      </FadeInUp>

      {savedNotice && (
        <p
          role="status"
          className="rounded-[var(--radius)] border border-[var(--primary)]/20 bg-[var(--sage)]/65 px-4 py-3 text-sm font-medium text-[var(--primary)]"
        >
          {savedNotice}
        </p>
      )}

      {/* Profile & Identity */}
      <GlassCard className="flex flex-col gap-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--primary)] font-display text-xl font-medium text-[var(--primary-foreground)] shadow-sm">
              {(user?.display_name || "M").slice(0, 2).toUpperCase()}
            </span>
            <div>
              <h2 className="font-display text-2xl font-medium">
                {user?.display_name ?? "Memory Lane Host"}
              </h2>
              <p className="text-sm text-[var(--muted-foreground)]">{user?.email ?? "Signed in"}</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--sage)] px-3 py-1 text-xs font-semibold text-[var(--primary)]">
            <UserCheck className="h-3.5 w-3.5" />
            Verified Host
          </span>
        </div>
      </GlassCard>

      {/* Appearance (Light / Dark / System Color Scheme) */}
      <GlassCard className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-[var(--primary)]" />
          <h2 className="font-display text-2xl font-medium">Appearance</h2>
        </div>
        <p className="text-sm text-[var(--muted-foreground)]">
          Choose between warm linen paper, candlelit obsidian dark mode, or your device preference.
        </p>
        <ThemePreferencePicker />
      </GlassCard>

      {/* Default Editorial Theme */}
      <GlassCard className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-2">
          <Palette className="h-5 w-5 text-[var(--primary)]" />
          <h2 className="font-display text-2xl font-medium">Default album theme</h2>
        </div>
        <p className="text-sm text-[var(--muted-foreground)]">
          Pre-selected automatically whenever you create a new memory space.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          {EDITORIAL_THEMES.map((preset) => {
            const active = prefs.defaultTheme === preset.name;
            return (
              <button
                key={preset.name}
                type="button"
                onClick={() => updatePref("defaultTheme", preset.name)}
                className={`flex flex-col gap-2 rounded-[var(--radius)] border p-4 text-left transition-all ${
                  active
                    ? "border-[var(--primary)] bg-white/90 shadow-sm ring-2 ring-[var(--ring)]/30"
                    : "border-[var(--border)] bg-white/55 hover:border-[var(--ring)]"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className="h-6 w-6 rounded-full border border-black/10"
                    style={{ background: preset.swatchVar }}
                  />
                  {active && <Check className="h-4 w-4 text-[var(--primary)]" />}
                </div>
                <span className="font-display text-base font-medium">{preset.name}</span>
                <span className="text-xs text-[var(--muted-foreground)]">{preset.description}</span>
              </button>
            );
          })}
        </div>
      </GlassCard>

      {/* Default Privacy, Moderation & AI Preferences */}
      <GlassCard className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-[var(--primary)]" />
          <h2 className="font-display text-2xl font-medium">Default privacy &amp; studio settings</h2>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={prefs.defaultVisibility === "link" ? "primary" : "secondary"}
            onClick={() => updatePref("defaultVisibility", "link")}
          >
            <Globe className="h-4 w-4" />
            Default: Anyone with link
          </Button>
          <Button
            type="button"
            variant={prefs.defaultVisibility === "private" ? "primary" : "secondary"}
            onClick={() => updatePref("defaultVisibility", "private")}
          >
            <Lock className="h-4 w-4" />
            Default: Private album
          </Button>
        </div>

        <label className="flex cursor-pointer items-start gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-white/60 p-4 text-sm">
          <input
            type="checkbox"
            checked={prefs.defaultAiOptIn}
            onChange={(e) => updatePref("defaultAiOptIn", e.target.checked)}
            className="mt-1 h-4 w-4 accent-[var(--primary)]"
          />
          <span>
            <strong className="inline-flex items-center gap-1.5 font-semibold">
              <Sparkles className="h-3.5 w-3.5 text-[var(--primary)]" />
              Enable AI Memory Studio by default
            </strong>
            <span className="block text-xs text-[var(--muted-foreground)]">
              Automatically opt new spaces into AI summaries, transcripts, and keepsakes.
            </span>
          </span>
        </label>

        <label className="flex cursor-pointer items-start gap-3 rounded-[var(--radius)] border border-[var(--border)] bg-white/60 p-4 text-sm">
          <input
            type="checkbox"
            checked={prefs.defaultAllowAnonymous}
            onChange={(e) => updatePref("defaultAllowAnonymous", e.target.checked)}
            className="mt-1 h-4 w-4 accent-[var(--primary)]"
          />
          <span>
            <strong className="font-semibold">Allow anonymous guest submissions</strong>
            <span className="block text-xs text-[var(--muted-foreground)]">
              Let guests share heartfelt notes anonymously when they prefer.
            </span>
          </span>
        </label>

        <label className="field max-w-xs">
          Default timezone
          <select
            value={prefs.timezone}
            onChange={(e) => updatePref("timezone", e.target.value)}
          >
            <option value="Africa/Lagos">Africa/Lagos (WAT)</option>
            <option value="UTC">UTC</option>
            <option value="Europe/London">Europe/London (GMT/BST)</option>
            <option value="America/New_York">America/New_York (EST/EDT)</option>
            <option value="America/Los_Angeles">America/Los_Angeles (PST/PDT)</option>
          </select>
        </label>
      </GlassCard>

      {/* Session & Security */}
      <GlassCard className="flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <h2 className="font-display text-2xl font-medium">Security &amp; session</h2>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            Update your password or sign out of this browser.
          </p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <Link
            href="/login?mode=recover"
            className="glass-pill inline-flex min-h-[44px] items-center gap-1.5 rounded-[var(--radius)] px-4 text-sm font-medium"
          >
            <KeyRound className="h-4 w-4" />
            Reset password
          </Link>
          <Button type="button" variant="destructive" onClick={handleSignOut}>
            <LogOut className="h-4 w-4" />
            Sign out
          </Button>
        </div>
      </GlassCard>
    </div>
  );
}
