"use client";

import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { ThemeToggle } from "@/components/theme-toggle";

/** Public-facing marketing & auth header (no mobile app bottom dock). */
export function SiteHeader({
  ctaHref = "/login?mode=signup&next=/app/create",
  ctaLabel = "Start a space",
}: {
  ctaHref?: string;
  ctaLabel?: string;
}) {
  return (
    <header className="glass-nav sticky top-0 z-40">
      <div className="site-frame flex h-14 items-center justify-between gap-3 sm:h-16">
        <Link href="/" className="group inline-flex items-center">
          <BrandMark size="sm" className="sm:hidden" />
          <BrandMark size="md" className="hidden sm:inline-flex" />
        </Link>

        <nav
          aria-label="Primary"
          className="hidden items-center gap-7 text-sm font-medium text-[var(--muted-foreground)] md:flex"
        >
          <Link href="/#how-it-unfolds" className="transition-colors hover:text-[var(--foreground)]">
            How it works
          </Link>
          <Link href="/#occasions" className="transition-colors hover:text-[var(--foreground)]">
            Occasions
          </Link>
          <Link href="/how-it-works" className="transition-colors hover:text-[var(--foreground)]">
            Privacy
          </Link>
        </nav>

        <div className="flex items-center gap-1.5 sm:gap-2.5">
          <ThemeToggle />
          <Link
            href="/login?mode=signin&next=/app"
            className="inline-flex min-h-[36px] items-center rounded-full px-3 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] sm:min-h-[40px] sm:px-3.5 sm:text-sm"
          >
            Sign in
          </Link>
          <Link
            href={ctaHref}
            className="inline-flex min-h-[36px] items-center rounded-full bg-[var(--primary)] px-3.5 text-xs font-semibold text-[var(--primary-foreground)] shadow-sm transition-all duration-200 hover:brightness-110 hover:shadow-md active:scale-[0.97] sm:min-h-[40px] sm:px-4 sm:text-sm"
          >
            {ctaLabel}
          </Link>
        </div>
      </div>
    </header>
  );
}
