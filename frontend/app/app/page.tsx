"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  FolderHeart,
  Plus,
  Settings2,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";

import { FadeInUp, GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";
import { ApiError, apiRequest } from "@/lib/api";
import { coverForOccasion, occasionLabel } from "@/lib/covers";
import { listMySpaces } from "@/lib/spaces";

type MePayload = {
  actor: {
    user?: { id: string; email: string; display_name: string };
  } | null;
};

type SpaceEntry = {
  space: { id: string; title: string; occasion?: string; event_date?: string | null };
  my_role: string;
};

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function AppHomePage() {
  const [userName, setUserName] = useState<string | null>(null);
  const [spaces, setSpaces] = useState<SpaceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [unauthorized, setUnauthorized] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await apiRequest<MePayload>("/v1/auth/me").catch(() => null);
        if (!cancelled) {
          setUserName(me?.actor?.user?.display_name ?? null);
        }
        const mine = await listMySpaces(false);
        if (!cancelled) {
          setSpaces(mine as SpaceEntry[]);
          setLoading(false);
        }
      } catch (failure: unknown) {
        if (cancelled) return;
        if (failure instanceof ApiError && failure.status === 401) {
          setUnauthorized(true);
        }
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (unauthorized) {
    return (
      <GlassCard className="mx-auto max-w-md p-8 text-center">
        <p className="font-display text-2xl font-medium">Sign in to enter Memory Lane</p>
        <p className="mt-2 text-sm text-[var(--muted-foreground)]">
          Access your albums, curation queue, and OpenRouter AI Memory Studio.
        </p>
        <div className="mt-5">
          <Link
            href="/login?mode=signin&next=/app"
            className="inline-flex min-h-[44px] items-center gap-2 rounded-full bg-[var(--primary)] px-6 text-sm font-medium text-[var(--primary-foreground)]"
          >
            Sign in
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </GlassCard>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      {/* Personalized Greeting Banner */}
      <FadeInUp className="cover-band rounded-2xl p-7 shadow-md sm:p-9">
        <img src="/covers/hero.jpg" alt="" className="cover-img" />
        <div className="relative z-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="eyebrow text-[var(--gold)]">Memory Lane Home</p>
            <h1 className="mt-2 font-display text-3xl font-medium leading-tight text-white sm:text-5xl">
              {greeting()}
              {userName ? `, ${userName.split(" ")[0]}` : ""}.
            </h1>
            <p className="mt-2 max-w-lg text-sm text-white/80">
              Your living keepsakes, guest contributions, and AI Memory Studio — all in one warm place.
            </p>
          </div>
          <div className="flex flex-wrap gap-2.5">
            <span className="glass-dark rounded-full px-4 py-2 text-xs font-semibold">
              {spaces.length} {spaces.length === 1 ? "active space" : "active spaces"}
            </span>
            <Link
              href="/app/create"
              className="inline-flex min-h-[40px] items-center gap-1.5 rounded-full bg-[var(--primary-foreground)] px-5 text-xs font-semibold text-[var(--foreground)] shadow transition-transform hover:scale-[1.02] active:scale-[0.98]"
            >
              <Plus className="h-4 w-4" />
              New space
            </Link>
          </div>
        </div>
      </FadeInUp>

      {/* Quick Actions */}
      <section aria-label="Quick actions">
        <StaggerGrid className="grid gap-4 sm:grid-cols-3">
          <StaggerItem>
            <Link href="/app/create" className="block h-full">
              <GlassCard interactive className="flex h-full items-center gap-4 p-5">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--sage)] text-[var(--primary)]">
                  <Plus className="h-5 w-5" />
                </span>
                <div>
                  <p className="font-display text-lg font-medium">Create a space</p>
                  <p className="text-xs text-[var(--muted-foreground)]">Launch a new album in 3 steps</p>
                </div>
              </GlassCard>
            </Link>
          </StaggerItem>
          <StaggerItem>
            <Link href="/app/studio" className="block h-full">
              <GlassCard interactive className="flex h-full items-center gap-4 p-5">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--marigold)] text-[var(--foreground)]">
                  <Sparkles className="h-5 w-5" />
                </span>
                <div>
                  <p className="font-display text-lg font-medium">AI Memory Studio</p>
                  <p className="text-xs text-[var(--muted-foreground)]">Summaries, transcripts &amp; films</p>
                </div>
              </GlassCard>
            </Link>
          </StaggerItem>
          <StaggerItem>
            <Link href="/app/account" className="block h-full">
              <GlassCard interactive className="flex h-full items-center gap-4 p-5">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--rose)] text-[var(--foreground)]">
                  <SlidersHorizontal className="h-5 w-5" />
                </span>
                <div>
                  <p className="font-display text-lg font-medium">Account &amp; Defaults</p>
                  <p className="text-xs text-[var(--muted-foreground)]">Themes, privacy &amp; preferences</p>
                </div>
              </GlassCard>
            </Link>
          </StaggerItem>
        </StaggerGrid>
      </section>

      {/* Recent Spaces */}
      <section aria-label="Recent spaces" className="flex flex-col gap-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="eyebrow text-[var(--bronze)]">Your collection</p>
            <h2 className="mt-1 font-display text-3xl font-medium">Recent memory spaces</h2>
          </div>
          <Link
            href="/app/spaces"
            className="glass-pill inline-flex min-h-[38px] items-center gap-1.5 rounded-full px-4 text-xs font-semibold"
          >
            <FolderHeart className="h-3.5 w-3.5" />
            View all
          </Link>
        </div>

        {loading ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((n) => (
              <div key={n} className="glass-panel h-60 animate-pulse rounded-[var(--radius)]" />
            ))}
          </div>
        ) : spaces.length === 0 ? (
          <GlassCard className="p-10 text-center">
            <p className="font-display text-2xl font-medium">Start your first memory album</p>
            <p className="mt-2 text-sm text-[var(--muted-foreground)]">
              Pick an occasion, share one guest link, and watch photos, voice notes, and stories arrive.
            </p>
            <div className="mt-5">
              <Link
                href="/app/create"
                className="inline-flex min-h-[44px] items-center gap-2 rounded-full bg-[var(--primary)] px-6 text-sm font-medium text-[var(--primary-foreground)]"
              >
                <Plus className="h-4 w-4" />
                Create your first space
              </Link>
            </div>
          </GlassCard>
        ) : (
          <StaggerGrid className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {spaces.slice(0, 6).map((entry) => (
              <StaggerItem key={entry.space.id}>
                <article className="space-card group flex h-full flex-col">
                  <Link
                    href={`/s/${entry.space.id}`}
                    className="relative aspect-[16/10] overflow-hidden bg-[var(--shadow-ink)]"
                  >
                    <img
                      src={coverForOccasion(entry.space.occasion)}
                      alt={entry.space.title}
                      className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                    />
                    <span className="glass-dark eyebrow absolute left-3 top-3 rounded-full px-2.5 py-1 text-[var(--gold)]">
                      {occasionLabel(entry.space.occasion)}
                    </span>
                  </Link>
                  <div className="flex flex-1 flex-col gap-3 p-5">
                    <Link href={`/s/${entry.space.id}`}>
                      <h3 className="font-display text-2xl font-medium transition-colors group-hover:text-[var(--primary)]">
                        {entry.space.title}
                      </h3>
                    </Link>
                    <div className="mt-auto flex flex-wrap gap-2 pt-1">
                      <Link
                        href={`/s/${entry.space.id}`}
                        className="glass-pill inline-flex min-h-[36px] items-center gap-1 rounded-full px-3 text-xs font-semibold"
                      >
                        Album
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                      <Link
                        href={`/s/${entry.space.id}/settings`}
                        className="glass-pill inline-flex min-h-[36px] items-center gap-1 rounded-full px-3 text-xs font-medium text-[var(--muted-foreground)]"
                      >
                        <Settings2 className="h-3.5 w-3.5" />
                        Curate
                      </Link>
                      <Link
                        href={`/s/${entry.space.id}/studio`}
                        className="glass-pill inline-flex min-h-[36px] items-center gap-1 rounded-full px-3 text-xs font-medium text-[var(--primary)]"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        Studio
                      </Link>
                    </div>
                  </div>
                </article>
              </StaggerItem>
            ))}
          </StaggerGrid>
        )}
      </section>
    </div>
  );
}
