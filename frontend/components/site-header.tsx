"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";

/** Public-facing marketing & auth header (no mobile app bottom dock). */
export function SiteHeader({
  ctaHref = "/login?mode=signup&next=/app/create",
  ctaLabel = "Create a space",
}: {
  ctaHref?: string;
  ctaLabel?: string;
}) {
  return (
    <header className="glass-nav sticky top-0 z-40">
      <div className="site-frame flex h-16 items-center justify-between gap-4">
        <Link href="/" className="group inline-flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--primary)] font-display text-sm font-semibold tracking-tight text-[var(--primary-foreground)] shadow-sm transition-transform duration-200 group-hover:scale-105">
            ML
          </span>
          <span className="font-display text-xl font-medium tracking-tight text-[var(--foreground)]">
            Memory Lane
          </span>
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-6 text-sm font-medium text-[var(--muted-foreground)] md:flex">
          <Link href="/how-it-works" className="transition-colors hover:text-[var(--foreground)]">
            How it works
          </Link>
          <Link href="/#occasions" className="transition-colors hover:text-[var(--foreground)]">
            Occasions
          </Link>
          <Link href="/login?mode=signin&next=/app" className="transition-colors hover:text-[var(--foreground)]">
            Go to App
          </Link>
        </nav>

        <div className="flex items-center gap-2.5">
          <Link
            href="/login?mode=signin&next=/app"
            className="inline-flex min-h-[40px] items-center rounded-full px-3.5 text-sm font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
          >
            Sign in
          </Link>
          <Link
            href={ctaHref}
            className="inline-flex min-h-[40px] items-center gap-1.5 rounded-full bg-[var(--primary)] px-4 text-sm font-medium text-[var(--primary-foreground)] shadow-sm transition-all duration-200 hover:brightness-110 hover:shadow-md active:scale-[0.97]"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {ctaLabel}
          </Link>
        </div>
      </div>
    </header>
  );
}
