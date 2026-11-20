"use client";

import { useCallback, useEffect, useState } from "react";

import { ContributionCard } from "@/components/contribution-card";
import { FeedFilters, toFeedParams, type FilterValues } from "@/components/feed-filters";
import { Lightbox } from "@/components/lightbox";
import { SpaceCoverBand, SpaceNav, useSpace } from "@/components/space-provider";
import { Button } from "@/components/ui/button";
import { GlassCard, StaggerGrid, StaggerItem } from "@/components/ui/motion";
import { ApiError, getContribution, listContributions, type ContributionDetail } from "@/lib/spaces";

/** Shared paginated editorial grid with filters; `mediaOnly` powers the gallery. */
export function MemoryFeed({ spaceId, mediaOnly = false }: { spaceId: string; mediaOnly?: boolean }) {
  const { token } = useSpace();
  const [filters, setFilters] = useState<FilterValues>({ q: "", kind: "", sort: "-created_at" });
  const [items, setItems] = useState<ContributionDetail[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openItem, setOpenItem] = useState<ContributionDetail | null>(null);

  const load = useCallback(
    async (nextCursor: string | null, append: boolean) => {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      setError(null);
      try {
        const params = toFeedParams(filters);
        if (mediaOnly) params.kind = "media,audio";
        if (nextCursor) params.cursor = nextCursor;
        const page = await listContributions(spaceId, params, token);
        const detailed = await Promise.all(
          page.items.map((card) => getContribution(card.id, token)),
        );
        setItems((current) => (append ? [...current, ...detailed] : detailed));
        setCursor(page.next_cursor);
        setHasMore(page.has_more);
      } catch (failure) {
        setError(failure instanceof ApiError ? failure.message : "Could not load memories.");
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [spaceId, token, filters, mediaOnly],
  );

  useEffect(() => {
    void load(null, false);
  }, [load]);

  return (
    <div className="pb-20">
      {mediaOnly && <SpaceCoverBand spaceId={spaceId} />}
      <main className="site-frame py-8">
        <SpaceNav spaceId={spaceId} active={mediaOnly ? "/gallery" : ""} />
        <div className="mb-6">
          <FeedFilters values={filters} onChange={setFilters} />
        </div>
        {loading && (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((n) => (
              <div key={n} className="glass-panel h-60 animate-pulse rounded-[var(--radius)]" />
            ))}
          </div>
        )}
        {error && (
          <GlassCard className="flex flex-col gap-3 p-5 text-sm text-red-900">
            <p role="alert">{error}</p>
            <div>
              <Button type="button" variant="secondary" onClick={() => load(cursor, true)}>
                Retry
              </Button>
            </div>
          </GlassCard>
        )}
        {!loading && !error && items.length === 0 && (
          <GlassCard className="p-10 text-center">
            <p className="font-display text-2xl font-medium">No memories here yet</p>
            <p className="mt-1.5 text-sm text-[var(--muted-foreground)]">
              Be the first to add a message, photo, video, or voice note to this keepsake album.
            </p>
          </GlassCard>
        )}
        {!loading && items.length > 0 && (
          <StaggerGrid className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <StaggerItem key={item.id}>
                <ContributionCard item={item} token={token} onOpen={setOpenItem} />
              </StaggerItem>
            ))}
          </StaggerGrid>
        )}
        {hasMore && !loading && (
          <div className="mt-8 flex justify-center">
            <Button
              type="button"
              variant="secondary"
              disabled={loadingMore}
              onClick={() => load(cursor, true)}
            >
              {loadingMore ? "Loading…" : "Load more memories"}
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
