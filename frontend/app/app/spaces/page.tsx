"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Plus, Settings2, Sparkles } from "lucide-react";

import { AnimatedTabs, FadeInUp, GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";
import { coverForOccasion, occasionLabel } from "@/lib/covers";
import { ApiError, listMySpaces } from "@/lib/spaces";

type SpaceEntry = {
  space: { id: string; title: string; occasion?: string; event_date?: string | null };
  my_role: string;
};

export default function AppSpacesPage() {
  const [spaces, setSpaces] = useState<SpaceEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"active" | "archived">("active");

  useEffect(() => {
    setLoading(true);
    setError(null);
    listMySpaces(tab === "archived")
      .then((mine) => {
        setSpaces(mine as SpaceEntry[]);
        setLoading(false);
      })
      .catch((failure: unknown) => {
        setError(failure instanceof ApiError ? failure.message : "Could not load your spaces.");
        setLoading(false);
      });
  }, [tab]);

  return (
    <div className="flex flex-col gap-6">
      <FadeInUp className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow text-[var(--bronze)]">Your collection</p>
          <h1 className="mt-1 font-display text-4xl font-medium">Memory spaces</h1>
        </div>
        <Link
          href="/app/create"
          className="inline-flex min-h-[44px] items-center gap-2 rounded-full bg-[var(--primary)] px-5 text-sm font-medium text-[var(--primary-foreground)] shadow-sm hover:brightness-110"
        >
          <Plus className="h-4 w-4" />
          Create a space
        </Link>
      </FadeInUp>

      <div>
        <AnimatedTabs
          layoutId="app-spaces-filter"
          value={tab}
          onChange={setTab}
          items={[
            { value: "active", label: "Active spaces" },
            { value: "archived", label: "Archived" },
          ]}
        />
      </div>

      {error && (
        <p role="alert" className="rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
          {error}
        </p>
      )}

      {loading ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((n) => (
            <div key={n} className="glass-panel h-60 animate-pulse rounded-[var(--radius)]" />
          ))}
        </div>
      ) : spaces.length === 0 ? (
        <GlassCard className="p-10 text-center">
          <p className="font-display text-2xl font-medium">
            {tab === "archived" ? "No archived spaces" : "No spaces yet"}
          </p>
          <p className="mt-2 text-sm text-[var(--muted-foreground)]">
            {tab === "archived"
              ? "Archived spaces will appear here."
              : "Create your first space in 3 quick steps."}
          </p>
        </GlassCard>
      ) : (
        <StaggerGrid className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {spaces.map((entry) => (
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
                  <span className="glass-dark absolute right-3 top-3 rounded-full px-2.5 py-0.5 text-[11px] font-medium capitalize">
                    {entry.my_role}
                  </span>
                </Link>
                <div className="flex flex-1 flex-col gap-3 p-5">
                  <Link href={`/s/${entry.space.id}`}>
                    <h2 className="font-display text-2xl font-medium transition-colors group-hover:text-[var(--primary)]">
                      {entry.space.title}
                    </h2>
                  </Link>
                  <div className="mt-auto flex flex-wrap gap-2 pt-2">
                    <Link
                      href={`/s/${entry.space.id}`}
                      className="glass-pill inline-flex min-h-[38px] items-center gap-1 rounded-full px-3.5 text-xs font-semibold"
                    >
                      Open album
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                    <Link
                      href={`/s/${entry.space.id}/settings`}
                      className="glass-pill inline-flex min-h-[38px] items-center gap-1 rounded-full px-3 text-xs font-medium text-[var(--muted-foreground)]"
                    >
                      <Settings2 className="h-3.5 w-3.5" />
                      Curate
                    </Link>
                    <Link
                      href={`/s/${entry.space.id}/studio`}
                      className="glass-pill inline-flex min-h-[38px] items-center gap-1 rounded-full px-3 text-xs font-medium text-[var(--primary)]"
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
    </div>
  );
}
