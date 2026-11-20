"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { SpaceNav, useSpace } from "@/components/space-provider";
import { ApiError, getContribution, listContributions, type ContributionDetail } from "@/lib/spaces";

const POLL_MS = 10_000;

/** Live celebration wall: newest first, polling for arrivals. */
export function WallView({ spaceId }: { spaceId: string }) {
  const { token } = useSpace();
  const [items, setItems] = useState<ContributionDetail[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const seen = useRef(new Set<string>());

  const refresh = useCallback(async () => {
    try {
      const page = await listContributions(spaceId, { sort: "-created_at", limit: 20 }, token);
      const fresh = page.items.filter((card) => !seen.current.has(card.id));
      if (fresh.length > 0) {
        const detailed = await Promise.all(fresh.map((card) => getContribution(card.id, token)));
        for (const card of fresh) seen.current.add(card.id);
        setItems((current) => {
          const known = new Set(current.map((item) => item.id));
          return [...detailed.filter((item) => !known.has(item.id)), ...current].slice(0, 60);
        });
      }
      setError(null);
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "Live updates paused.");
    }
  }, [spaceId, token]);

  useEffect(() => {
    void refresh();
    if (paused) return;
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh, paused]);

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-6 py-8">
      <SpaceNav spaceId={spaceId} active="/wall" />
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm opacity-70" role="status">
          {paused ? "Updates paused" : "Celebrating live — new memories appear here."}
        </p>
        <button
          type="button"
          onClick={() => setPaused((value) => !value)}
          className="min-h-[44px] rounded-full bg-black/5 px-4 text-sm font-medium"
        >
          {paused ? "Resume" : "Pause"}
        </button>
      </div>
      {error && (
        <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-900">
          {error}
        </p>
      )}
      {items.length === 0 && !error && (
        <p className="rounded-xl bg-black/5 px-4 py-6 text-center text-sm">
          The wall is quiet for now — contributions will stream in here.
        </p>
      )}
      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <article key={item.id} className="rounded-2xl border border-black/10 bg-white/70 p-4">
            <p className="text-sm font-semibold">{item.display_name ?? "Anonymous"}</p>
            {item.body && <p className="mt-1 whitespace-pre-wrap text-[15px]">{item.body}</p>}
            {item.attachments.length > 0 && (
              <p className="mt-1 text-xs opacity-60">
                +{item.attachments.length}{" "}
                {item.attachments.length === 1 ? "attachment" : "attachments"} — see the gallery
              </p>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}
