"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Plus, Sparkles } from "lucide-react";

import { FadeInUp, GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";
import { coverForOccasion, occasionLabel } from "@/lib/covers";
import { ApiError, listMySpaces } from "@/lib/spaces";

type SpaceEntry = {
  space: { id: string; title: string; occasion?: string };
  my_role: string;
};

export default function AppStudioHubPage() {
  const [spaces, setSpaces] = useState<SpaceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listMySpaces(false)
      .then((mine) => {
        setSpaces((mine as SpaceEntry[]).filter((s) => s.my_role === "owner" || s.my_role === "collaborator"));
        setLoading(false);
      })
      .catch((failure: unknown) => {
        setError(failure instanceof ApiError ? failure.message : "Could not load your spaces.");
        setLoading(false);
      });
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <FadeInUp>
        <p className="eyebrow text-[var(--bronze)]">Powered by OpenRouter</p>
        <h1 className="mt-1 font-display text-4xl font-medium">AI Memory Studio</h1>
        <p className="mt-2 max-w-xl text-sm text-[var(--muted-foreground)]">
          Choose a memory space to generate summaries, smart categories, photo captions, voice note
          transcripts, memory letters, digital books, artwork, and FFmpeg highlight films.
        </p>
      </FadeInUp>

      {error && (
        <p role="alert" className="rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
          {error}
        </p>
      )}

      {loading ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2].map((n) => (
            <div key={n} className="glass-panel h-56 animate-pulse rounded-[var(--radius)]" />
          ))}
        </div>
      ) : spaces.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <p className="font-display text-2xl font-medium">Create a space to unlock AI Studio</p>
          <p className="mt-2 text-sm text-[var(--muted-foreground)]">
            Once you have a memory space, you can transform real submissions into keepsakes here.
          </p>
          <div className="mt-5">
            <Link
              href="/app/create"
              className="inline-flex min-h-[44px] items-center gap-2 rounded-full bg-[var(--primary)] px-6 text-sm font-medium text-[var(--primary-foreground)]"
            >
              <Plus className="h-4 w-4" />
              Create a space
            </Link>
          </div>
        </GlassCard>
      ) : (
        <StaggerGrid className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {spaces.map((entry) => (
            <StaggerItem key={entry.space.id}>
              <Link href={`/s/${entry.space.id}/studio`} className="space-card group flex h-full flex-col">
                <div className="relative aspect-[16/10] overflow-hidden bg-[var(--shadow-ink)]">
                  <img
                    src={coverForOccasion(entry.space.occasion)}
                    alt={entry.space.title}
                    className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                  />
                  <span className="glass-dark eyebrow absolute left-3 top-3 rounded-full px-2.5 py-1 text-[var(--gold)]">
                    {occasionLabel(entry.space.occasion)}
                  </span>
                </div>
                <div className="flex flex-1 flex-col gap-2 p-5">
                  <h2 className="font-display text-2xl font-medium">{entry.space.title}</h2>
                  <span className="mt-auto inline-flex items-center gap-1.5 pt-2 text-xs font-semibold text-[var(--primary)]">
                    <Sparkles className="h-3.5 w-3.5" />
                    Open AI Studio
                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                  </span>
                </div>
              </Link>
            </StaggerItem>
          ))}
        </StaggerGrid>
      )}
    </div>
  );
}
