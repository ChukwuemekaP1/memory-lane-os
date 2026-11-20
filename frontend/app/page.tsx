import Link from "next/link";
import {
  ArrowRight,
  BookHeart,
  CalendarClock,
  Link2,
  Mic,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { BrandMark } from "@/components/brand-mark";
import { SiteHeader } from "@/components/site-header";
import { FadeInUp, GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";

const SHOWCASE_OCCASIONS = [
  {
    slug: "wedding",
    badge: "Wedding",
    title: "Botanical Garden Vows",
    subtitle: "Candid toasts, polaroids & handwritten blessings from every table.",
    cover: "/covers/wedding.jpg",
  },
  {
    slug: "birthday",
    badge: "Birthday",
    title: "Milestone Birthday",
    subtitle: "Voice notes, throwbacks & wishes unlocked together at midnight.",
    cover: "/covers/birthday.jpg",
  },
  {
    slug: "anniversary",
    badge: "Anniversary",
    title: "Golden Hour Years",
    subtitle: "Stories from loved ones woven into a keepsake memory book.",
    cover: "/covers/anniversary.jpg",
  },
  {
    slug: "family",
    badge: "Family",
    title: "Living Heirloom Archive",
    subtitle: "Preserve voices, recipes & family portraits across generations.",
    cover: "/covers/family.jpg",
  },
];

const JOURNEY_STEPS = [
  {
    num: "01",
    icon: Link2,
    title: "Share a single link",
    body: "Send your album link on WhatsApp or print a QR code for the table. Guests drop photos, videos, and voice notes with zero sign-up.",
  },
  {
    num: "02",
    icon: ShieldCheck,
    title: "Curate at your own pace",
    body: "Approve submissions calmly, keep private host notes separate, and lock the album behind a scheduled reveal countdown.",
  },
  {
    num: "03",
    icon: BookHeart,
    title: "Craft lasting keepsakes",
    body: "Turn real guest memories into voice transcripts, warm summaries, keepsake letters, digital memory books, and highlight films.",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      <SiteHeader />

      {/* Editorial Atmospheric Hero — sleek on mobile, magazine-scale on desktop */}
      <section className="home-hero py-14 sm:py-24 lg:py-32">
        <img
          src="/covers/hero.jpg"
          alt="Warm candlelit celebration dinner table"
          className="cover-img"
        />
        <div className="site-frame relative z-10">
          <FadeInUp className="max-w-2xl">
            <span className="glass-dark eyebrow mb-4 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[var(--gold)] sm:mb-6 sm:px-3.5 sm:py-1.5">
              <Sparkles className="h-3 w-3" />
              Collaborative Keepsake Albums
            </span>
            <h1 className="font-display text-[40px] font-medium leading-[1.06] tracking-tight text-white sm:text-6xl lg:text-[72px]">
              Gather every voice, photo &amp; story in one warm place.
            </h1>
            <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-white/85 sm:mt-6 sm:text-lg">
              Create a private memory album for weddings, birthdays, graduations, and family
              milestones. Guests contribute in seconds from one link — no app or account needed.
            </p>
            <div className="mt-7 flex flex-col gap-2.5 sm:mt-9 sm:flex-row sm:items-center sm:gap-3.5">
              <Link
                href="/login?mode=signup&next=/app/create"
                className="inline-flex min-h-[46px] items-center justify-center gap-2 rounded-full bg-white px-6 text-sm font-semibold text-[#17231B] shadow-lg transition-all duration-200 hover:scale-[1.02] hover:bg-[#FAF6EE] active:scale-[0.98]"
              >
                Start a space
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/login?mode=signin&next=/app"
                className="glass-dark inline-flex min-h-[46px] items-center justify-center gap-2 rounded-full px-6 text-sm font-medium transition-all duration-200 hover:bg-white/20 active:scale-[0.98]"
              >
                Open your spaces
              </Link>
            </div>

            {/* Subtle editorial trust line */}
            <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-white/75 sm:mt-9">
              <span className="inline-flex items-center gap-1.5">
                <Mic className="h-3.5 w-3.5 text-[var(--gold)]" />
                Voice notes &amp; photos
              </span>
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5 text-[var(--gold)]" />
                Private by default
              </span>
              <span className="inline-flex items-center gap-1.5">
                <CalendarClock className="h-3.5 w-3.5 text-[var(--gold)]" />
                Scheduled reveals
              </span>
            </div>
          </FadeInUp>
        </div>
      </section>

      {/* Editorial Occasion Gallery — compact 2-up on mobile, 4-up on desktop with glass overlays */}
      <section id="occasions" className="site-frame py-12 sm:py-20">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3 sm:mb-10">
          <div>
            <p className="eyebrow text-[var(--bronze)]">Crafted for life&apos;s milestones</p>
            <h2 className="mt-1.5 font-display text-3xl font-medium leading-tight sm:text-4xl lg:text-[42px]">
              Albums that feel like fine stationery
            </h2>
          </div>
          <Link
            href="/how-it-works"
            className="glass-pill inline-flex min-h-[38px] items-center gap-1.5 rounded-full px-4 text-xs font-medium text-[var(--foreground)] sm:text-sm"
          >
            Explore privacy &amp; curation
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>

        <StaggerGrid className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
          {SHOWCASE_OCCASIONS.map((item) => (
            <StaggerItem key={item.slug}>
              <Link
                href={`/login?mode=signup&next=${encodeURIComponent(`/app/create?occasion=${item.slug}`)}`}
                className="group relative block aspect-[4/5] overflow-hidden rounded-2xl bg-[var(--shadow-ink)] shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-lg"
              >
                <img
                  src={item.cover}
                  alt={item.title}
                  className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/25 to-black/10" />
                <span className="glass-dark eyebrow absolute left-3 top-3 rounded-full px-2.5 py-1 text-[10px] text-[var(--gold)]">
                  {item.badge}
                </span>
                <div className="absolute inset-x-0 bottom-0 p-3.5 sm:p-5">
                  <h3 className="font-display text-lg font-medium leading-snug text-white sm:text-xl">
                    {item.title}
                  </h3>
                  <p className="mt-1 hidden text-xs leading-relaxed text-white/80 sm:block">
                    {item.subtitle}
                  </p>
                  <span className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--gold)] sm:text-xs">
                    Start album
                    <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-1" />
                  </span>
                </div>
              </Link>
            </StaggerItem>
          ))}
        </StaggerGrid>
      </section>

      {/* How a Memory Lane Unfolds — sleek horizontal editorial rhythm (compact on mobile) */}
      <section id="how-it-unfolds" className="site-frame py-8 sm:py-16">
        <div className="mb-6 max-w-xl sm:mb-10">
          <p className="eyebrow text-[var(--bronze)]">Thoughtfully paced</p>
          <h2 className="mt-1.5 font-display text-3xl font-medium leading-tight sm:text-4xl">
            Effortless for guests. Calmly guided by you.
          </h2>
        </div>

        <StaggerGrid className="grid gap-3.5 sm:gap-5 md:grid-cols-3">
          {JOURNEY_STEPS.map((step) => {
            const Icon = step.icon;
            return (
              <StaggerItem key={step.num}>
                <GlassCard
                  interactive
                  className="flex h-full flex-row items-start gap-4 p-4 sm:flex-col sm:gap-3 sm:p-6"
                >
                  <div className="flex shrink-0 items-center justify-between sm:w-full">
                    <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--sage)] text-[var(--primary)]">
                      <Icon className="h-4 w-4 sm:h-5 sm:w-5" />
                    </span>
                    <span className="hidden font-display text-2xl text-[var(--muted-foreground)]/40 sm:inline">
                      {step.num}
                    </span>
                  </div>
                  <div>
                    <h3 className="font-display text-xl font-medium text-[var(--foreground)] sm:text-2xl">
                      {step.title}
                    </h3>
                    <p className="mt-1 text-xs leading-relaxed text-[var(--muted-foreground)] sm:mt-1.5 sm:text-sm">
                      {step.body}
                    </p>
                  </div>
                </GlassCard>
              </StaggerItem>
            );
          })}
        </StaggerGrid>
      </section>

      {/* Closing Keepsake Invitation Band */}
      <section className="site-frame py-10 sm:py-16">
        <div className="cover-band rounded-2xl px-6 py-10 text-center shadow-md sm:px-12 sm:py-14">
          <img src="/covers/anniversary.jpg" alt="" className="cover-img" />
          <div className="relative z-10 mx-auto max-w-xl">
            <p className="eyebrow text-[var(--gold)]">Begin a keepsake</p>
            <h2 className="mt-2 font-display text-3xl font-medium leading-tight text-white sm:text-4xl">
              Your favorite stories deserve a quieter home than a group chat.
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-white/80">
              Create your first space in under a minute and invite loved ones whenever you&apos;re ready.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Link
                href="/login?mode=signup&next=/app/create"
                className="inline-flex min-h-[44px] items-center gap-2 rounded-full bg-white px-6 text-sm font-semibold text-[#17231B] shadow-md transition-all hover:scale-[1.02] hover:bg-[#FAF6EE]"
              >
                Create your first space
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Clean Editorial Footer (zero developer/infrastructure jargon) */}
      <footer className="site-frame border-t border-[var(--border)]/80 py-8 sm:py-10">
        <div className="flex flex-col items-start justify-between gap-5 sm:flex-row sm:items-center">
          <div>
            <BrandMark size="sm" />
            <p className="mt-2 text-xs text-[var(--muted-foreground)]">
              Timeless collaborative albums for the people and moments you love most.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-5 text-xs font-medium text-[var(--muted-foreground)]">
            <Link href="/how-it-works" className="transition-colors hover:text-[var(--foreground)]">
              How it works
            </Link>
            <Link href="/#occasions" className="transition-colors hover:text-[var(--foreground)]">
              Occasions
            </Link>
            <Link href="/login?mode=signin&next=/app" className="transition-colors hover:text-[var(--foreground)]">
              Sign in
            </Link>
            <Link href="/login?mode=signup&next=/app/create" className="transition-colors hover:text-[var(--foreground)]">
              Create a space
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
