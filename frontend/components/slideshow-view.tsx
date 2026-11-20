"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";

import { SpaceCoverBand, SpaceNav, useSpace } from "@/components/space-provider";
import { AnimatePresence, GlassCard, motion } from "@/components/ui/motion";
import { ApiError, getContribution, listContributions, type ContributionDetail } from "@/lib/spaces";

const SLIDE_MS = 5500;

/** Cinematic frosted-glass slideshow over media memories (keyboard + auto-advance). */
export function SlideshowView({ spaceId }: { spaceId: string }) {
  const { token } = useSpace();
  const [slides, setSlides] = useState<ContributionDetail[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    listContributions(spaceId, { kind: "media", sort: "-taken_at", limit: 50 }, token, controller.signal)
      .then(async (page) => {
        const detailed = await Promise.all(page.items.map((card) => getContribution(card.id, token)));
        setSlides(detailed.filter((item) => item.attachments.length > 0));
        setLoading(false);
      })
      .catch((failure: unknown) => {
        if (controller.signal.aborted) return;
        setError(failure instanceof ApiError ? failure.message : "Could not load the slideshow.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [spaceId, token]);

  const step = useCallback(
    (delta: number) => {
      setIndex((current) => (slides.length === 0 ? 0 : (current + delta + slides.length) % slides.length));
    },
    [slides.length],
  );

  useEffect(() => {
    if (!playing || slides.length < 2) return;
    const timer = setInterval(() => step(1), SLIDE_MS);
    return () => clearInterval(timer);
  }, [playing, slides.length, step]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "ArrowRight") step(1);
      if (event.key === "ArrowLeft") step(-1);
      if (event.key === " ") {
        event.preventDefault();
        setPlaying((value) => !value);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [step]);

  const current = slides[index];
  const attachment = current?.attachments[0];
  const url = attachment?.urls.derivatives.preview ?? attachment?.urls.original;

  return (
    <div className="pb-20">
      <SpaceCoverBand spaceId={spaceId} />
      <main className="site-frame py-8">
        <SpaceNav spaceId={spaceId} active="/slideshow" />
        {loading && <div className="glass-panel h-96 animate-pulse rounded-[var(--radius)]" />}
        {error && (
          <p role="alert" className="rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
            {error}
          </p>
        )}
        {!loading && !error && slides.length === 0 && (
          <GlassCard className="p-10 text-center">
            <p className="font-display text-2xl font-medium">No photo or video memories yet</p>
            <p className="mt-1 text-sm text-[var(--muted-foreground)]">
              Once guests upload photos or videos, they will play here in a full-bleed keepsake showcase.
            </p>
          </GlassCard>
        )}
        {current && url && (
          <div className="relative overflow-hidden rounded-[var(--radius)] bg-[var(--shadow-ink)] shadow-2xl">
            <div className="relative aspect-[16/10] w-full sm:aspect-[16/9]">
              <AnimatePresence mode="wait">
                <motion.div
                  key={current.id}
                  initial={{ opacity: 0, scale: 1.02 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.98 }}
                  transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
                  className="absolute inset-0 flex items-center justify-center"
                >
                  {attachment?.kind === "video" ? (
                    <video src={url} controls autoPlay muted className="h-full w-full object-contain" />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={url}
                      alt={attachment?.caption ?? current.body ?? "Memory slide"}
                      className="h-full w-full object-contain"
                    />
                  )}
                </motion.div>
              </AnimatePresence>
            </div>

            <div className="glass-dark absolute inset-x-4 bottom-4 flex flex-wrap items-center justify-between gap-4 rounded-[var(--radius)] px-5 py-3.5">
              <div className="min-w-0">
                <p className="font-display text-lg font-medium text-white">
                  {current.display_name ?? "Anonymous guest"}
                </p>
                {(current.body || attachment?.caption) && (
                  <p className="truncate text-xs text-white/80">
                    {current.body ?? attachment?.caption}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-white/70">
                  {index + 1} / {slides.length}
                </span>
                <button
                  type="button"
                  aria-label="Previous slide"
                  onClick={() => step(-1)}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label={playing ? "Pause slideshow" : "Play slideshow"}
                  onClick={() => setPlaying((v) => !v)}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-[var(--foreground)] hover:brightness-95"
                >
                  {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                </button>
                <button
                  type="button"
                  aria-label="Next slide"
                  onClick={() => step(1)}
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 hover:bg-white/25"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
