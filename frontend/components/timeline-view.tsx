"use client";

import { useCallback, useEffect, useState } from "react";

import { ContributionCard } from "@/components/contribution-card";
import { Lightbox } from "@/components/lightbox";
import { SpaceCoverBand, SpaceNav, useSpace } from "@/components/space-provider";
import { Button } from "@/components/ui/button";
import { GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";
import { ApiError, getContribution, listContributions, type ContributionDetail } from "@/lib/spaces";

function monthLabel(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "long" });
}

function groupByMonth(items: ContributionDetail[]): Array<[string, ContributionDetail[]]> {
  const groups = new Map<string, ContributionDetail[]>();
  for (const item of items) {
    const key = monthLabel(item.taken_at ?? item.created_at);
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  }
  return [...groups.entries()];
}

export function TimelineView({ spaceId }: { spaceId: string }) {
  const { token } = useSpace();
  const [items, setItems] = useState<ContributionDetail[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openItem, setOpenItem] = useState<ContributionDetail | null>(null);

  const load = useCallback(
    async (nextCursor: string | null) => {
      setLoading(true);
      setError(null);
      try {
        const page = await listContributions(
          spaceId,
          { sort: "-taken_at", limit: 30, cursor: nextCursor ?? undefined },
          token,
        );
        const detailed = await Promise.all(page.items.map((card) => getContribution(card.id, token)));
        setItems((current) => (nextCursor ? [...current, ...detailed] : detailed));
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      } catch (failure) {
        setError(failure instanceof ApiError ? failure.message : "Could not load the timeline.");
      } finally {
        setLoading(false);
      }
    },
    [spaceId, token],
  );

  useEffect(() => {
    void load(null);
  }, [load]);

  return (
    <div className="pb-20">
      <SpaceCoverBand spaceId={spaceId} />
      <main className="site-frame py-8">
        <SpaceNav spaceId={spaceId} active="/timeline" />
        {loading && items.length === 0 && (
          <div className="glass-panel h-48 animate-pulse rounded-[var(--radius)]" />
        )}
        {error && (
          <p role="alert" className="rounded-[var(--radius)] bg-red-50 px-4 py-3 text-sm text-red-900">
            {error}
          </p>
        )}
        {!loading && !error && items.length === 0 && (
          <GlassCard className="p-10 text-center">
            <p className="font-display text-2xl font-medium">Nothing on the timeline yet</p>
            <p className="mt-1 text-sm text-[var(--muted-foreground)]">
              Shared memories will appear chronologically along this ribbon.
            </p>
          </GlassCard>
        )}

        <div className="relative mx-auto max-w-3xl pl-7 before:absolute before:bottom-0 before:left-2.5 before:top-2 before:w-0.5 before:bg-[var(--primary)]/25">
          {groupByMonth(items).map(([month, monthItems]) => (
            <section key={month} className="relative mb-10">
              <span className="absolute -left-[25px] top-1.5 h-3.5 w-3.5 rounded-full border-2 border-[var(--background)] bg-[var(--primary)] shadow-sm ring-4 ring-[var(--sage)]" />
              <h2 className="mb-4 font-display text-2xl font-medium text-[var(--foreground)]">
                {month}
              </h2>
              <StaggerGrid className="flex flex-col gap-4">
                {monthItems.map((item) => (
                  <StaggerItem key={item.id}>
                    <ContributionCard item={item} token={token} onOpen={setOpenItem} />
                  </StaggerItem>
                ))}
              </StaggerGrid>
            </section>
          ))}
        </div>

        {hasMore && (
          <div className="mt-6 flex justify-center">
            <Button type="button" variant="secondary" disabled={loading} onClick={() => load(cursor)}>
              Load earlier memories
            </Button>
          </div>
        )}
        {openItem && (
          <Lightbox item={openItem} onClose={() => setOpenItem(null)} />
        )}
      </main>
    </div>
  );
}
