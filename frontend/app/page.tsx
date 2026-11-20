import Link from "next/link";
import { ArrowRight, BookHeart, Link2, ShieldCheck, Sparkles } from "lucide-react";

import { ApiStatusCard } from "@/components/api-status-card";
import { SiteHeader } from "@/components/site-header";
import { FadeInUp, GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";

const PILLARS = [
  {
    icon: Link2,
    title: "Frictionless for guests",
    body: "Share one link or QR code. Friends and family contribute photos, videos, voice notes, and stories with zero sign-up or app download.",
  },
  {
    icon: ShieldCheck,
    title: "Curated calmly by you",
    body: "Review submissions in your private moderation queue, keep albums private or link-only, and schedule an emotional reveal date.",
  },
  {
    icon: BookHeart,
    title: "AI Memory Studio",
    body: "Turn real collected memories into heartfelt summaries, voice transcripts, captions, keepsake letters, memory books, and highlight films.",
  },
];

const SHOWCASE_OCCASIONS = [
  {
    slug: "wedding",
    badge: "Wedding",
    title: "Botanical Garden Celebration",
    subtitle: "Candid toasts, polaroids, and handwritten blessings from every table.",
    cover: "/covers/wedding.jpg",
    tint: "bg-[var(--sage)]",
  },
  {
    slug: "birthday",
    badge: "Birthday",
    title: "Milestone Birthday Keepsake",
    subtitle: "Voice notes, throwback photos, and heartfelt wishes unlocked at midnight.",
    cover: "/covers/birthday.jpg",
    tint: "bg-[var(--marigold)]",
  },
  {
    slug: "anniversary",
    badge: "Anniversary",
    title: "Golden Hour Years Together",
    subtitle: "Stories from family and friends woven into a digital memory book.",
    cover: "/covers/anniversary.jpg",
    tint: "bg-[var(--rose)]",
  },
  {
    slug: "family",
    badge: "Family",
    title: "Living Family Archive",
    subtitle: "Preserve voices, recipes, and heirloom photographs across generations.",
    cover: "/covers/family.jpg",
    tint: "bg-[var(--sage)]",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      <SiteHeader />

      {/* Atmospheric Full-Bleed Hero */}
      <section className="home-hero py-20 sm:py-28 lg:py-36">
        <img
          src="/covers/hero.jpg"
          alt="Warm candlelit celebration dinner table"
          className="cover-img"
        />
        <div className="site-frame relative z-10">
          <FadeInUp className="max-w-2xl">
            <span className="glass-dark eyebrow mb-6 inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[var(--gold)]">
              <Sparkles className="h-3.5 w-3.5" />
              A home for shared memories
            </span>
            <h1 className="font-display text-5xl font-medium leading-[1.04] tracking-tight text-[var(--primary-foreground)] sm:text-6xl lg:text-[76px]">
              Every memory in one warm place.
            </h1>
            <p className="mt-6 max-w-xl text-base leading-relaxed text-[var(--primary-foreground)]/85 sm:text-lg">
              Create a living memory album for weddings, birthdays, graduations, and family
              milestones. Guests share photos, voice notes, and stories with a single link—no
              account required.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3.5">
              <Link
                href="/login?mode=signup&next=/app/create"
                className="inline-flex min-h-[48px] items-center gap-2 rounded-full bg-[var(--primary-foreground)] px-6 text-sm font-semibold text-[var(--foreground)] shadow-lg transition-all duration-200 hover:scale-[1.02] hover:bg-white active:scale-[0.98]"
              >
                Start a space
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/login?mode=signin&next=/app"
                className="glass-dark inline-flex min-h-[48px] items-center gap-2 rounded-full px-6 text-sm font-medium transition-all duration-200 hover:bg-white/20 active:scale-[0.98]"
              >
                Open your spaces
              </Link>
            </div>
          </FadeInUp>
        </div>
      </section>

      {/* Feature Pillars (Floating Glass Cards) */}
      <section className="site-frame relative z-20 -mt-10 pb-16 sm:-mt-14">
        <StaggerGrid className="grid gap-5 md:grid-cols-3">
          {PILLARS.map((pillar) => {
            const Icon = pillar.icon;
            return (
              <StaggerItem key={pillar.title}>
                <GlassCard interactive className="flex h-full flex-col gap-3 p-6">
                  <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--sage)] text-[var(--primary)]">
                    <Icon className="h-5 w-5" />
                  </span>
                  <h2 className="font-display text-2xl font-medium text-[var(--foreground)]">
                    {pillar.title}
                  </h2>
                  <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
                    {pillar.body}
                  </p>
                </GlassCard>
              </StaggerItem>
            );
          })}
        </StaggerGrid>
      </section>

      {/* Editorial Occasion Showcase */}
      <section id="occasions" className="site-frame py-12 sm:py-16">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow text-[var(--bronze)]">Crafted for life&apos;s milestones</p>
            <h2 className="mt-2 font-display text-3xl font-medium leading-tight sm:text-4xl lg:text-[43px]">
              Albums that feel like fine stationery
            </h2>
          </div>
          <Link
            href="/how-it-works"
            className="glass-pill inline-flex min-h-[40px] items-center gap-1.5 rounded-full px-4 text-sm font-medium text-[var(--foreground)]"
          >
            See how it works
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <StaggerGrid className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {SHOWCASE_OCCASIONS.map((item) => (
            <StaggerItem key={item.slug}>
              <Link
                href={`/login?mode=signup&next=${encodeURIComponent(`/app/create?occasion=${item.slug}`)}`}
                className="space-card group flex h-full flex-col"
              >
                <div className="relative aspect-[16/10] overflow-hidden bg-[var(--shadow-ink)]">
                  <img
                    src={item.cover}
                    alt={item.title}
                    className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                  />
                  <span
                    className={`eyebrow absolute left-3 top-3 rounded-full px-2.5 py-1 text-[var(--foreground)] shadow-sm ${item.tint}`}
                  >
                    {item.badge}
                  </span>
                </div>
                <div className="flex flex-1 flex-col gap-2 p-5">
                  <h3 className="font-display text-xl font-medium text-[var(--foreground)]">
                    {item.title}
                  </h3>
                  <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
                    {item.subtitle}
                  </p>
                  <span className="mt-auto inline-flex items-center gap-1 pt-2 text-xs font-semibold text-[var(--primary)]">
                    Start this template
                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                  </span>
                </div>
              </Link>
            </StaggerItem>
          ))}
        </StaggerGrid>
      </section>

      {/* Footer + Live System Status */}
      <footer className="site-frame border-t border-[var(--border)] py-10">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-display text-lg font-medium">Memory Lane</p>
            <p className="text-xs text-[var(--muted-foreground)]">
              Backed by Neon PostgreSQL, Neon Auth, Neon Object Storage, and OpenRouter AI Studio.
            </p>
          </div>
          <div className="max-w-sm">
            <ApiStatusCard />
          </div>
        </div>
      </footer>
    </div>
  );
}
