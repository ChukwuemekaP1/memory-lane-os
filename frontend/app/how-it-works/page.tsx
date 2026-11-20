import Link from "next/link";
import { ArrowRight, CalendarClock, Lock, Send, Sparkles, UserCheck } from "lucide-react";

import { SiteHeader } from "@/components/site-header";
import { FadeInUp, GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";

const STEPS = [
  {
    step: "01",
    icon: Sparkles,
    title: "Create a space in under a minute",
    body: "Choose your occasion, add a warm welcome prompt, pick Botanical, Terracotta, or Golden Hour styling, and choose whether the album is link-visible or private.",
  },
  {
    step: "02",
    icon: Send,
    title: "Guests contribute without registering",
    body: "Share your guest contribution link via WhatsApp, invitations, or QR code. Guests drop photos, videos, voice notes, or written stories—optionally anonymously—without ever creating a password.",
  },
  {
    step: "03",
    icon: UserCheck,
    title: "Calm host curation & privacy",
    body: "Every submission lands in your owner cockpit. Approve or hide memories in one click, keep private host-only notes out of shared views, and keep all media encrypted in private object storage.",
  },
  {
    step: "04",
    icon: CalendarClock,
    title: "Scheduled reveals & AI Keepsake Studio",
    body: "Lock the album with a countdown until the big day, then use the OpenRouter-powered AI Studio to craft summaries, transcripts, memory letters, digital books, and highlight films.",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="min-h-screen pb-20">
      <SiteHeader />

      <section className="site-frame py-14 sm:py-20">
        <FadeInUp className="max-w-2xl">
          <p className="eyebrow text-[var(--bronze)]">Two-sided privacy &amp; curation</p>
          <h1 className="mt-3 font-display text-4xl font-medium leading-[1.1] sm:text-5xl">
            Effortless for guests. Calmly controlled by you.
          </h1>
          <p className="mt-4 text-base leading-relaxed text-[var(--muted-foreground)]">
            Memory Lane separates guest contribution links from owner curation—so loved ones can
            share freely while you protect privacy, moderate submissions, and decide when to reveal
            the finished album.
          </p>
        </FadeInUp>

        <StaggerGrid className="mt-12 grid gap-6 md:grid-cols-2">
          {STEPS.map((item) => {
            const Icon = item.icon;
            return (
              <StaggerItem key={item.step}>
                <GlassCard interactive className="flex h-full flex-col gap-3 p-7">
                  <div className="flex items-center justify-between">
                    <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--sage)] text-[var(--primary)]">
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="font-display text-2xl text-[var(--muted-foreground)]/50">
                      {item.step}
                    </span>
                  </div>
                  <h2 className="font-display text-2xl font-medium">{item.title}</h2>
                  <p className="text-sm leading-relaxed text-[var(--muted-foreground)]">
                    {item.body}
                  </p>
                </GlassCard>
              </StaggerItem>
            );
          })}
        </StaggerGrid>

        <GlassCard className="mt-12 flex flex-col items-start justify-between gap-6 p-8 sm:flex-row sm:items-center">
          <div className="flex items-start gap-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[var(--marigold)] text-[var(--foreground)]">
              <Lock className="h-5 w-5" />
            </span>
            <div>
              <h2 className="font-display text-2xl font-medium">Private by default</h2>
              <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                Original photos, videos, and voice notes stay in private Neon Object Storage behind
                short-lived signed URLs. Private owner messages never enter shared AI processing.
              </p>
            </div>
          </div>
          <Link
            href="/login?mode=signup&next=/app/create"
            className="inline-flex min-h-[46px] shrink-0 items-center gap-2 rounded-full bg-[var(--primary)] px-6 text-sm font-semibold text-[var(--primary-foreground)] shadow-sm transition-all hover:brightness-110 active:scale-[0.98]"
          >
            Create your space
            <ArrowRight className="h-4 w-4" />
          </Link>
        </GlassCard>
      </section>
    </div>
  );
}
