"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  Clock,
  Film,
  Home,
  Images,
  MessageSquareHeart,
  Plus,
  Settings2,
  Sparkles,
  Tv,
} from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { buildSpaceBottomTabs, MobileBottomNav } from "@/components/mobile-bottom-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { SiteHeader } from "@/components/site-header";
import { motion } from "@/components/ui/motion";
import { coverForOccasion, occasionLabel, themeClassForTokens } from "@/lib/covers";
import { ApiError, getSpace, type SpaceDetail } from "@/lib/spaces";
import { applyTokens, clearTokens, mergeTokens } from "@/lib/theme";

interface SpaceState {
  space: SpaceDetail;
  token: string | undefined;
  reload: () => void;
}

const SpaceContext = createContext<SpaceState | null>(null);

function storedToken(spaceId: string): string | undefined {
  try {
    return sessionStorage.getItem(`ml-guest-${spaceId}`) ?? undefined;
  } catch {
    return undefined;
  }
}

export function SpaceProvider({
  spaceId,
  children,
}: {
  spaceId: string;
  children: React.ReactNode;
}) {
  const searchParams = useSearchParams();
  const [token, setToken] = useState<string | undefined>(undefined);
  const [resolved, setResolved] = useState(false);
  const [detail, setDetail] = useState<SpaceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const fromUrl = searchParams.get("guest") ?? undefined;
    if (fromUrl) {
      try {
        sessionStorage.setItem(`ml-guest-${spaceId}`, fromUrl);
      } catch {
        /* private mode */
      }
      setToken(fromUrl);
    } else {
      setToken(storedToken(spaceId));
    }
    setResolved(true);
  }, [spaceId, searchParams]);

  useEffect(() => {
    if (!resolved) return;
    const controller = new AbortController();
    setDetail(null);
    setError(null);
    getSpace(spaceId, token, controller.signal).then(setDetail, (failure: unknown) => {
      if (controller.signal.aborted) return;
      setError(failure instanceof ApiError ? failure.message : "Could not load this space.");
    });
    return () => controller.abort();
  }, [spaceId, token, resolved, nonce]);

  useEffect(() => {
    if (detail) {
      applyTokens(mergeTokens(detail.theme.tokens));
    }
    return () => clearTokens();
  }, [detail]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  const value = useMemo(
    () => (detail ? { space: detail, token, reload } : null),
    [detail, token, reload],
  );

  if (error) {
    return (
      <div className="min-h-screen">
        <SiteHeader />
        <main className="site-frame py-16">
          <div role="alert" className="glass-panel mx-auto max-w-lg rounded-[var(--radius)] p-8 text-center">
            <p className="font-display text-2xl font-medium">This album isn&apos;t available</p>
            <p className="mt-2 text-sm text-[var(--muted-foreground)]">{error}</p>
          </div>
        </main>
      </div>
    );
  }
  if (!value) {
    return (
      <div className="min-h-screen">
        <SiteHeader />
        <main className="site-frame py-16">
          <div className="glass-panel mx-auto max-w-2xl animate-pulse rounded-[var(--radius)] p-10 text-center text-sm text-[var(--muted-foreground)]">
            Opening this memory space…
          </div>
        </main>
      </div>
    );
  }
  const themeClass = themeClassForTokens(detail?.theme?.tokens?.accent);
  const isStaff = detail?.my_role === "owner" || detail?.my_role === "collaborator";
  return (
    <SpaceContext.Provider value={value}>
      <div className={`min-h-screen pb-20 md:pb-0 ${themeClass}`}>
        <header className="glass-bar sticky top-0 z-40">
          <div className="site-frame flex h-16 items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Link
                href={isStaff ? "/app" : "/"}
                className="group inline-flex items-center"
              >
                <BrandMark size="sm" />
              </Link>
              {isStaff && (
                <Link
                  href="/app/spaces"
                  className="hidden rounded-full px-3 py-1 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--secondary)]/80 hover:text-[var(--foreground)] sm:inline-flex"
                >
                  All spaces
                </Link>
              )}
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              {isStaff ? (
                <>
                  <Link
                    href="/app/create"
                    className="hidden min-h-[38px] items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 text-xs font-semibold text-[var(--primary-foreground)] shadow-sm transition-all hover:brightness-110 sm:inline-flex"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    New space
                  </Link>
                  <Link
                    href="/app/account"
                    className="inline-flex min-h-[38px] items-center rounded-full border border-[var(--border)] bg-white/70 px-3.5 text-xs font-semibold text-[var(--foreground)] transition-colors hover:bg-white"
                  >
                    Account
                  </Link>
                </>
              ) : (
                <Link
                  href="/login?mode=signup&next=/app/create"
                  className="inline-flex min-h-[38px] items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 text-xs font-semibold text-[var(--primary-foreground)] shadow-sm transition-all hover:brightness-110"
                >
                  Start your own
                </Link>
              )}
            </div>
          </div>
        </header>
        {children}
        <MobileBottomNav
          tabs={buildSpaceBottomTabs(spaceId, isStaff)}
          guestToken={token}
        />
      </div>
    </SpaceContext.Provider>
  );
}

export function useSpace(): SpaceState {
  const state = useContext(SpaceContext);
  if (!state) throw new Error("useSpace must be used inside SpaceProvider");
  return state;
}

/** Link that carries the guest token so navigation never drops access. */
export function SpaceLink({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  const { token } = useSpace();
  const target = token ? `${href}?guest=${encodeURIComponent(token)}` : href;
  return (
    <Link href={target} className={className}>
      {children}
    </Link>
  );
}

function formatCountdown(targetIso: string): string | null {
  const diff = new Date(targetIso).getTime() - Date.now();
  if (diff <= 0) return null;
  const days = Math.floor(diff / 86_400_000);
  const hours = Math.floor((diff % 86_400_000) / 3_600_000);
  const mins = Math.floor((diff % 3_600_000) / 60_000);
  if (days > 0) return `${days}d ${hours}h`;
  return `${hours}h ${mins}m`;
}

export function SpaceCoverBand({ spaceId }: { spaceId: string }) {
  const { space } = useSpace();
  const detail = space.space;
  const canPost = space.my_permissions.includes("post");
  const when = detail.event_date
    ? new Date(`${detail.event_date}T12:00:00`).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;
  const countdown = detail.publish_at ? formatCountdown(detail.publish_at) : null;

  return (
    <section className="cover-band py-12 sm:py-16">
      <img
        src={coverForOccasion(detail.occasion)}
        alt={detail.title}
        className="cover-img"
      />
      <div className="h-1.5 w-full bg-[var(--space-tint)] opacity-90 absolute inset-x-0 top-0 z-10" />
      <div className="site-frame relative z-10 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl">
          <div className="flex flex-wrap items-center gap-2">
            <span className="glass-dark eyebrow rounded-full px-3 py-1 text-[var(--gold)]">
              {occasionLabel(detail.occasion)}
            </span>
            {when && (
              <span className="glass-dark rounded-full px-3 py-1 text-xs font-medium text-white/90">
                {when}
              </span>
            )}
            {detail.location_label && (
              <span className="glass-dark rounded-full px-3 py-1 text-xs font-medium text-white/90">
                {detail.location_label}
              </span>
            )}
          </div>
          <h1 className="mt-3 font-display text-4xl font-medium leading-[1.08] text-white sm:text-5xl">
            {detail.title}
          </h1>
          {detail.description && (
            <p className="mt-3 max-w-xl text-sm leading-relaxed text-white/85 sm:text-base">
              {detail.description}
            </p>
          )}
          <p className="mt-3 text-xs font-medium text-white/75">
            {space.stats.contributions} {space.stats.contributions === 1 ? "memory" : "memories"} ·{" "}
            {space.stats.contributors} {space.stats.contributors === 1 ? "contributor" : "contributors"}
          </p>
          {(space.preview || countdown) && (
            <div className="glass-dark mt-4 inline-flex items-center gap-2 rounded-full px-4 py-2 text-xs font-medium">
              <CalendarClock className="h-4 w-4 text-[var(--gold)]" />
              <span>
                {countdown
                  ? `Scheduled reveal in ${countdown} — guests can still contribute.`
                  : "Preview mode — visible to staff before reveal."}
              </span>
            </div>
          )}
        </div>

        {canPost && (
          <div className="shrink-0">
            <SpaceLink
              href={`/s/${spaceId}/contribute`}
              className="inline-flex min-h-[46px] items-center gap-2 rounded-full bg-white px-6 text-sm font-semibold text-[#17231B] shadow-lg transition-all duration-200 hover:scale-[1.02] hover:bg-[#FAF6EE] active:scale-[0.98]"
            >
              <Plus className="h-4 w-4" />
              Add your memory
            </SpaceLink>
          </div>
        )}
      </div>
    </section>
  );
}

const TABS = [
  { href: "", label: "Album", icon: Home },
  { href: "/gallery", label: "Gallery", icon: Images },
  { href: "/timeline", label: "Timeline", icon: Clock },
  { href: "/wall", label: "Live wall", icon: Tv },
  { href: "/slideshow", label: "Slideshow", icon: Film },
  { href: "/contribute", label: "Contribute", icon: MessageSquareHeart },
  { href: "/settings", label: "Curate & Share", icon: Settings2, staffOnly: true },
  { href: "/studio", label: "AI Studio", icon: Sparkles, staffOnly: true },
];

export function SpaceNav({ spaceId, active }: { spaceId: string; active: string }) {
  const { space } = useSpace();
  const staff = space.my_role === "owner" || space.my_role === "collaborator";
  return (
    <nav
      aria-label="Space sections"
      className="glass-panel mb-6 flex flex-wrap items-center gap-1 rounded-full p-1.5"
    >
      {TABS.filter((tab) => !("staffOnly" in tab) || staff).map((tab) => {
        const Icon = tab.icon;
        const isActive = active === tab.href;
        return (
          <SpaceLink
            key={tab.label}
            href={`/s/${spaceId}${tab.href}`}
            className={`relative inline-flex min-h-[38px] items-center gap-1.5 rounded-full px-3.5 text-xs font-semibold transition-colors sm:text-sm ${
              isActive
                ? "text-[var(--primary-foreground)]"
                : "text-[var(--foreground)]/75 hover:text-[var(--foreground)]"
            }`}
          >
            {isActive && (
              <motion.span
                layoutId="space-nav-pill"
                transition={{ type: "spring", stiffness: 420, damping: 32 }}
                className="absolute inset-0 rounded-full bg-[var(--primary)] shadow-sm"
              />
            )}
            <span className="relative z-10 inline-flex items-center gap-1.5">
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
            </span>
          </SpaceLink>
        );
      })}
    </nav>
  );
}
